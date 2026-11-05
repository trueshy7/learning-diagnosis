import { z } from 'zod';
import { getSession, saveSession, sessionVersion } from './session';
import * as s from './contracts';
import type { SubmitAttempt } from '../types/api';
export const useMock = false;
const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(
  /\/$/,
  '',
);
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly requestId = '',
    public readonly status = 0,
  ) {
    super(message);
  }
}
const messages: Record<number, string> = {
  401: '账号或密码错误，或登录已过期，请重新登录。',
  403: '当前账号无权执行此操作。',
  404: '记录不存在或接口暂未提供，请刷新或联系管理员。',
  409: '提交内容与已有记录冲突，请从历史记录核对。',
  422: '提交内容不符合要求，请检查填写内容。',
  502: '资料服务暂不可用，请稍后重试。',
};
const envelope = z.object({
  code: z.number(),
  message: z.string(),
  data: z.unknown(),
  request_id: z.string(),
});
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  method = 'GET',
  body?: unknown,
  key?: string,
): Promise<T> {
  const current = sessionVersion,
    session = getSession(),
    controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(baseUrl + path, {
      method,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(session ? { Authorization: 'Bearer ' + session.access_token } : {}),
        ...(key ? { 'Idempotency-Key': key } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (current !== sessionVersion)
      throw new ApiError('会话已变化，请重新打开页面。');
    if (response.status === 401 && path !== '/auth/login') {
      saveSession(null);
      window.dispatchEvent(new Event('group-session-expired'));
    }
    const raw: unknown = await response.json().catch(() => null),
      parsed = envelope.safeParse(raw);
    const requestId = parsed.success
      ? parsed.data.request_id
      : response.headers.get('X-Request-ID') || '';
    if (!response.ok)
      throw new ApiError(
        messages[response.status] || '服务暂时无法完成请求，请稍后重试。',
        requestId,
        response.status,
      );
    if (!parsed.success || parsed.data.code !== 0)
      throw new ApiError(
        '服务返回的数据暂时无法展示，请联系管理员。',
        requestId,
        response.status,
      );
    const data = schema.safeParse(parsed.data.data);
    if (!data.success)
      throw new ApiError(
        '服务返回的数据暂时无法展示，请联系管理员。',
        requestId,
        response.status,
      );
    if (current !== sessionVersion)
      throw new ApiError('会话已变化，请重新打开页面。');
    return data.data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new ApiError(
        '请求超时，请重试；测验可能已保存，重试将沿用原提交编号。',
      );
    throw new ApiError('无法连接服务，请检查后端是否启动以及网络连接。');
  } finally {
    window.clearTimeout(timeout);
  }
}
export function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : '操作未完成，请重试。';
}
export const api = {
  login: (username: string, password: string) =>
    request('/auth/login', s.loginSchema, 'POST', { username, password }),
  logout: () =>
    request('/auth/logout', z.object({ logged_out: z.literal(true) }), 'POST'),
  courses: () => request('/courses', z.array(s.courseSchema)),
  questions: (id: string) =>
    request(
      '/courses/' + encodeURIComponent(id) + '/questions',
      s.questionsSchema,
    ),
  submitAttempt: (body: SubmitAttempt, key: string) =>
    request('/attempts', s.attemptSchema, 'POST', body, key),
  attempts: () => request('/attempts', z.array(s.attemptSchema)),
  attempt: async (id: string) => {
    const result = await request(
      '/attempts/' + encodeURIComponent(id),
      s.attemptSchema,
    );
    if (result.id !== id)
      throw new ApiError('服务返回的测验记录不匹配，请重新打开。');
    return result;
  },
  regenerate: async (id: string) => {
    const result = await request(
      '/attempts/' + encodeURIComponent(id) + '/report',
      s.attemptSchema,
      'POST',
    );
    if (result.id !== id)
      throw new ApiError('服务返回的测验记录不匹配，请重新打开。');
    return result;
  },
  teacherOverview: () => request('/teacher/overview', s.overviewSchema),
  ingest: (body: z.infer<typeof s.ingestSchema>) =>
    request(
      '/teacher/resources',
      s.ingestResultSchema,
      'POST',
      s.ingestSchema.parse(body),
    ),
};
