"""测验快照、错题与学习进度计算；只读取当前用户的数据。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import course_points, course_questions, question_active, question_dict
from .models import Attempt, Question


def user_attempts(db: Session, user_id: str, course_id: str) -> list[Attempt]:
    rows = list(db.scalars(select(Attempt).where(
        Attempt.user_id == user_id, Attempt.course_id == course_id
    )))
    return sorted(rows, key=lambda row: (row.created_at, row.payload.get('_submitted_at_ns', 0), row.id),
                  reverse=True)


def snapshot_questions(bank: list[dict], answers: list, graded: list[dict]) -> list[dict]:
    selected = {answer.question_id: answer.selected_option_ids for answer in answers}
    results = {item['question_id']: item['correct'] for item in graded}
    return [{**question, 'selected_option_ids': selected.get(question['id'], []),
             'correct': results[question['id']]} for question in bank]


def wrong_questions(db: Session, user_id: str, course_id: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for attempt in user_attempts(db, user_id, course_id):
        for item in attempt.payload.get('_question_snapshot', []):
            latest.setdefault(item['id'], {**item, 'attempt_id': attempt.id,
                                           'attempt_created_at': attempt.created_at})
    results = []
    for item in latest.values():
        if item['correct']:
            continue
        current = db.get(Question, item['id'])
        results.append({**item, 'available_for_practice': bool(
            current and current.course_id == course_id and question_active(db, item['id']))})
    return sorted(results, key=lambda item: (-item['attempt_created_at'], item['id']))


def practice_questions(db: Session, user_id: str, course_id: str,
                       knowledge_point_id: str | None, limit: int) -> list[dict]:
    bank = [q for q in course_questions(db, course_id)
            if q.kind == 'single' and (knowledge_point_id is None or knowledge_point_id in q.knowledge_point_ids)]
    wrong_ids = {item['id'] for item in wrong_questions(db, user_id, course_id)}
    bank.sort(key=lambda question: (question.id not in wrong_ids, question.id))
    return [question_dict(row) for row in bank[:limit]]


def progress(db: Session, user_id: str, course_id: str) -> dict:
    attempts = list(reversed(user_attempts(db, user_id, course_id)))
    points = course_points(db, course_id)
    names = {point.id: point.name for point in points}
    totals: dict[str, list[int]] = {point.id: [0, 0] for point in points}
    timeline = []
    for attempt in attempts:
        per_attempt: dict[str, list[int]] = {}
        for answer in attempt.payload.get('_graded_answers', []):
            for point_id in answer['knowledge_point_ids']:
                totals.setdefault(point_id, [0, 0])
                per_attempt.setdefault(point_id, [0, 0])
                totals[point_id][0] += 1
                per_attempt[point_id][0] += 1
                if answer['correct']:
                    totals[point_id][1] += 1
                    per_attempt[point_id][1] += 1
        timeline.append({'attempt_id': attempt.id, 'created_at': attempt.created_at,
                         'kind': attempt.payload.get('kind', 'quiz'),
                         'score': attempt.payload['score'], 'max_score': attempt.payload['max_score'],
                         'knowledge_points': [_point_stat(point_id, names, counts)
                                              for point_id, counts in sorted(per_attempt.items())]})
    return {'course_id': course_id, 'attempt_count': len(attempts),
            'knowledge_points': [_point_stat(point_id, names, counts)
                                 for point_id, counts in sorted(totals.items())],
            'timeline': timeline}


def _point_stat(point_id: str, names: dict[str, str], counts: list[int]) -> dict:
    count, correct = counts
    return {'id': point_id, 'name': names.get(point_id, point_id), 'sample_count': count,
            'correct_count': correct, 'accuracy': round(correct / count, 4) if count else None}
