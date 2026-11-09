import assert from 'node:assert/strict';
import { createSeed } from '../src/mocks/repository';
import {
  attemptSchema,
  reportSchema,
  teacherQuestionSchema,
  studentQuestionSchema,
} from '../src/api/contracts';
import {
  grade,
  buildReport,
  publicQuestion,
} from '../src/mocks/services/engine';
const s = createSeed();
assert.equal(s.course.knowledge_points.length, 8);
const questions = Object.values(s.questions),
  resources = Object.values(s.resources),
  attempts = Object.values(s.attempts);
assert(questions.length >= 64);
assert(resources.length >= 20);
assert(attempts.length >= 10);
assert(questions.filter((q) => q.type === 'multiple_choice').length >= 16);
for (const kp of s.course.knowledge_points)
  assert(
    questions.filter((q) => q.knowledge_point_ids[0] === kp.knowledge_point_id)
      .length >= 8,
  );
assert.equal(new Set(questions.map((q) => q.stem)).size, questions.length);
for (const q of questions) {
  teacherQuestionSchema.parse(q);
  studentQuestionSchema.parse(publicQuestion(q));
  assert(!('correct_option_ids' in publicQuestion(q)));
  assert(
    q.correct_option_ids.every((id) =>
      q.options.some((o) => o.option_id === id),
    ),
  );
}
for (const r of resources) {
  assert(r.text_content && r.text_content.length > 60);
  assert(r.document_id);
  assert(
    r.knowledge_point_ids.every((id) =>
      s.course.knowledge_points.some((k) => k.knowledge_point_id === id),
    ),
  );
}
for (const item of attempts) {
  const a = attemptSchema.parse(item.value);
  const r = reportSchema.parse(s.reports[a.report_id!]);
  assert.deepEqual(
    grade(a.attempt_id, item.snapshot, a.result!.graded_answers).score,
    a.result!.score,
  );
  assert.deepEqual(r.score, a.result!.score);
  assert.equal(r.user_id, a.user_id);
  assert.equal(s.tasks[a.diagnosis_task_id!].report_id, a.report_id);
  for (const p of r.knowledge_points) {
    assert.equal(
      p.wrong_question_ids.length,
      p.question_count - p.correct_count,
    );
    if (p.question_count >= 3) {
      assert.equal(p.mastery_score, p.correct_count / p.question_count);
      assert.equal(
        p.mastery_status,
        p.correct_rate! < 0.6
          ? 'weak'
          : p.correct_rate! < 0.8
            ? 'consolidating'
            : 'mastered',
      );
    }
  }
  for (const e of r.evidences) {
    const resource = s.resources[e.resource_id];
    assert(resource);
    assert(resource.text_content!.includes(e.text));
    assert(resource.text_content!.includes(e.location.section!));
    assert.equal(e.document_id, resource.document_id);
  }
  for (const rec of r.recommendations) {
    assert(rec.resources.every((x) => !!s.resources[x.resource_id]));
    assert(rec.practice_questions.every((x) => !!s.questions[x.question_id]));
  }
  if (a.baseline_attempt_id) {
    const base = s.attempts[a.baseline_attempt_id].value;
    assert.equal(base.user_id, a.user_id);
    assert(base.submitted_at! < a.submitted_at!);
    assert.equal(r.comparison!.baseline_attempt_id, base.attempt_id);
  }
}
assert.equal(s.attempts['attempt-a-001'].value.result!.score.raw_score, 13);
assert.equal(s.attempts['attempt-a-002'].value.result!.score.raw_score, 19);
assert.equal(s.attempts['attempt-a-004'].value.result!.score.raw_score, 2);
assert.deepEqual(
  s.reports['report-a-001'].knowledge_points.map((p) => p.mastery_status),
  [
    'weak',
    'consolidating',
    'mastered',
    'consolidating',
    'weak',
    'weak',
    'mastered',
    'weak',
  ],
);
assert.equal(s.reports['report-a-004'].knowledge_points[0].mastery_score, null);
assert.equal(s.reports['report-a-004'].knowledge_points[0].correct_rate, 1);
const removed = resources[0];
removed.active = false;
assert(
  buildReport(
    s,
    s.attempts['attempt-a-001'].value,
    'test-report',
  ).recommendations.every((r) =>
    r.resources.every((x) => x.resource_id !== removed.resource_id),
  ),
);
const old = s.attempts['attempt-a-001'].snapshot[0].stem;
s.questions[questions[0].question_id].stem = '教师修改后的题干';
assert.equal(s.attempts['attempt-a-001'].snapshot[0].stem, old);
console.log(
  `PASS: 8 知识点 / ${questions.length} 题 / ${resources.length} 资料 / ${attempts.length} 学习记录；固定成绩、引用、比较、停用和快照检查通过。`,
);
