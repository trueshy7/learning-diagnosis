import type { Answer, Attempt, PointResult } from '../api/contracts';
export const numberText = (n: number | null | undefined) =>
  n == null || !Number.isFinite(n) ? '—' : n.toFixed(2).replace(/\.00$/, '');
export const percent = (n: number | null | undefined) =>
  n == null || !Number.isFinite(n) || n < 0 || n > 1
    ? '—'
    : `${numberText(n * 100)}%`;
export const deltaText = (n: number | null | undefined) =>
  n == null || !Number.isFinite(n)
    ? '不可比较'
    : `${n > 0 ? '+' : ''}${numberText(n)} 个百分点`;
export const dateText = (s: string | null) =>
  !s
    ? '—'
    : new Date(s).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        hour12: false,
      });
export function safeUrl(s: string | null) {
  try {
    const u = new URL(s || '');
    return ['http:', 'https:'].includes(u.protocol) &&
      !u.username &&
      !u.password
      ? u.href
      : null;
  } catch {
    return null;
  }
}
export function safeRedirect(value: unknown, role: string): string {
  const fallback = role === 'teacher' ? '/teacher/overview' : '/courses';
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\') ||
    Array.from(value).some((c) => c.charCodeAt(0) <= 32) ||
    /%2f|%5c/i.test(value)
  )
    return fallback;
  if (
    value.startsWith('/login') ||
    (role !== 'teacher' && value.startsWith('/teacher'))
  )
    return fallback;
  if (
    role === 'teacher' &&
    !value.startsWith('/teacher') &&
    !value.startsWith('/resources')
  )
    return fallback;
  return value;
}
export function serializeAnswers(
  a: Attempt,
  choices: Record<string, string[]>,
): Answer[] {
  return a.questions.map((q) => ({
    question_id: q.question_id,
    selected_option_ids: q.options
      .filter((o) => (choices[q.question_id] || []).includes(o.option_id))
      .map((o) => o.option_id),
  }));
}
export const masteryChartData = (points: PointResult[]) =>
  points
    .filter(
      (p) =>
        p.mastery_score !== null &&
        p.mastery_status !== 'insufficient_evidence',
    )
    .map((p) => ({ name: p.name, value: p.mastery_score! * 100 }));
export function validateFile(file: File, limit = 10 * 1024 * 1024) {
  if (file.size > limit) return '文件超过 10 MiB 上限';
  if (!/\.(txt|md|pdf)$/i.test(file.name)) return '仅支持 TXT、MD、文本型 PDF';
  const ext = file.name.split('.').pop()?.toLowerCase();
  if (
    file.type &&
    file.type !== 'application/octet-stream' &&
    !(
      {
        txt: ['text/plain'],
        md: ['text/plain', 'text/markdown'],
        pdf: ['application/pdf'],
      }[ext || ''] || []
    ).includes(file.type)
  )
    return '文件类型与扩展名不一致';
  return null;
}
export const cleanFilename = (s: string) =>
  Array.from(s.replace(/[\\/:*?"<>|]/g, '_'))
    .map((c) => (c.charCodeAt(0) < 32 ? '_' : c))
    .join('');
