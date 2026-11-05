import { z } from 'zod';
const id = z.string().min(1),
  count = z.number().int().nonnegative(),
  ratio = z.number().min(0).max(1);
export const userSchema = z.object({
  id,
  username: id,
  role: z.enum(['student', 'teacher']),
});
export const loginSchema = z.object({
  access_token: id,
  token_type: z.literal('bearer'),
  user: userSchema,
});
export const courseSchema = z.object({ id, name: id, description: z.string() });
export const questionSchema = z
  .object({
    id,
    stem: id,
    kind: z.literal('single'),
    knowledge_point_ids: z.array(id),
    options: z.array(z.object({ id, text: id })).min(2),
  })
  .strict()
  .refine((q) => new Set(q.options.map((o) => o.id)).size === q.options.length);
export const questionsSchema = z
  .object({ questions: z.array(questionSchema) })
  .refine(
    (q) =>
      new Set(q.questions.map((item) => item.id)).size === q.questions.length,
  );
const pointSchema = z
  .object({
    knowledge_point_id: id,
    name: id,
    correct_count: count,
    sample_count: count,
    accuracy: ratio.nullable(),
    status: z.enum([
      'insufficient_evidence',
      'weak',
      'needs_practice',
      'mastered',
    ]),
  })
  .refine(
    (p) =>
      p.correct_count <= p.sample_count &&
      (p.sample_count === 0
        ? p.accuracy === null
        : p.accuracy !== null &&
          Math.abs(p.accuracy - p.correct_count / p.sample_count) < 0.00001),
  );
const reportSchema = z.object({
  attempt_id: id,
  mode: z.literal('rule_template_demo'),
  knowledge_points: z.array(pointSchema),
  evidence: z.array(
    z.object({
      evidence_id: id,
      document_id: id,
      resource_id: id,
      chunk_id: id,
      knowledge_point_ids: z.array(id),
      text: z.string(),
      score: z.number(),
      location: z.union([z.string(), z.record(z.string(), z.unknown())]),
      source: z.string(),
      title: z.string(),
    }),
  ),
  recommendations: z.array(
    z.object({
      knowledge_point_id: id,
      resource_id: id,
      title: id,
      reason: z.string(),
    }),
  ),
  explanation: z.string(),
  comparison: z.array(
    z
      .object({
        knowledge_point_id: id,
        before_accuracy: ratio.nullable(),
        after_accuracy: ratio.nullable(),
        delta: z.number().min(-1).max(1).nullable(),
      })
      .refine(
        (p) =>
          p.delta === null ||
          (p.before_accuracy !== null &&
            p.after_accuracy !== null &&
            Math.abs(p.delta - (p.after_accuracy - p.before_accuracy)) <
              0.00001),
      ),
  ),
  trace: z.array(z.object({ agent: z.string(), status: z.string() })),
  fallback_status: z.string().nullable(),
});
export const attemptSchema = z
  .object({
    id,
    course_id: id,
    score: z.number().nonnegative(),
    max_score: z.number().positive(),
    percentage: z.number().min(0).max(100),
    created_at: z.number().int().nonnegative(),
    baseline_attempt_id: id.nullable(),
    status: z.literal('completed'),
    report: reportSchema.nullable(),
    ai_status: z.enum(['completed', 'unavailable', 'disabled', 'processing']),
    ai_message: z.string().nullable(),
  })
  .refine(
    (a) =>
      a.score <= a.max_score &&
      Math.abs(a.percentage - (a.score / a.max_score) * 100) <= 0.005001 &&
      (!a.report || a.report.attempt_id === a.id) &&
      (a.ai_status !== 'completed' || !!a.report),
  );
export const overviewSchema = z.object({
  user_count: count,
  question_count: count,
  attempt_count: count,
  resource_count: count,
});
export const ingestSchema = z.object({
  resource_id: id,
  document_id: id,
  course_id: id,
  title: id.max(200),
  text: id.max(200000),
  knowledge_point_ids: z.array(id).min(1),
  source: id,
});
export const ingestResultSchema = z.object({ chunks: count }).passthrough();
