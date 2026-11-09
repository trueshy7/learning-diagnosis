import { z } from 'zod';
import * as s from '../contracts';
import { request } from '../client';
import { endpoints as e } from '../endpoints';
import { requireId } from '../mappers';
export const api = {
  login: (username: string, password: string) =>
    request('POST', e.login, s.loginSchema, { data: { username, password } }),
  me: () => request('GET', e.me, s.userSchema),
  logout: () => request('POST', e.logout, z.null()),
  courses: () => request('GET', e.courses, z.array(s.courseSchema)),
  course: async (id: string) =>
    requireId(
      await request('GET', e.course(id), s.courseSchema),
      'course_id',
      id,
    ),
  createAttempt: (data: s.CreateAttempt) =>
    request('POST', e.attempts, s.attemptSchema, { data }),
  attempt: async (id: string) =>
    requireId(
      await request('GET', e.attempt(id), s.attemptSchema),
      'attempt_id',
      id,
    ),
  submit: async (id: string, data: s.SubmitAttempt, key: string) =>
    requireId(
      await request('POST', e.submit(id), s.submitResponseSchema, {
        data,
        key,
      }),
      'attempt_id',
      id,
    ),
  task: async (id: string, signal?: AbortSignal) =>
    requireId(
      await request('GET', e.task(id), s.taskSchema, { signal }),
      'task_id',
      id,
    ),
  retry: (id: string, key: string) =>
    request('POST', e.retry(id), s.taskSchema, { data: {}, key }),
  report: async (id: string, uid?: string) => {
    const report = requireId(
      await request(
        'GET',
        uid ? e.teacherReport(uid, id) : e.report(id),
        s.reportSchema,
      ),
      'report_id',
      id,
    );
    return uid ? requireId(report, 'user_id', uid) : report;
  },
  recommendations: (id: string) =>
    request(
      'GET',
      e.recommendations(id),
      z.object({
        report_id: z.literal(id),
        attempt_id: z.string(),
        recommendations: z.array(s.recommendationSchema),
        actions: z.object({
          can_retest: z.boolean(),
          can_practice: z.boolean(),
        }),
      }),
    ),
  comparison: (id: string) =>
    request('GET', e.comparison(id), s.comparisonSchema.nullable()),
  history: (params: object = {}) =>
    request('GET', e.reports, s.pageSchema(s.historySchema), { params }),
  resource: async (id: string, params: object = {}) =>
    requireId(
      await request('GET', e.resource(id), s.resourceSchema, { params }),
      'resource_id',
      id,
    ),
  file: (id: string) =>
    request('GET', e.file(id), z.instanceof(Blob), { blob: true }),
  overview: (course_id: string) =>
    request('GET', e.teacher('overview'), s.overviewSchema, {
      params: { course_id },
    }),
  students: (params: object) =>
    request(
      'GET',
      e.teacher('students'),
      s.pageSchema(s.teacherStudentSchema),
      { params },
    ),
  studentAttempts: (uid: string, params: object) =>
    request(
      'GET',
      e.teacher(`students/${encodeURIComponent(uid)}/attempts`),
      s.pageSchema(s.historySchema),
      { params },
    ),
  saveCourse: (id: string, data: z.infer<typeof s.courseWriteSchema>) =>
    request('PATCH', e.teacher('courses', id), s.courseSchema, { data }),
  knowledge: (params: object) =>
    request(
      'GET',
      e.teacher('knowledge-points'),
      s.pageSchema(s.knowledgeSchema),
      { params },
    ),
  saveKnowledge: (
    id: string | null,
    data: z.infer<typeof s.knowledgeWriteSchema>,
  ) =>
    request(
      id ? 'PATCH' : 'POST',
      e.teacher('knowledge-points', id || undefined),
      s.knowledgeSchema,
      { data },
    ),
  questions: (params: object) =>
    request(
      'GET',
      e.teacher('questions'),
      s.pageSchema(s.teacherQuestionSchema),
      { params },
    ),
  saveQuestion: (id: string | null, data: s.QuestionWrite) =>
    request(
      id ? 'PATCH' : 'POST',
      e.teacher('questions', id || undefined),
      s.teacherQuestionSchema,
      { data },
    ),
  resources: (params: object) =>
    request(
      'GET',
      e.teacher('resources'),
      s.pageSchema(s.teacherResourceSchema),
      { params },
    ),
  teacherResource: (id: string) =>
    request('GET', e.teacher('resources', id), s.resourceSchema),
  saveResource: (id: string | null, data: s.ResourceWrite) =>
    request(
      id ? 'PATCH' : 'POST',
      e.teacher('resources', id || undefined),
      s.resourceSchema,
      { data },
    ),
  upload: (data: FormData, signal?: AbortSignal) =>
    request(
      'POST',
      e.teacher('documents'),
      z.object({ document: s.documentSchema, task: s.taskSchema }),
      { data, signal, timeout: 60000 },
    ),
  document: (id: string) =>
    request('GET', e.teacher('documents', id), s.documentSchema),
};
