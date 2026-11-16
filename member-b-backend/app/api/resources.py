"""教师资料管理、PDF/DOCX 上传与学生阅读和鉴权下载。"""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from . import ok
from ..dependencies import DbSession, StudentUser, TeacherUser
from ..resource_schemas import ResourceCreateIn, ResourceUpdateIn, ResourceUploadIn
from ..services import resources, resource_files

router = APIRouter(tags=['课程资料'])
FILE_RESPONSES = {200: {'content': {media_type: {'schema': {'type': 'string', 'format': 'binary'}}
                                  for media_type in resource_files.MEDIA_TYPES.values()}}}


@router.post('/teacher/courses/{course_id}/resources', status_code=201)
def create_resource(course_id: str, body: ResourceCreateIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, resources.create_resource(db, user, course_id, body))


@router.post('/teacher/courses/{course_id}/resources/upload', status_code=201)
async def upload_resource(course_id: str, request: Request, user: TeacherUser, db: DbSession,
                          file: Annotated[UploadFile, File(description='PDF 或 DOCX，最大 10 MiB')],
                          title: Annotated[str, Form()],
                          knowledge_point_ids: Annotated[list[str], Form(
                              description='知识点 ID，可提交多个同名字段；兼容英文逗号分隔或 JSON 数组字符串',
                              examples=[['demo-kp-stack-concept', 'demo-kp-stack-operations']])],
                          source: Annotated[str, Form()] = '课程教师自编材料'):
    try:
        form = await request.form()
        allowed = {'file', 'title', 'source', 'knowledge_point_ids'}
        if set(form.keys()) - allowed:
            raise HTTPException(422, '文件上传表单包含未定义字段')
        if any(len(form.getlist(key)) != 1 for key in form.keys() if key != 'knowledge_point_ids'):
            raise HTTPException(422, '除知识点外，每个表单字段只能提交一次，一次只能上传一个文件')
        try:
            metadata = ResourceUploadIn(title=title, source=form.get('source', source),
                                        knowledge_point_ids=knowledge_point_ids)
        except ValidationError as exc:
            errors = [{**error, 'loc': ('body', *error['loc'])} for error in exc.errors()]
            raise RequestValidationError(errors) from exc
        data = await run_in_threadpool(resource_files.create_uploaded_resource, db, user, course_id, metadata, file)
        return ok(request, data)
    finally:
        await file.close()


@router.get('/teacher/courses/{course_id}/resources')
def teacher_resources(course_id: str, request: Request, user: TeacherUser, db: DbSession,
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                      status: Literal['active', 'deleted'] = 'active',
                      knowledge_point_id: str | None = Query(None, min_length=1, max_length=64),
                      keyword: str | None = Query(None, max_length=100)):
    return ok(request, resources.teacher_list(db, user, course_id, page, page_size,
                                             status, knowledge_point_id, keyword))


@router.get('/teacher/resources/{resource_id}')
def teacher_resource_detail(resource_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, resources.teacher_detail(db, user, resource_id))


@router.patch('/teacher/resources/{resource_id}')
def update_resource(resource_id: str, body: ResourceUpdateIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, resources.update_resource(db, user, resource_id, body))


@router.delete('/teacher/resources/{resource_id}')
def delete_resource(resource_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, resources.delete_resource(db, user, resource_id))


@router.get('/courses/{course_id}/resources')
def student_resources(course_id: str, request: Request, user: StudentUser, db: DbSession,
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                      knowledge_point_id: str | None = Query(None, min_length=1, max_length=64),
                      keyword: str | None = Query(None, max_length=100)):
    return ok(request, resources.student_list(db, user, course_id, page, page_size,
                                             knowledge_point_id, keyword))


@router.get('/resources/{resource_id}')
def student_resource_detail(resource_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, resources.student_detail(db, user, resource_id))


def _file_response(download):
    path, media_type, filename = download
    return FileResponse(path, media_type=media_type, filename=filename,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


@router.get('/teacher/resources/{resource_id}/file', response_class=FileResponse, responses=FILE_RESPONSES)
def teacher_original_file(resource_id: str, user: TeacherUser, db: DbSession):
    return _file_response(resource_files.teacher_download(db, user, resource_id))


@router.get('/resources/{resource_id}/file', response_class=FileResponse, responses=FILE_RESPONSES)
def student_original_file(resource_id: str, user: StudentUser, db: DbSession):
    return _file_response(resource_files.student_download(db, user, resource_id))
