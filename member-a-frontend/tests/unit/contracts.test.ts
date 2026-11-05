import { describe, it, expect } from 'vitest';
import { createSeed } from '../../src/mocks/repository';
import {
  reportSchema,
  studentQuestionSchema,
  questionWriteSchema,
  taskSchema,
} from '../../src/api/contracts';
import { publicQuestion } from '../../src/mocks/services/engine';
import { questionToWrite } from '../../src/api/mappers/teacher';
import { ApiError, parseEnvelope } from '../../src/api/client';
import { z } from 'zod';
describe('网络契约与不变量', () => {
  it.each([
    'unknown-status',
    'negative-count',
    'invalid-ratio',
    'contradictory-mastery',
    'dangling-evidence',
    'wrong-comparison',
  ])('拒绝非法报告 %s', (kind) => {
    const r = createSeed().reports['report-a-002'];
    if (kind === 'unknown-status')
      Object.assign(r.knowledge_points[0], { mastery_status: 'alien' });
    if (kind === 'negative-count') r.knowledge_points[0].question_count = -1;
    if (kind === 'invalid-ratio') r.knowledge_points[0].correct_rate = 2;
    if (kind === 'contradictory-mastery')
      Object.assign(r.knowledge_points[0], {
        mastery_status: 'insufficient_evidence',
        mastery_score: 1,
      });
    if (kind === 'dangling-evidence')
      r.knowledge_points[0].evidence_ids = ['missing'];
    if (kind === 'wrong-comparison') r.comparison!.current_attempt_id = 'other';
    expect(reportSchema.safeParse(r).success).toBe(false);
  });
  it('学生 DTO 拒绝答案及解析，教师 DTO 与学生分离', () => {
    const q = Object.values(createSeed().questions)[0];
    expect(studentQuestionSchema.safeParse(q).success).toBe(false);
    expect(studentQuestionSchema.parse(publicQuestion(q))).not.toHaveProperty(
      'correct_option_ids',
    );
    expect(
      studentQuestionSchema.safeParse({
        ...publicQuestion(q),
        explanation: 'leak',
      }).success,
    ).toBe(false);
  });
  it.each([
    'single-many',
    'multi-one',
    'foreign-answer',
    'no-kp',
    'blank-option',
  ])('题目表单拒绝 %s', (type) => {
    const q = questionToWrite(Object.values(createSeed().questions)[0]);
    if (type === 'single-many')
      q.correct_option_keys = q.options.slice(0, 2).map((o) => o.client_key);
    if (type === 'multi-one') q.type = 'multiple_choice';
    if (type === 'foreign-answer') q.correct_option_keys = ['not-an-option'];
    if (type === 'no-kp') q.knowledge_point_ids = [];
    if (type === 'blank-option') q.options[0].text = ' ';
    expect(questionWriteSchema.safeParse(q).success).toBe(false);
  });
  it('完成的诊断任务必须绑定报告', () => {
    const task = createSeed().tasks['task-a-001'];
    task.report_id = null;
    expect(taskSchema.safeParse(task).success).toBe(false);
  });
  it('解包成功与业务错误，即使 HTTP 200 也拒绝业务失败', () => {
    expect(
      parseEnvelope(
        { code: 'OK', message: '', data: { id: 'a' }, request_id: 'server-id' },
        z.object({ id: z.string() }),
      ),
    ).toEqual({ id: 'a' });
    expect(() =>
      parseEnvelope(
        {
          code: 'BUSINESS_FAILED',
          message: '失败',
          data: null,
          request_id: 'trace',
        },
        z.null(),
      ),
    ).toThrow('失败');
  });
  it('映射 HTTP/422、缺失 request_id 与非法 envelope', () => {
    try {
      parseEnvelope(
        { code: 'FORBIDDEN', message: '无权限', data: null },
        z.null(),
        403,
        'local:test',
      );
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).requestId).toBe('local:test');
      expect((e as ApiError).httpStatus).toBe(403);
    }
    expect(() =>
      parseEnvelope(
        { detail: [{ loc: ['body', 'title'], msg: '必填' }] },
        z.null(),
        422,
      ),
    ).toThrow('输入字段校验失败');
    expect(() => parseEnvelope('<html>fallback</html>', z.null())).toThrow(
      '接口响应格式异常',
    );
  });
});
