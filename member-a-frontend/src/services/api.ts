import type { Attempt, Course, Envelope, LoginResult, Question, SubmitAttempt, TeacherOverview } from '../types/api'
import { getSession, saveSession } from './session'
import { mockRequest, MockRequestError } from './mock'

export const useMock = import.meta.env.VITE_USE_MOCK !== 'false'
const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
export class ApiError extends Error {
  constructor(message: string, public readonly requestId?: string, public readonly status?: number) { super(message) }
}
async function request<T>(path: string, method = 'GET', body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const session = getSession()
  if (useMock) {
    try { return (await mockRequest<T>(path, method, body, session, extraHeaders)).data }
    catch (error) {
      if (error instanceof MockRequestError) throw new ApiError(error.message, error.requestId, error.status)
      throw error
    }
  }
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30000)
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method, signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}), ...extraHeaders },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    const envelope = await response.json().catch(() => null) as Envelope<T> | null
    if (!envelope || typeof envelope.code !== 'number' || typeof envelope.message !== 'string' || !('data' in envelope)) {
      throw new ApiError(`服务返回了不符合约定的响应（HTTP ${response.status}）。`, response.headers.get('X-Request-ID') ?? undefined, response.status)
    }
    if (!response.ok || envelope.code !== 0) {
      if (response.status === 401) saveSession(null)
      throw new ApiError(envelope.message || '请求失败，请重试。', envelope.request_id, response.status)
    }
    return envelope.data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') throw new ApiError('请求超时，请稍后重试。')
    throw new ApiError('无法连接服务，请检查后端是否启动，以及网络和跨域设置。')
  } finally { window.clearTimeout(timeout) }
}
export function errorText(error: unknown) {
  return error instanceof ApiError && error.requestId ? `${error.message}（请求编号：${error.requestId}）` : error instanceof Error ? error.message : '操作失败，请重试。'
}
export const api = {
  login: (username: string, password: string) => request<LoginResult>('/auth/login', 'POST', { username, password }),
  courses: () => request<Course[]>('/courses'),
  questions: (id: string) => request<{ questions: Question[] }>(`/courses/${encodeURIComponent(id)}/questions`),
  submitAttempt: (body: SubmitAttempt, idempotencyKey: string) => request<Attempt>('/attempts', 'POST', body, { 'Idempotency-Key': idempotencyKey }),
  attempts: () => request<Attempt[]>('/attempts'),
  attempt: (id: string) => request<Attempt>(`/attempts/${encodeURIComponent(id)}`),
  teacherOverview: () => request<TeacherOverview>('/teacher/overview'),
}
