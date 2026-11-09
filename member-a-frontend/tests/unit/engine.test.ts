import { it, expect } from 'vitest';
import { createSeed } from '../../src/mocks/repository';
import {
  grade,
  diagnose,
  publicQuestion,
  normalized,
} from '../../src/mocks/services/engine';
it('固定前后测 13/24、19/24，比较差值为 25 个百分点', () => {
  const s = createSeed();
  expect(s.reports['report-a-001'].score.raw_score).toBe(13);
  expect(s.reports['report-a-002'].score.raw_score).toBe(19);
  expect(
    s.reports['report-a-002'].comparison!.overall_delta_percentage_points,
  ).toBeCloseTo(25);
});
it.each([
  [0, 0, 'insufficient_evidence'],
  [2, 2, 'insufficient_evidence'],
  [3, 0, 'weak'],
  [3, 3, 'mastered'],
  [5, 3, 'consolidating'],
  [5, 4, 'mastered'],
])('规则边界 %i 题，%i 正确 → %s', (n, right, expected) => {
  const s = createSeed(),
    a = s.attempts['attempt-a-001'].value;
  const qs = Object.values(s.questions)
    .filter((q) => q.knowledge_point_ids[0] === 'kp-linear')
    .slice(0, Number(n));
  a.questions = qs.map(publicQuestion);
  if (qs.length)
    a.result = grade(
      a.attempt_id,
      qs,
      qs.map((q, i) => ({
        question_id: q.question_id,
        selected_option_ids: i < Number(right) ? q.correct_option_ids : [],
      })),
    );
  const p = diagnose(s, a)[0];
  expect(p.mastery_status).toBe(expected);
  expect(p.question_count).toBe(n);
  if (Number(n) < 3) expect(p.mastery_score).toBeNull();
});
it('多选集合完全匹配、漏选计零；多知识点不重复增加总题量', () => {
  const s = createSeed();
  const multi = s.questions['q-linear-03'],
    cross = s.questions['q-linear-07'];
  const r = grade(
    'test',
    [multi, cross, cross],
    [
      {
        question_id: multi.question_id,
        selected_option_ids: [...multi.correct_option_ids].reverse(),
      },
      {
        question_id: cross.question_id,
        selected_option_ids: cross.correct_option_ids,
      },
    ],
  );
  expect(r.score.total_count).toBe(2);
  expect(r.score.raw_score).toBe(2);
  expect(
    grade(
      'test',
      [multi],
      [
        {
          question_id: multi.question_id,
          selected_option_ids: multi.correct_option_ids.slice(0, 1),
        },
      ],
    ).score.raw_score,
  ).toBe(0);
  const a = s.attempts['attempt-a-001'].value;
  a.questions = [publicQuestion(cross)];
  a.result = grade(
    a.attempt_id,
    [cross],
    [
      {
        question_id: cross.question_id,
        selected_option_ids: cross.correct_option_ids,
      },
    ],
  );
  expect(diagnose(s, a).filter((p) => p.correct_count === 1)).toHaveLength(2);
});
it('多选顺序不改变提交语义', () =>
  expect(
    normalized([{ question_id: 'q', selected_option_ids: ['b', 'a', 'a'] }]),
  ).toBe(normalized([{ question_id: 'q', selected_option_ids: ['a', 'b'] }])));
