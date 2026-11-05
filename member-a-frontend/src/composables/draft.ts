import type { Attempt } from '../api/contracts';
import { answerSchema } from '../api/contracts';
import { z } from 'zod';
export const submitIntentKey = (a: Attempt) =>
  `learnmate-intent:${a.user_id}:${a.attempt_id}`;
export function restoreSubmitIntent(a: Attempt) {
  const key = submitIntentKey(a);
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw || a.status === 'submitted') {
      sessionStorage.removeItem(key);
      return null;
    }
    const intent = z
      .object({
        key: z.string().min(1).max(200),
        data: z.object({
          snapshot_version: z.literal(a.snapshot_version),
          answers: z.array(answerSchema),
        }),
      })
      .parse(JSON.parse(raw));
    if (
      intent.data.answers.length !== a.questions.length ||
      new Set(intent.data.answers.map((x) => x.question_id)).size !==
        a.questions.length ||
      intent.data.answers.some((answer) => {
        const q = a.questions.find((q) => q.question_id === answer.question_id);
        return (
          !q ||
          answer.selected_option_ids.some(
            (id) => !q.options.some((o) => o.option_id === id),
          ) ||
          new Set(answer.selected_option_ids).size !==
            answer.selected_option_ids.length ||
          (q.type === 'single_choice' && answer.selected_option_ids.length > 1)
        );
      })
    )
      throw new Error('invalid intent');
    return intent;
  } catch {
    sessionStorage.removeItem(key);
    return null;
  }
}
export const draftPrefix = (a: Attempt) =>
  `learnmate-draft:${a.user_id}:${a.course_id}:${a.attempt_id}:`;
export const draftKey = (a: Attempt) =>
  `${draftPrefix(a)}${a.snapshot_version}`;
export function restoreDraft(a: Attempt) {
  let stale = false;
  Object.keys(sessionStorage)
    .filter(
      (k) =>
        k.startsWith(draftPrefix(a)) &&
        (k !== draftKey(a) || a.status === 'submitted'),
    )
    .forEach((k) => {
      sessionStorage.removeItem(k);
      stale = true;
    });
  if (a.status === 'submitted') {
    sessionStorage.removeItem(draftKey(a));
    return { choices: {}, stale };
  }
  try {
    const raw: unknown = JSON.parse(
      sessionStorage.getItem(draftKey(a)) || '{}',
    );
    const choices: Record<string, string[]> = {};
    if (raw && typeof raw === 'object')
      for (const q of a.questions) {
        const input = (raw as Record<string, unknown>)[q.question_id];
        const valid = Array.isArray(input)
          ? q.options
              .filter((o) => input.includes(o.option_id))
              .map((o) => o.option_id)
          : [];
        choices[q.question_id] =
          q.type === 'single_choice' ? valid.slice(0, 1) : valid;
      }
    return { choices, stale };
  } catch {
    sessionStorage.removeItem(draftKey(a));
    return { choices: {}, stale: true };
  }
}
