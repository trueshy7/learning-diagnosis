import axios from 'axios';
import { z } from 'zod';
import { config } from '../config';

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public httpStatus = 0,
    public requestId = '',
    public fieldErrors: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}
export let generation = 0;
const controllers = new Set<AbortController>();
export function clearPrivateSession() {
  generation++;
  controllers.forEach((c) => c.abort());
  controllers.clear();
  sessionStorage.removeItem('learnmate-token');
  Object.keys(sessionStorage)
    .filter(
      (k) =>
        k.startsWith('learnmate-draft:') || k.startsWith('learnmate-intent:'),
    )
    .forEach((k) => sessionStorage.removeItem(k));
}
export const client = axios.create({ baseURL: config.apiBase, timeout: 10000 });
const envelopeSchema = z.object({
  code: z.string(),
  message: z.string(),
  data: z.unknown(),
  request_id: z.string().optional(),
  errors: z
    .array(z.object({ field: z.string(), message: z.string() }))
    .optional(),
});
export function parseEnvelope<T>(
  raw: unknown,
  schema: z.ZodType<T>,
  status = 200,
  localId = 'local:unknown',
): T {
  const e = envelopeSchema.safeParse(raw);
  if (!e.success) {
    const fastapi = z
      .object({
        detail: z.array(
          z.object({
            loc: z.array(z.union([z.string(), z.number()])),
            msg: z.string(),
          }),
        ),
      })
      .safeParse(raw);
    if (status === 422 && fastapi.success)
      throw new ApiError(
        'VALIDATION_ERROR',
        '输入字段校验失败',
        status,
        localId,
        fastapi.data.detail.map((x) => ({
          field: x.loc.join('.'),
          message: x.msg,
        })),
      );
    throw new ApiError(
      'INVALID_RESPONSE',
      '接口响应格式异常，请联系接口负责人',
      status,
      localId,
    );
  }
  const trace = e.data.request_id || localId;
  if (status >= 400 || e.data.code !== 'OK')
    throw new ApiError(
      e.data.code,
      e.data.message,
      status,
      trace,
      e.data.errors,
    );
  const parsed = schema.safeParse(e.data.data);
  if (!parsed.success)
    throw new ApiError(
      'INVALID_RESPONSE',
      `接口数据异常：${parsed.error.issues.map((x) => `${x.path.join('.')}: ${x.message}`).join('；')}`,
      status,
      trace,
    );
  return parsed.data;
}
export async function request<T>(
  method: string,
  url: string,
  schema: z.ZodType<T>,
  options: {
    data?: unknown;
    params?: object;
    signal?: AbortSignal;
    key?: string;
    timeout?: number;
    blob?: boolean;
  } = {},
): Promise<T> {
  const epoch = generation;
  const controller = new AbortController();
  controllers.add(controller);
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const localId = `local:${crypto.randomUUID()}`;
  try {
    const token = sessionStorage.getItem('learnmate-token');
    const response = await client.request({
      method,
      url,
      data: options.data,
      params: options.params,
      signal: controller.signal,
      timeout: options.timeout ?? 10000,
      responseType: options.blob ? 'blob' : 'json',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.key ? { 'Idempotency-Key': options.key } : {}),
      },
      validateStatus: () => true,
    });
    if (epoch !== generation)
      throw new ApiError('REQUEST_CANCELLED', '会话已变化');
    let raw: unknown = response.data;
    if (response.status === 401 && url !== '/auth/login') {
      sessionStorage.setItem('learnmate-expired', '1');
      clearPrivateSession();
      window.dispatchEvent(new Event('learnmate-expired'));
    }
    if (options.blob && raw instanceof Blob) {
      const mime = raw.type.split(';')[0].trim().toLowerCase();
      if (
        response.status >= 200 &&
        response.status < 300 &&
        !mime.includes('json')
      ) {
        if (
          ![
            'application/pdf',
            'text/plain',
            'text/markdown',
            'application/octet-stream',
          ].includes(mime) ||
          raw.size === 0
        )
          throw new ApiError(
            'INVALID_RESPONSE',
            '文件内容或类型不符合下载约定',
            response.status,
            localId,
          );
        return raw as T;
      }
      try {
        raw = JSON.parse(await raw.text());
      } catch {
        throw new ApiError(
          'INVALID_RESPONSE',
          '文件接口返回了无效内容',
          response.status,
          localId,
        );
      }
    }
    return parseEnvelope(raw, schema, response.status, localId);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (axios.isCancel(error))
      throw new ApiError('REQUEST_CANCELLED', '请求已取消', 0, localId);
    if (axios.isAxiosError(error))
      throw new ApiError(
        error.code === 'ECONNABORTED' ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
        error.code === 'ECONNABORTED'
          ? '请求超时，请确认服务状态'
          : '无法连接服务，请检查网络或后端地址',
        0,
        localId,
      );
    throw error;
  } finally {
    controllers.delete(controller);
    options.signal?.removeEventListener('abort', abort);
  }
}
