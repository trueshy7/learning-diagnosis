import { ApiError } from '../client';
import type { Score, Report, Attempt } from '../contracts';
export function sameScore(a: Score, b: Score) {
  return (
    a.raw_score === b.raw_score &&
    a.max_score === b.max_score &&
    a.correct_count === b.correct_count &&
    a.total_count === b.total_count &&
    Math.abs(a.percentage - b.percentage) <= 0.00500001
  );
}
export function verifyReport(report: Report, attempt: Attempt) {
  if (
    !attempt.result ||
    report.attempt_id !== attempt.attempt_id ||
    report.user_id !== attempt.user_id ||
    report.course_id !== attempt.course_id ||
    report.rule_version !== attempt.result.rule_version ||
    !sameScore(report.score, attempt.result.score)
  )
    throw new ApiError('INVALID_RESPONSE', '报告与关联测验或成绩不一致');
  return report;
}
export function requireId<T>(data: T, field: keyof T, expected: string): T {
  if (data[field] !== expected)
    throw new ApiError(
      'INVALID_RESPONSE',
      `响应 ${String(field)} 与请求不一致`,
    );
  return data;
}
