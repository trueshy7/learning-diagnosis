import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  attemptSchema,
  loginSchema,
  questionsSchema,
} from '../../src/group/services/contracts';
import { saveSession } from '../../src/group/services/session';
import {
  draftKey,
  restoreDraft,
  writeDraft,
} from '../../src/group/services/draft';
import { api, errorText } from '../../src/group/services/api';
const user = {
  access_token: 'test-token',
  token_type: 'bearer' as const,
  user: { id: 'student-1', username: 'student', role: 'student' as const },
};
const questions = [
  {
    id: 'q1',
    kind: 'single' as const,
    stem: '测试题',
    options: [
      { id: 'A', text: '甲' },
      { id: 'B', text: '乙' },
    ],
    knowledge_point_ids: ['kp-stack'],
  },
];
beforeEach(() => {
  sessionStorage.clear();
  saveSession(user);
  vi.unstubAllGlobals();
});
describe('组仓库协议', () => {
  it('接受仓库小写 bearer 和用户字段；拒绝残缺会话', () => {
    expect(loginSchema.safeParse(user).success).toBe(true);
    expect(
      loginSchema.safeParse({ ...user, user: { id: 'student-1' } }).success,
    ).toBe(false);
  });
  it('拒绝学生题目包含标准答案', () => {
    expect(questionsSchema.safeParse({ questions }).success).toBe(true);
    expect(
      questionsSchema.safeParse({
        questions: [{ ...questions[0], correct_option_ids: ['A'] }],
      }).success,
    ).toBe(false);
  });
  it('成绩保留且无诊断时允许显示；舍入正常；矛盾成绩被拒绝', () => {
    const attempt = {
      id: 'att-1',
      course_id: 'course-ds',
      score: 1,
      max_score: 6,
      percentage: 16.67,
      created_at: 1800000000,
      baseline_attempt_id: null,
      status: 'completed',
      report: null,
      ai_status: 'unavailable',
      ai_message: null,
    };
    expect(attemptSchema.safeParse(attempt).success).toBe(true);
    expect(
      attemptSchema.safeParse({ ...attempt, percentage: 25 }).success,
    ).toBe(false);
    expect(
      attemptSchema.safeParse({ ...attempt, ai_status: 'completed' }).success,
    ).toBe(false);
  });
  it('跨刷新恢复相同提交键和答案；试卷变更不沿用旧草稿', () => {
    const key = draftKey('course-ds');
    const draft = {
      key: crypto.randomUUID(),
      questions: questions.map((q) => JSON.stringify(q)),
      selected: { q1: 'A' },
      pending: {
        course_id: 'course-ds',
        answers: [{ question_id: 'q1', selected_option_ids: ['A'] }],
      },
    };
    writeDraft(key, draft);
    expect(restoreDraft(key, 'course-ds', undefined, questions)).toEqual(draft);
    expect(
      restoreDraft(key, 'course-ds', undefined, [
        { ...questions[0]!, stem: '新题' },
      ]),
    ).toBeNull();
    saveSession(null);
    expect(sessionStorage.getItem(key)).toBeNull();
  });
  it('拒绝本地提交意图与选项不一致', () => {
    const key = draftKey('course-ds');
    writeDraft(key, {
      key: crypto.randomUUID(),
      questions: questions.map((q) => JSON.stringify(q)),
      selected: { q1: 'A' },
      pending: {
        course_id: 'course-ds',
        answers: [{ question_id: 'q1', selected_option_ids: ['B'] }],
      },
    });
    expect(restoreDraft(key, 'course-ds', undefined, questions)).toBeNull();
  });
  it('数值 envelope 可登录；失败消息不透出服务秘密路径', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 0,
            message: 'ok',
            data: user,
            request_id: 'req1',
          }),
          { status: 200 },
        ),
      ),
    );
    expect(await api.login('student', 'secret')).toEqual(user);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 500,
            message: '/secret/key.sql',
            data: null,
            request_id: 'req2',
          }),
          { status: 500 },
        ),
      ),
    );
    try {
      await api.courses();
      throw new Error('应失败');
    } catch (error) {
      expect(errorText(error)).not.toContain('/secret');
    }
  });
});
