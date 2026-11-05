import { it, expect, vi } from 'vitest';
import { z } from 'zod';
import { createSeed } from '../../src/mocks/repository';
import {
  scoreSchema,
  pointResultSchema,
  reportSchema,
  comparisonSchema,
  resourceWriteSchema,
} from '../../src/api/contracts';
import { verifyReport } from '../../src/api/mappers';
import { ApiError, client } from '../../src/api/client';
import { api } from '../../src/api/services';
import {
  userError,
  taskError,
  validationMessage,
} from '../../src/utils/presentation';
import {
  restoreSubmitIntent,
  submitIntentKey,
} from '../../src/composables/draft';
it('拒绝带用户口令的外部链接', () => {
  expect(
    resourceWriteSchema.safeParse({
      course_id: 'c',
      title: '链接',
      description: '',
      kind: 'external',
      knowledge_point_ids: ['k'],
      difficulty: 'easy',
      active: true,
      text_content: null,
      external_url: 'https://name:secret@example.com/',
    }).success,
  ).toBe(false);
});
it('历史来源版本不一致返回410，不误打开新版本', async () => {
  const session = await api.login('demo_student_a', 'Demo123!');
  sessionStorage.setItem('learnmate-token', session.access_token);
  await expect(
    api.resource('res-linear-1', { resource_version: 'missing-old-version' }),
  ).rejects.toMatchObject({ httpStatus: 410 });
});
it('用户提示不回显SQL、内部路径、字段名或服务堆栈', () => {
  expect(
    userError(
      new ApiError(
        'INVALID_RESPONSE',
        'Traceback SQL password=/private/config',
      ),
    ),
  ).not.toMatch(/Traceback|SQL|password|private/);
  expect(
    userError(new ApiError('UNKNOWN_INTERNAL_CODE', 'secret')),
  ).not.toContain('secret');
  expect(taskError('SQL_DATABASE_FAILED')).not.toContain('SQL');
  const result = z.object({ stem: z.string().min(1) }).safeParse({ stem: '' });
  expect(result.success).toBe(false);
  if (!result.success) {
    expect(validationMessage(result.error)).toContain('题干');
    expect(validationMessage(result.error)).not.toMatch(/stem|Too small/);
  }
});
it('兼容两位小数成绩，但拒绝错误成绩与知识点统计', () => {
  const r = createSeed().reports['report-a-001'];
  expect(scoreSchema.safeParse({ ...r.score, percentage: 54.17 }).success).toBe(
    true,
  );
  expect(scoreSchema.safeParse({ ...r.score, percentage: 55 }).success).toBe(
    false,
  );
  expect(
    pointResultSchema.safeParse({ ...r.knowledge_points[0], correct_rate: 0.9 })
      .success,
  ).toBe(false);
  expect(
    pointResultSchema.safeParse({
      ...r.knowledge_points[0],
      wrong_question_ids: [],
    }).success,
  ).toBe(false);
});
it('拒绝重复引用、缺少缓存来源及矛盾百分点', () => {
  const r = createSeed().reports['report-a-002'];
  expect(
    reportSchema.safeParse({
      ...r,
      evidences: [...r.evidences, r.evidences[0]],
    }).success,
  ).toBe(false);
  expect(
    reportSchema.safeParse({ ...r, explanation_mode: 'cached' }).success,
  ).toBe(false);
  expect(
    reportSchema.safeParse({
      ...r,
      explanation_mode: 'cached',
      cached_from: {
        report_id: r.report_id,
        report_version: r.report_version,
        generated_at: r.generated_at,
      },
    }).success,
  ).toBe(true);
  const c = structuredClone(r.comparison!);
  c.knowledge_points[0].delta_percentage_points = 99;
  expect(comparisonSchema.safeParse(c).success).toBe(false);
});
it('完整报告与测验归属、规则、成绩不一致时拒绝展示', () => {
  const s = createSeed(),
    r = s.reports['report-a-001'],
    a = s.attempts['attempt-a-001'].value;
  expect(verifyReport(r, a)).toBe(r);
  for (const patch of [
    { user_id: 'other' },
    { course_id: 'other' },
    { rule_version: 'other' },
    { score: s.reports['report-a-006'].score },
  ])
    expect(() => verifyReport({ ...r, ...patch }, a)).toThrow();
});
it.each(['text/html', 'image/svg+xml', 'application/javascript', ''])(
  '拒绝200但危险或未知的文件类型 %s',
  async (type) => {
    vi.spyOn(client, 'request').mockResolvedValueOnce({
      data: new Blob(['<script>alert(1)</script>'], { type }),
      status: 200,
    });
    await expect(api.file('resource')).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  },
);
it('文件接口401即使不是有效JSON也会清理会话', async () => {
  sessionStorage.setItem('learnmate-token', 'test');
  vi.spyOn(client, 'request').mockResolvedValueOnce({
    data: new Blob(['unauthorized'], { type: 'text/plain' }),
    status: 401,
  });
  await expect(api.file('resource')).rejects.toBeInstanceOf(ApiError);
  expect(sessionStorage.getItem('learnmate-token')).toBeNull();
});
it('恢复提交意图前校验快照、题目和选项，损坏意图不会锁住界面', () => {
  const a = createSeed().attempts['attempt-a-001'].value;
  a.status = 'in_progress';
  const intent = {
    key: 'stable-key',
    data: {
      snapshot_version: a.snapshot_version,
      answers: a.questions.map((q) => ({
        question_id: q.question_id,
        selected_option_ids: [] as string[],
      })),
    },
  };
  sessionStorage.setItem(submitIntentKey(a), JSON.stringify(intent));
  expect(restoreSubmitIntent(a)?.key).toBe('stable-key');
  intent.data.answers[0].selected_option_ids = ['foreign'];
  sessionStorage.setItem(submitIntentKey(a), JSON.stringify(intent));
  expect(restoreSubmitIntent(a)).toBeNull();
  expect(sessionStorage.getItem(submitIntentKey(a))).toBeNull();
});
