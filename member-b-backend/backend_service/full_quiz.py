"""full-v1 学生测验、诊断任务与报告接口，挂载在 /api/v2。"""
import hashlib
import json
import secrets
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clients
from .catalog import course_questions, course_points
from .database import get_db
from .full_common import (ApiProblem, allowed_course, attempt_dto, course_dto, history_dto,
                          iso, own_attempt, own_task, page, question_dto, respond, score_dto,
                          task_dto, user_dto)
from .full_report import build_report, RULE_VERSION
from .models import (Course, FullAttempt, FullDocument, FullReport, FullTask, KnowledgeMeta, LoginSession,
                     Resource, ResourceMeta, StudentCourse, TeacherCourse, User)
from .security import check_password, current_user, token_hash

router = APIRouter(prefix='/api/v2')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LoginBody(Strict):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class CreateBody(Strict):
    course_id: str = Field(min_length=1)
    kind: Literal['initial', 'practice', 'retest']
    client_request_id: str = Field(min_length=1, max_length=200)
    baseline_attempt_id: str | None = None
    source_report_id: str | None = None
    question_ids: list[str] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode='after')
    def check_intent(self):
        if self.kind == 'initial' and any((self.baseline_attempt_id, self.source_report_id, self.question_ids)):
            raise ValueError('初测不能指定基线、来源报告或题目')
        if self.kind == 'practice' and (not self.source_report_id or not self.question_ids or self.baseline_attempt_id):
            raise ValueError('练习需要来源报告和题目')
        if self.kind == 'retest' and (not self.source_report_id or not self.baseline_attempt_id or self.question_ids):
            raise ValueError('复测需要来源报告与基线')
        if self.question_ids and len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError('题目不能重复')
        return self


class AnswerBody(Strict):
    question_id: str = Field(min_length=1)
    selected_option_ids: list[str] = Field(max_length=6)


class SubmitBody(Strict):
    snapshot_version: str = Field(min_length=1)
    answers: list[AnswerBody] = Field(min_length=1, max_length=200)


def require_student(user: User):
    if user.role != 'student':
        raise ApiProblem(403, 'FORBIDDEN', '仅学生可创建或提交测验')


def _course_bank(db: Session, course_id: str) -> list:
    rows = course_questions(db, course_id)
    return [row for row in rows if all((meta := db.get(KnowledgeMeta, point_id)) is None or meta.active
                                   for point_id in row.knowledge_point_ids)]


@router.post('/auth/login')
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not check_password(body.password, user.password_hash):
        raise ApiProblem(401, 'INVALID_CREDENTIALS', '用户名或密码错误')
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + 86400
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=expires))
    db.commit()
    return respond(request, {'access_token': token, 'token_type': 'Bearer',
                             'expires_at': iso(expires), 'user': user_dto(user)})


@router.get('/auth/me')
def me(request: Request, user: User = Depends(current_user)):
    return respond(request, user_dto(user))


@router.post('/auth/logout')
def logout(request: Request, authorization: str = Header(), user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    session = db.get(LoginSession, token_hash(authorization.split(' ', 1)[1]))
    if session:
        db.delete(session)
        db.commit()
    return respond(request, None)


@router.get('/courses')
def courses(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Course).order_by(Course.id)
    if user.role == 'teacher':
        query = query.join(TeacherCourse, TeacherCourse.course_id == Course.id).where(
            TeacherCourse.teacher_id == user.id)
    else:
        query = query.join(StudentCourse, StudentCourse.course_id == Course.id).where(
            StudentCourse.student_id == user.id)
    return respond(request, [course_dto(db, row, user) for row in db.scalars(query)])


@router.get('/courses/{course_id}')
def course(course_id: str, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    return respond(request, course_dto(db, allowed_course(db, user, course_id), user))


@router.get('/courses/{course_id}/knowledge-points')
def knowledge(course_id: str, request: Request, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    from .full_common import knowledge_dto
    allowed_course(db, user, course_id)
    return respond(request, [knowledge_dto(db, point) for point in course_points(db, course_id)])


@router.post('/attempts', status_code=201)
def create_attempt(body: CreateBody, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_student(user)
    allowed_course(db, user, body.course_id)
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(exclude_none=True), sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(FullAttempt).where(FullAttempt.user_id == user.id,
                                                   FullAttempt.client_request_id == body.client_request_id))
    if existing:
        if existing.payload['create_fingerprint'] != fingerprint:
            raise ApiProblem(409, 'REFERENCE_CONFLICT', '同一创建编号对应不同请求')
        return respond(request, attempt_dto(existing))
    bank = _course_bank(db, body.course_id)
    by_id = {row.id: row for row in bank}
    source = None
    if body.source_report_id:
        source = db.get(FullReport, body.source_report_id)
        if source is None or source.user_id != user.id or source.course_id != body.course_id:
            raise ApiProblem(422, 'INVALID_BASELINE', '来源报告不属于本人该课程')
    if body.kind == 'practice':
        allowed = {item['question_id'] for rec in source.payload['recommendations']
                   for item in rec['practice_questions']}
        if not set(body.question_ids) <= allowed or not set(body.question_ids) <= set(by_id):
            raise ApiProblem(422, 'INVALID_BASELINE', '练习题不属于来源报告的可用推荐')
        bank = [by_id[question_id] for question_id in body.question_ids]
    if body.kind == 'retest':
        baseline = db.get(FullAttempt, body.baseline_attempt_id)
        if (baseline is None or baseline.user_id != user.id or baseline.course_id != body.course_id or
                baseline.status != 'submitted' or source.attempt_id != baseline.id):
            raise ApiProblem(422, 'INVALID_BASELINE', '基线测验与来源报告不匹配')
    if not bank:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '该课程当前没有可用题目')
    public = [question_dto(db, row) for row in bank]
    answer_key = {row.id: {'correct_option_ids': row.correct_option_ids,
                           'knowledge_point_ids': row.knowledge_point_ids,
                           'type': question_dto(db, row)['type']} for row in bank}
    now = int(time.time())
    row = FullAttempt(id='attv2-' + uuid.uuid4().hex, user_id=user.id, course_id=body.course_id,
                      client_request_id=body.client_request_id, kind=body.kind, status='in_progress',
                      snapshot_version='snap-' + uuid.uuid4().hex, created_at=now,
                      submitted_at=None, payload={'questions': public, 'answer_key': answer_key,
                          'baseline_attempt_id': body.baseline_attempt_id,
                          'source_report_id': body.source_report_id,
                          'create_fingerprint': fingerprint, 'result': None,
                          'task_id': None, 'report_id': None})
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(FullAttempt).where(FullAttempt.user_id == user.id,
                                                       FullAttempt.client_request_id == body.client_request_id))
        if existing and existing.payload['create_fingerprint'] == fingerprint:
            return respond(request, attempt_dto(existing))
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '同一创建编号对应不同请求') from None
    return respond(request, attempt_dto(row))


@router.get('/attempts')
def attempts(request: Request, course_id: str | None = None, kind: str | None = None,
             page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_student(user)
    rows = list(db.scalars(select(FullAttempt).where(FullAttempt.user_id == user.id,
                                                     FullAttempt.status == 'submitted')))
    rows = [row for row in rows if (course_id is None or row.course_id == course_id)
            and (kind is None or row.kind == kind)]
    rows.sort(key=lambda row: (row.submitted_at or 0, row.id), reverse=True)
    return respond(request, page([history_dto(row, db) for row in rows], page_no, page_size))


@router.get('/attempts/{attempt_id}')
def attempt(attempt_id: str, request: Request, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    require_student(user)
    return respond(request, attempt_dto(own_attempt(db, user, attempt_id)))


def _grade(attempt: FullAttempt, answers: list[AnswerBody]) -> tuple[dict, list[dict]]:
    bank = {item['question_id']: item for item in attempt.payload['questions']}
    supplied = {item.question_id: item for item in answers}
    if len(supplied) != len(answers) or set(supplied) != set(bank):
        raise ApiProblem(422, 'INVALID_OPTIONS', '答案必须覆盖试卷中的每道题且不能重复')
    grades = []
    for question_id, question in bank.items():
        values = supplied[question_id].selected_option_ids
        valid = {option['option_id'] for option in question['options']}
        if len(set(values)) != len(values) or not set(values) <= valid or (
                question['type'] == 'single_choice' and len(values) > 1):
            raise ApiProblem(422, 'INVALID_OPTIONS', '选项不属于试卷或单选题选择过多')
        correct = set(values) == set(attempt.payload['answer_key'][question_id]['correct_option_ids'])
        grades.append({'question_id': question_id, 'selected_option_ids': values,
                       'is_correct': correct})
    score = score_dto(sum(item['is_correct'] for item in grades), len(grades))
    return {'attempt_id': attempt.id, 'score': score, 'graded_answers': grades,
            'rule_version': RULE_VERSION}, grades


def _submission_fingerprint(body: SubmitBody) -> str:
    canonical = {'snapshot_version': body.snapshot_version,
                 'answers': sorted([{'question_id': item.question_id,
                                     'selected_option_ids': sorted(item.selected_option_ids)}
                                    for item in body.answers], key=lambda item: item['question_id'])}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


async def diagnose_attempt(db: Session, attempt: FullAttempt, task: FullTask):
    resources = list(db.scalars(select(Resource).where(Resource.course_id == attempt.course_id,
                                                       Resource.status.in_(['seeded', 'indexed']))))
    resources = [row for row in resources if (meta := db.get(ResourceMeta, row.resource_id)) is None or meta.active]
    graded = [{'question_id': item['question_id'],
               'knowledge_point_ids': attempt.payload['answer_key'][item['question_id']]['knowledge_point_ids'],
               'correct': item['is_correct']} for item in attempt.payload['result']['graded_answers']]
    payload = {'attempt_id': attempt.id, 'course_id': attempt.course_id,
               'graded_answers': graded,
               'knowledge_points': [{'id': point.id, 'name': point.name} for point in course_points(db, attempt.course_id)],
               'resource_catalog': [{'resource_id': row.resource_id, 'title': row.title,
                                     'knowledge_point_ids': row.knowledge_point_ids} for row in resources]}
    baseline_id = attempt.payload.get('baseline_attempt_id')
    if baseline_id:
        baseline_report = db.scalar(select(FullReport).where(FullReport.attempt_id == baseline_id))
        if baseline_report:
            payload['baseline'] = {'knowledge_points': [
                {'knowledge_point_id': point['knowledge_point_id'], 'name': point['name'],
                 'correct_count': point['correct_count'], 'sample_count': point['question_count'],
                 'accuracy': point['correct_rate'],
                 'status': {'consolidating': 'needs_practice'}.get(point['mastery_status'], point['mastery_status'])}
                for point in baseline_report.payload['knowledge_points']]}
    report, status, message = await clients.diagnose(payload)
    task.updated_at = int(time.time())
    if status != 'completed' or report is None:
        task.status = 'failed'
        task.error_code = 'MODEL_UNAVAILABLE'
        task.error_message = message or '诊断服务暂不可用，成绩已保存。'
        db.commit()
        return
    report_id = 'rep-' + attempt.id
    record = build_report(db, attempt, report, report_id, task.updated_at)
    stored = db.get(FullReport, report_id)
    if stored is None:
        db.add(FullReport(id=report_id, attempt_id=attempt.id, user_id=attempt.user_id,
                          course_id=attempt.course_id, generated_at=task.updated_at, payload=record))
    else:
        stored.payload = record
        stored.generated_at = task.updated_at
    task.status = 'completed'
    task.report_id = report_id
    task.error_code = None
    task.error_message = None
    attempt.payload = {**attempt.payload, 'report_id': report_id}
    db.commit()


@router.post('/attempts/{attempt_id}/submit')
async def submit(attempt_id: str, body: SubmitBody, request: Request,
                 idempotency_key: str = Header(min_length=1, max_length=200),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_student(user)
    row = own_attempt(db, user, attempt_id)
    if body.snapshot_version != row.snapshot_version:
        raise ApiProblem(409, 'SNAPSHOT_MISMATCH', '试卷版本不匹配，请重新加载')
    fingerprint = _submission_fingerprint(body)
    if row.status == 'submitted':
        if row.payload.get('submit_fingerprint') == fingerprint:
            return respond(request, {'attempt_id': row.id, 'submitted_at': iso(row.submitted_at),
                                     'result': row.payload['result'], 'diagnosis_task_id': row.payload['task_id']})
        raise ApiProblem(409, 'ATTEMPT_ALREADY_SUBMITTED', '测验已提交，不能覆盖答案')
    result, grades = _grade(row, body.answers)
    now = int(time.time())
    task_id = 'task-' + row.id
    payload = {**row.payload, 'result': result, 'task_id': task_id,
               'submit_fingerprint': fingerprint, 'submit_key': idempotency_key,
               'graded_answers': [{'question_id': item['question_id'],
                                   'knowledge_point_ids': row.payload['answer_key'][item['question_id']]['knowledge_point_ids'],
                                   'correct': item['is_correct']} for item in grades]}
    changed = db.execute(update(FullAttempt).where(FullAttempt.id == row.id,
                                                    FullAttempt.status == 'in_progress').values(
                                                        status='submitted', submitted_at=now, payload=payload))
    if changed.rowcount != 1:
        db.rollback()
        db.refresh(row)
        if row.payload.get('submit_fingerprint') == fingerprint:
            return respond(request, {'attempt_id': row.id, 'submitted_at': iso(row.submitted_at),
                                     'result': row.payload['result'], 'diagnosis_task_id': row.payload['task_id']})
        raise ApiProblem(409, 'ATTEMPT_ALREADY_SUBMITTED', '测验已提交，不能覆盖答案')
    task = FullTask(id=task_id, user_id=user.id, course_id=row.course_id,
                    kind='diagnosis', status='running', attempt_id=row.id, document_id=None,
                    report_id=None, retry_count=0, retry_key=None, created_at=now, updated_at=now,
                    error_code=None, error_message=None)
    db.add(task)
    db.commit()
    db.refresh(row)
    await diagnose_attempt(db, row, task)
    return respond(request, {'attempt_id': row.id, 'submitted_at': iso(row.submitted_at),
                             'result': row.payload['result'], 'diagnosis_task_id': task_id})


@router.get('/attempts/{attempt_id}/result')
def attempt_result(attempt_id: str, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    require_student(user)
    row = own_attempt(db, user, attempt_id)
    if row.status != 'submitted':
        raise ApiProblem(409, 'ATTEMPT_NOT_SUBMITTED', '测验尚未提交')
    return respond(request, row.payload['result'])


@router.get('/tasks/{task_id}')
def task(task_id: str, request: Request, user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    return respond(request, task_dto(own_task(db, user, task_id)))


@router.post('/tasks/{task_id}/retry', status_code=202)
async def retry_task(task_id: str, request: Request, body: dict,
                     idempotency_key: str = Header(min_length=1, max_length=200),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body:
        raise ApiProblem(422, 'VALIDATION_ERROR', '重试请求体必须为空对象')
    row = own_task(db, user, task_id)
    if row.retry_key == idempotency_key:
        return respond(request, task_dto(row))
    if row.status != 'failed' or row.retry_count >= 2:
        raise ApiProblem(409, 'TASK_NOT_RETRYABLE', '任务当前不可重试')
    claimed = db.execute(update(FullTask).where(
        FullTask.id == task_id, FullTask.status == 'failed', FullTask.retry_count < 2).values(
            retry_count=FullTask.retry_count + 1, retry_key=idempotency_key,
            status='running', updated_at=int(time.time()), error_code=None, error_message=None))
    if claimed.rowcount != 1:
        db.rollback()
        db.refresh(row)
        if row.retry_key == idempotency_key:
            return respond(request, task_dto(row))
        raise ApiProblem(409, 'TASK_NOT_RETRYABLE', '任务当前不可重试')
    db.commit()
    db.refresh(row)
    if row.kind == 'diagnosis':
        attempt = db.get(FullAttempt, row.attempt_id)
        await diagnose_attempt(db, attempt, row)
    else:
        from .full_teacher import process_document
        await process_document(db, db.get(FullDocument, row.document_id), row)
    return respond(request, task_dto(row))


@router.get('/reports')
def reports(request: Request, course_id: str | None = None, kind: str | None = None,
            page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    return attempts(request, course_id, kind, page_no, page_size, user, db)


def _report(db: Session, user: User, report_id: str) -> FullReport:
    row = db.get(FullReport, report_id)
    if row is None:
        raise ApiProblem(404, 'REPORT_NOT_FOUND', '报告不存在')
    if row.user_id != user.id:
        raise ApiProblem(403, 'FORBIDDEN', '不能访问其他用户的报告')
    return row


@router.get('/reports/{report_id}')
def report(report_id: str, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    return respond(request, _report(db, user, report_id).payload)


@router.get('/reports/{report_id}/recommendations')
def recommendations(report_id: str, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    row = _report(db, user, report_id)
    return respond(request, {'report_id': row.id, 'attempt_id': row.attempt_id,
                             'recommendations': row.payload['recommendations'],
                             'actions': row.payload['actions']})


@router.get('/reports/{report_id}/comparison')
def comparison(report_id: str, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    return respond(request, _report(db, user, report_id).payload['comparison'])
