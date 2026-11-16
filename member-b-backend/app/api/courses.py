"""已发布课程目录、学生的课程及选退课。"""

from fastapi import APIRouter, Query, Request

from . import ok
from ..dependencies import CurrentUser, DbSession, StudentUser
from ..schemas import CourseStatus
from ..services import courses

router = APIRouter(prefix='/courses', tags=['课程与选课'])


@router.get('')
def list_courses(request: Request, user: CurrentUser, db: DbSession,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 keyword: str | None = Query(None, max_length=100)):
    return ok(request, courses.available_courses(db, user, page, page_size, keyword))


# 固定路径先注册，避免 mine 被当作 course_id。
@router.get('/mine')
def my_courses(request: Request, user: StudentUser, db: DbSession,
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               keyword: str | None = Query(None, max_length=100), status: CourseStatus | None = None):
    return ok(request, courses.enrolled_courses(db, user, page, page_size, keyword, status))


@router.get('/{course_id}')
def course_detail(course_id: str, request: Request, user: CurrentUser, db: DbSession):
    return ok(request, courses.course_detail(db, user, course_id))


@router.put('/{course_id}/enrollment')
def enroll(course_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, courses.set_enrollment(db, user, course_id))


@router.delete('/{course_id}/enrollment')
def withdraw(course_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, courses.set_enrollment(db, user, course_id, withdraw=True))


