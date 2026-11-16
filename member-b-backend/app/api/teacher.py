"""教师自己的课程、章节及知识点管理。"""

from fastapi import APIRouter, Query, Request

from . import ok
from ..dependencies import DbSession, TeacherUser
from ..schemas import ChapterCreateIn, CourseCreateIn, CourseStatus, CourseUpdateIn, KnowledgePointCreateIn
from ..services import courses

router = APIRouter(prefix='/teacher', tags=['教师课程'])


@router.post('/courses', status_code=201)
def create_course(body: CourseCreateIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, courses.create_course(db, user, body))


@router.get('/courses')
def list_courses(request: Request, user: TeacherUser, db: DbSession,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 keyword: str | None = Query(None, max_length=100), status: CourseStatus | None = None):
    return ok(request, courses.teacher_courses(db, user, page, page_size, keyword, status))


@router.get('/courses/{course_id}')
def course_detail(course_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, courses.teacher_course_detail(db, user, course_id))


@router.patch('/courses/{course_id}')
def update_course(course_id: str, body: CourseUpdateIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, courses.update_course(db, user, course_id, body))


@router.post('/courses/{course_id}/chapters', status_code=201)
def create_chapter(course_id: str, body: ChapterCreateIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, courses.create_chapter(db, user, course_id, body))


@router.post('/courses/{course_id}/chapters/{chapter_id}/knowledge-points', status_code=201)
def create_knowledge_point(course_id: str, chapter_id: str, body: KnowledgePointCreateIn,
                           request: Request, user: TeacherUser, db: DbSession):
    return ok(request, courses.create_knowledge_point(db, user, course_id, chapter_id, body))

