import type {
  Answer,
  Attempt,
  Comparison,
  PointResult,
  Report,
  Result,
  StudentQuestion,
  TeacherQuestion,
} from '../../api/contracts';
import type { State } from '../repository';

export const publicQuestion = (q: TeacherQuestion): StudentQuestion => ({
  question_id: q.question_id,
  type: q.type,
  stem: q.stem,
  options: structuredClone(q.options),
  knowledge_point_ids: [...q.knowledge_point_ids],
  difficulty: q.difficulty,
});
export const normalized = (answers: Answer[]) =>
  JSON.stringify(
    [...answers]
      .map((a) => ({
        question_id: a.question_id,
        selected_option_ids: [...new Set(a.selected_option_ids)].sort(),
      }))
      .sort((a, b) => a.question_id.localeCompare(b.question_id)),
  );
export function grade(
  attemptId: string,
  snapshot: TeacherQuestion[],
  answers: Answer[],
): Result {
  const unique = [...new Map(snapshot.map((q) => [q.question_id, q])).values()];
  const graded = unique.map((q) => {
    const selected = [
      ...new Set(
        answers.find((a) => a.question_id === q.question_id)
          ?.selected_option_ids || [],
      ),
    ];
    return {
      question_id: q.question_id,
      selected_option_ids: selected,
      is_correct:
        JSON.stringify([...selected].sort()) ===
        JSON.stringify([...q.correct_option_ids].sort()),
    };
  });
  const n = graded.filter((a) => a.is_correct).length;
  return {
    attempt_id: attemptId,
    rule_version: 'mock-rule-v1',
    graded_answers: graded,
    score: {
      correct_count: n,
      total_count: unique.length,
      raw_score: n,
      max_score: unique.length,
      percentage: (n / unique.length) * 100,
    },
  };
}
export function diagnose(state: State, a: Attempt): PointResult[] {
  return state.course.knowledge_points.map((kp) => {
    const qs = [
      ...new Map(
        a.questions
          .filter((q) => q.knowledge_point_ids.includes(kp.knowledge_point_id))
          .map((q) => [q.question_id, q]),
      ).values(),
    ];
    const correct = qs.filter(
      (q) =>
        a.result!.graded_answers.find((g) => g.question_id === q.question_id)
          ?.is_correct,
    ).length;
    const rate = qs.length ? correct / qs.length : null;
    return {
      knowledge_point_id: kp.knowledge_point_id,
      name: kp.name,
      correct_count: correct,
      question_count: qs.length,
      correct_rate: rate,
      mastery_score: qs.length >= 3 ? rate : null,
      mastery_status:
        qs.length < 3
          ? 'insufficient_evidence'
          : rate! < 0.6
            ? 'weak'
            : rate! < 0.8
              ? 'consolidating'
              : 'mastered',
      coverage_reason:
        qs.length === 0
          ? 'not_tested'
          : qs.length < 3
            ? 'too_few_questions'
            : null,
      wrong_question_ids: qs
        .filter(
          (q) =>
            !a.result!.graded_answers.find(
              (g) => g.question_id === q.question_id,
            )?.is_correct,
        )
        .map((q) => q.question_id),
      explanation:
        qs.length < 3
          ? '本次覆盖题量不足，暂不判断掌握程度。'
          : `本次 ${qs.length} 道有效题答对 ${correct} 道，请结合错题核对操作过程。`,
      evidence_ids: [],
    };
  });
}
export function compare(
  state: State,
  a: Attempt,
  points: PointResult[],
): Comparison | null {
  if (!a.baseline_attempt_id) return null;
  const base = state.attempts[a.baseline_attempt_id]?.value;
  if (
    !base?.result ||
    base.user_id !== a.user_id ||
    base.course_id !== a.course_id
  )
    return null;
  const prev = diagnose(state, base);
  const versionOk = base.result.rule_version === a.result!.rule_version;
  const knowledge_points = points.map((p) => {
    const old = prev.find(
      (k) => k.knowledge_point_id === p.knowledge_point_id,
    )!;
    const comparable =
      versionOk && old.question_count >= 3 && p.question_count >= 3;
    return {
      knowledge_point_id: p.knowledge_point_id,
      name: p.name,
      comparable,
      reason: comparable ? null : '两次覆盖题量不足或规则版本不一致',
      baseline_correct_rate: old.correct_rate,
      current_correct_rate: p.correct_rate,
      baseline_question_count: old.question_count,
      current_question_count: p.question_count,
      delta_percentage_points: comparable
        ? (p.correct_rate! - old.correct_rate!) * 100
        : null,
      difficulty_note:
        '原创演示题均为基础难度；不同题目仍可能存在难度差异，变化不代表教学因果效果。',
    };
  });
  const overall_comparable =
    versionOk &&
    knowledge_points.every((p) => p.comparable) &&
    base.questions.length === a.questions.length;
  return {
    baseline_attempt_id: base.attempt_id,
    current_attempt_id: a.attempt_id,
    baseline_rule_version: base.result.rule_version,
    current_rule_version: a.result!.rule_version,
    overall_comparable,
    overall_reason: overall_comparable
      ? null
      : '覆盖范围、题量或规则不满足整卷比较条件',
    overall_delta_percentage_points: overall_comparable
      ? a.result!.score.percentage - base.result.score.percentage
      : null,
    knowledge_points,
  };
}
export function buildReport(state: State, a: Attempt, rid: string): Report {
  const points = diagnose(state, a);
  const evidences: Report['evidences'] = [];
  const recommendations: Report['recommendations'] = [];
  for (const p of points) {
    if (p.mastery_status === 'insufficient_evidence') continue;
    const resources = Object.values(state.resources)
      .filter(
        (r) =>
          r.active &&
          r.availability === 'available' &&
          r.knowledge_point_ids.includes(p.knowledge_point_id),
      )
      .slice(0, 2);
    const r = resources[0];
    if (r?.text_content && r.document_id) {
      const eid = `ev-${rid}-${p.knowledge_point_id}`;
      evidences.push({
        evidence_id: eid,
        resource_id: r.resource_id,
        document_id: r.document_id,
        chunk_id: `chunk-${r.document_id}-1`,
        document_title: r.title,
        knowledge_point_ids: r.knowledge_point_ids,
        text: r.text_content.slice(r.text_content.indexOf('\n\n') + 2, 240),
        location: r.location || {
          page_start: null,
          page_end: null,
          section: null,
        },
        source_label: r.source_label,
        resource_version: r.resource_version,
        availability: 'available',
      });
      p.evidence_ids = [eid];
    }
    if (p.mastery_status === 'mastered') continue;
    const practice = Object.values(state.questions)
      .filter(
        (q) =>
          q.active &&
          q.knowledge_point_ids.includes(p.knowledge_point_id) &&
          /-0[78]$/.test(q.question_id),
      )
      .slice(0, 2);
    recommendations.push({
      recommendation_id: `rec-${rid}-${p.knowledge_point_id}`,
      knowledge_point_id: p.knowledge_point_id,
      priority: recommendations.length + 1,
      reason: `本次该知识点答对 ${p.correct_count}/${p.question_count}，建议先复习定义，再独立完成练习。`,
      next_step: `阅读 ${p.name} 资料，记录一处易错边界，再尝试练习。`,
      estimated_minutes: 15,
      evidence_ids: [...p.evidence_ids],
      resources: structuredClone(resources),
      practice_questions: practice.map((q) => ({
        question_id: q.question_id,
        title: q.stem,
        type: q.type,
      })),
    });
  }
  return {
    report_id: rid,
    attempt_id: a.attempt_id,
    user_id: a.user_id,
    course_id: a.course_id,
    generated_at: a.submitted_at!,
    report_version: 'mock-report-v1',
    rule_version: 'mock-rule-v1',
    data_version: 'mock-data-v1',
    source_mode: 'mock',
    explanation_mode: 'rule_template',
    is_degraded: false,
    degraded_reasons: [],
    retrieval_status: evidences.length ? 'available' : 'not_requested',
    score: structuredClone(a.result!.score),
    summary:
      '本报告为本地模拟规则结果。结合题量阅读知识点状态，再按建议完成复习与复测；不代表对整体学习能力的判断。',
    knowledge_points: points,
    evidences,
    recommendations,
    comparison: compare(state, a, points),
    agent_steps: [],
    actions: {
      can_retest: true,
      can_practice: recommendations.some(
        (r) => r.practice_questions.length > 0,
      ),
    },
  };
}
export function scenarioReport(state: State, original: Report): Report {
  const r = structuredClone(original);
  if (state.scenario === 'retrieval-empty') {
    r.retrieval_status = 'empty';
    r.evidences = [];
    r.knowledge_points.forEach((p) => (p.evidence_ids = []));
    r.recommendations.forEach((p) => (p.evidence_ids = []));
  }
  if (state.scenario === 'model-fallback') {
    r.is_degraded = true;
    r.degraded_reasons = ['模拟模型不可用，使用规则模板解释'];
  }
  if (state.scenario === 'empty-recommendations') {
    r.recommendations = [];
    r.actions.can_practice = false;
  }
  if (state.scenario === 'resource-removed') {
    r.evidences.forEach((e) => (e.availability = 'removed'));
    r.recommendations.forEach((p) =>
      p.resources.forEach((x) => {
        x.availability = 'removed';
        x.active = false;
      }),
    );
  }
  if (state.scenario === 'long-content') {
    r.summary += ' 请逐步检查过程，核对题量与来源。'.repeat(70);
    r.recommendations.forEach(
      (x) => (x.reason += ' 阅读时写出操作前后状态并检查边界。'.repeat(20)),
    );
  }
  return r;
}
