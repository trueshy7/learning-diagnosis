import { openDB, type IDBPDatabase } from 'idb';
import type {
  Attempt,
  Course,
  DocumentRecord,
  Report,
  Resource,
  Task,
  TeacherQuestion,
  User,
} from '../api/contracts';
import { course, questions, resources, users } from './fixtures/catalog';
import { buildReport, grade, publicQuestion } from './services/engine';

export interface InternalAttempt {
  value: Attempt;
  snapshot: TeacherQuestion[];
  fingerprint?: string;
  submitKey?: string;
}
export interface State {
  mock_schema_version: number;
  course: Course;
  users: User[];
  questions: Record<string, TeacherQuestion>;
  resources: Record<string, Resource>;
  tokens: Record<string, { user_id: string; expires: number }>;
  attempts: Record<string, InternalAttempt>;
  tasks: Record<string, Task>;
  reports: Record<string, Report>;
  documents: Record<string, DocumentRecord>;
  files: Record<string, Blob>;
  creationKeys: Record<string, { attemptId: string; body: string }>;
  retryKeys: Record<string, boolean>;
  scenario: string;
  delayMs: number;
}
export function createSeed(): State {
  const state: State = {
    mock_schema_version: 1,
    course: structuredClone(course),
    users: structuredClone(users),
    questions: Object.fromEntries(
      questions.map((q) => [q.question_id, structuredClone(q)]),
    ),
    resources: Object.fromEntries(
      resources.map((r) => [r.resource_id, structuredClone(r)]),
    ),
    tokens: {},
    attempts: {},
    tasks: {},
    reports: {},
    documents: {},
    files: {},
    creationKeys: {},
    retryKeys: {},
    scenario: 'normal',
    delayMs: 0,
  };
  const cases: [string, number[], number[], string | null][] = [
    ['a-001', [1, 2, 3], [1, 2, 3, 2, 1, 0, 3, 1], null],
    ['a-002', [4, 5, 6], [2, 3, 3, 3, 2, 1, 3, 2], 'attempt-a-001'],
    ['a-003', [1, 2, 3], [2, 2, 3, 2, 2, 2, 3, 2], null],
    ['a-004', [1, 2], [2], null],
    ['a-005', [1, 2, 3], [0, 0, 0, 0, 0, 0, 0, 0], null],
    ['a-006', [1, 2, 3], [3, 3, 3, 3, 3, 3, 3, 3], null],
    ['b-001', [1, 2, 3], [2, 2, 2, 2, 2, 2, 2, 2], null],
    ['b-002', [4, 5, 6], [3, 2, 3, 2, 3, 2, 3, 2], 'attempt-b-001'],
    ['b-003', [7, 8], [1, 1, 1], null],
    ['b-004', [1, 2, 3], [0, 1, 1, 0, 2, 1, 0, 1], null],
  ];
  cases.forEach(([suffix, indices, counts, baseline], n) => {
    let snapshot = questions.filter((q) =>
      indices.includes(Number(q.question_id.slice(-2))),
    );
    if (suffix === 'a-004')
      snapshot = snapshot.filter((q) => q.question_id.startsWith('q-linear'));
    if (suffix === 'b-003') snapshot = snapshot.slice(0, 5);
    const seen: Record<string, number> = {};
    const answers = snapshot.map((q) => {
      const kp = q.knowledge_point_ids[0];
      const k = course.knowledge_points.findIndex(
        (p) => p.knowledge_point_id === kp,
      );
      const pos = seen[kp] || 0;
      seen[kp] = pos + 1;
      return {
        question_id: q.question_id,
        selected_option_ids:
          pos < (counts[k] || 0) ? [...q.correct_option_ids] : [],
      };
    });
    const aid = `attempt-${suffix}`,
      rid = `report-${suffix}`,
      tid = `task-${suffix}`;
    const time = new Date(Date.UTC(2026, 9, 1 + n, 2)).toISOString();
    const a: Attempt = {
      attempt_id: aid,
      user_id: suffix.startsWith('a') ? 'student-a' : 'student-b',
      course_id: course.course_id,
      kind: baseline
        ? 'retest'
        : ['a-004', 'b-003'].includes(suffix)
          ? 'practice'
          : 'initial',
      baseline_attempt_id: baseline,
      source_report_id: baseline?.replace('attempt-', 'report-') || null,
      status: 'submitted',
      snapshot_version: 'seed-v1',
      created_at: time,
      submitted_at: time,
      questions: snapshot.map(publicQuestion),
      result: grade(aid, snapshot, answers),
      diagnosis_task_id: tid,
      report_id: rid,
    };
    state.attempts[aid] = { value: a, snapshot: structuredClone(snapshot) };
    state.reports[rid] = buildReport(state, a, rid);
    state.tasks[tid] = {
      task_id: tid,
      kind: 'diagnosis',
      status: 'completed',
      attempt_id: aid,
      document_id: null,
      report_id: rid,
      progress: 1,
      current_step: '模拟报告已保存',
      error_code: null,
      error_message: null,
      can_retry: false,
      retry_count: 0,
      created_at: time,
      updated_at: time,
    };
  });
  return state;
}
export interface Repository {
  change<T>(fn: (s: State) => T): Promise<T>;
  reset(): Promise<void>;
}
export function memoryRepository(): Repository {
  let state = createSeed();
  let queue: Promise<unknown> = Promise.resolve();
  return {
    change<T>(fn: (s: State) => T) {
      const next = queue.then(() => {
        const copy = structuredClone(state);
        const result = fn(copy);
        state = copy;
        return structuredClone(result);
      });
      queue = next.catch(() => undefined);
      return next;
    },
    async reset() {
      await queue;
      state = createSeed();
    },
  };
}
export async function indexedRepository(): Promise<Repository> {
  const db: IDBPDatabase = await openDB('learning-diagnosis-demo-v1', 1, {
    upgrade(database) {
      database.createObjectStore('demo-state');
    },
  });
  const repo: Repository = {
    async change<T>(fn: (s: State) => T) {
      const tx = db.transaction('demo-state', 'readwrite');
      try {
        const state: State = (await tx.store.get('state')) || createSeed();
        if (state.mock_schema_version !== 1)
          throw new Error('演示数据结构不兼容，请通过场景面板重置');
        const result = fn(state);
        await tx.store.put(state, 'state');
        await tx.done;
        return result;
      } catch (error) {
        try {
          tx.abort();
        } catch {
          /* transaction may already have completed */
        }
        await tx.done.catch(() => undefined);
        throw error;
      }
    },
    async reset() {
      await db.put('demo-state', createSeed(), 'state');
    },
  };
  await repo.change(() => null);
  return repo;
}
let repository: Repository = memoryRepository();
export const setRepository = (r: Repository) => {
  repository = r;
};
export const getRepository = () => repository;
