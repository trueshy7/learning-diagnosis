"""题库、试卷及学生正式测验接口。"""

from typing import Literal

from fastapi import APIRouter, Query, Request

from . import ok
from ..dependencies import DbSession, StudentUser, TeacherUser
from ..exam_schemas import AttemptStartIn, ExamIn, PaperIn, QuestionIn, SaveAnswersIn
from ..services import exams

router = APIRouter(tags=['测验业务'])


@router.post('/teacher/courses/{course_id}/questions', status_code=201)
def create_question(course_id: str, body: QuestionIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.create_question(db, user, course_id, body))


@router.get('/teacher/courses/{course_id}/questions')
def list_questions(course_id: str, request: Request, user: TeacherUser, db: DbSession,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   status: Literal['draft', 'active', 'disabled'] | None = None,
                   kind: Literal['single', 'multiple'] | None = None,
                   knowledge_point_id: str | None = Query(None, min_length=1, max_length=64),
                   keyword: str | None = Query(None, max_length=100)):
    return ok(request, exams.list_questions(db, user, course_id, page, page_size,
                                            status, kind, knowledge_point_id, keyword))


@router.get('/teacher/questions/{question_id}')
def question_detail(question_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.question_detail(db, user, question_id))


@router.put('/teacher/questions/{question_id}')
def update_question(question_id: str, body: QuestionIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.update_question(db, user, question_id, body))


@router.delete('/teacher/questions/{question_id}')
def disable_question(question_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.disable_question(db, user, question_id))


@router.post('/teacher/courses/{course_id}/exams', status_code=201)
def create_exam(course_id: str, body: ExamIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.create_exam(db, user, course_id, body))


@router.get('/teacher/courses/{course_id}/exams')
def teacher_exams(course_id: str, request: Request, user: TeacherUser, db: DbSession,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 status: Literal['draft', 'published', 'archived'] | None = None):
    return ok(request, exams.list_exams(db, user, course_id, page, page_size, status))


@router.get('/teacher/exams/{exam_id}')
def teacher_exam_detail(exam_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.teacher_exam_detail(db, user, exam_id))


@router.put('/teacher/exams/{exam_id}')
def update_exam(exam_id: str, body: ExamIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.update_exam(db, user, exam_id, body))


@router.put('/teacher/exams/{exam_id}/questions')
def set_paper(exam_id: str, body: PaperIn, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.set_paper(db, user, exam_id, body))


@router.post('/teacher/exams/{exam_id}/publish')
def publish_exam(exam_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.publish_exam(db, user, exam_id))


@router.post('/teacher/exams/{exam_id}/archive')
def archive_exam(exam_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.archive_exam(db, user, exam_id))


@router.get('/teacher/exams/{exam_id}/results')
def teacher_results(exam_id: str, request: Request, user: TeacherUser, db: DbSession,
                    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                    student_id: int | None = Query(None, ge=1)):
    return ok(request, exams.teacher_results(db, user, exam_id, page, page_size, student_id))


@router.get('/teacher/attempts/{attempt_id}/result')
def teacher_attempt_result(attempt_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.teacher_attempt_result(db, user, attempt_id))


@router.get('/teacher/attempts/{attempt_id}/diagnosis-input')
def diagnosis_input(attempt_id: str, request: Request, user: TeacherUser, db: DbSession):
    return ok(request, exams.diagnosis_input(db, user, attempt_id))


@router.get('/courses/{course_id}/exams')
def available_exams(course_id: str, request: Request, user: StudentUser, db: DbSession,
                    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return ok(request, exams.list_exams(db, user, course_id, page, page_size))


@router.get('/courses/{course_id}/attempts')
def my_attempts(course_id: str, request: Request, user: StudentUser, db: DbSession,
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return ok(request, exams.my_attempts(db, user, course_id, page, page_size))


@router.post('/exams/{exam_id}/attempts')
def start_attempt(exam_id: str, request: Request, user: StudentUser, db: DbSession,
                  body: AttemptStartIn | None = None):
    return ok(request, exams.start_attempt(db, user, exam_id, body or AttemptStartIn()))


@router.get('/attempts/{attempt_id}')
def attempt_detail(attempt_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, exams.attempt_detail(db, user, attempt_id))


@router.put('/attempts/{attempt_id}/answers')
def save_answers(attempt_id: str, body: SaveAnswersIn, request: Request, user: StudentUser, db: DbSession):
    return ok(request, exams.save_answers(db, user, attempt_id, body))


@router.post('/attempts/{attempt_id}/submit')
def submit_attempt(attempt_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, exams.submit_attempt(db, user, attempt_id))


@router.get('/attempts/{attempt_id}/result')
def attempt_result(attempt_id: str, request: Request, user: StudentUser, db: DbSession):
    return ok(request, exams.attempt_result(db, user, attempt_id))
