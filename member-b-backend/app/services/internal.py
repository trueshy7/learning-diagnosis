"""B 对 C/D 的数据出口；不执行分块、索引或诊断，不访问其他成员的数据库。"""

from functools import wraps
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..internal_schemas import ERROR_MESSAGES
from ..models import Course, CourseResource, DiagnosisTask, ExamAttempt, ResourceIndexState, ResourceKnowledgePoint
from . import exams
from .resource_index import content_hash, index_status


def operation(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        try:
            return function(db, *args, **kwargs)
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, '内部数据服务暂不可用，请稍后重试') from exc
    return wrapped


def _scoped(query, column, service):
    return query if '*' in service.course_ids else query.where(column.in_(service.course_ids))


def _course(db, service, course_id):
    if not service.allows(course_id):
        raise HTTPException(404, '课程不存在或无权访问')
    if db.scalar(select(Course.id).where(Course.id == course_id)) is None:
        raise HTTPException(404, '课程不存在或无权访问')


def _resource(db, service, resource_id, *, write=False):
    query = _scoped(select(CourseResource).where(CourseResource.id == resource_id),
                    CourseResource.course_id, service)
    resource = db.scalar(query.with_for_update(read=not write).execution_options(populate_existing=True))
    if resource is None:
        raise HTTPException(404, '资料不存在或无权访问')
    return resource


def _points(db, resource_id):
    return db.scalars(select(ResourceKnowledgePoint.knowledge_point_id).where(
        ResourceKnowledgePoint.resource_id == resource_id).order_by(ResourceKnowledgePoint.knowledge_point_id)
                      .with_for_update(read=True)).all()


def _state(db, resource_id, *, write=False):
    return db.scalar(select(ResourceIndexState).where(ResourceIndexState.resource_id == resource_id)
                     .with_for_update(read=not write).execution_options(populate_existing=True))


def _state_data(resource, state):
    return {
        'resource_version': resource.version,
        'status': index_status(resource, state),
        'indexed_version': state.indexed_version if state else None,
        'document_id': state.document_id if state else None,
        'indexed_hash': state.indexed_hash if state else None,
        'last_error': state.last_error if state else None,
        'acknowledged_at': state.acknowledged_at if state else None,
    }


def _page(records, limit):
    more = len(records) > limit
    items = records[:limit]
    return items, items[-1].id if more else None


@operation
def courses(db, service, after_id, limit):
    query = _scoped(select(Course), Course.id, service)
    if after_id is not None:
        query = query.where(Course.id > after_id)
    records = db.scalars(query.order_by(Course.id).limit(limit + 1)).all()
    items, cursor = _page(records, limit)
    return {'items': [{key: getattr(item, key) for key in ('id', 'name', 'status', 'updated_at')}
                      for item in items], 'next_after_id': cursor}


@operation
def resource_manifest(db, service, course_id, after_id, limit):
    _course(db, service, course_id)
    # 清单不读取大正文，保留 deleted 墓碑。重复全量扫描保证并发修改最终可见。
    columns = [getattr(CourseResource, key) for key in ('id', 'course_id', 'title', 'version', 'status', 'updated_at')]
    query = select(*columns).where(CourseResource.course_id == course_id)
    if after_id is not None:
        query = query.where(CourseResource.id > after_id)
    records = db.execute(query.order_by(CourseResource.id).limit(limit + 1)).all()
    items, cursor = _page(records, limit)
    states = {state.resource_id: state for state in db.scalars(select(ResourceIndexState).where(
        ResourceIndexState.resource_id.in_([item.id for item in items]))).all()} if items else {}
    return {'items': [{key: getattr(item, key) for key in ('id', 'course_id', 'title', 'version', 'status', 'updated_at')}
                      | {'index_status': index_status(item, states.get(item.id))} for item in items],
            'next_after_id': cursor}


@operation
def resource_detail(db, service, resource_id):
    resource = _resource(db, service, resource_id)
    # 资料共享锁在正文、标签、状态读取期间保留，避免混合不同业务版本。
    points = _points(db, resource.id) if resource.status == 'active' else []
    state = _state(db, resource.id)
    data = {key: getattr(resource, key) for key in ('id', 'course_id', 'title', 'version', 'status', 'updated_at')}
    data['index_state'] = _state_data(resource, state)
    if resource.status == 'active':
        data |= {'text': resource.text, 'source': resource.source, 'knowledge_point_ids': points,
                 'content_hash': content_hash(resource, points)}
    return data


@operation
def report_index_state(db, service, resource_id, body):
    resource = _resource(db, service, resource_id, write=True)
    if body.resource_version != resource.version:
        raise HTTPException(409, '资料版本已变化，请重新读取当前版本')
    if body.status == 'ready':
        if resource.status != 'active':
            raise HTTPException(409, '资料已删除，不能回报索引就绪')
        if body.content_hash != content_hash(resource, _points(db, resource.id)):
            raise HTTPException(409, '资料摘要不匹配，请重新读取当前版本')
    if body.status == 'deleted' and resource.status != 'deleted':
        raise HTTPException(409, '有效资料不能回报索引已删除')
    state = _state(db, resource.id, write=True)
    if state is None:
        state = ResourceIndexState(resource_id=resource.id, resource_version=resource.version, status='pending')
        db.add(state)
    current = index_status(resource, state)
    if current == 'ready':
        if body.status != 'ready' or state.document_id != body.document_id or state.indexed_hash != body.content_hash:
            raise HTTPException(409, '当前版本已索引成功，不能覆盖为其他结果')
        return _state_data(resource, state)
    if current == 'deleted':
        if body.status != 'deleted':
            raise HTTPException(409, '当前版本已确认删除，不能覆盖为其他结果')
        return _state_data(resource, state)
    error = ERROR_MESSAGES[body.error_code] if body.status == 'failed' else None
    if current == 'failed' and body.status == 'failed' and state.last_error == error:
        return _state_data(resource, state)
    state.resource_version = resource.version
    state.status = body.status
    state.last_error = error
    state.acknowledged_at = state.updated_at = int(time.time())
    if body.status == 'ready':
        state.indexed_version = resource.version
        state.document_id = body.document_id
        state.indexed_hash = body.content_hash
    elif body.status == 'deleted':
        state.indexed_version = state.document_id = state.indexed_hash = None
    db.flush()
    data = _state_data(resource, state)
    db.commit()
    return data


def _resource_catalog(db, attempt):
    # 已就绪记录仍校验当前正文摘要；知识点只暴露此次测验快照范围内的交集。
    records = db.scalars(select(CourseResource).join(ResourceIndexState).where(
        CourseResource.course_id == attempt.course_id, CourseResource.status == 'active',
        ResourceIndexState.status == 'ready', ResourceIndexState.resource_version == CourseResource.version,
        ResourceIndexState.indexed_version == CourseResource.version,
    ).order_by(CourseResource.id)).all()
    if not records:
        return []
    ids = [item.id for item in records]
    states = {state.resource_id: state for state in db.scalars(select(ResourceIndexState).where(
        ResourceIndexState.resource_id.in_(ids))).all()}
    grouped = {item: [] for item in ids}
    for link in db.scalars(select(ResourceKnowledgePoint).where(ResourceKnowledgePoint.resource_id.in_(ids))).all():
        grouped[link.resource_id].append(link.knowledge_point_id)
    allowed = {point['id'] for point in attempt.knowledge_snapshot}
    catalog = []
    for resource in records:
        state = states.get(resource.id)
        points = sorted(allowed.intersection(grouped[resource.id]))
        if not points or index_status(resource, state) != 'ready':
            continue
        if state.indexed_hash != content_hash(resource, grouped[resource.id]):
            continue
        catalog.append({'resource_id': resource.id, 'resource_version': resource.version,
                        'document_id': state.document_id, 'content_hash': state.indexed_hash,
                        'title': resource.title, 'knowledge_point_ids': points})
    return catalog


@operation
def diagnosis_input(db, service, attempt_id):
    query = _scoped(select(ExamAttempt.course_id).where(ExamAttempt.id == attempt_id),
                    ExamAttempt.course_id, service)
    course_id = db.scalar(query)
    if course_id is None:
        raise HTTPException(404, '测验记录不存在或无权访问')
    attempt = exams._attempt(db, attempt_id)
    # 已到期的记录沿用现有懒结算规则；仍在作答中的测验由 _result 拒绝导出。
    changed = exams._expire_if_due(db, attempt)
    data = build_diagnosis_input(db, attempt)
    if changed:
        db.commit()
    return data


def build_diagnosis_input(db, attempt):
    """只组装数据，不鉴权/提交；调用方负责锁定已完成测验与事务。"""
    result, baseline = exams.diagnosis_assessment(db, attempt)
    catalog = _resource_catalog(db, attempt)
    data = {
        'contract_version': 'b-internal-1', 'assessment_policy': 'kp-accuracy-v1',
        'attempt_id': attempt.id, 'exam_id': attempt.exam_id, 'course_id': attempt.course_id,
        'attempt_status': attempt.status, 'started_at': attempt.started_at, 'submitted_at': attempt.submitted_at,
        'score': result['score'], 'total_score': result['total_score'], 'percentage': result['percentage'],
        'knowledge_points': attempt.knowledge_snapshot, 'knowledge_point_stats': result['knowledge_points'],
        'graded_answers': [{'question_id': item['id'], 'answered': bool(item['selected_option_ids']),
                            **{key: value for key, value in item.items() if key != 'id'}}
                           for item in result['questions']],
        'baseline': None, 'resource_catalog': catalog,
        'warnings': [] if catalog else ['暂无可用的课程检索资料'],
    }
    if baseline is not None:
        # 不从当前题库或目录反推历史基准，保留已评分统计快照。
        data['baseline'] = {key: getattr(baseline, key) for key in ('exam_id', 'submitted_at')}
        data['baseline'] |= {'attempt_id': baseline.id, 'attempt_status': baseline.status,
                             'assessment_policy': 'kp-accuracy-v1',
                             'score': exams._number(baseline.score), 'total_score': exams._number(baseline.total_score),
                             'knowledge_points': baseline.knowledge_point_stats}
    return data


@operation
def diagnosis_task_input(db, service, task_id):
    query = _scoped(select(DiagnosisTask).join(ExamAttempt).where(DiagnosisTask.id == task_id),
                    ExamAttempt.course_id, service)
    task = db.scalar(query)
    if task is None:
        raise HTTPException(404, '诊断任务不存在或无权访问')
    if task.input_snapshot is None:
        raise HTTPException(409, '诊断任务尚未准备输入，请稍后重试')
    return {'task_id': task.id, 'attempt_id': task.attempt_id, 'input_hash': task.input_hash,
            'input': task.input_snapshot}
