import { z } from 'zod';
import { answerSchema } from './index';
const id = z.string().min(1);
export const loginRequestSchema = z
  .object({
    username: z.string().trim().min(1).max(100),
    password: z.string().min(1).max(200),
  })
  .strict();
export const createAttemptRequestSchema = z
  .object({
    course_id: id,
    kind: z.enum(['initial', 'practice', 'retest']),
    client_request_id: z.string().min(1).max(200),
    baseline_attempt_id: id.optional(),
    source_report_id: id.optional(),
    question_ids: z.array(id).min(1).max(200).optional(),
  })
  .strict()
  .superRefine((data, ctx) => {
    if (
      data.kind === 'initial' &&
      (data.baseline_attempt_id || data.source_report_id || data.question_ids)
    )
      ctx.addIssue({
        code: 'custom',
        message: '前测由服务选择试卷，不携带基准或指定题目',
      });
    if (
      data.kind === 'practice' &&
      (!data.source_report_id ||
        !data.question_ids?.length ||
        data.baseline_attempt_id)
    )
      ctx.addIssue({
        code: 'custom',
        message: '推荐练习需要来源报告和合法题目',
      });
    if (
      data.kind === 'retest' &&
      (!data.source_report_id || !data.baseline_attempt_id || data.question_ids)
    )
      ctx.addIssue({
        code: 'custom',
        message: '复测需指定来源报告和基准测验，由服务选题',
      });
  });
export const submitAttemptRequestSchema = z
  .object({ snapshot_version: id, answers: z.array(answerSchema) })
  .strict();
export const uploadMetadataSchema = z
  .object({
    course_id: id,
    title: z.string().trim().min(1).max(100),
    knowledge_point_ids: z.array(id).min(1),
  })
  .strict();
