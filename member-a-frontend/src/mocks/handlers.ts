import { http, HttpResponse, delay } from 'msw';
import { z } from 'zod';
import * as schema from '../api/contracts';
import {
  loginRequestSchema,
  createAttemptRequestSchema,
  submitAttemptRequestSchema,
} from '../api/contracts/requests';
import type {
  Attempt,
  CreateAttempt,
  History,
  SubmitAttempt,
  Task,
  User,
} from '../api/contracts';
import { config } from '../config';
import { validateFile } from '../utils';
import { getRepository, type State } from './repository';
import {
  buildReport,
  grade,
  normalized,
  publicQuestion,
  scenarioReport,
} from './services/engine';

class DomainError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
const fail = (status: number, code: string, message: string): never => {
  throw new DomainError(status, code, message);
};
const find = <T>(value: T | undefined, message = '记录不存在'): T =>
  value ?? fail(404, 'NOT_FOUND', message);
const uuid = (prefix: string) => `${prefix}-${crypto.randomUUID()}`;
const now = () => new Date().toISOString();
const envelope = (data: unknown, status = 200) =>
  HttpResponse.json(
    { code: 'OK', message: '成功', data, request_id: uuid('mock-request') },
    { status },
  );
function auth(s: State, request: Request): User {
  const token =
    request.headers.get('Authorization')?.replace(/^Bearer /, '') || '';
  const session = s.tokens[token];
  if (!session) return fail(401, 'AUTH_REQUIRED', '请先登录');
  if (session.expires <= Date.now())
    return fail(401, 'TOKEN_EXPIRED', '登录已过期，请重新登录');
  return find(s.users.find((u) => u.user_id === session.user_id));
}
function owner(user: User, uid: string) {
  if (user.user_id !== uid) fail(403, 'FORBIDDEN', '无权访问其他用户的记录');
}
function teacher(user: User) {
  if (user.role !== 'teacher') fail(403, 'FORBIDDEN', '此操作仅限教师');
}
function validCourse(s: State, id: unknown) {
  if (id !== s.course.course_id) fail(404, 'NOT_FOUND', '课程不存在');
}
function knowledgeIds(s: State, ids: string[]) {
  if (
    ids.some(
      (id) =>
        !s.course.knowledge_points.some(
          (p) => p.knowledge_point_id === id && p.active,
        ),
    )
  )
    fail(422, 'VALIDATION_ERROR', '包含不存在或停用的知识点');
}
function paginate<T>(items: T[], url: URL) {
  const page = Number(url.searchParams.get('page') ?? 1);
  const page_size = Number(url.searchParams.get('page_size') ?? 10);
  if (
    !Number.isInteger(page) ||
    page < 1 ||
    !Number.isInteger(page_size) ||
    page_size < 1 ||
    page_size > 50
  )
    fail(422, 'VALIDATION_ERROR', '分页参数需为有效正整数，单页不超过50条');
  return {
    items: items.slice((page - 1) * page_size, page * page_size),
    total: items.length,
    page,
    page_size,
  };
}
function advanceTask(s: State, t: Task) {
  if (['completed', 'failed'].includes(t.status)) return;
  const elapsed = Date.now() - Date.parse(t.updated_at);
  if (s.scenario === 'diagnosis-stuck' && t.kind === 'diagnosis') {
    t.status = 'running';
    t.current_step = '模拟持续处理';
    t.progress = null;
    return;
  }
  if (elapsed < config.mockTaskMs / 3) return;
  t.status = 'running';
  t.progress = 0.5;
  t.current_step =
    t.kind === 'diagnosis'
      ? '模拟规则诊断与资料匹配'
      : '模拟资料处理（不建立向量索引）';
  if (elapsed < config.mockTaskMs) return;
  if (
    (s.scenario === 'diagnosis-failed' && t.kind === 'diagnosis') ||
    (s.scenario === 'upload-failed' && t.kind === 'document_ingestion') ||
    t.error_code === 'NO_TEXT'
  ) {
    t.status = 'failed';
    t.progress = null;
    t.error_code ||= 'MOCK_PROCESSING_FAILED';
    t.error_message ||= '模拟处理失败，成绩或原文件已经保存';
    t.can_retry = t.retry_count < 2;
  } else {
    t.status = 'completed';
    t.progress = 1;
    t.current_step = '模拟处理完成';
    t.can_retry = false;
    if (t.kind === 'diagnosis') {
      const a = s.attempts[t.attempt_id!].value;
      const rid = a.report_id || uuid('report');
      s.reports[rid] = buildReport(s, a, rid);
      a.report_id = rid;
      t.report_id = rid;
    }
  }
  if (t.kind === 'document_ingestion') {
    const doc = s.documents[t.document_id!];
    doc.status = t.status;
    doc.error_code = t.error_code;
    doc.error_message = t.error_message;
    s.resources[doc.resource_id].availability =
      t.status === 'completed' ? 'available' : 'failed';
  }
}
function history(s: State, uid: string, url: URL) {
  if (s.scenario === 'empty-history') return paginate<History>([], url);
  const items = Object.values(s.attempts)
    .map((x) => x.value)
    .filter(
      (a) =>
        a.user_id === uid &&
        a.status === 'submitted' &&
        (!url.searchParams.get('kind') ||
          a.kind === url.searchParams.get('kind')) &&
        (!url.searchParams.get('course_id') ||
          a.course_id === url.searchParams.get('course_id')),
    )
    .sort((a, b) => b.submitted_at!.localeCompare(a.submitted_at!));
  return paginate(
    items.map((a) => ({
      attempt_id: a.attempt_id,
      report_id: a.report_id,
      kind: a.kind,
      baseline_attempt_id: a.baseline_attempt_id,
      submitted_at: a.submitted_at,
      score: a.result?.score || null,
      diagnosis_task_id: a.diagnosis_task_id,
      diagnosis_status: a.diagnosis_task_id
        ? s.tasks[a.diagnosis_task_id].status
        : null,
    })),
    url,
  );
}
function courseFor(s: State, u: User) {
  const list = Object.values(s.attempts)
    .map((a) => a.value)
    .filter((a) => a.user_id === u.user_id);
  const latest = list
    .filter((a) => a.status === 'submitted')
    .sort((a, b) => b.submitted_at!.localeCompare(a.submitted_at!))[0];
  return {
    ...s.course,
    latest_attempt_id: latest?.attempt_id || null,
    latest_report_id: latest?.report_id || null,
    active_attempt_id:
      list.find((a) => a.status === 'in_progress')?.attempt_id || null,
  };
}
function dispatch(
  s: State,
  request: Request,
  url: URL,
  body: unknown,
  upload?: { file: File; content: string; fields: FormData },
): { data: unknown; status?: number; binary?: Blob; lost?: boolean } {
  const path = decodeURIComponent(url.pathname.replace(/^.*\/api\/v1/, ''));
  const method = request.method;
  const segments = path.split('/').filter(Boolean);
  if (path === '/auth/login' && method === 'POST') {
    const input = loginRequestSchema.parse(body);
    const user = s.users.find((u) => u.username === input.username);
    if (!user || input.password !== 'Demo123!')
      return fail(401, 'INVALID_CREDENTIALS', '账号或密码错误');
    const token = uuid('demo-session');
    const expires = Date.now() + 3600_000;
    s.tokens[token] = { user_id: user.user_id, expires };
    return {
      data: {
        access_token: token,
        token_type: 'Bearer',
        expires_at: new Date(expires).toISOString(),
        user,
      },
    };
  }
  const user = auth(s, request);
  if (path === '/auth/me') return { data: user };
  if (path === '/auth/logout' && method === 'POST') {
    delete s.tokens[request.headers.get('Authorization')!.slice(7)];
    return { data: null };
  }
  if (path === '/courses') return { data: [courseFor(s, user)] };
  if (segments[0] === 'courses') {
    validCourse(s, segments[1]);
    return {
      data:
        segments[2] === 'knowledge-points'
          ? s.course.knowledge_points
          : courseFor(s, user),
    };
  }
  if ((path === '/reports' || path === '/attempts') && method === 'GET')
    return { data: history(s, user.user_id, url) };
  if (path === '/attempts' && method === 'POST') {
    if (user.role !== 'student') fail(403, 'FORBIDDEN', '仅学生可创建测验');
    const data = createAttemptRequestSchema.parse(body) as CreateAttempt;
    validCourse(s, data.course_id);
    const key = `${user.user_id}:${data.client_request_id}`;
    if (s.creationKeys[key]) {
      if (s.creationKeys[key].body !== JSON.stringify(data))
        fail(409, 'REFERENCE_CONFLICT', '创建请求标识已用于其他内容');
      return {
        data: s.attempts[s.creationKeys[key].attemptId].value,
        status: 201,
      };
    }
    let qs = Object.values(s.questions).filter(
      (q) => q.active && /-0[123]$/.test(q.question_id),
    );
    if (data.kind === 'initial' && data.question_ids)
      fail(422, 'VALIDATION_ERROR', '前测由服务选题');
    if (data.kind !== 'initial') {
      const report = find(s.reports[data.source_report_id || '']);
      owner(user, report.user_id);
      if (report.course_id !== data.course_id)
        fail(422, 'INVALID_BASELINE', '报告课程不一致');
      if (data.kind === 'retest') {
        const base = find(s.attempts[data.baseline_attempt_id || '']?.value);
        owner(user, base.user_id);
        if (
          base.status !== 'submitted' ||
          base.attempt_id !== report.attempt_id ||
          base.course_id !== data.course_id ||
          data.question_ids
        )
          fail(422, 'INVALID_BASELINE', '复测基准必须对应当前报告');
        qs = Object.values(s.questions).filter(
          (q) => q.active && /-0[456]$/.test(q.question_id),
        );
      } else {
        const allowed = new Set(
          report.recommendations.flatMap((r) =>
            r.practice_questions.map((q) => q.question_id),
          ),
        );
        if (
          !data.question_ids?.length ||
          data.question_ids.some((id) => !allowed.has(id))
        )
          fail(422, 'INVALID_OPTIONS', '练习题不属于当前推荐');
        qs = [...new Set(data.question_ids)]
          .map((id) => find(s.questions[id]))
          .filter((q) => q.active);
      }
    }
    if (!qs.length || (data.kind !== 'practice' && qs.length < 24))
      fail(409, 'REFERENCE_CONFLICT', '当前启用题目不足，请联系教师');
    const aid = uuid('attempt');
    const a: Attempt = {
      attempt_id: aid,
      user_id: user.user_id,
      course_id: data.course_id,
      kind: data.kind,
      baseline_attempt_id: data.baseline_attempt_id || null,
      source_report_id: data.source_report_id || null,
      status: 'in_progress',
      snapshot_version: uuid('snapshot'),
      created_at: now(),
      submitted_at: null,
      questions: qs.map(publicQuestion),
      result: null,
      diagnosis_task_id: null,
      report_id: null,
    };
    if (s.scenario === 'long-content')
      a.questions[0].stem += ' 请结合操作条件与边界说明进行判断。'.repeat(50);
    s.attempts[aid] = { value: a, snapshot: structuredClone(qs) };
    s.creationKeys[key] = { attemptId: aid, body: JSON.stringify(data) };
    return { data: a, status: 201 };
  }
  if (segments[0] === 'attempts') {
    const internal = find(s.attempts[segments[1]], '测验不存在');
    const a = internal.value;
    owner(user, a.user_id);
    if (segments[2] === 'submit' && method === 'POST') {
      const data = submitAttemptRequestSchema.parse(body) as SubmitAttempt;
      if (data.snapshot_version !== a.snapshot_version)
        fail(409, 'SNAPSHOT_MISMATCH', '试卷版本已变化，请重新加载');
      if (!request.headers.get('Idempotency-Key'))
        fail(422, 'VALIDATION_ERROR', '提交缺少幂等标识');
      if (
        data.answers.length !== a.questions.length ||
        new Set(data.answers.map((x) => x.question_id)).size !==
          a.questions.length
      )
        fail(
          422,
          'INVALID_OPTIONS',
          '每道题必须且只能提交一次，未答使用空数组',
        );
      for (const answer of data.answers) {
        const q = a.questions.find((q) => q.question_id === answer.question_id);
        if (
          !q ||
          answer.selected_option_ids.some(
            (id) => !q.options.some((o) => o.option_id === id),
          ) ||
          (q.type === 'single_choice' &&
            new Set(answer.selected_option_ids).size > 1)
        )
          fail(422, 'INVALID_OPTIONS', '题目或选项不属于本试卷');
      }
      const fingerprint = normalized(data.answers);
      if (
        a.status === 'submitted' &&
        fingerprint !==
          (internal.fingerprint || normalized(a.result!.graded_answers))
      )
        fail(409, 'ATTEMPT_ALREADY_SUBMITTED', '本次已提交，不能覆盖原答案');
      if (a.status !== 'submitted') {
        a.status = 'submitted';
        a.submitted_at = now();
        a.result = grade(a.attempt_id, internal.snapshot, data.answers);
        internal.fingerprint = fingerprint;
        internal.submitKey = request.headers.get('Idempotency-Key')!;
        const tid = uuid('task');
        a.diagnosis_task_id = tid;
        s.tasks[tid] = {
          task_id: tid,
          kind: 'diagnosis',
          status: 'queued',
          attempt_id: a.attempt_id,
          document_id: null,
          report_id: null,
          progress: 0,
          current_step: '成绩已保存，等待模拟诊断',
          error_code: null,
          error_message: null,
          can_retry: false,
          retry_count: 0,
          created_at: now(),
          updated_at: now(),
        };
      }
      return {
        data: {
          attempt_id: a.attempt_id,
          submitted_at: a.submitted_at,
          result: a.result,
          diagnosis_task_id: a.diagnosis_task_id,
        },
        lost: s.scenario === 'submit-committed-response-lost',
      };
    }
    if (segments[2] === 'result') {
      if (!a.result) fail(409, 'ATTEMPT_NOT_SUBMITTED', '尚未提交');
      return { data: a.result };
    }
    return { data: a };
  }
  if (segments[0] === 'tasks') {
    const task = find(s.tasks[segments[1]]);
    if (task.kind === 'document_ingestion') teacher(user);
    else owner(user, s.attempts[task.attempt_id!].value.user_id);
    advanceTask(s, task);
    if (segments[2] === 'retry' && method === 'POST') {
      const retryKey = `${task.task_id}:${request.headers.get('Idempotency-Key') || ''}`;
      s.retryKeys ||= {};
      if (s.retryKeys[retryKey]) return { data: task, status: 202 };
      if (!task.can_retry || task.retry_count >= 2)
        fail(409, 'TASK_NOT_RETRYABLE', '该任务当前不能重试');
      if (!request.headers.get('Idempotency-Key'))
        fail(422, 'VALIDATION_ERROR', '缺少重试标识');
      s.retryKeys[retryKey] = true;
      task.retry_count++;
      task.status = 'queued';
      task.updated_at = now();
      task.can_retry = false;
      if (task.error_code !== 'NO_TEXT') {
        task.error_code = null;
        task.error_message = null;
      }
      if (['diagnosis-failed', 'upload-failed'].includes(s.scenario))
        s.scenario = 'normal';
      return { data: task, status: 202 };
    }
    return { data: task };
  }
  if (segments[0] === 'reports') {
    const r = find(s.reports[segments[1]], '报告不存在');
    owner(user, r.user_id);
    const report = scenarioReport(s, r);
    if (segments[2] === 'recommendations')
      return {
        data: {
          report_id: report.report_id,
          attempt_id: report.attempt_id,
          recommendations: report.recommendations,
          actions: report.actions,
        },
      };
    if (segments[2] === 'comparison') return { data: report.comparison };
    return { data: report };
  }
  if (segments[0] === 'resources') {
    const r = find(s.resources[segments[1]], '资料不存在');
    if (
      url.searchParams.has('resource_version') &&
      url.searchParams.get('resource_version') !== r.resource_version
    )
      fail(
        410,
        'RESOURCE_REMOVED',
        '该历史版本当前不可访问，报告中的原引用片段仍保留',
      );
    if (
      !r.active ||
      r.availability === 'removed' ||
      s.scenario === 'resource-removed'
    )
      fail(410, 'RESOURCE_REMOVED', '来源已移除；报告中仍保留生成时的引用片段');
    if (r.availability !== 'available')
      fail(409, 'REFERENCE_CONFLICT', '资料尚未处理完成');
    if (
      (url.searchParams.get('document_id') &&
        url.searchParams.get('document_id') !== r.document_id) ||
      (url.searchParams.get('chunk_id') &&
        url.searchParams.get('chunk_id') !== `chunk-${r.document_id}-1`)
    )
      fail(403, 'FORBIDDEN', '文档片段与资源不匹配');
    if (segments[2] === 'file') {
      const file = s.files[r.document_id || ''];
      if (!file) fail(404, 'NOT_FOUND', '无可下载的原文件');
      return { data: null, binary: file };
    }
    return { data: r };
  }
  if (segments[0] === 'teacher') {
    teacher(user);
    const entity = segments[1];
    const id = segments[2];
    if (url.searchParams.has('course_id'))
      validCourse(s, url.searchParams.get('course_id'));
    if (entity === 'overview') {
      const attempts = Object.values(s.attempts)
        .map((a) => a.value)
        .filter((a) => a.status === 'submitted');
      return {
        data: {
          course_id: s.course.course_id,
          student_count: s.users.filter((u) => u.role === 'student').length,
          submitted_attempt_count: attempts.length,
          average_percentage: attempts.length
            ? attempts.reduce((v, a) => v + a.result!.score.percentage, 0) /
              attempts.length
            : null,
          recent_attempts: attempts
            .slice(-5)
            .reverse()
            .map((a) => ({
              attempt_id: a.attempt_id,
              report_id: a.report_id,
              kind: a.kind,
              baseline_attempt_id: a.baseline_attempt_id,
              submitted_at: a.submitted_at,
              score: a.result!.score,
              diagnosis_task_id: a.diagnosis_task_id,
              diagnosis_status: s.tasks[a.diagnosis_task_id!].status,
            })),
        },
      };
    }
    if (entity === 'students') {
      if (segments[3] === 'reports') {
        const r = find(s.reports[segments[4]]);
        if (r.user_id !== id) fail(403, 'FORBIDDEN', '报告不属于指定学生');
        return { data: scenarioReport(s, r) };
      }
      if (segments[3] === 'attempts') return { data: history(s, id, url) };
      const query = url.searchParams.get('q') || '';
      return {
        data: paginate(
          s.users
            .filter(
              (u) =>
                u.role === 'student' &&
                (u.display_name.includes(query) || u.username.includes(query)),
            )
            .map((u) => {
              const list = Object.values(s.attempts)
                .map((a) => a.value)
                .filter(
                  (a) => a.user_id === u.user_id && a.status === 'submitted',
                )
                .sort((a, b) => b.submitted_at!.localeCompare(a.submitted_at!));
              return {
                user_id: u.user_id,
                display_name: u.display_name,
                submitted_attempt_count: list.length,
                latest_attempt_id: list[0]?.attempt_id || null,
                latest_report_id: list[0]?.report_id || null,
              };
            }),
          url,
        ),
      };
    }
    if (entity === 'courses' && method === 'PATCH') {
      validCourse(s, id);
      Object.assign(s.course, schema.courseWriteSchema.parse(body));
      return { data: courseFor(s, user) };
    }
    if (entity === 'knowledge-points') {
      if (method === 'GET') {
        const query = url.searchParams.get('q') || '';
        return {
          data: paginate(
            s.course.knowledge_points.filter(
              (p) =>
                p.name.includes(query) &&
                (!url.searchParams.has('active') ||
                  String(p.active) === url.searchParams.get('active')),
            ),
            url,
          ),
        };
      }
      const data = schema.knowledgeWriteSchema.parse(body);
      validCourse(s, data.course_id);
      if (
        s.course.knowledge_points.some(
          (p) => p.name === data.name && p.knowledge_point_id !== id,
        )
      )
        fail(409, 'DUPLICATE_NAME', '知识点名称已存在');
      if (id) {
        const p = find(
          s.course.knowledge_points.find((p) => p.knowledge_point_id === id),
        );
        if (
          !data.active &&
          Object.values(s.questions).some(
            (q) => q.active && q.knowledge_point_ids.includes(id),
          )
        )
          fail(
            409,
            'REFERENCE_CONFLICT',
            '仍有启用题目关联，请先调整关联或停用题目',
          );
        Object.assign(p, data);
        return { data: p };
      }
      const p = { ...data, knowledge_point_id: uuid('kp') };
      s.course.knowledge_points.push(p);
      return { data: p, status: 201 };
    }
    if (entity === 'questions') {
      if (method === 'GET') {
        if (id) return { data: find(s.questions[id]) };
        return {
          data: paginate(
            Object.values(s.questions).filter(
              (q) =>
                (!url.searchParams.get('type') ||
                  q.type === url.searchParams.get('type')) &&
                (!url.searchParams.get('knowledge_point_id') ||
                  q.knowledge_point_ids.includes(
                    url.searchParams.get('knowledge_point_id')!,
                  )) &&
                (!url.searchParams.has('active') ||
                  String(q.active) === url.searchParams.get('active')),
            ),
            url,
          ),
        };
      }
      const data = schema.questionWriteSchema.parse(body);
      validCourse(s, data.course_id);
      knowledgeIds(s, data.knowledge_point_ids);
      const old = id ? find(s.questions[id]) : null;
      const qid = id || uuid('q');
      const opts = data.options.map((o) => ({
        option_id:
          o.option_id && old?.options.some((x) => x.option_id === o.option_id)
            ? o.option_id
            : uuid('option'),
        label: o.label,
        text: o.text,
      }));
      const { correct_option_keys, ...write } = data;
      const q: schema.TeacherQuestion = {
        ...write,
        question_id: qid,
        options: opts,
        correct_option_ids: correct_option_keys.map(
          (key) =>
            opts[data.options.findIndex((o) => o.client_key === key)].option_id,
        ),
        version: String(Number(old?.version || '0') + 1),
      };
      s.questions[qid] = q;
      return { data: q, status: old ? 200 : 201 };
    }
    if (entity === 'resources') {
      if (method === 'GET' && id) return { data: find(s.resources[id]) };
      if (method === 'GET')
        return {
          data: paginate(
            Object.values(s.resources)
              .filter(
                (r) =>
                  (!url.searchParams.get('kind') ||
                    r.kind === url.searchParams.get('kind')) &&
                  (!url.searchParams.get('knowledge_point_id') ||
                    r.knowledge_point_ids.includes(
                      url.searchParams.get('knowledge_point_id')!,
                    )) &&
                  (!url.searchParams.has('active') ||
                    String(r.active) === url.searchParams.get('active')),
              )
              .map((r) => {
                const doc = r.document_id ? s.documents[r.document_id] : null;
                return {
                  ...r,
                  ingestion_task_id: doc?.task_id || null,
                  error_code: doc?.error_code || null,
                  error_message: doc?.error_message || null,
                };
              }),
            url,
          ),
        };
      const data = schema.resourceWriteSchema.parse(body);
      validCourse(s, data.course_id);
      knowledgeIds(s, data.knowledge_point_ids);
      const old = id ? find(s.resources[id]) : null;
      if (!old && data.kind === 'document')
        fail(422, 'VALIDATION_ERROR', '文档资源必须通过上传创建');
      const rid = id || uuid('res');
      const r: schema.Resource = {
        ...data,
        resource_id: rid,
        source_label: old?.source_label || '教师自编演示资料',
        availability: !data.active
          ? 'removed'
          : old?.kind === 'document'
            ? s.documents[old.document_id || '']?.status === 'completed'
              ? 'available'
              : old.availability
            : 'available',
        document_id:
          old?.document_id || (data.kind === 'note' ? uuid('doc') : null),
        resource_version: uuid('version'),
        file_available: old?.file_available || false,
        filename: old?.filename || null,
        location: old?.location || {
          page_start: null,
          page_end: null,
          section: null,
        },
      };
      if (old?.kind === 'document') {
        r.kind = old.kind;
        r.text_content = old.text_content;
        r.external_url = old.external_url;
      }
      s.resources[rid] = r;
      return { data: r, status: old ? 200 : 201 };
    }
    if (entity === 'documents') {
      if (method === 'GET') {
        const doc = find(s.documents[id]);
        advanceTask(s, s.tasks[doc.task_id]);
        return { data: doc };
      }
      if (!upload) return fail(422, 'VALIDATION_ERROR', '缺少文件');
      const { file, content, fields } = upload;
      validCourse(s, fields.get('course_id'));
      const error = validateFile(file);
      if (error)
        fail(
          file.size > config.uploadLimit ? 413 : 415,
          file.size > config.uploadLimit
            ? 'FILE_TOO_LARGE'
            : 'UNSUPPORTED_FILE_TYPE',
          error,
        );
      const kpids = z
        .array(z.string())
        .min(1)
        .parse(JSON.parse(String(fields.get('knowledge_point_ids'))));
      knowledgeIds(s, kpids);
      const title = z
        .string()
        .trim()
        .min(1)
        .max(100)
        .parse(fields.get('title'));
      const did = uuid('doc'),
        rid = uuid('res'),
        tid = uuid('task');
      const isPDF = /\.pdf$/i.test(file.name);
      const noText = file.size === 0 || /scan|empty/i.test(file.name);
      const doc: schema.DocumentRecord = {
        document_id: did,
        resource_id: rid,
        course_id: s.course.course_id,
        filename: file.name,
        size_bytes: file.size,
        content_type: file.type || 'application/octet-stream',
        version: '1',
        task_id: tid,
        status: 'queued',
        error_code: null,
        error_message: null,
        created_at: now(),
      };
      const task: Task = {
        task_id: tid,
        kind: 'document_ingestion',
        status: 'queued',
        attempt_id: null,
        document_id: did,
        report_id: null,
        progress: 0,
        current_step: '已接收，等待模拟处理',
        error_code: noText ? 'NO_TEXT' : null,
        error_message: noText ? '未检测到可提取文本（模拟检查）' : null,
        can_retry: false,
        retry_count: 0,
        created_at: now(),
        updated_at: now(),
      };
      s.documents[did] = doc;
      s.tasks[tid] = task;
      s.files[did] = file;
      s.resources[rid] = {
        resource_id: rid,
        course_id: s.course.course_id,
        title,
        kind: 'document',
        knowledge_point_ids: kpids,
        difficulty: 'easy',
        active: true,
        availability: 'processing',
        source_label: '教师上传演示文件',
        description: isPDF
          ? 'PDF 仅模拟受理与处理，不进行 OCR、文本解析或向量索引。'
          : '本地保存的上传文本。',
        document_id: did,
        resource_version: '1',
        filename: file.name,
        text_content: isPDF ? null : content,
        external_url: null,
        file_available: true,
        location: { page_start: null, page_end: null, section: null },
      };
      return { data: { document: doc, task }, status: 202 };
    }
  }
  return fail(404, 'UNIMPLEMENTED_API', `未实现的模拟接口：${method} ${path}`);
}
export const handlers = [
  http.all('*/api/v1/*', async ({ request }) => {
    try {
      let body: unknown = undefined;
      let upload: { file: File; content: string; fields: FormData } | undefined;
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        if (
          request.headers.get('content-type')?.includes('multipart/form-data')
        ) {
          const fields = await request.formData();
          const file = fields.get('file');
          if (file instanceof File)
            upload = {
              file,
              fields,
              content: /\.(txt|md)$/i.test(file.name) ? await file.text() : '',
            };
        } else {
          const raw = await request.text();
          body = raw ? JSON.parse(raw) : {};
        }
      }
      const repo = getRepository();
      const pause = await repo.change((s) => s.delayMs);
      if (pause > 0) await delay(pause);
      const result = await repo.change((s) => {
        const r = dispatch(s, request, new URL(request.url), body, upload);
        if (
          s.scenario === 'invalid-response' &&
          request.method === 'GET' &&
          /\/(reports|tasks)\//.test(request.url)
        )
          return { data: { unexpected_status: 'alien', negative_count: -1 } };
        return r;
      });
      if (result.lost) return HttpResponse.error();
      if (result.binary)
        return new HttpResponse(result.binary, {
          headers: {
            'Content-Type': result.binary.type || 'application/octet-stream',
            'Content-Disposition': 'attachment; filename="document"',
          },
        });
      return envelope(result.data, result.status);
    } catch (error) {
      const status =
        error instanceof DomainError
          ? error.status
          : error instanceof z.ZodError || error instanceof SyntaxError
            ? 422
            : 500;
      const code =
        error instanceof DomainError
          ? error.code
          : status === 422
            ? 'VALIDATION_ERROR'
            : 'MOCK_ERROR';
      return HttpResponse.json(
        {
          code,
          message: error instanceof Error ? error.message : '模拟服务异常',
          data: null,
          request_id: uuid('mock-request'),
        },
        { status },
      );
    }
  }),
];
