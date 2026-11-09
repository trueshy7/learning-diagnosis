"""full-v1 前端协议的序列化与授权辅助函数。与 group-v0 分开。"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (Attempt, Course, FullAttempt, FullTask, KnowledgePoint, KnowledgeMeta,
                     Question, QuestionMeta, QuestionState, Resource, ResourceMeta,
                     StudentCourse, TeacherCourse, User)
from .security import teacher_course


class ApiProblem(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code, {'code': code, 'message': message})


def respond(request, data):
    return {'code': 'OK', 'message': '成功', 'data': data, 'request_id': request.state.request_id}


def iso(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z') if value is not None else None


def user_dto(user: User) -> dict:
    return {'user_id': user.id, 'username': user.username,
            'display_name': user.username, 'role': user.role}


def allowed_course(db: Session, user: User, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise ApiProblem(404, 'NOT_FOUND', '课程不存在')
    if user.role == 'teacher' and db.get(TeacherCourse, (user.id, course_id)) is None:
        raise ApiProblem(403, 'FORBIDDEN', '没有该课程的教师权限')
    if user.role == 'student' and db.get(StudentCourse, (user.id, course_id)) is None:
        raise ApiProblem(403, 'FORBIDDEN', '尚未获得该课程的学习权限')
    return course


def own_attempt(db: Session, user: User, attempt_id: str) -> FullAttempt:
    row = db.get(FullAttempt, attempt_id)
    if row is None:
        raise ApiProblem(404, 'ATTEMPT_NOT_FOUND', '测验不存在')
    if row.user_id != user.id:
        raise ApiProblem(403, 'FORBIDDEN', '不能访问其他用户的测验')
    return row


def own_task(db: Session, user: User, task_id: str) -> FullTask:
    row = db.get(FullTask, task_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '任务不存在')
    if row.user_id != user.id and (user.role != 'teacher' or
                                   db.get(TeacherCourse, (user.id, row.course_id)) is None):
        raise ApiProblem(403, 'FORBIDDEN', '不能访问该任务')
    return row


def knowledge_dto(db: Session, point: KnowledgePoint) -> dict:
    meta = db.get(KnowledgeMeta, point.id)
    return {'knowledge_point_id': point.id, 'course_id': point.course_id, 'name': point.name,
            'description': meta.description if meta else '',
            'sort_order': meta.sort_order if meta else 0,
            'active': meta.active if meta else True}


def course_dto(db: Session, course: Course, user: User) -> dict:
    points = list(db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == course.id).order_by(KnowledgePoint.id)))
    points.sort(key=lambda point: (knowledge_dto(db, point)['sort_order'], point.id))
    latest = None
    active = None
    if user.role == 'student':
        rows = list(db.scalars(select(FullAttempt).where(
            FullAttempt.user_id == user.id, FullAttempt.course_id == course.id)))
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        latest = next((row for row in rows if row.status == 'submitted'), None)
        active = next((row for row in rows if row.status == 'in_progress'), None)
    return {'course_id': course.id, 'title': course.name, 'description': course.description,
            'knowledge_points': [knowledge_dto(db, point) for point in points],
            'latest_attempt_id': latest.id if latest else None,
            'active_attempt_id': active.id if active else None,
            'latest_report_id': latest.payload.get('report_id') if latest else None}


def question_dto(db: Session, question: Question, *, teacher: bool = False) -> dict:
    meta = db.get(QuestionMeta, question.id)
    state = db.get(QuestionState, question.id)
    options = [{'option_id': option['id'], 'label': option.get('label', option['id']),
                'text': option['text']} for option in question.options]
    result = {'question_id': question.id,
              'type': 'multiple_choice' if question.kind in ('multiple', 'multiple_choice') else 'single_choice',
              'stem': question.stem, 'options': options,
              'knowledge_point_ids': question.knowledge_point_ids,
              'difficulty': meta.difficulty if meta else 'easy'}
    if teacher:
        result.update({'course_id': question.course_id,
                       'correct_option_ids': question.correct_option_ids,
                       'explanation': meta.explanation if meta else '',
                       'active': state.active if state else True,
                       'version': f'v{meta.version if meta else 1}'})
    return result


def score_dto(correct: int, total: int) -> dict:
    return {'correct_count': correct, 'total_count': total,
            'raw_score': correct, 'max_score': total,
            'percentage': round(correct * 100 / total, 2)}


def attempt_dto(row: FullAttempt) -> dict:
    payload = row.payload
    return {'attempt_id': row.id, 'user_id': row.user_id, 'course_id': row.course_id,
            'kind': row.kind, 'baseline_attempt_id': payload.get('baseline_attempt_id'),
            'source_report_id': payload.get('source_report_id'), 'status': row.status,
            'snapshot_version': row.snapshot_version, 'created_at': iso(row.created_at),
            'submitted_at': iso(row.submitted_at), 'questions': payload['questions'],
            'result': payload.get('result'), 'diagnosis_task_id': payload.get('task_id'),
            'report_id': payload.get('report_id')}


def task_dto(row: FullTask) -> dict:
    return {'task_id': row.id, 'kind': row.kind, 'status': row.status,
            'attempt_id': row.attempt_id, 'document_id': row.document_id,
            'report_id': row.report_id, 'progress': 1 if row.status == 'completed' else None,
            'current_step': '处理完成' if row.status == 'completed' else None,
            'error_code': row.error_code, 'error_message': row.error_message,
            'can_retry': row.status == 'failed' and row.retry_count < 2,
            'retry_count': row.retry_count, 'created_at': iso(row.created_at),
            'updated_at': iso(row.updated_at)}


def history_dto(row: FullAttempt, db: Session) -> dict:
    task_id = row.payload.get('task_id')
    task = db.get(FullTask, task_id) if task_id else None
    return {'attempt_id': row.id, 'report_id': row.payload.get('report_id'),
            'kind': row.kind, 'baseline_attempt_id': row.payload.get('baseline_attempt_id'),
            'submitted_at': iso(row.submitted_at),
            'score': row.payload.get('result', {}).get('score') if row.payload.get('result') else None,
            'diagnosis_task_id': task_id, 'diagnosis_status': task.status if task else None}


def page(items: list, page_no: int, page_size: int) -> dict:
    start = (page_no - 1) * page_size
    return {'items': items[start:start + page_size], 'total': len(items),
            'page': page_no, 'page_size': page_size}


def resource_dto(db: Session, row: Resource, *, teacher: bool = False) -> dict:
    meta = db.get(ResourceMeta, row.resource_id)
    kind = meta.kind if meta else 'document'
    active = meta.active if meta else row.status != 'deleted'
    availability = ('removed' if row.status == 'deleted' or not active else
                    'failed' if row.status == 'failed' else
                    'processing' if row.status == 'processing' else 'available')
    result = {'resource_id': row.resource_id, 'course_id': row.course_id,
              'title': row.title, 'kind': kind, 'knowledge_point_ids': row.knowledge_point_ids,
              'difficulty': meta.difficulty if meta else 'easy', 'active': active,
              'availability': availability, 'source_label': row.source,
              'description': meta.description if meta else '',
              'document_id': row.document_id if kind == 'document' else None,
              'resource_version': f'v{meta.version}' if meta else (row.index_version or 'v1'),
              'text_content': meta.text_content if meta else None,
              'external_url': meta.external_url if meta else None,
              'file_available': bool(meta and meta.filename and availability == 'available'),
              'filename': meta.filename if meta else None,
              'location': None}
    if teacher:
        return {key: result[key] for key in ('resource_id', 'course_id', 'title', 'kind',
            'knowledge_point_ids', 'difficulty', 'active', 'availability', 'source_label')} | {
                'document_id': result['document_id'],
                'ingestion_task_id': meta.ingestion_task_id if meta else None,
                'error_code': meta.error_code if meta else None,
                'error_message': meta.error_message if meta else None}
    return result
