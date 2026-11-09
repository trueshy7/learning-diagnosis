import { it, expect } from 'vitest';
import {
  percent,
  numberText,
  deltaText,
  masteryChartData,
  safeUrl,
  safeRedirect,
  serializeAnswers,
  validateFile,
  cleanFilename,
} from '../../src/utils';
import { createSeed } from '../../src/mocks/repository';
import { restoreDraft, draftKey } from '../../src/composables/draft';
it.each([
  [0, '0%'],
  [null, '—'],
  [undefined, '—'],
  [1, '100%'],
  [0.6, '60%'],
  [0.8, '80%'],
  [2, '—'],
  [NaN, '—'],
] as const)('比例 %s → %s', (n, text) => expect(percent(n)).toBe(text));
it('分数零与未知分开，差值用百分点', () => {
  expect(numberText(0)).toBe('0');
  expect(numberText(null)).toBe('—');
  expect(deltaText(20)).toBe('+20 个百分点');
  expect(deltaText(-20)).toBe('-20 个百分点');
  expect(deltaText(0)).toBe('0 个百分点');
  expect(deltaText(null)).toBe('不可比较');
});
it('证据不足不进入掌握度图，真实零掌握仍可展示', () => {
  const s = createSeed();
  expect(masteryChartData(s.reports['report-a-004'].knowledge_points)).toEqual(
    [],
  );
  expect(
    masteryChartData(s.reports['report-a-005'].knowledge_points),
  ).toHaveLength(8);
  expect(
    masteryChartData(s.reports['report-a-005'].knowledge_points)[0].value,
  ).toBe(0);
});
it('安全 URL、跳转与文件限制', () => {
  expect(safeUrl('javascript:alert(1)')).toBeNull();
  expect(safeUrl('data:text/html,x')).toBeNull();
  expect(safeUrl('https://example.com/a')).toBe('https://example.com/a');
  for (const x of [
    'https://evil.com',
    '//evil.com',
    '/\\evil',
    '/%2fevil',
    '/teacher/questions',
  ])
    expect(safeRedirect(x, 'student')).toBe('/courses');
  expect(safeRedirect('/reports/abc', 'student')).toBe('/reports/abc');
  expect(validateFile(new File(['a'], 'bad.exe'))).toContain('仅支持');
  expect(
    validateFile(new File(['a'], 'note.txt', { type: 'text/plain' })),
  ).toBeNull();
  expect(validateFile(new File(['long'], 'a.txt'), 1)).toContain('超过');
  expect(cleanFilename('../a\\b.pdf')).toBe('.._a_b.pdf');
});
it('答案按快照顺序规范化，去重、过滤非法选项，空答为空集合', () => {
  const a = createSeed().attempts['attempt-a-001'].value;
  const q = a.questions[2];
  const values = [
    q.options[1].option_id,
    q.options[0].option_id,
    q.options[0].option_id,
    'invalid',
  ];
  const output = serializeAnswers(a, { [q.question_id]: values });
  expect(output[2].selected_option_ids).toEqual(
    q.options.slice(0, 2).map((o) => o.option_id),
  );
  expect(output[0].selected_option_ids).toEqual([]);
  expect(output).toHaveLength(24);
});
it('草稿隔离用户和快照，已提交草稿丢弃', () => {
  const a = createSeed().attempts['attempt-a-001'].value;
  a.status = 'in_progress';
  sessionStorage.setItem(
    draftKey(a),
    JSON.stringify({
      [a.questions[0].question_id]: [
        a.questions[0].options[0].option_id,
        'bad',
      ],
    }),
  );
  expect(restoreDraft(a).choices[a.questions[0].question_id]).toHaveLength(1);
  const other = { ...a, user_id: 'student-b' };
  expect(restoreDraft(other).choices[a.questions[0].question_id]).toEqual([]);
  const changed = { ...a, snapshot_version: 'v2' };
  expect(restoreDraft(changed).stale).toBe(true);
  expect(sessionStorage.getItem(draftKey(a))).toBeNull();
  sessionStorage.setItem(draftKey(a), '{}');
  a.status = 'submitted';
  expect(restoreDraft(a).choices).toEqual({});
  expect(sessionStorage.getItem(draftKey(a))).toBeNull();
});
