import { z } from 'zod';

const id = z.string().min(1);
const count = z.number().int().nonnegative();
const ratio = z.number().min(0).max(1);
const time = z.iso.datetime();
const title = z.string().trim().min(1, '请输入名称').max(100);
const description = z.string().max(3000);
export const roleSchema = z.enum(['student', 'teacher']);
export const difficultySchema = z.enum(['easy', 'medium', 'hard']);
export const taskStatusSchema = z.enum([
  'queued',
  'running',
  'completed',
  'failed',
]);
export const userSchema = z.object({
  user_id: id,
  username: id,
  display_name: id,
  role: roleSchema,
});
export const loginSchema = z.object({
  access_token: id,
  token_type: z.literal('Bearer'),
  expires_at: time,
  user: userSchema,
});
export const knowledgeSchema = z.object({
  knowledge_point_id: id,
  course_id: id,
  name: title,
  description,
  sort_order: count,
  active: z.boolean(),
});
export const courseSchema = z.object({
  course_id: id,
  title,
  description,
  knowledge_points: z.array(knowledgeSchema),
  latest_attempt_id: id.nullable(),
  active_attempt_id: id.nullable(),
  latest_report_id: id.nullable(),
});
export const optionSchema = z.object({
  option_id: id,
  label: id,
  text: z.string().min(1).max(500),
});
export const studentQuestionSchema = z
  .object({
    question_id: id,
    type: z.enum(['single_choice', 'multiple_choice']),
    stem: z.string().min(1).max(2000),
    options: z.array(optionSchema).min(2).max(6),
    knowledge_point_ids: z.array(id).min(1),
    difficulty: difficultySchema,
  })
  .strict()
  .superRefine((q, ctx) => {
    if (
      new Set(q.options.map((o) => o.option_id)).size !== q.options.length ||
      new Set(q.knowledge_point_ids).size !== q.knowledge_point_ids.length
    )
      ctx.addIssue({ code: 'custom', message: '题目包含重复选项或知识点标识' });
  });
export const answerSchema = z.object({
  question_id: id,
  selected_option_ids: z.array(id),
});
export const scoreSchema = z
  .object({
    correct_count: count,
    total_count: count.positive(),
    raw_score: z.number().nonnegative(),
    max_score: z.number().positive(),
    percentage: z.number().min(0).max(100),
  })
  .refine(
    (s) =>
      s.correct_count <= s.total_count &&
      s.raw_score <= s.max_score &&
      s.raw_score === s.correct_count &&
      s.max_score === s.total_count &&
      Math.abs(s.percentage - (s.correct_count / s.total_count) * 100) <=
        0.00500001,
    '成绩字段相互矛盾',
  );
export const resultSchema = z
  .object({
    attempt_id: id,
    score: scoreSchema,
    graded_answers: z.array(answerSchema.extend({ is_correct: z.boolean() })),
    rule_version: id,
  })
  .refine(
    (r) =>
      r.graded_answers.length === r.score.total_count &&
      new Set(r.graded_answers.map((a) => a.question_id)).size ===
        r.graded_answers.length &&
      r.graded_answers.filter((a) => a.is_correct).length ===
        r.score.correct_count,
    '判分明细与总成绩不一致',
  );
export const attemptSchema = z
  .object({
    attempt_id: id,
    user_id: id,
    course_id: id,
    kind: z.enum(['initial', 'practice', 'retest']),
    baseline_attempt_id: id.nullable(),
    source_report_id: id.nullable(),
    status: z.enum(['in_progress', 'submitted']),
    snapshot_version: id,
    created_at: time,
    submitted_at: time.nullable(),
    questions: z.array(studentQuestionSchema).min(1),
    result: resultSchema.nullable(),
    diagnosis_task_id: id.nullable(),
    report_id: id.nullable(),
  })
  .superRefine((a, ctx) => {
    if (
      a.status === 'in_progress' &&
      (a.result || a.submitted_at || a.diagnosis_task_id || a.report_id)
    )
      ctx.addIssue({ code: 'custom', message: '未提交测验不应已有成绩或报告' });
    if (a.kind === 'retest' && (!a.baseline_attempt_id || !a.source_report_id))
      ctx.addIssue({ code: 'custom', message: '复测缺少基准关联' });
    if (
      a.result &&
      a.result.graded_answers.some(
        (g) =>
          !a.questions.some(
            (q) =>
              q.question_id === g.question_id &&
              g.selected_option_ids.every((id) =>
                q.options.some((o) => o.option_id === id),
              ),
          ),
      )
    )
      ctx.addIssue({ code: 'custom', message: '判分明细不属于当前试卷快照' });
    if (
      a.result &&
      (a.result.attempt_id !== a.attempt_id ||
        a.result.score.total_count !== a.questions.length)
    )
      ctx.addIssue({ code: 'custom', message: '测验与成绩不一致' });
    if (
      a.status === 'submitted' &&
      (!a.result || !a.submitted_at || !a.diagnosis_task_id)
    )
      ctx.addIssue({ code: 'custom', message: '已提交测验缺少成绩或任务' });
    if (
      new Set(a.questions.map((q) => q.question_id)).size !== a.questions.length
    )
      ctx.addIssue({ code: 'custom', message: '试卷含重复题' });
  });
export const submitResponseSchema = z
  .object({
    attempt_id: id,
    submitted_at: time,
    result: resultSchema,
    diagnosis_task_id: id,
  })
  .refine(
    (r) => r.attempt_id === r.result.attempt_id,
    '提交结果测验标识不一致',
  );
export const taskSchema = z
  .object({
    task_id: id,
    kind: z.enum(['diagnosis', 'document_ingestion']),
    status: taskStatusSchema,
    attempt_id: id.nullable(),
    document_id: id.nullable(),
    report_id: id.nullable(),
    progress: ratio.nullable(),
    current_step: z.string().nullable(),
    error_code: z.string().nullable(),
    error_message: z.string().nullable(),
    can_retry: z.boolean(),
    retry_count: count,
    created_at: time,
    updated_at: time,
  })
  .refine(
    (t) =>
      !(t.kind === 'diagnosis' && t.status === 'completed' && !t.report_id),
    '完成的诊断任务缺少报告',
  );
export const pointResultSchema = z
  .object({
    knowledge_point_id: id,
    name: id,
    correct_count: count,
    question_count: count,
    correct_rate: ratio.nullable(),
    mastery_score: ratio.nullable(),
    mastery_status: z.enum([
      'weak',
      'consolidating',
      'mastered',
      'insufficient_evidence',
    ]),
    coverage_reason: z.enum(['not_tested', 'too_few_questions']).nullable(),
    wrong_question_ids: z.array(id),
    explanation: z.string(),
    evidence_ids: z.array(id),
  })
  .superRefine((p, ctx) => {
    if (
      new Set(p.wrong_question_ids).size !== p.wrong_question_ids.length ||
      p.wrong_question_ids.length !== p.question_count - p.correct_count ||
      (p.question_count > 0 &&
        (p.correct_rate === null ||
          Math.abs(p.correct_rate - p.correct_count / p.question_count) >
            0.0001)) ||
      (p.question_count === 0 &&
        (p.mastery_status !== 'insufficient_evidence' ||
          p.coverage_reason !== 'not_tested')) ||
      (p.mastery_score !== null &&
        p.correct_rate !== null &&
        Math.abs(p.mastery_score - p.correct_rate) > 0.0001)
    )
      ctx.addIssue({ code: 'custom', message: '知识点统计与题量不一致' });
    if (
      p.correct_count > p.question_count ||
      (p.question_count === 0 &&
        (p.correct_rate !== null || p.mastery_score !== null)) ||
      (p.mastery_status === 'insufficient_evidence' &&
        (p.mastery_score !== null || !p.coverage_reason)) ||
      (p.mastery_status !== 'insufficient_evidence' &&
        (p.mastery_score === null ||
          p.correct_rate === null ||
          p.coverage_reason !== null))
    )
      ctx.addIssue({ code: 'custom', message: '知识点数据与覆盖状态矛盾' });
  });
const locationSchema = z.object({
  page_start: count.nullable(),
  page_end: count.nullable(),
  section: z.string().nullable(),
});
export const evidenceSchema = z.object({
  evidence_id: id,
  resource_id: id,
  document_id: id,
  chunk_id: id,
  document_title: id,
  knowledge_point_ids: z.array(id),
  text: z.string(),
  location: locationSchema,
  source_label: id,
  resource_version: id,
  availability: z.enum(['available', 'removed', 'unknown']),
});
export const resourceSummarySchema = z.object({
  resource_id: id,
  course_id: id,
  title,
  kind: z.enum(['note', 'document', 'external']),
  knowledge_point_ids: z.array(id),
  difficulty: difficultySchema,
  active: z.boolean(),
  availability: z.enum(['available', 'processing', 'failed', 'removed']),
  source_label: id,
});
export const resourceSchema = resourceSummarySchema.extend({
  description,
  document_id: id.nullable(),
  resource_version: id,
  text_content: z.string().nullable(),
  external_url: z.string().nullable(),
  file_available: z.boolean(),
  filename: z.string().min(1).nullable().optional(),
  location: locationSchema.nullable(),
});
export const recommendationSchema = z.object({
  recommendation_id: id,
  knowledge_point_id: id,
  priority: count,
  reason: z.string(),
  next_step: z.string(),
  estimated_minutes: count.nullable(),
  evidence_ids: z.array(id),
  resources: z.array(resourceSummarySchema),
  practice_questions: z.array(
    z.object({
      question_id: id,
      title: id,
      type: z.enum(['single_choice', 'multiple_choice']),
    }),
  ),
});
export const comparisonPointSchema = z
  .object({
    knowledge_point_id: id,
    name: id,
    comparable: z.boolean(),
    reason: z.string().nullable(),
    baseline_correct_rate: ratio.nullable(),
    current_correct_rate: ratio.nullable(),
    baseline_question_count: count,
    current_question_count: count,
    delta_percentage_points: z.number().min(-100).max(100).nullable(),
    difficulty_note: z.string(),
  })
  .refine(
    (p) =>
      p.comparable
        ? p.delta_percentage_points !== null &&
          p.baseline_correct_rate !== null &&
          p.current_correct_rate !== null
        : p.delta_percentage_points === null && !!p.reason,
    '比较值与可比状态矛盾',
  )
  .refine(
    (p) =>
      !p.comparable ||
      (p.baseline_question_count > 0 &&
        p.current_question_count > 0 &&
        Math.abs(
          p.delta_percentage_points! -
            (p.current_correct_rate! - p.baseline_correct_rate!) * 100,
        ) <= 0.02),
    '百分点变化与正确率不一致',
  );
export const comparisonSchema = z
  .object({
    baseline_attempt_id: id,
    current_attempt_id: id,
    baseline_rule_version: id,
    current_rule_version: id,
    overall_comparable: z.boolean(),
    overall_reason: z.string().nullable(),
    overall_delta_percentage_points: z.number().min(-100).max(100).nullable(),
    knowledge_points: z.array(comparisonPointSchema),
  })
  .refine(
    (c) =>
      c.overall_comparable
        ? c.overall_delta_percentage_points !== null
        : c.overall_delta_percentage_points === null && !!c.overall_reason,
    '总分对比状态矛盾',
  );
export const reportSchema = z
  .object({
    report_id: id,
    attempt_id: id,
    user_id: id,
    course_id: id,
    generated_at: time,
    report_version: id,
    rule_version: id,
    data_version: id,
    source_mode: z.enum(['mock', 'backend']),
    explanation_mode: z.enum(['llm', 'rule_template', 'cached']),
    cached_from: z
      .object({ report_id: id, report_version: id, generated_at: time })
      .nullable()
      .optional(),
    is_degraded: z.boolean(),
    degraded_reasons: z.array(z.string()),
    retrieval_status: z.enum(['available', 'empty', 'failed', 'not_requested']),
    score: scoreSchema,
    summary: z.string(),
    knowledge_points: z.array(pointResultSchema),
    evidences: z.array(evidenceSchema),
    recommendations: z.array(recommendationSchema),
    comparison: comparisonSchema.nullable(),
    agent_steps: z.array(
      z.object({
        step: z.enum(['diagnosis', 'retrieval', 'recommendation']),
        status: z.enum(['completed', 'skipped', 'failed']),
        summary: z.string(),
        duration_ms: count.nullable(),
      }),
    ),
    actions: z.object({ can_retest: z.boolean(), can_practice: z.boolean() }),
  })
  .superRefine((r, ctx) => {
    const ids = new Set(r.evidences.map((e) => e.evidence_id));
    const points = new Set(r.knowledge_points.map((p) => p.knowledge_point_id));
    if (
      ids.size !== r.evidences.length ||
      points.size !== r.knowledge_points.length
    )
      ctx.addIssue({ code: 'custom', message: '报告中含重复知识点或证据标识' });
    if (r.explanation_mode === 'cached' && !r.cached_from)
      ctx.addIssue({ code: 'custom', message: '历史分析缺少原始报告信息' });
    if (
      r.knowledge_points.some((p) => p.evidence_ids.some((e) => !ids.has(e))) ||
      r.recommendations.some(
        (p) =>
          !points.has(p.knowledge_point_id) ||
          p.evidence_ids.some((e) => !ids.has(e)),
      )
    )
      ctx.addIssue({ code: 'custom', message: '报告含悬空引用或知识点' });
    if (r.comparison && r.comparison.current_attempt_id !== r.attempt_id)
      ctx.addIssue({ code: 'custom', message: '对比不属于当前测验' });
  });
export const historySchema = z.object({
  attempt_id: id,
  report_id: id.nullable(),
  kind: z.enum(['initial', 'practice', 'retest']),
  baseline_attempt_id: id.nullable(),
  submitted_at: time.nullable(),
  score: scoreSchema.nullable(),
  diagnosis_task_id: id.nullable(),
  diagnosis_status: taskStatusSchema.nullable(),
});
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z.object({
    items: z.array(item),
    total: count,
    page: count.positive(),
    page_size: count.positive().max(50),
  });
export const teacherQuestionSchema = studentQuestionSchema.safeExtend({
  course_id: id,
  correct_option_ids: z.array(id),
  explanation: description,
  active: z.boolean(),
  version: id,
});
export const courseWriteSchema = z.object({ title, description });
export const knowledgeWriteSchema = z.object({
  course_id: id,
  name: title,
  description,
  sort_order: count,
  active: z.boolean(),
});
export const questionWriteSchema = z
  .object({
    course_id: id,
    type: z.enum(['single_choice', 'multiple_choice']),
    stem: z.string().trim().min(1).max(2000),
    options: z
      .array(
        z.object({
          option_id: id.nullable(),
          client_key: id,
          label: id,
          text: z.string().trim().min(1).max(500),
        }),
      )
      .min(2)
      .max(6),
    correct_option_keys: z.array(id).min(1),
    knowledge_point_ids: z.array(id).min(1, '至少选择一个知识点'),
    difficulty: difficultySchema,
    explanation: description,
    active: z.boolean(),
  })
  .superRefine((q, ctx) => {
    const keys = new Set(q.options.map((o) => o.client_key));
    const existingIds = q.options
      .map((o) => o.option_id)
      .filter((id): id is string => id !== null);
    if (
      keys.size !== q.options.length ||
      new Set(existingIds).size !== existingIds.length ||
      new Set(q.correct_option_keys).size !== q.correct_option_keys.length ||
      q.correct_option_keys.some((k) => !keys.has(k)) ||
      (q.type === 'single_choice' && q.correct_option_keys.length !== 1) ||
      (q.type === 'multiple_choice' && q.correct_option_keys.length < 2)
    )
      ctx.addIssue({
        code: 'custom',
        path: ['correct_option_keys'],
        message: '单选需一个答案，多选至少两个；答案须对应当前选项',
      });
  });
export const resourceWriteSchema = z
  .object({
    course_id: id,
    title,
    description,
    kind: z.enum(['note', 'external', 'document']),
    knowledge_point_ids: z.array(id).min(1),
    difficulty: difficultySchema,
    active: z.boolean(),
    text_content: z.string().nullable(),
    external_url: z.string().nullable(),
  })
  .superRefine((r, ctx) => {
    if (r.kind === 'note' && !r.text_content?.trim())
      ctx.addIssue({
        code: 'custom',
        path: ['text_content'],
        message: '请输入正文',
      });
    if (r.kind === 'external') {
      try {
        const url = new URL(r.external_url ?? '');
        if (
          !['http:', 'https:'].includes(url.protocol) ||
          url.username ||
          url.password
        )
          throw new Error();
      } catch {
        ctx.addIssue({
          code: 'custom',
          path: ['external_url'],
          message: '链接仅允许不含用户名和密码的 http/https 地址',
        });
      }
    }
  });
export const documentSchema = z.object({
  document_id: id,
  resource_id: id,
  course_id: id,
  filename: id,
  size_bytes: count,
  content_type: id,
  version: id,
  task_id: id,
  status: taskStatusSchema,
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  created_at: time,
});
export const teacherResourceSchema = resourceSummarySchema.extend({
  document_id: id.nullable(),
  ingestion_task_id: id.nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
});
export const overviewSchema = z.object({
  course_id: id,
  student_count: count,
  submitted_attempt_count: count,
  average_percentage: z.number().min(0).max(100).nullable(),
  recent_attempts: z.array(historySchema),
});
export const teacherStudentSchema = z.object({
  user_id: id,
  display_name: id,
  submitted_attempt_count: count,
  latest_attempt_id: id.nullable(),
  latest_report_id: id.nullable(),
});

export type User = z.infer<typeof userSchema>;
export type Course = z.infer<typeof courseSchema>;
export type Knowledge = z.infer<typeof knowledgeSchema>;
export type StudentQuestion = z.infer<typeof studentQuestionSchema>;
export type TeacherQuestion = z.infer<typeof teacherQuestionSchema>;
export type Answer = z.infer<typeof answerSchema>;
export type Score = z.infer<typeof scoreSchema>;
export type Result = z.infer<typeof resultSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type Task = z.infer<typeof taskSchema>;
export type PointResult = z.infer<typeof pointResultSchema>;
export type Evidence = z.infer<typeof evidenceSchema>;
export type Resource = z.infer<typeof resourceSchema>;
export type Recommendation = z.infer<typeof recommendationSchema>;
export type Comparison = z.infer<typeof comparisonSchema>;
export type Report = z.infer<typeof reportSchema>;
export type History = z.infer<typeof historySchema>;
export type DocumentRecord = z.infer<typeof documentSchema>;
export type QuestionWrite = z.infer<typeof questionWriteSchema>;
export type ResourceWrite = z.infer<typeof resourceWriteSchema>;
export interface CreateAttempt {
  course_id: string;
  kind: Attempt['kind'];
  client_request_id: string;
  baseline_attempt_id?: string;
  source_report_id?: string;
  question_ids?: string[];
}
export interface SubmitAttempt {
  snapshot_version: string;
  answers: Answer[];
}
