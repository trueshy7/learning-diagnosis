"""显式设置 TEST_MYSQL_URL 后，在临时独立 MySQL 库运行完整业务链路。

不会使用 DATABASE_URL 的业务库；只删除本测试新建的随机库。
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import main
from app.database import Base, get_db
from app.models import Course, CourseChapter, CourseEnrollment, KnowledgePoint, User
from app.security import hash_password
from app.services import exams

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MYSQL_URL'), reason='未配置独立 MySQL 集成测试连接')


@pytest.fixture
def mysql_api(monkeypatch):
    url = make_url(os.environ['TEST_MYSQL_URL'])
    if url.get_backend_name() != 'mysql':
        pytest.fail('TEST_MYSQL_URL 必须为 MySQL，不能使用 SQLite')
    name = 'ld_exam_test_' + uuid.uuid4().hex
    admin = create_engine(url.set(database=None), connect_args={'connect_timeout': 5})
    engine = None
    created = False
    try:
        with admin.begin() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        created = True
        engine = create_engine(url.set(database=name), connect_args={'connect_timeout': 5})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add_all([User(id=1, username='student01', email='student@example.com', role='student', password_hash=hash_password('Example123!')),
                        User(id=2, username='teacher01', email='teacher@example.com', role='teacher', password_hash=hash_password('Example123!'))])
            db.flush()
            db.add(Course(id='course', name='课程', teacher_id=2, status='published'))
            db.flush()
            db.add(CourseChapter(id='chapter', course_id='course', name='章节'))
            db.flush()
            db.add_all([KnowledgePoint(id='kp1', course_id='course', chapter_id='chapter', name='知识点一'),
                        KnowledgePoint(id='kp2', course_id='course', chapter_id='chapter', name='未测知识点')])
            db.add(CourseEnrollment(course_id='course', student_id=1))
            db.commit()
        clock = {'now': 1800000000}
        monkeypatch.setattr(exams.time, 'time', lambda: clock['now'])
        monkeypatch.setattr(main, 'engine', engine)

        def database():
            with Session(engine, autoflush=False) as db:
                yield db

        main.app.dependency_overrides[get_db] = database
        with TestClient(main.app) as client:
            def headers(username):
                response = client.post('/user/login', json={'username': username, 'password': 'Example123!'})
                assert response.status_code == 200
                return {'Authorization': 'Bearer ' + response.json()['data']['access_token']}
            yield client, headers('teacher01'), headers('student01'), clock, engine
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.exec_driver_sql(f'DROP DATABASE `{name}`')
        admin.dispose()


def make_exam(client, teacher, title='测验'):
    question_ids = []
    for i in range(3):
        response = client.post('/teacher/courses/course/questions', headers=teacher, json={
            'kind': 'single', 'stem': f'题目{i}', 'status': 'active', 'explanation': '正确答案解析',
            'knowledge_point_ids': ['kp1'], 'options': [
                {'label': 'A', 'text': '正确选项', 'is_correct': True},
                {'label': 'B', 'text': '错误选项', 'is_correct': False},
            ],
        })
        assert response.status_code == 201, response.text
        question_ids.append(response.json()['data']['id'])
    response = client.post('/teacher/courses/course/exams', headers=teacher, json={'title': title, 'duration_seconds': 60})
    assert response.status_code == 201, response.text
    exam_id = response.json()['data']['id']
    response = client.put(f'/teacher/exams/{exam_id}/questions', headers=teacher,
                          json={'questions': [{'question_id': qid, 'score': '2.50'} for qid in question_ids]})
    assert response.status_code == 200, response.text
    response = client.post(f'/teacher/exams/{exam_id}/publish', headers=teacher)
    assert response.status_code == 200, response.text
    return exam_id, question_ids


def test_mysql_full_flow_snapshot_history_and_diagnosis_export(mysql_api):
    client, teacher, student, clock, engine = mysql_api
    exam_id, question_ids = make_exam(client, teacher)
    start = client.post(f'/exams/{exam_id}/attempts', headers=student)
    assert start.status_code == 200, start.text
    attempt_id = start.json()['data']['id']
    assert client.post(f'/exams/{exam_id}/attempts', headers=student).json()['data']['id'] == attempt_id
    paper = client.get(f'/attempts/{attempt_id}', headers=student)
    assert 'is_correct' not in paper.text and 'explanation' not in paper.text
    questions = paper.json()['data']['questions']
    answers = [{'question_id': item['id'], 'selected_option_ids': [item['options'][0]['id']], 'revision': 0} for item in questions]
    response = client.put(f'/attempts/{attempt_id}/answers', headers=student, json={'answers': answers})
    assert response.status_code == 200, response.text
    assert client.put(f'/attempts/{attempt_id}/answers', headers=student, json={'answers': answers}).status_code == 409
    # 改题库不会改变已发布快照或此次判分。
    changed = client.put(f'/teacher/questions/{question_ids[0]}', headers=teacher, json={
        'kind': 'single', 'stem': '后来修改的题目', 'status': 'disabled',
        'knowledge_point_ids': ['kp1'], 'options': [
            {'label': 'A', 'text': '现在错误', 'is_correct': False},
            {'label': 'B', 'text': '现在正确', 'is_correct': True},
        ],
    })
    assert changed.status_code == 200, changed.text
    result = client.post(f'/attempts/{attempt_id}/submit', headers=student)
    assert result.status_code == 200, result.text
    assert result.json()['data']['score'] == 7.5
    assert result.json()['data']['knowledge_points'][0]['status'] == 'mastered'
    assert result.json()['data']['knowledge_points'][1]['accuracy'] is None
    assert client.post(f'/attempts/{attempt_id}/submit', headers=student).json()['data']['score'] == 7.5
    assert client.get(f'/teacher/exams/{exam_id}/results', headers=teacher).json()['data']['total'] == 1
    exported = client.get(f'/teacher/attempts/{attempt_id}/diagnosis-input', headers=teacher)
    assert exported.status_code == 200 and len(exported.json()['data']['graded_answers']) == 3
    assert client.put(f'/teacher/exams/{exam_id}', headers=teacher, json={'title': '修改'}).status_code == 409


def test_mysql_timeout_and_retest_comparison(mysql_api):
    client, teacher, student, clock, engine = mysql_api
    first, _ = make_exam(client, teacher, '初测')
    attempt_id = client.post(f'/exams/{first}/attempts', headers=student).json()['data']['id']
    clock['now'] += 60
    result = client.get(f'/attempts/{attempt_id}/result', headers=student)
    assert result.status_code == 200, result.text
    assert result.json()['data']['status'] == 'expired' and result.json()['data']['score'] == 0
    second, _ = make_exam(client, teacher, '复测')
    attempt = client.post(f'/exams/{second}/attempts', headers=student, json={'baseline_attempt_id': attempt_id})
    assert attempt.status_code == 200, attempt.text
    second_id = attempt.json()['data']['id']
    result = client.post(f'/attempts/{second_id}/submit', headers=student)
    assert result.status_code == 200
    assert result.json()['data']['comparison'][0]['delta'] == 0
