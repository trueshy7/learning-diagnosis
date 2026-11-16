import type { Answer, Attempt, Course, Envelope, LoginResult, Question, Report, SubmitAttempt, User } from '../types/api'

const courses: Course[] = [{ id: 'course-ds', name: '数据结构', description: '栈、队列与二叉树的入门测验。初始数据仅供验证交互流程。' }]
const questions: Question[] = [
  { id: 'q-stack-1', stem: '栈的基本访问规则是什么？', options: [{ id: 'A', text: '后进先出' }, { id: 'B', text: '先进先出' }], knowledge_point_ids: ['kp-stack'], kind: 'single' },
  { id: 'q-queue-1', stem: '队列通常遵循什么访问规则？', options: [{ id: 'A', text: '后进先出' }, { id: 'B', text: '先进先出' }], knowledge_point_ids: ['kp-queue'], kind: 'single' },
  { id: 'q-tree-1', stem: '二叉树中，一个结点最多有几个孩子？', options: [{ id: 'A', text: '两个' }, { id: 'B', text: '三个' }], knowledge_point_ids: ['kp-tree'], kind: 'single' },
]
// 样例答案只在离线 mock 中使用；真实模式的题目接口不下发答案。
const answerKeys: Record<string, string> = { 'q-stack-1': 'A', 'q-queue-1': 'B', 'q-tree-1': 'A' }
const knowledge = [{ id: 'kp-stack', name: '栈' }, { id: 'kp-queue', name: '队列' }, { id: 'kp-tree', name: '二叉树' }]
const storageKey = (user: User) => `learning-demo-attempts-v1:${user.id}`
function readAttempts(user: User): Attempt[] {
  try { return JSON.parse(localStorage.getItem(storageKey(user)) ?? '[]') as Attempt[] }
  catch { return [] }
}
export class MockRequestError extends Error {
  readonly requestId = `mock-${crypto.randomUUID()}`
  constructor(message: string, public readonly status: number) { super(message) }
}
function fail(message: string, status = 422): never { throw new MockRequestError(message, status) }
interface IdempotencyRecord { fingerprint: string; attemptId: string }
function readIdempotency(user: User): Record<string, IdempotencyRecord> {
  try { return JSON.parse(localStorage.getItem(`${storageKey(user)}:idempotency`) ?? '{}') as Record<string, IdempotencyRecord> }
  catch { return {} }
}
function makeReport(id: string, answers: Answer[], baseline?: Attempt): Report {
  const results = knowledge.map(kp => {
    const relevant = questions.filter(q => q.knowledge_point_ids.includes(kp.id))
    const count = relevant.filter(q => answers.find(a => a.question_id === q.id)?.selected_option_ids.join(',') === answerKeys[q.id]).length
    return { knowledge_point_id: kp.id, name: kp.name, correct_count: count, sample_count: relevant.length, accuracy: count / relevant.length, status: 'insufficient_evidence' as const }
  })
  return {
    attempt_id: id, mode: 'rule_template_demo', knowledge_points: results,
    evidence: [{ evidence_id: 'demo-e1', document_id: 'demo-doc-ds', resource_id: 'demo-res-stack', chunk_id: 'demo-chunk-1', knowledge_point_ids: ['kp-stack'], text: '栈是一种后进先出（LIFO）的线性表，插入与删除都在栈顶进行。', score: 1, location: '本地样例第 1 节', source: '随项目提供的演示材料', title: '数据结构基础样例' }],
    recommendations: results.filter(kp => kp.correct_count < kp.sample_count).map(kp => ({ knowledge_point_id: kp.knowledge_point_id, resource_id: `demo-res-${kp.knowledge_point_id}`, title: `${kp.name}基础复习（样例）`, reason: '本次该知识点存在答错情况，请先阅读基础概念并完成更多练习。' })),
    explanation: '本报告由浏览器中的固定规则与样例材料生成，未调用检索服务或大模型。每个知识点只有一道题，证据不足，不能据此认定已掌握或薄弱。真实诊断与推荐由 B 对接 C、D 后返回。',
    comparison: baseline ? results.map(kp => { const before = baseline.report?.knowledge_points.find(x => x.knowledge_point_id === kp.knowledge_point_id)?.accuracy ?? null; return { knowledge_point_id: kp.knowledge_point_id, before_accuracy: before, after_accuracy: kp.accuracy, delta: before === null ? null : kp.accuracy - before } }) : [],
    trace: [{ agent: '本地固定规则', status: '已完成样例计算' }, { agent: '检索与多智能体服务', status: '本地模式未调用' }], fallback_status: 'local_mock_only',
  }
}
export async function mockRequest<T>(path: string, method: string, body: unknown, session: LoginResult | null, headers: Record<string, string> = {}): Promise<Envelope<T>> {
  const request_id = `mock-${crypto.randomUUID()}`
  let data: unknown
  if (path === '/auth/login' && method === 'POST') {
    const credentials = body as { username: string; password: string }
    if (!['student', 'teacher'].includes(credentials.username) || credentials.password !== 'demo12345') fail('账号或密码错误。样例账号：student / teacher，密码：demo12345。', 401)
    const role = credentials.username === 'teacher' ? 'teacher' : 'student'
    data = { access_token: `local-demo-${role}`, token_type: 'bearer', user: { id: `demo-${role}`, username: credentials.username, role } }
  } else {
    if (!session) fail('请先登录。', 401)
    const user = session.user
    if (path === '/courses') data = courses
    else if (path === '/courses/course-ds/questions') data = { questions }
    else if (path === '/attempts' && method === 'GET') data = readAttempts(user)
    else if (path === '/attempts' && method === 'POST') {
      const submission = body as SubmitAttempt
      if (submission.course_id !== 'course-ds') fail('课程不存在。', 404)
      if (submission.answers.length !== questions.length || questions.some(q => !submission.answers.some(a => a.question_id === q.id && a.selected_option_ids.length === 1 && q.options.some(o => o.id === a.selected_option_ids[0])))) fail('请完成所有题目，并确保每题只选择一个有效选项。')
      const old = readAttempts(user)
      const baseline = submission.baseline_attempt_id ? old.find(a => a.id === submission.baseline_attempt_id && a.course_id === submission.course_id) : undefined
      if (submission.baseline_attempt_id && !baseline) fail('复测基线不存在，或不属于当前课程和账号。')
      const key = headers['Idempotency-Key']
      const fingerprint = JSON.stringify(submission)
      const keys = readIdempotency(user)
      if (key && keys[key]) {
        if (keys[key].fingerprint !== fingerprint) fail('同一幂等键不能用于不同答案。', 409)
        const existing = old.find(item => item.id === keys[key]!.attemptId)
        if (existing) return { code: 0, message: 'ok', data: existing as T, request_id }
      }
      const id = `local-${crypto.randomUUID()}`
      const report = makeReport(id, submission.answers, baseline)
      const score = report.knowledge_points.reduce((sum, kp) => sum + kp.correct_count, 0)
      const attempt: Attempt = { id, course_id: submission.course_id, created_at: Math.floor(Date.now() / 1000), baseline_attempt_id: submission.baseline_attempt_id ?? null, score, max_score: questions.length, percentage: Number((score / questions.length * 100).toFixed(1)), status: 'completed', report, ai_status: 'completed', ai_message: '本地样例固定规则演示。' }
      localStorage.setItem(storageKey(user), JSON.stringify([attempt, ...old]))
      if (key) { keys[key] = { fingerprint, attemptId: id }; localStorage.setItem(`${storageKey(user)}:idempotency`, JSON.stringify(keys)) }
      data = attempt
    } else if (path.startsWith('/attempts/')) {
      data = readAttempts(user).find(a => a.id === decodeURIComponent(path.slice('/attempts/'.length)))
      if (!data) fail('未找到该次测验，请从历史记录重新进入。', 404)
    } else if (path === '/teacher/overview') {
      if (user.role !== 'teacher') fail('此页面仅供教师账号使用。', 403)
      data = { user_count: 2, question_count: questions.length, attempt_count: readAttempts(user).length, resource_count: 1 }
    } else fail('本地样例暂未实现此接口。', 404)
  }
  return { code: 0, message: 'ok', data: data as T, request_id }
}
