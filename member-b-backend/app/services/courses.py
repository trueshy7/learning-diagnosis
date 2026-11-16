"""课程管理与选课；写操作先锁课程，提交前提取返回值。"""

from collections import defaultdict
from functools import wraps
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Course, CourseChapter, CourseEnrollment, KnowledgePoint, User
from ..schemas import CourseCreateIn, CourseUpdateIn, ChapterCreateIn, KnowledgePointCreateIn


def database_operation(function):
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
            if code == 1062:
                raise HTTPException(409, '名称或关联记录已存在') from exc
            if code in (1451, 1452):
                raise HTTPException(409, '关联数据不存在或仍被引用') from exc
            raise HTTPException(503, '课程服务暂不可用，请稍后重试') from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, '课程服务暂不可用，请稍后重试') from exc
    return wrapped


def _course(db, course_id, *, teacher_id=None, lock=False):
    query = select(Course).where(Course.id == course_id)
    if teacher_id is not None:
        query = query.where(Course.teacher_id == teacher_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    course = db.scalar(query)
    if course is None:
        raise HTTPException(404, '课程不存在或无权访问')
    return course


def _course_data(course, enrollment_count=0):
    return {name: getattr(course, name) for name in (
        'id', 'name', 'description', 'teacher_id', 'status', 'created_at', 'updated_at',
    )} | {'enrollment_count': enrollment_count}


def _enrollment_count(db, course_id):
    return db.scalar(select(func.count()).select_from(CourseEnrollment).where(
        CourseEnrollment.course_id == course_id, CourseEnrollment.status == 'active',
    )) or 0


def _chapter_data(chapter):
    return {name: getattr(chapter, name) for name in (
        'id', 'course_id', 'name', 'description', 'sort_order', 'created_at', 'updated_at',
    )}


def _point_data(point):
    return {name: getattr(point, name) for name in (
        'id', 'course_id', 'chapter_id', 'name', 'description', 'sort_order', 'status',
    )}


def _tree(db, course_id, *, include_disabled):
    chapters = db.scalars(select(CourseChapter).where(CourseChapter.course_id == course_id)
                          .order_by(CourseChapter.sort_order, CourseChapter.id)).all()
    query = select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)
    if not include_disabled:
        query = query.where(KnowledgePoint.status == 'active')
    points = db.scalars(query.order_by(KnowledgePoint.sort_order, KnowledgePoint.id)).all()
    grouped = defaultdict(list)
    for point in points:
        grouped[point.chapter_id].append(_point_data(point))
    return [_chapter_data(chapter) | {'knowledge_points': grouped[chapter.id]} for chapter in chapters]


def _page(db, query, page, page_size, *, student_id=None):
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    courses = db.scalars(query.order_by(Course.created_at.desc(), Course.id)
                         .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [course.id for course in courses]
    counts, enrollments = {}, {}
    if ids:
        counts = dict(db.execute(select(CourseEnrollment.course_id, func.count()).where(
            CourseEnrollment.course_id.in_(ids), CourseEnrollment.status == 'active',
        ).group_by(CourseEnrollment.course_id)).all())
        if student_id is not None:
            enrollments = {row.course_id: row for row in db.scalars(select(CourseEnrollment).where(
                CourseEnrollment.course_id.in_(ids), CourseEnrollment.student_id == student_id,
                CourseEnrollment.status == 'active',
            )).all()}
    items = []
    for course in courses:
        item = _course_data(course, counts.get(course.id, 0))
        if student_id is not None:
            enrollment = enrollments.get(course.id)
            item |= {'is_enrolled': enrollment is not None,
                     'enrolled_at': enrollment.enrolled_at if enrollment else None}
        items.append(item)
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


def _filters(query, keyword, status=None):
    if keyword:
        query = query.where(Course.name.contains(keyword.strip(), autoescape=True))
    if status is not None:
        query = query.where(Course.status == status)
    return query


@database_operation
def create_course(db: Session, teacher: User, body: CourseCreateIn):
    now = int(time.time())
    course = Course(id=uuid.uuid4().hex, name=body.name, description=body.description,
                    teacher_id=teacher.id, status='draft', created_at=now, updated_at=now)
    db.add(course)
    db.flush()
    data = _course_data(course)
    db.commit()
    return data


@database_operation
def teacher_courses(db: Session, teacher: User, page, page_size, keyword, status):
    query = _filters(select(Course).where(Course.teacher_id == teacher.id), keyword, status)
    return _page(db, query, page, page_size)


@database_operation
def teacher_course_detail(db: Session, teacher: User, course_id):
    course = _course(db, course_id, teacher_id=teacher.id)
    return _course_data(course, _enrollment_count(db, course_id)) | {
        'chapters': _tree(db, course_id, include_disabled=True),
    }


@database_operation
def update_course(db: Session, teacher: User, course_id, body: CourseUpdateIn):
    course = _course(db, course_id, teacher_id=teacher.id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    target = changes.get('status', course.status)
    allowed = {'draft': {'draft', 'published', 'archived'},
               'published': {'published', 'archived'}, 'archived': {'archived'}}
    if target not in allowed[course.status]:
        raise HTTPException(409, '不允许该课程状态变更')
    if target == 'published' and course.status != 'published':
        point = db.scalar(select(KnowledgePoint.id).where(
            KnowledgePoint.course_id == course_id, KnowledgePoint.status == 'active',
        ).limit(1).with_for_update())
        if point is None:
            raise HTTPException(409, '发布课程前至少添加一个章节和有效知识点')
    changed = any(getattr(course, key) != value for key, value in changes.items())
    for key, value in changes.items():
        setattr(course, key, value)
    if changed:
        course.updated_at = int(time.time())
    db.flush()
    data = _course_data(course, _enrollment_count(db, course_id))
    db.commit()
    return data


def _editable_course(db, teacher, course_id):
    course = _course(db, course_id, teacher_id=teacher.id, lock=True)
    if course.status == 'archived':
        raise HTTPException(409, '已归档课程不能新增章节或知识点')
    return course


@database_operation
def create_chapter(db: Session, teacher: User, course_id, body: ChapterCreateIn):
    _editable_course(db, teacher, course_id)
    now = int(time.time())
    chapter = CourseChapter(id=uuid.uuid4().hex, course_id=course_id,
                            **body.model_dump(), created_at=now, updated_at=now)
    db.add(chapter)
    db.flush()
    data = _chapter_data(chapter)
    db.commit()
    return data


@database_operation
def create_knowledge_point(db: Session, teacher: User, course_id, chapter_id, body: KnowledgePointCreateIn):
    _editable_course(db, teacher, course_id)
    chapter = db.scalar(select(CourseChapter).where(
        CourseChapter.id == chapter_id, CourseChapter.course_id == course_id,
    ).with_for_update())
    if chapter is None:
        raise HTTPException(404, '章节不存在或不属于指定课程')
    point = KnowledgePoint(id=uuid.uuid4().hex, course_id=course_id, chapter_id=chapter_id, **body.model_dump())
    db.add(point)
    db.flush()
    data = _point_data(point)
    db.commit()
    return data


@database_operation
def available_courses(db: Session, user: User, page, page_size, keyword):
    query = _filters(select(Course).where(Course.status == 'published'), keyword)
    return _page(db, query, page, page_size, student_id=user.id if user.role == 'student' else None)


@database_operation
def enrolled_courses(db: Session, student: User, page, page_size, keyword, status):
    query = select(Course).join(CourseEnrollment, CourseEnrollment.course_id == Course.id).where(
        CourseEnrollment.student_id == student.id, CourseEnrollment.status == 'active',
    )
    return _page(db, _filters(query, keyword, status), page, page_size, student_id=student.id)


@database_operation
def course_detail(db: Session, user: User, course_id):
    course = _course(db, course_id)
    owner = user.role == 'teacher' and course.teacher_id == user.id
    enrollment = None
    if user.role == 'student':
        enrollment = db.scalar(select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == user.id,
            CourseEnrollment.status == 'active',
        ))
    enrolled = enrollment is not None
    if not owner and course.status != 'published' and not (enrolled and course.status == 'archived'):
        raise HTTPException(404, '课程不存在或无权访问')
    return _course_data(course, _enrollment_count(db, course_id)) | {
        'is_enrolled': enrolled,
        'enrolled_at': enrollment.enrolled_at if enrollment else None,
        'chapters': _tree(db, course_id, include_disabled=owner) if owner or enrolled else None,
    }


@database_operation
def set_enrollment(db: Session, student: User, course_id, *, withdraw=False):
    course = _course(db, course_id, lock=True)
    if not withdraw and course.status != 'published':
        raise HTTPException(409, '只能选择已发布的课程')
    enrollment = db.scalar(select(CourseEnrollment).where(
        CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == student.id,
    ).with_for_update().execution_options(populate_existing=True))
    now = int(time.time())
    if enrollment is None:
        if withdraw:
            raise HTTPException(404, '选课记录不存在')
        enrollment = CourseEnrollment(course_id=course_id, student_id=student.id,
                                      status='active', enrolled_at=now, updated_at=now)
        db.add(enrollment)
    elif withdraw and enrollment.status != 'withdrawn':
        enrollment.status = 'withdrawn'
        enrollment.updated_at = now
    elif not withdraw and enrollment.status == 'withdrawn':
        enrollment.status = 'active'
        enrollment.enrolled_at = now
        enrollment.updated_at = now
    db.flush()
    data = {name: getattr(enrollment, name) for name in (
        'course_id', 'student_id', 'status', 'enrolled_at', 'updated_at',
    )}
    db.commit()
    return data
