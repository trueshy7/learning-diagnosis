"""仅限服务凭证访问的 B → C/D 数据接口。"""

from fastapi import APIRouter, Query, Request

from . import ok
from ..dependencies import DbSession
from ..internal_schemas import IndexStateIn
from ..internal_security import CService, DService
from ..services import internal

router = APIRouter(prefix='/internal', tags=['内部服务数据'])


@router.get('/courses', summary='C 查询授权课程清单')
def courses(request: Request, service: CService, db: DbSession,
            after_id: str | None = Query(None, min_length=1, max_length=64),
            limit: int = Query(100, ge=1, le=100)):
    return ok(request, internal.courses(db, service, after_id, limit))


@router.get('/courses/{course_id}/resources', summary='C 查询资料清单（含删除墓碑）')
def resource_manifest(course_id: str, request: Request, service: CService, db: DbSession,
                      after_id: str | None = Query(None, min_length=1, max_length=64),
                      limit: int = Query(100, ge=1, le=100)):
    return ok(request, internal.resource_manifest(db, service, course_id, after_id, limit))


@router.get('/resources/{resource_id}', summary='C 获取当前资料正文及摘要')
def resource_detail(resource_id: str, request: Request, service: CService, db: DbSession):
    return ok(request, internal.resource_detail(db, service, resource_id))


@router.put('/resources/{resource_id}/index-state', summary='C 回报当前版本索引或删除结果')
def report_index_state(resource_id: str, body: IndexStateIn, request: Request, service: CService, db: DbSession):
    return ok(request, internal.report_index_state(db, service, resource_id, body))


@router.get('/attempts/{attempt_id}/diagnosis-input', summary='D 获取完整已结束测验诊断输入')
def diagnosis_input(attempt_id: str, request: Request, service: DService, db: DbSession):
    return ok(request, internal.diagnosis_input(db, service, attempt_id))


@router.get('/diagnosis-tasks/{task_id}/input', summary='D 获取任务冻结的诊断输入')
def diagnosis_task_input(task_id: str, request: Request, service: DService, db: DbSession):
    return ok(request, internal.diagnosis_task_input(db, service, task_id))
