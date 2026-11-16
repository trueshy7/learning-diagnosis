"""独立 MySQL 库验证评分/任务原子性、租约竞争和冻结输入；不连接业务库。"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Barrier

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.models import DiagnosisTask, ExamAttempt
from app.services import diagnosis_dispatch as dispatch
from app.services import diagnosis_tasks
from test_mysql_exams import make_exam, mysql_api

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MYSQL_URL'), reason='未配置独立 MySQL 集成测试连接')
D_HEADERS = {'Authorization': 'Bearer ' + 'd' * 40}


@pytest.fixture
def mysql_tasks(mysql_api, monkeypatch):
    for name, value in [('DIAGNOSIS_AUTO_ENQUEUE', True), ('C_SERVICE_KEY', 'c' * 40),
                        ('D_SERVICE_KEY', 'd' * 40), ('D_SERVICE_COURSE_IDS', '*'),
                        ('DIAGNOSIS_SERVICE_KEY', 't' * 40), ('DIAGNOSIS_URL', 'http://diagnosis.test'),
                        ('DIAGNOSIS_TIMEOUT', 10), ('DIAGNOSIS_MAX_ATTEMPTS', 5)]:
        monkeypatch.setattr(config, name, value)
    client, teacher, student, clock, engine = mysql_api
    exam_id, _ = make_exam(client, teacher)
    attempt = client.post(f'/exams/{exam_id}/attempts', headers=student)
    assert attempt.status_code == 200, attempt.text
    aid = attempt.json()['data']['id']
    return client, teacher, student, clock, engine, aid


def accepted(request):
    payload = json.loads(request.content)
    return httpx.Response(202, json={'task_id': payload['task_id'], 'attempt_id': payload['attempt_id'], 'status': 'accepted'})


def test_mysql_submit_persists_one_task_and_worker_can_fetch_input_over_http(mysql_tasks):
    client, teacher, student, clock, engine, aid = mysql_tasks
    assert client.post(f'/attempts/{aid}/submit', headers=student).status_code == 200
    assert client.post(f'/attempts/{aid}/submit', headers=student).status_code == 200
    with Session(engine) as db:
        task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.attempt_id == aid))
        assert task.status == 'pending' and task.input_snapshot is None
        assert db.scalar(select(func.count()).select_from(DiagnosisTask)) == 1
    factory = sessionmaker(engine, autoflush=False)
    notifications = []

    def handler(request):
        payload = json.loads(request.content)
        notifications.append(payload)
        # 网络调用期间，独立 HTTP 请求能够读取已提交的冻结快照。
        response = client.get(payload['input_path'], headers=D_HEADERS)
        assert response.status_code == 200, response.text
        data = response.json()['data']
        assert data['input']['attempt_id'] == aid
        assert dispatch.snapshot_hash(data['input']) == data['input_hash'] == payload['input_hash']
        return accepted(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert dispatch.dispatch_batch(factory, client=http)['delivered'] == 1
        assert dispatch.dispatch_batch(factory, client=http)['delivered'] == 0
    result = client.get(f'/attempts/{aid}/diagnosis-task', headers=student)
    assert result.status_code == 200 and result.json()['data']['status'] == 'delivered'
    assert len(notifications) == 1


def test_mysql_enqueue_failure_rolls_back_scores_and_task_together(mysql_tasks, monkeypatch):
    client, teacher, student, clock, engine, aid = mysql_tasks
    original = diagnosis_tasks.ensure_task
    def fail_after_insert(db, attempt):
        original(db, attempt)
        db.flush()
        from sqlalchemy.exc import SQLAlchemyError
        raise SQLAlchemyError('injected private failure')
    monkeypatch.setattr(diagnosis_tasks, 'ensure_task', fail_after_insert)
    response = client.post(f'/attempts/{aid}/submit', headers=student)
    assert response.status_code == 503 and 'private' not in response.text
    with Session(engine) as db:
        assert db.get(ExamAttempt, aid).status == 'in_progress'
        assert db.get(ExamAttempt, aid).score is None
        assert db.scalar(select(func.count()).select_from(DiagnosisTask)) == 0


def test_mysql_concurrent_workers_claim_at_most_one_active_lease(mysql_tasks):
    client, teacher, student, clock, engine, aid = mysql_tasks
    assert client.post(f'/attempts/{aid}/submit', headers=student).status_code == 200
    factory = sessionmaker(engine, autoflush=False)
    service = dispatch.configuration()
    barrier = Barrier(2)
    def claim():
        barrier.wait(timeout=5)
        return dispatch.claim_next(factory, service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        deliveries = [future.result(timeout=10) for future in futures]
    assert sum(item is not None for item in deliveries) == 1
    delivery = next(item for item in deliveries if item is not None)
    clock['now'] += 41
    current = dispatch.claim_next(factory, service)
    assert current is not None and current.lease_token != delivery.lease_token
    receipt = {'task_id': current.task_id, 'attempt_id': aid, 'status': 'accepted'}
    assert dispatch.finish_delivery(factory, current, receipt=receipt) == 'delivered'
    assert dispatch.finish_delivery(factory, delivery, error=dispatch.DeliveryError('late', retryable=True)) == 'stale'


def test_mysql_worker_restart_reuses_frozen_input_and_retry_id(mysql_tasks):
    client, teacher, student, clock, engine, aid = mysql_tasks
    client.post(f'/attempts/{aid}/submit', headers=student)
    factory = sessionmaker(engine, autoflush=False)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as http:
        assert dispatch.dispatch_batch(factory, client=http)['pending'] == 1
    with Session(engine) as db:
        task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.attempt_id == aid))
        snapshot, digest, identity = task.input_snapshot, task.input_hash, task.id
    # 使用全新 Session 工厂模拟 worker 重启。
    clock['now'] += 5
    with httpx.Client(transport=httpx.MockTransport(accepted)) as http:
        assert dispatch.dispatch_batch(sessionmaker(engine, autoflush=False), client=http)['delivered'] == 1
    with Session(engine) as db:
        task = db.get(DiagnosisTask, identity)
        assert task.input_snapshot == snapshot and task.input_hash == digest and task.attempt_count == 2


def test_mysql_task_migration_is_repeatable_and_does_not_enqueue_history(mysql_tasks):
    client, teacher, student, clock, engine, aid = mysql_tasks
    text = (Path(__file__).resolve().parents[1] / 'sql/create_diagnosis_tasks.sql').read_text()
    statements = ['\n'.join(line for line in part.splitlines() if not line.lstrip().startswith('--')).strip()
                  for part in text.split(';')]
    for _ in range(2):
        with engine.begin() as connection:
            for statement in statements:
                if statement and not statement.startswith('USE '):
                    connection.exec_driver_sql(statement)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DiagnosisTask)) == 0
    assert client.post(f'/attempts/{aid}/submit', headers=student).status_code == 200
