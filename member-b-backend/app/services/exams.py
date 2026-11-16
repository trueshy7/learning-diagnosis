"""教师题库、固定试卷、学生作答和评分的数据库事务。"""

from functools import wraps
from decimal import Decimal
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .. import config
from ..models import (Course, CourseEnrollment, KnowledgePoint, Question, QuestionOption,
                      QuestionKnowledgePoint, Exam, ExamQuestion, ExamAttempt, ExamAnswer)
from .assessment import compare_statistics, grade_paper
from .courses import _course


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
                raise HTTPException(409, '测验记录重复或关联数据冲突') from exc
            raise HTTPException(503, '测验服务暂不可用，请稍后重试') from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, '测验服务暂不可用，请稍后重试') from exc
    return wrapped


def _number(value):
    return float(Decimal(value).quantize(Decimal('0.01'))) if value is not None else None


def _editable_course(db, teacher, course_id):
    course = _course(db, course_id, teacher_id=teacher.id, lock=True)
    if course.status == 'archived':
        raise HTTPException(409, '已归档课程不能维护题库或试卷')
    return course


def _teacher_object(db, model, identity, teacher, *, editable=False):
    course_id = db.scalar(select(model.course_id).where(model.id == identity))
    if course_id is None:
        raise HTTPException(404, '题目或试卷不存在或无权访问')
    if editable:
        _editable_course(db, teacher, course_id)
    else:
        _course(db, course_id, teacher_id=teacher.id)
    row = db.scalar(select(model).where(model.id == identity).with_for_update()
                    .execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, '题目或试卷不存在或无权访问')
    return row


def _active_point(db, course_id, point_id):
    point = db.scalar(select(KnowledgePoint).where(
        KnowledgePoint.id == point_id, KnowledgePoint.course_id == course_id,
        KnowledgePoint.status == 'active',
    ).with_for_update(read=True))
    if point is None:
        raise HTTPException(409, '知识点不存在、已停用或不属于当前课程')
    return point


def _question_snapshot(db, question):
    options = db.scalars(select(QuestionOption).where(QuestionOption.question_id == question.id)
                         .order_by(QuestionOption.sort_order).with_for_update(read=True)).all()
    points = db.scalars(select(KnowledgePoint).join(
        QuestionKnowledgePoint, QuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
    ).where(QuestionKnowledgePoint.question_id == question.id,
            QuestionKnowledgePoint.course_id == question.course_id).with_for_update(read=True)).all()
    return {'id': question.id, 'kind': question.kind, 'stem': question.stem,
            'explanation': question.explanation,
            'options': [{'id': option.id, 'label': option.label, 'text': option.text,
                         'is_correct': option.is_correct} for option in options],
            'knowledge_points': [{'id': point.id, 'name': point.name, 'status': point.status} for point in points]}


def _question_data(db, question):
    data = _question_snapshot(db, question)
    return data | {'course_id': question.course_id, 'status': question.status,
                   'created_at': question.created_at, 'updated_at': question.updated_at,
                   'knowledge_point_ids': [point['id'] for point in data['knowledge_points']]}


def _write_question_children(db, question, body):
    for position, option in enumerate(body.options):
        db.add(QuestionOption(id=uuid.uuid4().hex, question_id=question.id,
                              **option.model_dump(), sort_order=position))
    db.add(QuestionKnowledgePoint(course_id=question.course_id, question_id=question.id,
                                  knowledge_point_id=body.knowledge_point_ids[0]))
    db.flush()


@operation
def create_question(db, teacher, course_id, body):
    _editable_course(db, teacher, course_id)
    _active_point(db, course_id, body.knowledge_point_ids[0])
    now = int(time.time())
    question = Question(id=uuid.uuid4().hex, course_id=course_id, kind=body.kind,
                        stem=body.stem, explanation=body.explanation, status=body.status,
                        created_at=now, updated_at=now)
    db.add(question)
    db.flush()
    _write_question_children(db, question, body)
    data = _question_data(db, question)
    db.commit()
    return data


@operation
def question_detail(db, teacher, question_id):
    return _question_data(db, _teacher_object(db, Question, question_id, teacher))


@operation
def update_question(db, teacher, question_id, body):
    question = _teacher_object(db, Question, question_id, teacher, editable=True)
    _active_point(db, question.course_id, body.knowledge_point_ids[0])
    db.execute(delete(QuestionOption).where(QuestionOption.question_id == question.id))
    db.execute(delete(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id == question.id))
    for field in ('kind', 'stem', 'explanation', 'status'):
        setattr(question, field, getattr(body, field))
    question.updated_at = int(time.time())
    _write_question_children(db, question, body)
    data = _question_data(db, question)
    db.commit()
    return data


@operation
def disable_question(db, teacher, question_id):
    question = _teacher_object(db, Question, question_id, teacher, editable=True)
    question.status = 'disabled'
    question.updated_at = int(time.time())
    data = {'id': question.id, 'status': question.status}
    db.commit()
    return data


def _page(db, query, page, page_size, model):
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(model.created_at.desc(), model.id)
                         .offset((page - 1) * page_size).limit(page_size)).all()
    return total, records


@operation
def list_questions(db, teacher, course_id, page, page_size, status, kind, point_id, keyword):
    _course(db, course_id, teacher_id=teacher.id)
    query = select(Question).where(Question.course_id == course_id)
    if status:
        query = query.where(Question.status == status)
    if kind:
        query = query.where(Question.kind == kind)
    if keyword:
        query = query.where(Question.stem.contains(keyword.strip(), autoescape=True))
    if point_id:
        query = query.where(Question.id.in_(select(QuestionKnowledgePoint.question_id).where(
            QuestionKnowledgePoint.course_id == course_id, QuestionKnowledgePoint.knowledge_point_id == point_id)))
    total, records = _page(db, query, page, page_size, Question)
    return {'items': [{key: getattr(row, key) for key in (
        'id', 'course_id', 'kind', 'stem', 'status', 'created_at', 'updated_at',
    )} for row in records], 'total': total, 'page': page, 'page_size': page_size}


def _exam_data(exam):
    return {key: getattr(exam, key) for key in (
        'id', 'course_id', 'title', 'status', 'duration_seconds', 'question_count', 'created_at', 'updated_at',
    )} | {'total_score': _number(exam.total_score)}


def _paper(db, exam_id):
    return db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
                      .order_by(ExamQuestion.sort_order).with_for_update(read=True)).all()


def _require_draft(exam):
    if exam.status != 'draft':
        raise HTTPException(409, '只有草稿试卷可以修改，已发布内容保持不变')


@operation
def create_exam(db, teacher, course_id, body):
    _editable_course(db, teacher, course_id)
    now = int(time.time())
    exam = Exam(id=uuid.uuid4().hex, course_id=course_id, **body.model_dump(), status='draft',
                question_count=0, total_score=Decimal('0'), knowledge_snapshot=[], created_at=now, updated_at=now)
    db.add(exam)
    db.flush()
    data = _exam_data(exam)
    db.commit()
    return data


@operation
def update_exam(db, teacher, exam_id, body):
    exam = _teacher_object(db, Exam, exam_id, teacher, editable=True)
    _require_draft(exam)
    exam.title, exam.duration_seconds = body.title, body.duration_seconds
    exam.updated_at = int(time.time())
    data = _exam_data(exam)
    db.commit()
    return data


@operation
def set_paper(db, teacher, exam_id, body):
    exam = _teacher_object(db, Exam, exam_id, teacher, editable=True)
    _require_draft(exam)
    ids = [item.question_id for item in body.questions]
    questions = db.scalars(select(Question).where(Question.course_id == exam.course_id, Question.id.in_(ids))
                           .with_for_update()).all()
    if len(questions) != len(ids) or any(question.status != 'active' for question in questions):
        raise HTTPException(409, '试卷题目必须存在、已启用且属于当前课程')
    db.execute(delete(ExamQuestion).where(ExamQuestion.exam_id == exam.id))
    for position, item in enumerate(body.questions):
        db.add(ExamQuestion(exam_id=exam.id, course_id=exam.course_id, question_id=item.question_id,
                            sort_order=position, score=item.score, snapshot=None))
    exam.question_count = len(body.questions)
    exam.total_score = sum((item.score for item in body.questions), Decimal('0'))
    exam.updated_at = int(time.time())
    db.flush()
    data = _exam_data(exam)
    db.commit()
    return data


@operation
def publish_exam(db, teacher, exam_id):
    exam = _teacher_object(db, Exam, exam_id, teacher, editable=True)
    if exam.status == 'published':
        data = _exam_data(exam)
        db.commit()
        return data
    _require_draft(exam)
    course = _course(db, exam.course_id, teacher_id=teacher.id, lock=True)
    if course.status != 'published':
        raise HTTPException(409, '只有已发布课程可以发布测验')
    paper = _paper(db, exam.id)
    if not paper:
        raise HTTPException(409, '试卷至少包含一道题目')
    for item in paper:
        question = db.scalar(select(Question).where(Question.id == item.question_id).with_for_update())
        if question is None or question.status != 'active' or question.course_id != exam.course_id:
            raise HTTPException(409, '试卷存在不可用题目')
        snapshot = _question_snapshot(db, question)
        correct_count = sum(option['is_correct'] for option in snapshot['options'])
        if (len(snapshot['options']) < 2 or len(snapshot['knowledge_points']) != 1
                or snapshot['knowledge_points'][0]['status'] != 'active'
                or (question.kind == 'single' and correct_count != 1)
                or (question.kind == 'multiple' and correct_count < 2)):
            raise HTTPException(409, '题目选项、标准答案或知识点关联不完整')
        item.snapshot = snapshot
    points = db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == exam.course_id, KnowledgePoint.status == 'active',
    ).order_by(KnowledgePoint.id).with_for_update(read=True)).all()
    exam.knowledge_snapshot = [{'id': point.id, 'name': point.name} for point in points]
    exam.question_count = len(paper)
    exam.total_score = sum((item.score for item in paper), Decimal('0'))
    exam.status, exam.updated_at = 'published', int(time.time())
    data = _exam_data(exam)
    db.commit()
    return data


@operation
def archive_exam(db, teacher, exam_id):
    exam = _teacher_object(db, Exam, exam_id, teacher)
    exam.status, exam.updated_at = 'archived', int(time.time())
    data = _exam_data(exam)
    db.commit()
    return data


@operation
def teacher_exam_detail(db, teacher, exam_id):
    exam = _teacher_object(db, Exam, exam_id, teacher)
    questions = []
    for item in _paper(db, exam.id):
        snapshot = item.snapshot
        if snapshot is None:
            question = db.scalar(select(Question).where(Question.id == item.question_id).with_for_update(read=True))
            snapshot = _question_snapshot(db, question)
        questions.append(snapshot | {'score': _number(item.score), 'sort_order': item.sort_order})
    return _exam_data(exam) | {'questions': questions}


@operation
def list_exams(db, user, course_id, page, page_size, status=None):
    course = _course(db, course_id, teacher_id=user.id if user.role == 'teacher' else None)
    query = select(Exam).where(Exam.course_id == course_id)
    if user.role == 'student':
        enrolled = db.scalar(select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == user.id,
            CourseEnrollment.status == 'active',
        ))
        if enrolled is None or course.status == 'draft':
            raise HTTPException(404, '课程不存在或无权访问')
        query = query.where(Exam.status == 'published')
    elif status:
        query = query.where(Exam.status == status)
    total, records = _page(db, query, page, page_size, Exam)
    return {'items': [_exam_data(row) for row in records], 'total': total, 'page': page,
            'page_size': page_size, 'course_status': course.status}


def _attempt_data(attempt):
    return {key: getattr(attempt, key) for key in (
        'id', 'exam_id', 'course_id', 'student_id', 'baseline_attempt_id', 'status',
        'started_at', 'expires_at', 'submitted_at',
    )} | {'score': _number(attempt.score), 'total_score': _number(attempt.total_score),
         'server_time': int(time.time())}


def _attempt(db, attempt_id, student_id=None):
    query = select(ExamAttempt).where(ExamAttempt.id == attempt_id)
    if student_id is not None:
        query = query.where(ExamAttempt.student_id == student_id)
    attempt = db.scalar(query.with_for_update().execution_options(populate_existing=True))
    if attempt is None:
        raise HTTPException(404, '测验记录不存在或无权访问')
    return attempt


def _snapshot_paper(db, exam_id):
    paper = _paper(db, exam_id)
    if not paper or any(item.snapshot is None for item in paper):
        raise HTTPException(409, '试卷快照不完整')
    return paper


def _answers(db, attempt):
    return db.scalars(select(ExamAnswer).where(ExamAnswer.attempt_id == attempt.id)
                      .with_for_update()).all()


def _finalize(db, attempt, *, expired):
    if attempt.status != 'in_progress':
        return
    paper = _snapshot_paper(db, attempt.exam_id)
    answers = {answer.question_id: answer for answer in _answers(db, attempt)}
    total, grades, stats = grade_paper(
        [{'question_id': item.question_id, 'score': item.score, 'snapshot': item.snapshot} for item in paper],
        {key: value.selected_option_ids for key, value in answers.items()}, attempt.knowledge_snapshot,
    )
    now = int(time.time())
    for grade in grades:
        answer = answers.get(grade['question_id'])
        if answer is None:
            answer = ExamAnswer(attempt_id=attempt.id, exam_id=attempt.exam_id,
                                question_id=grade['question_id'], selected_option_ids=[], revision=0, updated_at=now)
            db.add(answer)
        answer.correct, answer.score = grade['correct'], grade['score']
    attempt.score, attempt.knowledge_point_stats = total, stats
    attempt.status = 'expired' if expired else 'submitted'
    attempt.submitted_at = attempt.expires_at if expired else now
    db.flush()
    if config.DIAGNOSIS_AUTO_ENQUEUE:
        from .diagnosis_tasks import ensure_task
        ensure_task(db, attempt)
        db.flush()


def _expire_if_due(db, attempt):
    if attempt.status == 'in_progress' and int(time.time()) >= attempt.expires_at:
        _finalize(db, attempt, expired=True)
        return True
    return False


@operation
def start_attempt(db, student, exam_id, body):
    course_id = db.scalar(select(Exam.course_id).where(Exam.id == exam_id))
    if course_id is None:
        raise HTTPException(404, '试卷不存在或无权访问')
    course = _course(db, course_id, lock=True)
    exam = db.scalar(select(Exam).where(Exam.id == exam_id).with_for_update()
                     .execution_options(populate_existing=True))
    if exam is None:
        raise HTTPException(404, '试卷不存在或无权访问')
    existing = db.scalar(select(ExamAttempt).where(
        ExamAttempt.exam_id == exam_id, ExamAttempt.student_id == student.id,
    ).with_for_update().execution_options(populate_existing=True))
    if existing:
        if body.baseline_attempt_id is not None and body.baseline_attempt_id != existing.baseline_attempt_id:
            raise HTTPException(409, '测验已开始，不能修改复测基准')
        _expire_if_due(db, existing)
        data = _attempt_data(existing)
        db.commit()
        return data
    enrolled = db.scalar(select(CourseEnrollment).where(
        CourseEnrollment.course_id == course_id, CourseEnrollment.student_id == student.id,
        CourseEnrollment.status == 'active',
    ).with_for_update(read=True))
    if enrolled is None:
        raise HTTPException(404, '课程不存在或无权访问')
    if course.status != 'published' or exam.status != 'published':
        raise HTTPException(409, '只有已发布课程中的已发布试卷允许开始测验')
    baseline_id = body.baseline_attempt_id
    if baseline_id:
        baseline = db.scalar(select(ExamAttempt).where(
            ExamAttempt.id == baseline_id, ExamAttempt.student_id == student.id,
            ExamAttempt.course_id == course_id,
        ).with_for_update(read=True))
        if baseline is None or baseline.status == 'in_progress' or baseline.exam_id == exam_id:
            raise HTTPException(409, '复测基准必须是本人同课程另一份试卷的已完成测验')
    paper = _snapshot_paper(db, exam.id)
    now = int(time.time())
    attempt = ExamAttempt(id=uuid.uuid4().hex, exam_id=exam.id, course_id=course_id, student_id=student.id,
                          baseline_attempt_id=baseline_id, status='in_progress', started_at=now,
                          expires_at=now + exam.duration_seconds, submitted_at=None, score=None,
                          total_score=exam.total_score, knowledge_snapshot=exam.knowledge_snapshot,
                          knowledge_point_stats=None)
    db.add(attempt)
    db.flush()
    for item in paper:
        db.add(ExamAnswer(attempt_id=attempt.id, exam_id=exam.id, question_id=item.question_id,
                          selected_option_ids=[], revision=0, correct=None, score=None, updated_at=now))
    db.flush()
    data = _attempt_data(attempt)
    db.commit()
    return data


def _public_question(item):
    snapshot = item.snapshot
    return {'id': item.question_id, 'kind': snapshot['kind'], 'stem': snapshot['stem'],
            'options': [{key: option[key] for key in ('id', 'label', 'text')} for option in snapshot['options']],
            'knowledge_point_ids': [point['id'] for point in snapshot['knowledge_points']],
            'score': _number(item.score), 'sort_order': item.sort_order}


@operation
def attempt_detail(db, student, attempt_id):
    attempt = _attempt(db, attempt_id, student.id)
    expired = _expire_if_due(db, attempt)
    data = _attempt_data(attempt) | {
        'questions': [_public_question(item) for item in _snapshot_paper(db, attempt.exam_id)],
        'answers': [{'question_id': answer.question_id, 'selected_option_ids': answer.selected_option_ids,
                     'revision': answer.revision} for answer in _answers(db, attempt)],
    }
    if expired:
        db.commit()
    return data


@operation
def save_answers(db, student, attempt_id, body):
    attempt = _attempt(db, attempt_id, student.id)
    if _expire_if_due(db, attempt):
        db.commit()
        raise HTTPException(409, '测验已超时并结算，请查看结果')
    if attempt.status != 'in_progress':
        raise HTTPException(409, '测验已结束，不能修改答案')
    paper = {item.question_id: item for item in _snapshot_paper(db, attempt.exam_id)}
    answers = {answer.question_id: answer for answer in _answers(db, attempt)}
    # 先校验整批再写入，任一冲突不部分保存。
    for item in body.answers:
        question = paper.get(item.question_id)
        answer = answers.get(item.question_id)
        if question is None or answer is None:
            raise HTTPException(422, '题目不属于本次测验')
        allowed = {option['id'] for option in question.snapshot['options']}
        if not set(item.selected_option_ids) <= allowed:
            raise HTTPException(422, '选项不属于对应题目')
        if question.snapshot['kind'] == 'single' and len(item.selected_option_ids) > 1:
            raise HTTPException(422, '单选题最多选择一个选项')
        if item.revision != answer.revision:
            raise HTTPException(409, '答案版本冲突，请重新获取最新答案')
    now = int(time.time())
    for item in body.answers:
        answer = answers[item.question_id]
        answer.selected_option_ids = list(item.selected_option_ids)
        answer.revision += 1
        answer.updated_at = now
    data = {'attempt_id': attempt.id, 'answers': [
        {'question_id': item.question_id, 'revision': answers[item.question_id].revision,
         'selected_option_ids': answers[item.question_id].selected_option_ids} for item in body.answers]}
    db.commit()
    return data


def _result(db, attempt):
    if attempt.status == 'in_progress':
        raise HTTPException(409, '测验尚未结束')
    paper = _snapshot_paper(db, attempt.exam_id)
    answers = {answer.question_id: answer for answer in _answers(db, attempt)}
    details = []
    for item in paper:
        answer = answers[item.question_id]
        details.append(_public_question(item) | {
            'selected_option_ids': answer.selected_option_ids,
            'correct_option_ids': [option['id'] for option in item.snapshot['options'] if option['is_correct']],
            'correct': answer.correct, 'earned_score': _number(answer.score),
            'explanation': item.snapshot['explanation'],
        })
    comparison = []
    if attempt.baseline_attempt_id:
        baseline = db.scalar(select(ExamAttempt).where(ExamAttempt.id == attempt.baseline_attempt_id)
                             .with_for_update(read=True))
        comparison = compare_statistics(baseline.knowledge_point_stats or [], attempt.knowledge_point_stats or [])
    return _attempt_data(attempt) | {'questions': details,
        'knowledge_points': attempt.knowledge_point_stats, 'comparison': comparison,
        'percentage': round(float(attempt.score / attempt.total_score * 100), 2)}


@operation
def submit_attempt(db, student, attempt_id):
    attempt = _attempt(db, attempt_id, student.id)
    _finalize(db, attempt, expired=int(time.time()) >= attempt.expires_at)
    data = _result(db, attempt)
    db.commit()
    return data


@operation
def attempt_result(db, student, attempt_id):
    attempt = _attempt(db, attempt_id, student.id)
    expired = _expire_if_due(db, attempt)
    data = _result(db, attempt)
    if expired:
        db.commit()
    return data


@operation
def my_attempts(db, student, course_id, page, page_size):
    query = select(ExamAttempt).where(ExamAttempt.student_id == student.id, ExamAttempt.course_id == course_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(ExamAttempt.started_at.desc(), ExamAttempt.id)
                         .offset((page - 1) * page_size).limit(page_size).with_for_update()).all()
    changed = False
    for attempt in records:
        changed = _expire_if_due(db, attempt) or changed
    data = {'items': [_attempt_data(attempt) for attempt in records], 'total': total,
            'page': page, 'page_size': page_size}
    if changed:
        db.commit()
    return data


def _teacher_attempt(db, teacher, attempt_id):
    course_id = db.scalar(select(ExamAttempt.course_id).where(ExamAttempt.id == attempt_id))
    if course_id is None:
        raise HTTPException(404, '测验记录不存在或无权访问')
    _course(db, course_id, teacher_id=teacher.id)
    return _attempt(db, attempt_id)


@operation
def teacher_attempt_result(db, teacher, attempt_id):
    attempt = _teacher_attempt(db, teacher, attempt_id)
    changed = _expire_if_due(db, attempt)
    data = _result(db, attempt)
    if changed:
        db.commit()
    return data


@operation
def teacher_results(db, teacher, exam_id, page, page_size, student_id):
    exam = _teacher_object(db, Exam, exam_id, teacher)
    query = select(ExamAttempt).where(ExamAttempt.exam_id == exam.id)
    if student_id is not None:
        query = query.where(ExamAttempt.student_id == student_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records = db.scalars(query.order_by(ExamAttempt.started_at.desc(), ExamAttempt.id)
                         .offset((page - 1) * page_size).limit(page_size).with_for_update()).all()
    changed = False
    for attempt in records:
        changed = _expire_if_due(db, attempt) or changed
    data = {'items': [_attempt_data(attempt) for attempt in records], 'total': total,
            'page': page, 'page_size': page_size}
    if changed:
        db.commit()
    return data


def diagnosis_assessment(db, attempt):
    """新旧导出共用历史评分及基准读取；不读取当前题库。"""
    result = _result(db, attempt)
    baseline = None
    if attempt.baseline_attempt_id:
        baseline = db.scalar(select(ExamAttempt).where(ExamAttempt.id == attempt.baseline_attempt_id)
                             .with_for_update(read=True))
    return result, baseline


@operation
def diagnosis_input(db, teacher, attempt_id):
    """保留 D 旧模型的最小输入；完整新契约由 /internal 导出。"""
    attempt = _teacher_attempt(db, teacher, attempt_id)
    changed = _expire_if_due(db, attempt)
    result, baseline = diagnosis_assessment(db, attempt)
    data = {'attempt_id': attempt.id, 'course_id': attempt.course_id,
            'knowledge_points': attempt.knowledge_snapshot, 'resource_catalog': [],
            'graded_answers': [{'question_id': item['id'], 'knowledge_point_ids': item['knowledge_point_ids'],
                                'correct': item['correct']} for item in result['questions']]}
    if baseline is not None:
        # D 的严格请求模型不接收 B 留存的 evidence_question_ids。
        fields = ('knowledge_point_id', 'name', 'correct_count', 'sample_count', 'accuracy', 'status')
        data['baseline'] = {'knowledge_points': [
            {key: stat[key] for key in fields} for stat in baseline.knowledge_point_stats or []]}
    if changed:
        db.commit()
    return data


@operation
def expire_due_attempts(db, limit=100):
    now = int(time.time())
    records = db.scalars(select(ExamAttempt).where(
        ExamAttempt.status == 'in_progress', ExamAttempt.expires_at <= now,
    ).order_by(ExamAttempt.expires_at, ExamAttempt.id).limit(limit)
                        .with_for_update(skip_locked=True)).all()
    for attempt in records:
        _finalize(db, attempt, expired=True)
    db.commit()
    return len(records)
