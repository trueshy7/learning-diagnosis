import type { TeacherQuestion, QuestionWrite } from '../contracts';
export function questionToWrite(q: TeacherQuestion): QuestionWrite {
  return {
    course_id: q.course_id,
    type: q.type,
    stem: q.stem,
    options: q.options.map((o) => ({ ...o, client_key: o.option_id })),
    correct_option_keys: [...q.correct_option_ids],
    knowledge_point_ids: [...q.knowledge_point_ids],
    difficulty: q.difficulty,
    explanation: q.explanation,
    active: q.active,
  };
}
