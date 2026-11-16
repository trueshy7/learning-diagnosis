"""课程资料 CRUD、教师归属和学生选课权限；不调用 C/D。"""

from functools import wraps
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..models import (CourseEnrollment, CourseResource, KnowledgePoint, ResourceFile,
                      ResourceIndexState, ResourceKnowledgePoint)
from .courses import _course
from .resource_index import index_status, mark_pending


def operation(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        try:
            return function(db, *args, **kwargs)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            code = exc.orig.args[0] if getattr(exc.orig, 'args', ()) else None
            if code in (1062, 1451, 1452):
                raise HTTPException(409, '资料记录重复或关联数据冲突') from exc
            raise HTTPException(503, '资料服务暂不可用，请稍后重试') from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, '资料服务暂不可用，请稍后重试') from exc
    return wrapped


def _editable(course):
    if course.status == 'archived':
        raise HTTPException(409, '已归档课程的资料只允许查询')


def _teacher_resource(db, teacher, resource_id, *, lock=False):
    course_id = db.scalar(select(CourseResource.course_id).where(CourseResource.id == resource_id))
    if course_id is None:
        raise HTTPException(404, '资料不存在或无权访问')
    course = _course(db, course_id, teacher_id=teacher.id, lock=lock)
    query = select(CourseResource).where(CourseResource.id == resource_id, CourseResource.course_id == course.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    resource = db.scalar(query)
    if resource is None:
        raise HTTPException(404, '资料不存在或无权访问')
    return course, resource


def _student_course(db, student, course_id):
    course = _course(db, course_id)
    if course.status not in ('published', 'archived'):
        raise HTTPException(404, '课程不存在或无权访问')
    enrolled = db.scalar(select(CourseEnrollment).where(
        CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == student.id,
        CourseEnrollment.status == 'active',
    ))
    if enrolled is None:
        raise HTTPException(404, '课程不存在或无权访问')
    return course


def _validate_points(db, course_id, ids, *, lock=True):
    query = select(KnowledgePoint.id).where(
        KnowledgePoint.course_id == course_id, KnowledgePoint.status == 'active',
        KnowledgePoint.id.in_(ids),
    )
    if lock:
        query = query.with_for_update(read=True)
    found = db.scalars(query).all()
    if set(found) != set(ids):
        raise HTTPException(409, '知识点不存在、已停用或不属于当前课程')


def _links(db, resource_id, *, lock=False):
    query = select(ResourceKnowledgePoint).where(ResourceKnowledgePoint.resource_id == resource_id)
    if lock:
        query = query.with_for_update()
    return db.scalars(query.order_by(ResourceKnowledgePoint.knowledge_point_id)).all()


def _summary(resource, point_ids, state=None):
    return {key: getattr(resource, key) for key in (
        'id', 'course_id', 'title', 'source', 'version', 'status', 'created_at', 'updated_at',
    )} | {'knowledge_point_ids': sorted(point_ids), 'index_status': index_status(resource, state)}


def _detail(db, resource):
    files = db.scalars(select(ResourceFile).where(ResourceFile.resource_id == resource.id)).all()
    state = db.scalar(select(ResourceIndexState).where(ResourceIndexState.resource_id == resource.id))
    return _summary(resource, [link.knowledge_point_id for link in _links(db, resource.id)], state) | {
        'text': resource.text, 'original_file': _file_data(files[0]) if files else None,
    }


def _file_data(file):
    return {key: getattr(file, key) for key in (
        'id', 'resource_version', 'original_filename', 'media_type', 'size_bytes',
        'sha256', 'extraction_info', 'created_at',
    )}


def _write_links(db, resource, ids):
    db.add_all([ResourceKnowledgePoint(resource_id=resource.id, course_id=resource.course_id,
                                       knowledge_point_id=point_id) for point_id in ids])


def _create_record(db, teacher_id, course_id, body):
    course = _course(db, course_id, teacher_id=teacher_id, lock=True)
    _editable(course)
    _validate_points(db, course_id, body.knowledge_point_ids)
    now = int(time.time())
    resource = CourseResource(id=uuid.uuid4().hex, course_id=course_id, title=body.title,
                              text=body.text, source=body.source, version=1, status='active',
                              created_at=now, updated_at=now)
    db.add(resource)
    db.flush()
    _write_links(db, resource, body.knowledge_point_ids)
    mark_pending(db, resource, new=True)
    db.flush()
    return resource


@operation
def create_resource(db, teacher, course_id, body):
    resource = _create_record(db, teacher.id, course_id, body)
    data = _summary(resource, body.knowledge_point_ids) | {'text': resource.text, 'original_file': None}
    db.commit()
    return data


@operation
def teacher_detail(db, teacher, resource_id):
    _, resource = _teacher_resource(db, teacher, resource_id)
    return _detail(db, resource)


@operation
def update_resource(db, teacher, resource_id, body):
    course, resource = _teacher_resource(db, teacher, resource_id, lock=True)
    if resource.status == 'deleted':
        raise HTTPException(409, '资料已删除，不能修改')
    _editable(course)
    if body.expected_version != resource.version:
        raise HTTPException(409, '资料版本冲突，请重新获取详情后修改')
    old_ids = [link.knowledge_point_id for link in _links(db, resource.id, lock=True)]
    changes = body.model_dump(exclude_unset=True, exclude={'expected_version'})
    new_ids = changes.pop('knowledge_point_ids', None)
    if new_ids is not None:
        _validate_points(db, resource.course_id, new_ids)
    links_changed = new_ids is not None and set(new_ids) != set(old_ids)
    changed = links_changed or any(getattr(resource, key) != value for key, value in changes.items())
    if changed:
        if resource.version >= 2147483647:
            raise HTTPException(409, '资料版本已达到上限，不能继续修改')
        for key, value in changes.items():
            setattr(resource, key, value)
        if links_changed:
            db.execute(delete(ResourceKnowledgePoint).where(ResourceKnowledgePoint.resource_id == resource.id))
            _write_links(db, resource, new_ids)
        resource.version += 1
        resource.updated_at = int(time.time())
        mark_pending(db, resource)
        db.flush()
    files = db.scalars(select(ResourceFile).where(ResourceFile.resource_id == resource.id)).all()
    state = db.scalar(select(ResourceIndexState).where(ResourceIndexState.resource_id == resource.id))
    data = _summary(resource, new_ids if links_changed else old_ids, state) | {
        'text': resource.text, 'original_file': _file_data(files[0]) if files else None,
    }
    db.commit()
    return data


@operation
def delete_resource(db, teacher, resource_id):
    course, resource = _teacher_resource(db, teacher, resource_id, lock=True)
    if resource.status != 'deleted':
        _editable(course)
        if resource.version >= 2147483647:
            raise HTTPException(409, '资料版本已达到上限，不能继续修改')
        resource.status = 'deleted'
        resource.version += 1
        resource.updated_at = int(time.time())
        mark_pending(db, resource)
    data = {key: getattr(resource, key) for key in ('id', 'course_id', 'status', 'version', 'updated_at')}
    db.commit()
    return data


def _list(db, course_id, page, page_size, status, point_id, keyword):
    query = select(CourseResource).where(CourseResource.course_id == course_id, CourseResource.status == status)
    if keyword:
        query = query.where(CourseResource.title.contains(keyword.strip(), autoescape=True))
    if point_id:
        query = query.where(CourseResource.id.in_(select(ResourceKnowledgePoint.resource_id).where(
            ResourceKnowledgePoint.course_id == course_id, ResourceKnowledgePoint.knowledge_point_id == point_id)))
    total = db.scalar(select(func.count()).select_from(query.with_only_columns(CourseResource.id).subquery())) or 0
    # MEDIUMTEXT 正文不在列表查询中加载。
    columns = [getattr(CourseResource, key) for key in (
        'id', 'course_id', 'title', 'source', 'version', 'status', 'created_at', 'updated_at',
    )]
    records = db.execute(query.with_only_columns(*columns)
                         .order_by(CourseResource.updated_at.desc(), CourseResource.id)
                         .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [record.id for record in records]
    grouped = {resource_id: [] for resource_id in ids}
    files = {}
    states = {}
    if ids:
        links = db.scalars(select(ResourceKnowledgePoint).where(
            ResourceKnowledgePoint.course_id == course_id, ResourceKnowledgePoint.resource_id.in_(ids),
        )).all()
        for link in links:
            grouped[link.resource_id].append(link.knowledge_point_id)
        files = {file.resource_id: _file_data(file) for file in db.scalars(
            select(ResourceFile).where(ResourceFile.resource_id.in_(ids))).all()}
        states = {state.resource_id: state for state in db.scalars(
            select(ResourceIndexState).where(ResourceIndexState.resource_id.in_(ids))).all()}
    return {'items': [_summary(record, grouped[record.id], states.get(record.id))
                      | {'original_file': files.get(record.id)} for record in records],
            'total': total, 'page': page, 'page_size': page_size}


@operation
def teacher_list(db, teacher, course_id, page, page_size, status='active', point_id=None, keyword=None):
    _course(db, course_id, teacher_id=teacher.id)
    return _list(db, course_id, page, page_size, status, point_id, keyword)


@operation
def student_list(db, student, course_id, page, page_size, point_id=None, keyword=None):
    _student_course(db, student, course_id)
    return _list(db, course_id, page, page_size, 'active', point_id, keyword)


def _student_resource(db, student, resource_id):
    course_id = db.scalar(select(CourseResource.course_id).where(
        CourseResource.id == resource_id, CourseResource.status == 'active',
    ))
    if course_id is None:
        raise HTTPException(404, '资料不存在或无权访问')
    _student_course(db, student, course_id)
    resource = db.scalar(select(CourseResource).where(
        CourseResource.id == resource_id, CourseResource.course_id == course_id, CourseResource.status == 'active',
    ))
    if resource is None:
        raise HTTPException(404, '资料不存在或无权访问')
    return resource


@operation
def student_detail(db, student, resource_id):
    resource = _student_resource(db, student, resource_id)
    return _detail(db, resource)
