"""显式 TEST_MYSQL_URL 启用，沿用随机独立测试库，绝不使用业务库。"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
import os
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.internal_schemas import IndexStateIn
from app.internal_security import ServicePrincipal
from app.models import CourseResource, ResourceIndexState
from app.resource_schemas import ResourceUpdateIn
from app.services import internal, resources
from test_mysql_resources import create_material, mysql_resources

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MYSQL_URL'), reason='未配置独立 MySQL 集成测试连接')
C_HEADERS = {'Authorization': 'Bearer ' + 'c' * 40}
D_HEADERS = {'Authorization': 'Bearer ' + 'd' * 40}


@pytest.fixture
def mysql_internal(mysql_resources, monkeypatch):
    for name, key in [('C', 'c'), ('D', 'd')]:
        monkeypatch.setattr(config, f'{name}_SERVICE_KEY', key * 40)
        monkeypatch.setattr(config, f'{name}_SERVICE_COURSE_IDS', 'course')
    return mysql_resources


def acknowledge(client, identity, **changes):
    detail = client.get(f'/internal/resources/{identity}', headers=C_HEADERS).json()['data']
    response = client.put(f'/internal/resources/{identity}/index-state', headers=C_HEADERS, json={
        'resource_version': detail['version'], 'status': 'ready', 'document_id': 'doc-' + identity,
        'content_hash': detail['content_hash'], **changes,
    })
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_mysql_index_version_update_delete_and_callback_guards(mysql_internal):
    client, users, engine = mysql_internal
    material = create_material(client, users['teacher01'])
    identity = material['id']
    assert material['index_status'] == 'pending'
    assert client.get(f'/internal/resources/{identity}', headers=D_HEADERS).status_code == 401
    first = acknowledge(client, identity)
    assert first['indexed_version'] == 1
    assert acknowledge(client, identity) == first
    updated = client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'], json={
        'expected_version': 1, 'knowledge_point_ids': ['kp2'],
    })
    assert updated.json()['data']['version'] == 2 and updated.json()['data']['index_status'] == 'pending'
    with Session(engine) as db:
        state = db.get(ResourceIndexState, identity)
        assert state.resource_version == 2 and state.indexed_version == 1 and state.status == 'pending'
    stale = client.put(f'/internal/resources/{identity}/index-state', headers=C_HEADERS, json={
        'resource_version': 1, 'status': 'ready', 'document_id': first['document_id'], 'content_hash': first['indexed_hash'],
    })
    assert stale.status_code == 409
    acknowledge(client, identity)
    assert client.delete(f'/teacher/resources/{identity}', headers=users['teacher01']).status_code == 200
    manifest = client.get('/internal/courses/course/resources', headers=C_HEADERS).json()['data']['items']
    assert manifest[0]['status'] == 'deleted' and manifest[0]['version'] == 3
    payload = {'resource_version': 3, 'status': 'deleted'}
    response = client.put(f'/internal/resources/{identity}/index-state', headers=C_HEADERS, json=payload)
    assert response.status_code == 200 and response.json()['data']['status'] == 'deleted'
    with Session(engine) as db:
        assert db.get(CourseResource, identity).status == 'deleted'
        assert db.get(ResourceIndexState, identity).indexed_version is None


def test_mysql_index_reset_and_content_update_roll_back_together(mysql_internal, monkeypatch):
    client, users, engine = mysql_internal
    material = create_material(client, users['teacher01'])
    identity = material['id']
    acknowledge(client, identity)
    from app.models import User
    with Session(engine, autoflush=False) as db:
        teacher = db.get(User, 2)
        def fail_commit():
            raise RuntimeError('injected before commit')
        monkeypatch.setattr(db, 'commit', fail_commit)
        with pytest.raises(RuntimeError):
            resources.update_resource(db, teacher, identity, ResourceUpdateIn(expected_version=1, text='不能提交的正文'))
        db.rollback()
    with Session(engine) as db:
        assert db.get(CourseResource, identity).version == 1
        assert db.get(CourseResource, identity).text == material['text']
        assert db.get(ResourceIndexState, identity).status == 'ready'


def test_mysql_late_callback_waits_for_resource_lock_then_rejects_old_version(mysql_internal):
    client, users, engine = mysql_internal
    material = create_material(client, users['teacher01'])
    identity = material['id']
    detail = client.get(f'/internal/resources/{identity}', headers=C_HEADERS).json()['data']
    payload = IndexStateIn(resource_version=1, status='ready', document_id='old-doc', content_hash=detail['content_hash'])
    principal = ServicePrincipal('C', frozenset({'course'}))
    started = Event()

    def late_callback():
        from fastapi import HTTPException
        with Session(engine, autoflush=False) as db:
            started.set()
            try:
                internal.report_index_state(db, principal, identity, payload)
            except HTTPException as exc:
                return exc.status_code
        return 200

    with Session(engine, autoflush=False) as db, ThreadPoolExecutor(max_workers=1) as pool:
        resource = db.scalar(select(CourseResource).where(CourseResource.id == identity).with_for_update())
        future = pool.submit(late_callback)
        try:
            assert started.wait(timeout=5)
            # 写锁释放前回报不能完成；否则可能读到旧版本并错误确认 ready。
            with pytest.raises(FutureTimeout):
                future.result(timeout=0.2)
            resource.text, resource.version = '新版本', 2
            from app.services.resource_index import mark_pending
            mark_pending(db, resource)
            db.commit()
        finally:
            db.rollback()  # 发生异常也先释放锁，再等待线程池退出。
        assert future.result(timeout=10) == 409
    with Session(engine) as db:
        assert db.get(ResourceIndexState, identity).status == 'pending'
        assert db.get(ResourceIndexState, identity).resource_version == 2


def test_mysql_index_migration_backfills_only_missing_states_and_is_repeatable(mysql_internal):
    client, users, engine = mysql_internal
    material = create_material(client, users['teacher01'])
    identity = material['id']
    first = acknowledge(client, identity)
    sql = (Path(__file__).resolve().parents[1] / 'sql' / 'create_resource_index_states.sql').read_text()
    # 脚本无存储过程；忽略目标业务库 USE，在随机独立库中执行 DDL 和回填。
    statements = ['\n'.join(line for line in part.splitlines() if not line.lstrip().startswith('--')).strip()
                  for part in sql.split(';')]
    def migrate():
        with engine.connect() as connection:
            for statement in statements:
                if statement and not statement.startswith('USE '):
                    connection.exec_driver_sql(statement)
            connection.commit()
    migrate()
    assert client.get(f'/internal/resources/{identity}', headers=C_HEADERS).json()['data']['index_state'] == first
    with Session(engine) as db:
        db.delete(db.get(ResourceIndexState, identity))
        db.get(CourseResource, identity).status = 'deleted'
        db.commit()
    migrate()
    migrate()
    with Session(engine) as db:
        state = db.get(ResourceIndexState, identity)
        assert state.status == 'pending' and state.resource_version == 1 and state.indexed_version is None


def test_mysql_completed_attempt_exports_real_ready_catalog(mysql_internal):
    client, users, engine = mysql_internal
    material = create_material(client, users['teacher01'], knowledge_point_ids=['kp1'])
    identity = material['id']
    question = client.post('/teacher/courses/course/questions', headers=users['teacher01'], json={
        'kind': 'single', 'stem': '访问顺序？', 'explanation': '后进先出', 'status': 'active',
        'knowledge_point_ids': ['kp1'], 'options': [
            {'label': 'A', 'text': '后进先出', 'is_correct': True},
            {'label': 'B', 'text': '先进先出', 'is_correct': False},
        ],
    })
    assert question.status_code == 201, question.text
    qid = question.json()['data']['id']
    exam = client.post('/teacher/courses/course/exams', headers=users['teacher01'], json={
        'title': '内部导出联调', 'duration_seconds': 600,
    })
    assert exam.status_code == 201, exam.text
    eid = exam.json()['data']['id']
    paper = client.put(f'/teacher/exams/{eid}/questions', headers=users['teacher01'], json={
        'questions': [{'question_id': qid, 'score': 10}],
    })
    assert paper.status_code == 200, paper.text
    assert client.post(f'/teacher/exams/{eid}/publish', headers=users['teacher01']).status_code == 200
    attempt = client.post(f'/exams/{eid}/attempts', headers=users['student01'])
    assert attempt.status_code == 200, attempt.text
    aid = attempt.json()['data']['id']
    assert client.get(f'/internal/attempts/{aid}/diagnosis-input', headers=D_HEADERS).status_code == 409
    assert client.post(f'/attempts/{aid}/submit', headers=users['student01']).status_code == 200
    acknowledge(client, identity)
    result = client.get(f'/internal/attempts/{aid}/diagnosis-input', headers=D_HEADERS)
    assert result.status_code == 200, result.text
    data = result.json()['data']
    assert data['resource_catalog'][0]['resource_id'] == identity
    assert data['graded_answers'][0]['answered'] is False
    assert data['graded_answers'][0]['correct_option_ids'] and data['warnings'] == []
    assert client.delete(f'/teacher/resources/{identity}', headers=users['teacher01']).status_code == 200
    assert client.get(f'/internal/attempts/{aid}/diagnosis-input', headers=D_HEADERS).json()['data']['resource_catalog'] == []
