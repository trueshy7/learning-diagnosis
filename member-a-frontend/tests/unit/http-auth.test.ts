import { it, expect, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { http, HttpResponse, delay } from 'msw';
import { api } from '../../src/api/services';
import {
  request,
  ApiError,
  client,
  clearPrivateSession,
} from '../../src/api/client';
import { useAuth } from '../../src/stores/auth';
import { server } from '../../src/mocks/node';
import { getRepository } from '../../src/mocks/repository';
import { z } from 'zod';
async function login() {
  const r = await api.login('demo_student_a', 'Demo123!');
  sessionStorage.setItem('learnmate-token', r.access_token);
  return r;
}
it('共享身份初始化只请求一次，角色来自 /me', async () => {
  await login();
  setActivePinia(createPinia());
  const auth = useAuth();
  const spy = vi.spyOn(api, 'me');
  await Promise.all([auth.bootstrap(), auth.bootstrap(), auth.bootstrap()]);
  expect(spy).toHaveBeenCalledTimes(1);
  expect(auth.user?.role).toBe('student');
});
it('403 保留会话，401 清空，错误口令不触发全局过期事件', async () => {
  await login();
  await expect(api.report('report-b-001')).rejects.toMatchObject({
    httpStatus: 403,
  });
  expect(sessionStorage.getItem('learnmate-token')).not.toBeNull();
  const listener = vi.fn();
  window.addEventListener('learnmate-expired', listener);
  await expect(api.login('demo_student_a', 'wrong')).rejects.toMatchObject({
    code: 'INVALID_CREDENTIALS',
  });
  expect(listener).not.toHaveBeenCalled();
  await getRepository().change((s) =>
    Object.values(s.tokens).forEach((t) => (t.expires = 0)),
  );
  await expect(api.me()).rejects.toMatchObject({ httpStatus: 401 });
  expect(sessionStorage.getItem('learnmate-token')).toBeNull();
  expect(listener).toHaveBeenCalledTimes(1);
  window.removeEventListener('learnmate-expired', listener);
});
it('退出后迟到请求不能恢复旧账号', async () => {
  await login();
  setActivePinia(createPinia());
  const auth = useAuth();
  server.use(
    http.get('http://localhost/api/v1/auth/me', async () => {
      await delay(50);
      return HttpResponse.json({
        code: 'OK',
        message: '',
        request_id: 'late',
        data: {
          user_id: 'student-a',
          username: 'old',
          display_name: '旧用户',
          role: 'student',
        },
      });
    }),
  );
  const boot = auth.bootstrap();
  auth.clear();
  await boot;
  expect(auth.user).toBeNull();
});
it('取消和超时映射为不同前端错误', async () => {
  const spy = vi.spyOn(client, 'request');
  spy.mockRejectedValueOnce({ isAxiosError: true, code: 'ECONNABORTED' });
  await expect(request('GET', '/test', z.null())).rejects.toMatchObject({
    code: 'REQUEST_TIMEOUT',
  });
  const controller = new AbortController();
  controller.abort();
  await expect(
    request('GET', '/test', z.null(), { signal: controller.signal }),
  ).rejects.toMatchObject({ code: 'REQUEST_CANCELLED' });
  clearPrivateSession();
});
it('JSON 错误 Blob 不会被当作文件下载', async () => {
  vi.spyOn(client, 'request').mockResolvedValueOnce({
    data: new Blob(
      [
        JSON.stringify({
          code: 'RESOURCE_REMOVED',
          message: '已移除',
          data: null,
          request_id: 'blob-error',
        }),
      ],
      { type: 'application/json' },
    ),
    status: 410,
  });
  try {
    await api.file('missing');
    throw new Error('should fail');
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).httpStatus).toBe(410);
  }
});
it('并发重复提交只产生一次结果/任务，不同答案拒绝；响应丢失可查询恢复', async () => {
  await login();
  const a = await api.createAttempt({
    course_id: 'course-ds',
    kind: 'initial',
    client_request_id: 'unique-intent',
  });
  const data = {
    snapshot_version: a.snapshot_version,
    answers: a.questions.map((q) => ({
      question_id: q.question_id,
      selected_option_ids: [] as string[],
    })),
  };
  const [r1, r2] = await Promise.all([
    api.submit(a.attempt_id, data, 'submit-key'),
    api.submit(a.attempt_id, data, 'submit-key'),
  ]);
  expect(r1.diagnosis_task_id).toBe(r2.diagnosis_task_id);
  expect(r1.result.score.raw_score).toBe(0);
  data.answers[0].selected_option_ids = [a.questions[0].options[0].option_id];
  await expect(
    api.submit(a.attempt_id, data, 'submit-key'),
  ).rejects.toMatchObject({ httpStatus: 409 });
  const b = await api.createAttempt({
    course_id: 'course-ds',
    kind: 'initial',
    client_request_id: 'second-intent',
  });
  await getRepository().change(
    (s) => (s.scenario = 'submit-committed-response-lost'),
  );
  await expect(
    api.submit(
      b.attempt_id,
      { ...data, snapshot_version: b.snapshot_version },
      'lost-key',
    ),
  ).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  const saved = await api.attempt(b.attempt_id);
  expect(saved.status).toBe('submitted');
  expect(saved.diagnosis_task_id).toBeTruthy();
});
it('任务重试同一幂等标识不重复增加次数', async () => {
  await login();
  await getRepository().change((s) => {
    const t = s.tasks['task-a-001'];
    t.status = 'failed';
    t.can_retry = true;
    t.error_message = '模拟故障';
  });
  const [a, b] = await Promise.all([
    api.retry('task-a-001', 'one-retry'),
    api.retry('task-a-001', 'one-retry'),
  ]);
  expect(a.retry_count).toBe(1);
  expect(b.retry_count).toBe(1);
  expect(a.attempt_id).toBe(b.attempt_id);
});
it('教师可读停用资源元数据并恢复，学生来源接口停用时返回410', async () => {
  const session = await api.login('demo_teacher', 'Demo123!');
  sessionStorage.setItem('learnmate-token', session.access_token);
  const original = await api.teacherResource('res-linear-1');
  await api.saveResource(original.resource_id, { ...original, active: false });
  await expect(api.resource(original.resource_id)).rejects.toMatchObject({
    httpStatus: 410,
  });
  const inactive = await api.teacherResource(original.resource_id);
  expect(inactive.active).toBe(false);
  await api.saveResource(original.resource_id, { ...inactive, active: true });
  expect((await api.resource(original.resource_id)).availability).toBe(
    'available',
  );
});
