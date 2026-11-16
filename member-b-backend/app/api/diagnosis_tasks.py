"""本人学生与所属教师查询、补建或重试诊断通知任务。"""

from fastapi import APIRouter, Request

from . import ok
from ..dependencies import DbSession, StudentUser, TeacherUser
from ..services.diagnosis_tasks import user_task

router = APIRouter(tags=['诊断任务'])


@router.get('/attempts/{attempt_id}/diagnosis-task', summary='学生查询本人测验的诊断任务')
def student_task(attempt_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, user_task(db, user, attempt_id))


@router.post('/attempts/{attempt_id}/diagnosis-task', status_code=202, summary='学生补建或重试本人诊断任务')
def student_create_task(attempt_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, user_task(db, user, attempt_id, create=True))


@router.get('/teacher/attempts/{attempt_id}/diagnosis-task', summary='教师查询所属课程的诊断任务')
def teacher_task(attempt_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, user_task(db, user, attempt_id, teacher=True))


@router.post('/teacher/attempts/{attempt_id}/diagnosis-task', status_code=202, summary='教师补建或重试诊断任务')
def teacher_create_task(attempt_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, user_task(db, user, attempt_id, teacher=True, create=True))
