"""full-v1 教师维护、资料与文件接口，挂载在 /api/v2。"""
import json
import time
import uuid
from io import BytesIO
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import clients
from .catalog import course_points, course_questions, question_active
from .database import SessionLocal, get_db
from .full_common import (ApiProblem, allowed_course, course_dto, history_dto, iso,
                          knowledge_dto, page, question_dto, resource_dto, respond, task_dto)
from .models import (Attempt, Course, FullAttempt, FullDocument, FullReport, FullTask,
                     KnowledgeMeta, KnowledgePoint, Question, QuestionMeta, QuestionState,
                     Resource, ResourceMeta, TeacherCourse, User)
from .security import current_user, teacher_course, teacher_user

router = APIRouter(prefix='/api/v2')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CourseWrite(Strict):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=3000)

    @model_validator(mode='after')
    def check_title(self):
        if not self.title.strip():
            raise ValueError('课程名称不能为空')
        return self


class KnowledgeWrite(Strict):
    course_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=3000)
    sort_order: int = Field(ge=0)
    active: bool

    @model_validator(mode='after')
    def check_name(self):
        if not self.name.strip():
            raise ValueError('知识点名称不能为空')
        return self


class OptionWrite(Strict):
    option_id: str | None
    client_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=500)


class QuestionWrite(Strict):
    course_id: str = Field(min_length=1)
    type: str = Field(pattern=r'^(single_choice|multiple_choice)$')
    stem: str = Field(min_length=1, max_length=2000)
    options: list[OptionWrite] = Field(min_length=2, max_length=6)
    correct_option_keys: list[str] = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)
    difficulty: str = Field(pattern=r'^(easy|medium|hard)$')
    explanation: str = Field(max_length=3000)
    active: bool

    @model_validator(mode='after')
    def validate_question(self):
        keys = [option.client_key for option in self.options]
        ids = [option.option_id for option in self.options if option.option_id]
        if (len(set(keys)) != len(keys) or len(set(ids)) != len(ids) or
            len(set(self.correct_option_keys)) != len(self.correct_option_keys) or
            not set(self.correct_option_keys) <= set(keys) or
            len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids) or
            (self.type == 'single_choice' and len(self.correct_option_keys) != 1) or
            (self.type == 'multiple_choice' and len(self.correct_option_keys) < 2)):
            raise ValueError('选项、答案或知识点关联不合法')
        if not self.stem.strip() or any(not option.text.strip() for option in self.options):
            raise ValueError('题干与选项文本不能为空')
        return self


class ResourceWrite(Strict):
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=3000)
    kind: str = Field(pattern=r'^(note|external|document)$')
    knowledge_point_ids: list[str] = Field(min_length=1)
    difficulty: str = Field(pattern=r'^(easy|medium|hard)$')
    active: bool
    text_content: str | None
    external_url: str | None

    @model_validator(mode='after')
    def validate_resource(self):
        if not self.title.strip() or (self.text_content is not None and len(self.text_content) > 200_000):
            raise ValueError('资料标题不能为空，正文不能超过 20 万字符')
        if self.kind == 'note' and not (self.text_content or '').strip():
            raise ValueError('笔记正文不能为空')
        if self.kind == 'external':
            parsed = urlsplit(self.external_url or '')
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('外部链接须为不含账号密码的 http/https 地址')
        return self


def _teacher_course(db: Session, user: User, course_id: str) -> Course:
    try:
        return teacher_course(db, user, course_id)
    except HTTPException as exc:
        if getattr(exc, 'status_code', None) == 404:
            raise ApiProblem(404, 'NOT_FOUND', '课程不存在') from exc
        raise ApiProblem(403, 'FORBIDDEN', '没有该课程的教师权限') from exc


def _course_ids(db: Session, user: User) -> list[str]:
    return list(db.scalars(select(TeacherCourse.course_id).where(TeacherCourse.teacher_id == user.id)))


def _submitted(db: Session, course_id: str) -> list[FullAttempt]:
    rows = list(db.scalars(select(FullAttempt).where(
        FullAttempt.course_id == course_id, FullAttempt.status == 'submitted')))
    rows.sort(key=lambda row: (row.submitted_at or 0, row.id), reverse=True)
    return rows


@router.get('/teacher/overview')
def overview(request: Request, course_id: str, user: User = Depends(teacher_user),
             db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    rows = _submitted(db, course_id)
    students = {row.user_id for row in rows}
    scores = [row.payload['result']['score']['percentage'] for row in rows]
    return respond(request, {'course_id': course_id, 'student_count': len(students),
                             'submitted_attempt_count': len(rows),
                             'average_percentage': round(sum(scores) / len(scores), 2) if scores else None,
                             'recent_attempts': [history_dto(row, db) for row in rows[:10]]})


@router.get('/teacher/students')
def students(request: Request, course_id: str, q: str = '',
             page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
             user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    grouped: dict[str, list[FullAttempt]] = {}
    for row in _submitted(db, course_id):
        grouped.setdefault(row.user_id, []).append(row)
    items = []
    for student_id, rows in grouped.items():
        student = db.get(User, student_id)
        if student and q.casefold() in student.username.casefold():
            items.append({'user_id': student_id, 'display_name': student.username,
                          'submitted_attempt_count': len(rows),
                          'latest_attempt_id': rows[0].id,
                          'latest_report_id': rows[0].payload.get('report_id')})
    items.sort(key=lambda item: item['display_name'])
    return respond(request, page(items, page_no, page_size))


@router.get('/teacher/students/{student_id}/attempts')
def student_attempts(student_id: str, request: Request, course_id: str,
                     page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
                     user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    student = db.get(User, student_id)
    if student is None or student.role != 'student':
        raise ApiProblem(404, 'NOT_FOUND', '学生不存在')
    rows = [row for row in _submitted(db, course_id) if row.user_id == student_id]
    return respond(request, page([history_dto(row, db) for row in rows], page_no, page_size))


@router.get('/teacher/students/{student_id}/reports/{report_id}')
def student_report(student_id: str, report_id: str, request: Request,
                   user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(FullReport, report_id)
    if row is None:
        raise ApiProblem(404, 'REPORT_NOT_FOUND', '报告不存在')
    _teacher_course(db, user, row.course_id)
    if row.user_id != student_id:
        raise ApiProblem(403, 'FORBIDDEN', '报告不属于指定学生')
    return respond(request, row.payload)


@router.patch('/teacher/courses/{course_id}')
def update_course(course_id: str, body: CourseWrite, request: Request,
                  user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = _teacher_course(db, user, course_id)
    row.name = body.title.strip()
    row.description = body.description
    db.commit()
    return respond(request, course_dto(db, row, user))


@router.get('/teacher/knowledge-points')
def knowledge_list(request: Request, course_id: str, q: str = '', active: bool | None = None,
                   page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
                   user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    items = [knowledge_dto(db, row) for row in course_points(db, course_id)]
    items = [item for item in items if q.casefold() in item['name'].casefold()
             and (active is None or item['active'] == active)]
    items.sort(key=lambda item: (item['sort_order'], item['knowledge_point_id']))
    return respond(request, page(items, page_no, page_size))


def _point_write(db: Session, user: User, body: KnowledgeWrite, point: KnowledgePoint | None) -> dict:
    _teacher_course(db, user, body.course_id)
    name = body.name.strip()
    if any(other.id != (point.id if point else None) and other.name.casefold() == name.casefold()
           for other in course_points(db, body.course_id)):
        raise ApiProblem(409, 'DUPLICATE_NAME', '课程内已有同名知识点')
    if point is not None and point.course_id != body.course_id:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '不能将知识点迁移到其他课程')
    if not body.active and point is not None:
        if any(point.id in question.knowledge_point_ids for question in course_questions(db, body.course_id)):
            raise ApiProblem(409, 'REFERENCE_CONFLICT', '该知识点仍关联启用题目')
    if point is None:
        point = KnowledgePoint(id='kp-' + uuid.uuid4().hex, course_id=body.course_id, name=name)
        db.add(point)
    else:
        point.name = name
    meta = db.get(KnowledgeMeta, point.id)
    if meta is None:
        meta = KnowledgeMeta(point_id=point.id, description=body.description,
                             sort_order=body.sort_order, active=body.active)
        db.add(meta)
    else:
        meta.description = body.description
        meta.sort_order = body.sort_order
        meta.active = body.active
    db.commit()
    return knowledge_dto(db, point)


@router.post('/teacher/knowledge-points', status_code=201)
def create_knowledge(body: KnowledgeWrite, request: Request,
                     user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    return respond(request, _point_write(db, user, body, None))


@router.patch('/teacher/knowledge-points/{point_id}')
def update_knowledge(point_id: str, body: KnowledgeWrite, request: Request,
                     user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    point = db.get(KnowledgePoint, point_id)
    if point is None:
        raise ApiProblem(404, 'NOT_FOUND', '知识点不存在')
    _teacher_course(db, user, point.course_id)
    return respond(request, _point_write(db, user, body, point))


@router.get('/teacher/questions')
def question_list(request: Request, course_id: str, type: str | None = None,
                  knowledge_point_id: str | None = None, active: bool | None = None,
                  page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
                  user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    items = [question_dto(db, row, teacher=True) for row in course_questions(
        db, course_id, include_inactive=True)]
    items = [item for item in items if (type is None or item['type'] == type)
             and (knowledge_point_id is None or knowledge_point_id in item['knowledge_point_ids'])
             and (active is None or item['active'] == active)]
    return respond(request, page(items, page_no, page_size))


@router.get('/teacher/questions/{question_id}')
def question_detail(question_id: str, request: Request,
                    user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(Question, question_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '题目不存在')
    _teacher_course(db, user, row.course_id)
    return respond(request, question_dto(db, row, teacher=True))


def _question_write(db: Session, user: User, body: QuestionWrite,
                    row: Question | None) -> dict:
    _teacher_course(db, user, body.course_id)
    if row is not None and row.course_id != body.course_id:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '不能将题目迁移到其他课程')
    points = {point.id for point in course_points(db, body.course_id)
              if (meta := db.get(KnowledgeMeta, point.id)) is None or meta.active}
    if not set(body.knowledge_point_ids) <= points:
        raise ApiProblem(422, 'VALIDATION_ERROR', '知识点不存在、已停用或不属于课程')
    old_ids = {option['id'] for option in row.options} if row else set()
    option_ids = {}
    options = []
    for option in body.options:
        if option.option_id and option.option_id not in old_ids:
            raise ApiProblem(422, 'INVALID_OPTIONS', '选项 ID 不属于本题')
        option_id = option.option_id or 'opt-' + uuid.uuid4().hex
        option_ids[option.client_key] = option_id
        options.append({'id': option_id, 'label': option.label, 'text': option.text.strip()})
    correct = [option_ids[key] for key in body.correct_option_keys]
    if row is None:
        row = Question(id='q-' + uuid.uuid4().hex, course_id=body.course_id,
                       stem=body.stem.strip(), kind='multiple' if body.type == 'multiple_choice' else 'single',
                       options=options, correct_option_ids=correct,
                       knowledge_point_ids=body.knowledge_point_ids)
        db.add(row)
    else:
        row.stem = body.stem.strip()
        row.kind = 'multiple' if body.type == 'multiple_choice' else 'single'
        row.options = options
        row.correct_option_ids = correct
        row.knowledge_point_ids = body.knowledge_point_ids
    meta = db.get(QuestionMeta, row.id)
    if meta is None:
        meta = QuestionMeta(question_id=row.id, difficulty=body.difficulty,
                            explanation=body.explanation, version=1)
        db.add(meta)
    else:
        meta.difficulty = body.difficulty
        meta.explanation = body.explanation
        meta.version += 1
    state = db.get(QuestionState, row.id)
    if state is None:
        db.add(QuestionState(question_id=row.id, active=body.active))
    else:
        state.active = body.active
    db.commit()
    return question_dto(db, row, teacher=True)


@router.post('/teacher/questions', status_code=201)
def create_question(body: QuestionWrite, request: Request,
                    user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    return respond(request, _question_write(db, user, body, None))


@router.patch('/teacher/questions/{question_id}')
def update_question(question_id: str, body: QuestionWrite, request: Request,
                    user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(Question, question_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '题目不存在')
    _teacher_course(db, user, row.course_id)
    return respond(request, _question_write(db, user, body, row))


def _resource_points(db: Session, course_id: str, point_ids: list[str]):
    active = {point.id for point in course_points(db, course_id)
              if (meta := db.get(KnowledgeMeta, point.id)) is None or meta.active}
    if len(set(point_ids)) != len(point_ids) or not set(point_ids) <= active:
        raise ApiProblem(422, 'VALIDATION_ERROR', '资料知识点不存在、已停用或不属于课程')


@router.get('/teacher/resources')
def resources(request: Request, course_id: str, kind: str | None = None,
              knowledge_point_id: str | None = None, active: bool | None = None,
              page_no: int = Query(1, alias='page', ge=1), page_size: int = Query(10, ge=1, le=50),
              user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    rows = list(db.scalars(select(Resource).where(Resource.course_id == course_id).order_by(Resource.resource_id)))
    items = [resource_dto(db, row, teacher=True) for row in rows]
    items = [item for item in items if (kind is None or item['kind'] == kind)
             and (knowledge_point_id is None or knowledge_point_id in item['knowledge_point_ids'])
             and (active is None or item['active'] == active)]
    return respond(request, page(items, page_no, page_size))


@router.get('/teacher/resources/{resource_id}')
def teacher_resource(resource_id: str, request: Request,
                     user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(Resource, resource_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '资料不存在')
    _teacher_course(db, user, row.course_id)
    return respond(request, resource_dto(db, row))


async def _write_resource(db: Session, user: User, body: ResourceWrite,
                          row: Resource | None) -> dict:
    _teacher_course(db, user, body.course_id)
    _resource_points(db, body.course_id, body.knowledge_point_ids)
    if row is not None and row.course_id != body.course_id:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '不能将资料迁移到其他课程')
    if row is None and body.kind == 'document':
        raise ApiProblem(422, 'VALIDATION_ERROR', '文档资料须通过文件上传创建')
    meta = db.get(ResourceMeta, row.resource_id) if row else None
    if row is not None and (meta.kind if meta else 'document') != body.kind:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '不能修改资料类型')
    resource_id = row.resource_id if row else 'res-' + uuid.uuid4().hex
    document_id = row.document_id if row else 'doc-' + uuid.uuid4().hex
    result = None
    if body.kind == 'note' or (body.kind == 'document' and row is not None):
        text = body.text_content if body.kind == 'note' else meta.text_content if meta else None
        if body.kind == 'document' and text is None:
            # 演示种子没有原文副本，不能假装已同步 C 的索引元信息。
            if row.title != body.title or row.knowledge_point_ids != body.knowledge_point_ids:
                raise ApiProblem(409, 'REFERENCE_CONFLICT', '该旧资料缺少正文，无法同步标题或知识点')
        elif text:
            try:
                result = await clients.ingest({'resource_id': resource_id, 'document_id': document_id,
                    'course_id': body.course_id, 'title': body.title.strip(), 'text': text,
                    'knowledge_point_ids': body.knowledge_point_ids, 'source': '教师课程材料'})
            except httpx.HTTPError as exc:
                raise ApiProblem(503, 'SERVICE_UNAVAILABLE', '资料索引服务暂不可用') from exc
    if row is not None and meta is None:
        meta = ResourceMeta(resource_id=row.resource_id, kind='document', description='',
                            difficulty='easy', active=True, version=1,
                            text_content=None, external_url=None, filename=None,
                            ingestion_task_id=None, error_code=None, error_message=None)
        db.add(meta)
    if row is None:
        row = Resource(resource_id=resource_id, document_id=document_id,
                       course_id=body.course_id, title=body.title.strip(), source='教师课程材料',
                       knowledge_point_ids=body.knowledge_point_ids,
                       status='indexed', index_version=result.get('index_version') if result else None,
                       chunk_count=result.get('chunks', 0) if result else 0,
                       updated_at=int(time.time()))
        db.add(row)
        meta = ResourceMeta(resource_id=resource_id, kind=body.kind,
                            description=body.description, difficulty=body.difficulty,
                            active=body.active, version=1,
                            text_content=body.text_content if body.kind == 'note' else None,
                            external_url=body.external_url if body.kind == 'external' else None,
                            filename=None, ingestion_task_id=None, error_code=None, error_message=None)
        db.add(meta)
    else:
        row.title = body.title.strip()
        row.knowledge_point_ids = body.knowledge_point_ids
        row.updated_at = int(time.time())
        if result:
            row.index_version = result.get('index_version')
            row.chunk_count = result.get('chunks', 0)
        meta.description = body.description
        meta.difficulty = body.difficulty
        meta.active = body.active
        meta.version += 1
        if body.kind == 'note':
            meta.text_content = body.text_content
        if body.kind == 'external':
            meta.external_url = body.external_url
    db.commit()
    return resource_dto(db, row)


@router.post('/teacher/resources', status_code=201)
async def create_resource(body: ResourceWrite, request: Request,
                          user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    return respond(request, await _write_resource(db, user, body, None))


@router.patch('/teacher/resources/{resource_id}')
async def update_resource(resource_id: str, body: ResourceWrite, request: Request,
                          user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(Resource, resource_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '资料不存在')
    _teacher_course(db, user, row.course_id)
    return respond(request, await _write_resource(db, user, body, row))


def _readable_resource(db: Session, user: User, resource_id: str) -> tuple[Resource, dict]:
    row = db.get(Resource, resource_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '资料不存在')
    allowed_course(db, user, row.course_id)
    detail = resource_dto(db, row)
    if detail['availability'] == 'removed':
        raise ApiProblem(410, 'RESOURCE_REMOVED', '资料已停用或移除')
    if detail['availability'] != 'available':
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '资料尚未可用')
    return row, detail


@router.get('/resources/{resource_id}')
def read_resource(resource_id: str, request: Request, document_id: str | None = None,
                  chunk_id: str | None = None, resource_version: str | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    row, detail = _readable_resource(db, user, resource_id)
    if resource_version is not None and resource_version != detail['resource_version']:
        raise ApiProblem(410, 'RESOURCE_REMOVED', '引用的资料版本已不可用')
    if document_id is not None and document_id != row.document_id:
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '文档不属于该资料')
    if chunk_id is not None:
        query = select(FullReport).where(FullReport.course_id == row.course_id)
        if user.role == 'student':
            query = query.where(FullReport.user_id == user.id)
        reports = list(db.scalars(query))
        if not any(any(ev['resource_id'] == resource_id and ev['chunk_id'] == chunk_id
                       for ev in report.payload['evidences']) for report in reports):
            raise ApiProblem(409, 'REFERENCE_CONFLICT', '片段不属于已授权报告')
    return respond(request, detail)


@router.get('/resources/{resource_id}/file')
def read_file(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row, detail = _readable_resource(db, user, resource_id)
    if not detail['file_available']:
        raise ApiProblem(404, 'NOT_FOUND', '该资料没有可下载文件')
    document = db.get(FullDocument, row.document_id)
    if document is None or document.status != 'completed':
        raise ApiProblem(409, 'REFERENCE_CONFLICT', '文件尚未可用')
    safe_name = document.filename.replace('\\', '/').split('/')[-1].replace('"', '_')
    fallback = ''.join(char if char.isascii() and char.isalnum() or char in '._-' else '_'
                       for char in safe_name) or 'download'
    return Response(content=document.content, media_type=document.content_type,
                    headers={'Content-Disposition': f'attachment; filename="{fallback}"; '
                                                    f"filename*=UTF-8''{quote(safe_name)}",
                             'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


def document_dto(row: FullDocument) -> dict:
    return {'document_id': row.id, 'resource_id': row.resource_id, 'course_id': row.course_id,
            'filename': row.filename, 'size_bytes': row.size_bytes,
            'content_type': row.content_type, 'version': row.version,
            'task_id': row.task_id, 'status': row.status,
            'error_code': row.error_code, 'error_message': row.error_message,
            'created_at': iso(row.created_at)}


@router.post('/teacher/documents', status_code=202)
async def upload_document(request: Request, background: BackgroundTasks,
                          course_id: str = Form(), title: str = Form(),
                          knowledge_point_ids: str = Form(), file: UploadFile = File(),
                          user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    _teacher_course(db, user, course_id)
    if not title.strip() or len(title.strip()) > 100:
        raise ApiProblem(422, 'VALIDATION_ERROR', '资料标题长度须为 1 至 100 字符')
    try:
        point_ids = json.loads(knowledge_point_ids)
    except (ValueError, TypeError):
        raise ApiProblem(422, 'VALIDATION_ERROR', '知识点字段须为 JSON 数组') from None
    if not isinstance(point_ids, list) or not point_ids or not all(isinstance(item, str) for item in point_ids):
        raise ApiProblem(422, 'VALIDATION_ERROR', '至少选择一个有效知识点')
    _resource_points(db, course_id, point_ids)
    filename = (file.filename or '').replace('\\', '/').split('/')[-1]
    suffix = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    mime = {'txt': 'text/plain', 'md': 'text/markdown', 'pdf': 'application/pdf'}.get(suffix)
    if mime is None:
        raise ApiProblem(415, 'UNSUPPORTED_FILE_TYPE', '仅支持 TXT、Markdown、文本型 PDF')
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ApiProblem(413, 'FILE_TOO_LARGE', '文件不能超过 10 MiB')
    if not raw:
        raise ApiProblem(422, 'VALIDATION_ERROR', '文件不能为空')
    if suffix == 'pdf' and not raw.startswith(b'%PDF-'):
        raise ApiProblem(415, 'UNSUPPORTED_FILE_TYPE', 'PDF 文件格式不正确')
    if suffix != 'pdf' and raw.startswith(b'%PDF-'):
        raise ApiProblem(415, 'UNSUPPORTED_FILE_TYPE', '文件扩展名与内容不一致')
    now = int(time.time())
    resource_id = 'res-' + uuid.uuid4().hex
    document_id = 'doc-' + uuid.uuid4().hex
    task_id = 'task-' + uuid.uuid4().hex
    resource = Resource(resource_id=resource_id, document_id=document_id, course_id=course_id,
                        title=title.strip(), source=f'教师上传/{filename}',
                        knowledge_point_ids=point_ids, status='processing', index_version=None,
                        chunk_count=0, updated_at=now)
    meta = ResourceMeta(resource_id=resource_id, kind='document', description='',
                        difficulty='easy', active=True, version=1, text_content=None,
                        external_url=None, filename=filename, ingestion_task_id=task_id,
                        error_code=None, error_message=None)
    document = FullDocument(id=document_id, resource_id=resource_id, course_id=course_id,
                            task_id=task_id, version='v1', filename=filename,
                            content_type=mime, size_bytes=len(raw), content=raw,
                            text=None, status='queued', created_at=now,
                            error_code=None, error_message=None)
    task = FullTask(id=task_id, user_id=user.id, course_id=course_id,
                    kind='document_ingestion', status='queued', attempt_id=None,
                    document_id=document_id, report_id=None, retry_count=0, retry_key=None,
                    created_at=now, updated_at=now, error_code=None, error_message=None)
    db.add_all([resource, meta, document, task])
    db.commit()
    accepted = {'document': document_dto(document), 'task': task_dto(task)}
    background.add_task(process_document_background, document_id, task_id)
    return respond(request, accepted)


async def process_document_background(document_id: str, task_id: str):
    with SessionLocal() as db:
        document = db.get(FullDocument, document_id)
        task = db.get(FullTask, task_id)
        if document and task:
            await process_document(db, document, task)


async def process_document(db: Session, document: FullDocument, task: FullTask):
    resource = db.get(Resource, document.resource_id)
    meta = db.get(ResourceMeta, document.resource_id)
    task.status = 'running'
    task.updated_at = int(time.time())
    document.status = 'running'
    db.commit()
    try:
        if document.content_type == 'application/pdf':
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(document.content))
            if reader.is_encrypted:
                raise ValueError('ENCRYPTED_DOCUMENT')
            if len(reader.pages) > 100:
                raise ValueError('PARSING_FAILED')
            text = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        else:
            text = document.content.decode('utf-8-sig')
        text = text.strip()
        if not text:
            raise ValueError('NO_TEXT')
        if len(text) > 200_000:
            raise ValueError('FILE_TOO_LARGE')
        result = await clients.ingest({'resource_id': resource.resource_id,
            'document_id': document.id, 'course_id': document.course_id,
            'title': resource.title, 'text': text,
            'knowledge_point_ids': resource.knowledge_point_ids,
            'source': resource.source})
    except ValueError as exc:
        code = str(exc) if str(exc) in {'NO_TEXT', 'ENCRYPTED_DOCUMENT', 'FILE_TOO_LARGE'} else 'PARSING_FAILED'
        message = {'NO_TEXT': '未提取到正文，请检查是否为扫描件。',
                   'ENCRYPTED_DOCUMENT': '加密 PDF 暂不支持。',
                   'FILE_TOO_LARGE': '提取正文超过 20 万字符。',
                   'PARSING_FAILED': '文件无法解析。'}[code]
    except Exception as exc:
        code, message = ('MODEL_UNAVAILABLE', '资料索引服务暂不可用。') if isinstance(exc, httpx.HTTPError) else (
            'PARSING_FAILED', '文件无法解析。')
    else:
        document.text = text
        document.status = 'completed'
        document.error_code = None
        document.error_message = None
        resource.status = 'indexed'
        resource.index_version = result.get('index_version')
        resource.chunk_count = result.get('chunks', 0)
        resource.updated_at = int(time.time())
        meta.text_content = text
        meta.error_code = None
        meta.error_message = None
        task.status = 'completed'
        task.updated_at = resource.updated_at
        task.error_code = None
        task.error_message = None
        db.commit()
        return
    document.status = 'failed'
    document.error_code = code
    document.error_message = message
    resource.status = 'failed'
    resource.updated_at = int(time.time())
    meta.error_code = code
    meta.error_message = message
    task.status = 'failed'
    task.updated_at = resource.updated_at
    task.error_code = code
    task.error_message = message
    db.commit()


@router.get('/teacher/documents/{document_id}')
def teacher_document(document_id: str, request: Request,
                     user: User = Depends(teacher_user), db: Session = Depends(get_db)):
    row = db.get(FullDocument, document_id)
    if row is None:
        raise ApiProblem(404, 'NOT_FOUND', '文档不存在')
    _teacher_course(db, user, row.course_id)
    return respond(request, document_dto(row))
