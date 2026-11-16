"""测验规则与 HTTP 边界测试，数据库使用替身。"""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import config, main
from app.database import get_db
from app.exam_schemas import QuestionIn
from app.models import (Course, CourseEnrollment, Exam, ExamAnswer, ExamAttempt,
                        ExamQuestion, KnowledgePoint, Question, QuestionOption, User)
from app.security import current_user
from app.services import exams
from app.services.assessment import classify, compare_statistics, grade_paper


def question_body(**overrides):
    return {'kind': 'single', 'stem': '栈的访问原则是什么？', 'explanation': '后进先出。',
            'status': 'active', 'knowledge_point_ids': ['kp1'], 'options': [
                {'label': 'A', 'text': '后进先出', 'is_correct': True},
                {'label': 'B', 'text': '先进先出', 'is_correct': False},
            ], **overrides}


def make_paper():
    paper = []
    for number, score in enumerate(('2.50', '3.50', '4.00', '5.25'), start=1):
        qid = f'q{number}'
        multiple = number == 4
        options = [{'id': qid + 'a', 'label': 'A', 'text': '选项一', 'is_correct': True},
                   {'id': qid + 'b', 'label': 'B', 'text': '选项二', 'is_correct': multiple}]
        if multiple:
            options.append({'id': qid + 'c', 'label': 'C', 'text': '选项三', 'is_correct': False})
        paper.append(ExamQuestion(exam_id='exam', course_id='course', question_id=qid,
                                 score=Decimal(score), sort_order=number - 1, snapshot={
            'id': qid, 'kind': 'multiple' if multiple else 'single', 'stem': '测试题',
            'options': options, 'explanation': 'SECRET EXPLANATION',
            'knowledge_points': [{'id': 'kp2' if multiple else 'kp1', 'name': '知识点', 'status': 'active'}],
        }))
    return paper


def grade_input(paper):
    return [{'question_id': item.question_id, 'score': item.score, 'snapshot': item.snapshot} for item in paper]


POINTS = [{'id': 'kp1', 'name': '栈'}, {'id': 'kp2', 'name': '队列'}, {'id': 'kp3', 'name': '未覆盖'}]


def test_deterministic_grading_multiselect_blank_and_uncovered_points():
    total, grades, stats = grade_paper(grade_input(make_paper()), {
        'q1': ['q1a'], 'q2': ['q2a'], 'q3': ['q3a'], 'q4': ['q4a', 'q4b'],
    }, POINTS)
    assert total == Decimal('15.25') and all(item['correct'] for item in grades)
    assert stats[0]['status'] == 'mastered' and stats[0]['sample_count'] == 3
    assert stats[1]['status'] == 'insufficient_evidence'
    assert stats[2]['sample_count'] == 0 and stats[2]['accuracy'] is None
    assert grade_paper(grade_input(make_paper()), {}, POINTS)[0] == Decimal('0')
    for selection in (['q4a'], ['q4a', 'q4b', 'q4c'], ['q4c'], ['q4a', 'q4a', 'q4b']):
        assert grade_paper(grade_input(make_paper()), {'q4': selection}, POINTS)[0] == Decimal('0')


@pytest.mark.parametrize(('samples', 'correct', 'status'), [(2, 2, 'insufficient_evidence'),
    (5, 2, 'weak'), (5, 3, 'needs_practice'), (5, 4, 'mastered')])
def test_diagnosis_thresholds(samples, correct, status):
    assert classify(samples, correct) == status


def test_comparison_only_uses_common_points_with_enough_evidence():
    before = [{'knowledge_point_id': 'kp1', 'sample_count': 3, 'accuracy': 0.333333},
              {'knowledge_point_id': 'kp2', 'sample_count': 2, 'accuracy': 0.5}]
    after = [{'knowledge_point_id': 'kp1', 'sample_count': 3, 'accuracy': 1.0},
             {'knowledge_point_id': 'kp2', 'sample_count': 4, 'accuracy': 1.0}]
    assert compare_statistics(before, after) == [{'knowledge_point_id': 'kp1', 'before_accuracy': 0.333333,
                                                 'after_accuracy': 1.0, 'delta': 0.666667}]


@pytest.fixture
def exam_api(monkeypatch):
    monkeypatch.setattr(config, 'DIAGNOSIS_AUTO_ENQUEUE', False)  # 任务入队边界由 test_diagnosis_tasks 单独覆盖。
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    monkeypatch.setattr(exams.time, 'time', lambda: 1000)
    db = Mock(spec=Session)
    user = User(id=1, role='student', username='student01', email='student@example.com')
    course = Course(id='course', teacher_id=2, name='数据结构', status='published', created_at=0, updated_at=0)
    exam = Exam(id='exam', course_id='course', title='初测', status='published', duration_seconds=60,
                question_count=4, total_score=Decimal('15.25'), knowledge_snapshot=POINTS, created_at=0, updated_at=0)
    attempt = ExamAttempt(id='attempt', exam_id='exam', course_id='course', student_id=1,
                          status='in_progress', started_at=950, expires_at=1010, submitted_at=None,
                          baseline_attempt_id=None, score=None, total_score=exam.total_score,
                          knowledge_snapshot=POINTS, knowledge_point_stats=None)
    paper = make_paper()
    answers = [ExamAnswer(attempt_id='attempt', exam_id='exam', question_id=item.question_id,
                          selected_option_ids=[], revision=0, correct=None, score=None, updated_at=950) for item in paper]
    db.scalar.return_value = attempt

    def select_rows(query):
        entity = query.column_descriptions[0]['entity']
        result = Mock()
        result.all.return_value = {ExamQuestion: paper, ExamAnswer: answers,
                                   ExamAttempt: [attempt], KnowledgePoint: [], Question: []}.get(entity, [])
        return result

    db.scalars.side_effect = select_rows
    state = {'course': course, 'exam': exam, 'attempt': attempt, 'paper': paper, 'answers': answers}
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(main.app) as client:
            yield client, db, user, state
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(current_user, None)


def test_attempt_view_never_leaks_answers_or_explanations(exam_api):
    client, db, user, state = exam_api
    response = client.get('/attempts/attempt')
    assert response.status_code == 200
    assert 'is_correct' not in response.text and 'correct_option_ids' not in response.text
    assert 'SECRET EXPLANATION' not in response.text
    assert len(response.json()['data']['questions']) == 4
    query = db.scalar.call_args.args[0].compile(dialect=mysql.dialect())
    assert query.params['student_id_1'] == user.id
    assert 'FOR UPDATE' in str(query)


def test_save_versioned_answers_then_submit_and_repeat(exam_api):
    client, db, user, state = exam_api
    body = {'answers': [{'question_id': f'q{i}', 'selected_option_ids': [f'q{i}a'], 'revision': 0} for i in range(1, 4)]}
    body['answers'].append({'question_id': 'q4', 'selected_option_ids': ['q4a', 'q4b'], 'revision': 0})
    response = client.put('/attempts/attempt/answers', json=body)
    assert response.status_code == 200
    assert all(item['revision'] == 1 for item in response.json()['data']['answers'])
    assert client.put('/attempts/attempt/answers', json=body).status_code == 409
    result = client.post('/attempts/attempt/submit')
    assert result.status_code == 200
    assert result.json()['data']['score'] == 15.25
    assert result.json()['data']['knowledge_points'][0]['status'] == 'mastered'
    assert 'SECRET EXPLANATION' in result.text
    assert client.post('/attempts/attempt/submit').json()['data'] == result.json()['data']
    assert client.put('/attempts/attempt/answers', json=body).status_code == 409


@pytest.mark.parametrize(('selected', 'qid', 'revision', 'status'), [
    (['q1a', 'q1b'], 'q1', 0, 422), (['foreign'], 'q1', 0, 422),
    (['q1a'], 'foreign-question', 0, 422), (['q1a'], 'q1', 1, 409),
])
def test_bad_batch_does_not_partially_save(exam_api, selected, qid, revision, status):
    client, db, user, state = exam_api
    response = client.put('/attempts/attempt/answers', json={'answers': [
        {'question_id': 'q2', 'selected_option_ids': ['q2a'], 'revision': 0},
        {'question_id': qid, 'selected_option_ids': selected, 'revision': revision},
    ]})
    assert response.status_code == status
    assert all(answer.selected_option_ids == [] and answer.revision == 0 for answer in state['answers'])
    db.commit.assert_not_called()


@pytest.mark.parametrize('path', ['/attempts/attempt', '/attempts/attempt/result'])
def test_deadline_boundary_expires_and_grades_last_saved_answers(exam_api, path):
    client, db, user, state = exam_api
    state['attempt'].expires_at = 1000
    state['answers'][0].selected_option_ids = ['q1a']
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()['data']['status'] == 'expired'
    assert response.json()['data']['score'] == 2.5
    assert state['attempt'].submitted_at == 1000
    db.commit.assert_called_once()


def test_late_save_finalizes_but_rejects_new_answer(exam_api):
    client, db, user, state = exam_api
    state['attempt'].expires_at = 999
    response = client.put('/attempts/attempt/answers', json={'answers': [
        {'question_id': 'q1', 'selected_option_ids': ['q1a'], 'revision': 0},
    ]})
    assert response.status_code == 409
    assert state['attempt'].status == 'expired' and state['attempt'].score == 0
    assert state['answers'][0].selected_option_ids == []
    db.commit.assert_called_once()


def test_in_progress_result_is_not_disclosed(exam_api):
    client, db, user, state = exam_api
    assert client.get('/attempts/attempt/result').status_code == 409


@pytest.mark.parametrize(('method', 'path', 'body'), [
    ('GET', '/attempts/other', None), ('GET', '/attempts/other/result', None),
    ('POST', '/attempts/other/submit', None),
    ('PUT', '/attempts/other/answers', {'answers': [{'question_id': 'q1', 'selected_option_ids': [], 'revision': 0}]}),
])
def test_nonexistent_or_other_students_attempt_is_404(exam_api, method, path, body):
    client, db, user, state = exam_api
    db.scalar.return_value = None
    assert client.request(method, path, json=body).status_code == 404
    assert db.scalar.call_args.args[0].compile(dialect=mysql.dialect()).params['student_id_1'] == user.id


def test_start_creates_one_attempt_and_initial_blank_answers(exam_api):
    client, db, user, state = exam_api
    enrolled = CourseEnrollment(course_id='course', student_id=1, status='active')
    db.scalar.side_effect = ['course', state['course'], state['exam'], None, enrolled]
    response = client.post('/exams/exam/attempts')
    assert response.status_code == 200
    records = [call.args[0] for call in db.add.call_args_list]
    attempt = next(row for row in records if isinstance(row, ExamAttempt))
    assert len([row for row in records if isinstance(row, ExamAnswer)]) == 4
    assert attempt.student_id == user.id and attempt.expires_at == 1060
    assert response.json()['data']['id'] == attempt.id
    db.scalar.side_effect = ['course', state['course'], state['exam'], attempt]
    assert client.post('/exams/exam/attempts').json()['data']['id'] == attempt.id
    assert db.add.call_count == 5


@pytest.mark.parametrize('condition', ['not_enrolled', 'course_archived', 'exam_draft', 'bad_baseline'])
def test_start_requires_enrollment_published_state_and_valid_baseline(exam_api, condition):
    client, db, user, state = exam_api
    enrolled = CourseEnrollment(course_id='course', student_id=1, status='active')
    if condition == 'course_archived':
        state['course'].status = 'archived'
    if condition == 'exam_draft':
        state['exam'].status = 'draft'
    db.scalar.side_effect = ['course', state['course'], state['exam'], None,
                             None if condition == 'not_enrolled' else enrolled, None]
    response = client.post('/exams/exam/attempts', json={'baseline_attempt_id': 'other'} if condition == 'bad_baseline' else {})
    assert response.status_code == (404 if condition == 'not_enrolled' else 409)
    db.add.assert_not_called()


def test_existing_attempt_can_resume_after_course_archived_or_withdrawal(exam_api):
    client, db, user, state = exam_api
    state['course'].status = 'archived'
    db.scalar.side_effect = ['course', state['course'], state['exam'], state['attempt']]
    assert client.post('/exams/exam/attempts').status_code == 200
    db.add.assert_not_called()


def test_timeout_batch_uses_skip_locked(exam_api):
    client, db, user, state = exam_api
    state['attempt'].expires_at = 999
    assert exams.expire_due_attempts(db, 10) == 1
    query = db.scalars.call_args_list[0].args[0].compile(dialect=mysql.dialect())
    assert 'SKIP LOCKED' in str(query)
    assert state['attempt'].status == 'expired'


@pytest.mark.parametrize('changes', [
    {'knowledge_point_ids': []}, {'knowledge_point_ids': ['kp1', 'kp2']},
    {'kind': 'essay'}, {'stem': ' '}, {'status': 'published'},
    {'options': [{'label': 'A', 'text': 'a', 'is_correct': False}, {'label': 'B', 'text': 'b', 'is_correct': False}]},
    {'options': [{'label': 'A', 'text': 'a', 'is_correct': True}, {'label': 'A', 'text': 'b', 'is_correct': False}]},
    {'kind': 'multiple'}, {'options': [{'label': 'A', 'text': 'a', 'is_correct': 'true'},
                                      {'label': 'B', 'text': 'b', 'is_correct': False}]},
])
def test_question_schema_rejects_invalid_answer_keys(changes):
    with pytest.raises(ValidationError):
        QuestionIn.model_validate(question_body(**changes))


@pytest.mark.parametrize(('method', 'path', 'body'), [
    ('POST', '/teacher/courses/course/questions', question_body()),
    ('GET', '/teacher/courses/course/questions', None), ('GET', '/teacher/questions/q1', None),
    ('PUT', '/teacher/questions/q1', question_body()), ('DELETE', '/teacher/questions/q1', None),
    ('POST', '/teacher/courses/course/exams', {'title': '测验'}),
    ('GET', '/teacher/courses/course/exams', None), ('GET', '/teacher/exams/exam', None),
    ('PUT', '/teacher/exams/exam', {'title': '测验'}),
    ('PUT', '/teacher/exams/exam/questions', {'questions': [{'question_id': 'q1', 'score': 1}]}),
    ('POST', '/teacher/exams/exam/publish', None), ('POST', '/teacher/exams/exam/archive', None),
    ('GET', '/teacher/exams/exam/results', None), ('GET', '/teacher/attempts/attempt/result', None),
    ('GET', '/teacher/attempts/attempt/diagnosis-input', None),
])
def test_student_cannot_use_teacher_exam_endpoints(exam_api, method, path, body):
    client, db, user, state = exam_api
    assert client.request(method, path, json=body).status_code == 403
    db.scalar.assert_not_called()


@pytest.mark.parametrize(('method', 'path'), [('GET', '/courses/course/exams'),
    ('GET', '/courses/course/attempts'), ('POST', '/exams/exam/attempts'),
    ('GET', '/attempts/attempt'), ('POST', '/attempts/attempt/submit'), ('GET', '/attempts/attempt/result')])
def test_teacher_cannot_use_student_exam_endpoints(exam_api, method, path):
    client, db, user, state = exam_api
    user.role = 'teacher'
    assert client.request(method, path).status_code == 403


def test_teacher_cannot_access_other_teachers_question(exam_api):
    client, db, user, state = exam_api
    user.role, user.id = 'teacher', 2
    db.scalar.side_effect = ['course', None]
    assert client.get('/teacher/questions/q1').status_code == 404
    assert db.scalar.call_args.args[0].compile(dialect=mysql.dialect()).params['teacher_id_1'] == 2


def test_publish_freezes_question_options_and_all_active_points(exam_api):
    client, db, user, state = exam_api
    user.role, user.id = 'teacher', 2
    state['exam'].status = 'draft'
    state['paper'][:] = state['paper'][:1]
    q = Question(id='q1', course_id='course', kind='single', stem='原题干', explanation='解析', status='active')
    options = [QuestionOption(id='q1a', question_id='q1', label='A', text='一', is_correct=True, sort_order=0),
               QuestionOption(id='q1b', question_id='q1', label='B', text='二', is_correct=False, sort_order=1)]
    kp = KnowledgePoint(id='kp1', course_id='course', chapter_id='ch', name='栈', status='active')
    db.scalar.side_effect = ['course', state['course'], state['exam'], state['course'], q]

    def scalars(query):
        entity = query.column_descriptions[0]['entity']
        result = Mock()
        result.all.return_value = {ExamQuestion: state['paper'], QuestionOption: options, KnowledgePoint: [kp]}[entity]
        return result

    db.scalars.side_effect = scalars
    assert client.post('/teacher/exams/exam/publish').status_code == 200
    assert state['paper'][0].snapshot['stem'] == '原题干'
    q.stem = '修改后的题干'
    options[0].text = '修改后的选项'
    assert state['paper'][0].snapshot['stem'] == '原题干'
    assert state['paper'][0].snapshot['options'][0]['text'] == '一'
    assert state['exam'].knowledge_snapshot == [{'id': 'kp1', 'name': '栈'}]


@pytest.mark.parametrize('path', ['/teacher/exams/exam', '/teacher/exams/exam/questions'])
def test_published_paper_cannot_be_modified(exam_api, path):
    client, db, user, state = exam_api
    user.role, user.id = 'teacher', 2
    db.scalar.side_effect = ['course', state['course'], state['exam']]
    body = {'title': '新标题'} if path.endswith('/exam') else {'questions': [{'question_id': 'q1', 'score': 1}]}
    assert client.put(path, json=body).status_code == 409
    db.commit.assert_not_called()


def test_grade_and_submit_database_failure_never_report_success(exam_api):
    client, db, user, state = exam_api
    db.commit.side_effect = SQLAlchemyError('private DB failure')
    response = client.post('/attempts/attempt/submit')
    assert response.status_code == 503 and 'private DB failure' not in response.text
    db.rollback.assert_called_once()


@pytest.mark.parametrize('retest', [False, True])
def test_teacher_exports_diagnosis_contract_without_private_grading_keys(exam_api, retest):
    client, db, user, state = exam_api
    # 先按真实评分规则结算，再切换到所属教师导出。
    assert client.post('/attempts/attempt/submit').status_code == 200
    user.role, user.id = 'teacher', 2
    baseline = ExamAttempt(id='baseline', knowledge_point_stats=state['attempt'].knowledge_point_stats)
    if retest:
        state['attempt'].baseline_attempt_id = 'baseline'
    db.scalar.side_effect = ['course', state['course'], state['attempt']] + ([baseline, baseline] if retest else [])
    response = client.get('/teacher/attempts/attempt/diagnosis-input')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['resource_catalog'] == [] and len(data['graded_answers']) == 4
    assert set(data['graded_answers'][0]) == {'question_id', 'knowledge_point_ids', 'correct'}
    assert 'selected_option_ids' not in response.text and 'explanation' not in response.text
    if retest:
        assert set(data['baseline']['knowledge_points'][0]) == {
            'knowledge_point_id', 'name', 'correct_count', 'sample_count', 'accuracy', 'status'}
    else:
        assert 'baseline' not in data
