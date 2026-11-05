import { z } from 'zod';
import { getSession } from './session';
import type { Question, SubmitAttempt } from '../types/api';
const body = z.object({
  course_id: z.string(),
  answers: z.array(
    z.object({
      question_id: z.string(),
      selected_option_ids: z.array(z.string()),
    }),
  ),
  baseline_attempt_id: z.string().optional(),
});
const stored = z.object({
  key: z.string().uuid(),
  questions: z.array(z.string()),
  selected: z.record(z.string(), z.string()),
  pending: body.nullable(),
});
export type Draft = z.infer<typeof stored>;
export function draftKey(course: string, baseline?: string) {
  return (
    'learnmate-group-draft:' +
    JSON.stringify([getSession()?.user.id, course, baseline || null])
  );
}
export function restoreDraft(
  key: string,
  course: string,
  baseline: string | undefined,
  questions: Question[],
): Draft | null {
  try {
    const parsed = stored.safeParse(
      JSON.parse(sessionStorage.getItem(key) || 'null'),
    );
    if (!parsed.success) return null;
    const d = parsed.data;
    const signature = questions.map((q) => JSON.stringify(q));
    if (JSON.stringify(signature) !== JSON.stringify(d.questions)) return null;
    const valid = (selected: Record<string, string>) =>
      Object.entries(selected).every(([id, option]) =>
        questions.some(
          (q) => q.id === id && q.options.some((o) => o.id === option),
        ),
      );
    if (!valid(d.selected)) return null;
    if (d.pending) {
      const p = d.pending;
      if (
        p.course_id !== course ||
        p.baseline_attempt_id !== baseline ||
        p.answers.length !== questions.length ||
        new Set(p.answers.map((a) => a.question_id)).size !==
          questions.length ||
        p.answers.some(
          (a) =>
            a.selected_option_ids.length !== 1 ||
            !questions.some(
              (q) =>
                q.id === a.question_id &&
                q.options.some((o) => o.id === a.selected_option_ids[0]),
            ),
        ) ||
        p.answers.some(
          (a) => d.selected[a.question_id] !== a.selected_option_ids[0],
        )
      )
        return null;
    }
    return d;
  } catch {
    return null;
  }
}
export function writeDraft(key: string, draft: Draft) {
  try {
    sessionStorage.setItem(key, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}
export function submission(
  course: string,
  baseline: string | undefined,
  questions: Question[],
  selected: Record<string, string>,
): SubmitAttempt {
  return {
    course_id: course,
    answers: questions.map((q) => ({
      question_id: q.id,
      selected_option_ids: [selected[q.id]!],
    })),
    ...(baseline ? { baseline_attempt_id: baseline } : {}),
  };
}
