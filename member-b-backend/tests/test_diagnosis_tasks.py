"""任务入队、权限、冻结输入、HTTP 投递、重试和过期租约边界。"""

from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from app import config
from app.models import DiagnosisTask, ExamAttempt
from app.services import diagnosis_dispatch as dispatch
from app.services import exams
from test_internal import C_HEADERS, D_HEADERS, internal_api
from test_resources import compile_query, resource_api, rows


@pytest.fixture
def task_api(internal_api, monkeypatch):
    client, db, user, state = internal_api
    user.id, user.role = 1, 'student'
    monkeypatch.setattr(config, 'DIAGNOSIS_AUTO_ENQUEUE', True)
    monkeypatch.setattr(config, 'DIAGNOSIS_SERVICE_KEY', 't' * 40)
    monkeypatch.setattr(config, 'DIAGNOSIS_URL', 'http://diagnosis.test')
    monkeypatch.setattr(config, 'DIAGNOSIS_TIMEOUT', 10)
    monkeypatch.setattr(config, 'DIAGNOSIS_MAX_ATTEMPTS', 5)
    state['task'], state['now'], state['db_open'], state['events'] = None, 1000, False, []
    monkeypatch.setattr(dispatch.time, 'time', lambda: state['now'])
    original_scalar, original_add, original_execute = db.scalar.side_effect, db.add.side_effect, db.execute.side_effect
    original_scalars = db.scalars.side_effect

    def scalar(statement):
        entity = statement.column_descriptions[0].get('entity')
        params = compile_query(statement).params
        if entity is DiagnosisTask:
            task = state['task']
            if task is None or params.get('id_1', task.id) != task.id or params.get('attempt_id_1', task.attempt_id) != task.attempt_id:
                return None
            if 'course_id_1' in params and state['attempt'].course_id not in params['course_id_1']:
                return None
            if 'next_retry_at_1' in params and not (
                (task.status == 'pending' and task.next_retry_at <= state['now']) or
                (task.status == 'dispatching' and task.lease_expires_at <= state['now'])
            ):
                return None
            return task
        if entity is ExamAttempt and 'student_id_1' in params and params['student_id_1'] != state['attempt'].student_id:
            return None
        return original_scalar(statement)

    def add(item):
        if isinstance(item, DiagnosisTask):
            state['task'] = item
        else:
            original_add(item)

    def execute(statement):
        if getattr(statement, 'is_select', False) and statement.column_descriptions[0].get('entity') is DiagnosisTask:
            task = state['task']
            eligible = task and ((task.status == 'pending' and task.next_retry_at <= state['now']) or
                                (task.status == 'dispatching' and task.lease_expires_at <= state['now']))
            scope = compile_query(statement).params.get('course_id_1')
            if scope is not None and state['attempt'].course_id not in scope:
                eligible = False
            return rows([SimpleNamespace(id=task.id, attempt_id=task.attempt_id)] if eligible else [])
        return original_execute(statement)

    db.scalar.side_effect, db.add.side_effect, db.execute.side_effect = scalar, add, execute
    def scalars(statement):
        if statement.column_descriptions[0].get('entity') is ExamAttempt:
            return rows([state['attempt']] if state['attempt'].status == 'in_progress'
                        and state['attempt'].expires_at <= state['now'] else [])
        return original_scalars(statement)
    db.scalars.side_effect = scalars
    db.commit.side_effect = lambda: state['events'].append('commit')

    @contextmanager
    def factory():
        assert not state['db_open']
        state['db_open'] = True
        try:
            yield db
        finally:
            state['db_open'] = False

    yield client, db, user, state, factory


def create_task(client):
    response = client.post('/attempts/attempt/diagnosis-task')
    assert response.status_code == 202, response.text
    return response.json()['data']


def ack(request):
    payload = json.loads(request.content)
    return httpx.Response(202, json={'task_id': payload['task_id'], 'attempt_id': payload['attempt_id'], 'status': 'accepted'})


def run(factory, handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return dispatch.dispatch_batch(factory, client=client)


def test_submit_and_repeat_enqueue_exactly_one_task_in_grading_transaction(task_api):
    client, db, _, state, _ = task_api
    state['attempt'].status = 'in_progress'
    first = client.post('/attempts/attempt/submit')
    assert first.status_code == 200, first.text
    task = state['task']
    assert task is not None and task.attempt_id == 'attempt' and task.status == 'pending'
    assert task.input_snapshot is None and task.attempt_count == 0
    assert client.post('/attempts/attempt/submit').json()['data'] == first.json()['data']
    assert state['task'] is task
    assert len([call for call in db.add.call_args_list if isinstance(call.args[0], DiagnosisTask)]) == 1
    assert db.flush.call_count >= 2


@pytest.mark.parametrize('entry', ['lazy', 'batch'])
def test_lazy_and_batch_expiry_also_enqueue(task_api, entry):
    client, db, _, state, _ = task_api
    state['attempt'].status, state['attempt'].expires_at = 'in_progress', 999
    if entry == 'lazy':
        response = client.get('/attempts/attempt/result')
        assert response.status_code == 200 and response.json()['data']['status'] == 'expired'
    else:
        assert exams.expire_due_attempts(db, 10) == 1
        assert state['attempt'].status == 'expired'
    assert state['task'].status == 'pending'


def test_auto_disabled_can_be_manually_created_without_duplicates(task_api, monkeypatch):
    client, db, _, state, _ = task_api
    monkeypatch.setattr(config, 'DIAGNOSIS_AUTO_ENQUEUE', False)
    state['attempt'].status = 'in_progress'
    assert client.post('/attempts/attempt/submit').status_code == 200
    assert state['task'] is None
    assert client.get('/attempts/attempt/diagnosis-task').status_code == 404
    first = create_task(client)
    assert create_task(client) == first
    assert client.get('/attempts/attempt/diagnosis-task').json()['data'] == first


def test_missing_task_get_keeps_overdue_grading_when_auto_enqueue_disabled(task_api, monkeypatch):
    client, db, _, state, _ = task_api
    monkeypatch.setattr(config, 'DIAGNOSIS_AUTO_ENQUEUE', False)
    state['attempt'].status, state['attempt'].expires_at = 'in_progress', 999
    assert client.get('/attempts/attempt/diagnosis-task').status_code == 404
    assert state['attempt'].status == 'expired' and state['task'] is None
    db.commit.assert_called_once()


def test_unfinished_or_foreign_attempt_cannot_create_or_read_task(task_api):
    client, db, user, state, _ = task_api
    state['attempt'].status = 'in_progress'
    for method in ('get', 'post'):
        assert getattr(client, method)('/attempts/attempt/diagnosis-task').status_code == 409
    assert state['task'] is None
    user.id = 99
    for method in ('get', 'post'):
        assert getattr(client, method)('/attempts/attempt/diagnosis-task').status_code == 404


def test_teacher_must_own_course_and_cannot_use_student_route(task_api):
    client, db, user, state, _ = task_api
    create_task(client)
    user.id, user.role = 7, 'teacher'
    assert client.get('/teacher/attempts/attempt/diagnosis-task').status_code == 200
    assert client.post('/teacher/attempts/attempt/diagnosis-task').status_code == 202
    assert client.get('/attempts/attempt/diagnosis-task').status_code == 403
    user.id = 8
    assert client.get('/teacher/attempts/attempt/diagnosis-task').status_code == 404
    assert client.post('/teacher/attempts/attempt/diagnosis-task').status_code == 404


def test_task_public_data_never_leaks_frozen_answers_or_credentials(task_api):
    client, db, _, state, factory = task_api
    create_task(client)
    run(factory, ack)
    data = client.get('/attempts/attempt/diagnosis-task').json()['data']
    assert data['status'] == 'delivered'
    assert not {'input_snapshot', 'input_hash', 'receipt', 'lease_token', 'lease_expires_at'} & data.keys()


def test_network_runs_only_after_snapshot_and_lease_commit_with_no_db_session(task_api):
    client, db, _, state, factory = task_api
    public = create_task(client)

    def handler(request):
        assert not state['db_open'] and state['events'][-1] == 'commit'
        assert state['task'].status == 'dispatching' and state['task'].input_snapshot is not None
        assert request.url == 'http://diagnosis.test/internal/diagnosis-tasks'
        assert request.headers['Authorization'] == 'Bearer ' + 't' * 40
        assert request.headers['Idempotency-Key'] == public['id']
        payload = json.loads(request.content)
        assert payload['attempt_id'] == 'attempt' and payload['course_id'] == 'course'
        assert 'graded_answers' not in payload and 'token' not in request.content.decode()
        path = payload['input_path']
        # D 在收到通知时即可读取已提交的快照；用户和 C 无权读取。
        response = client.get(path, headers=D_HEADERS)
        assert response.status_code == 200
        data = response.json()['data']
        assert dispatch.snapshot_hash(data['input']) == payload['input_hash'] == data['input_hash']
        assert client.get(path, headers=C_HEADERS).status_code == 401
        assert client.get(path).status_code == 401
        return ack(request)

    assert run(factory, handler)['delivered'] == 1
    assert state['task'].receipt['status'] == 'accepted' and state['task'].lease_token is None
    # delivered 不等同于 D 已完成诊断；重复 worker 不再发送。
    assert run(factory, lambda _: pytest.fail('不应重复投递'))['delivered'] == 0


def test_frozen_input_survives_timeout_resource_changes_and_retry(task_api):
    client, db, _, state, factory = task_api
    create_task(client)
    payloads = []

    def timeout(request):
        payloads.append(json.loads(request.content))
        raise httpx.ReadTimeout('private upstream URL', request=request)

    assert run(factory, timeout)['pending'] == 1
    task = state['task']
    before, digest = deepcopy(task.input_snapshot), task.input_hash
    assert task.next_retry_at == 1005 and 'private' not in task.last_error
    state['resource'].text = '教师后来修改的正文'
    state['now'] = 1004
    assert run(factory, lambda _: pytest.fail('尚未到重试时间'))['pending'] == 0
    state['now'] = 1005

    def success(request):
        payloads.append(json.loads(request.content))
        return ack(request)

    assert run(factory, success)['delivered'] == 1
    assert payloads[0] == payloads[1]
    assert task.input_snapshot == before and task.input_hash == digest and task.attempt_count == 2


@pytest.mark.parametrize('status,retryable', [(401, False), (403, False), (404, False), (409, False),
    (422, False), (302, False), (408, True), (425, True), (429, True), (500, True), (503, True)])
def test_http_error_classification_never_saves_upstream_error_body(task_api, status, retryable):
    client, db, _, state, factory = task_api
    create_task(client)
    counts = run(factory, lambda _: httpx.Response(status, text='private credentials / raw traceback'))
    assert counts['pending' if retryable else 'failed'] == 1
    assert 'private' not in state['task'].last_error


@pytest.mark.parametrize('body', [b'not json', b'{}', b'x' * 65537,
    json.dumps({'task_id': 'wrong', 'attempt_id': 'attempt', 'status': 'accepted'}).encode(),
    json.dumps({'task_id': 'wrong', 'attempt_id': 'attempt', 'status': 'completed'}).encode()],
    ids=['not-json', 'missing-fields', 'too-large', 'wrong-id', 'wrong-status'])
def test_invalid_or_oversized_receipt_is_not_success(task_api, body):
    client, db, _, state, factory = task_api
    create_task(client)
    assert run(factory, lambda _: httpx.Response(202, content=body))['failed'] == 1
    assert state['task'].delivered_at is None


def test_max_attempts_and_manual_retry_keep_same_id_and_frozen_input(task_api, monkeypatch):
    client, db, _, state, factory = task_api
    monkeypatch.setattr(config, 'DIAGNOSIS_MAX_ATTEMPTS', 1)
    first = create_task(client)
    assert run(factory, lambda _: httpx.Response(503))['failed'] == 1
    task = state['task']
    snapshot, digest = deepcopy(task.input_snapshot), task.input_hash
    retried = create_task(client)
    assert retried['id'] == first['id'] and retried['attempt_count'] == 0 and retried['status'] == 'pending'
    assert task.input_snapshot == snapshot and task.input_hash == digest
    assert run(factory, ack)['delivered'] == 1
    assert create_task(client)['status'] == 'delivered'


def test_crash_lease_recovers_and_late_worker_cannot_overwrite_new_receipt(task_api):
    client, db, _, state, factory = task_api
    create_task(client)
    service = dispatch.configuration()
    old = dispatch.claim_next(factory, service)
    assert dispatch.claim_next(factory, service) is None
    state['now'] = state['task'].lease_expires_at
    current = dispatch.claim_next(factory, service)
    assert current.task_id == old.task_id and current.lease_token != old.lease_token
    receipt = {'task_id': current.task_id, 'attempt_id': 'attempt', 'status': 'accepted'}
    assert dispatch.finish_delivery(factory, current, receipt=receipt) == 'delivered'
    assert dispatch.finish_delivery(factory, old, error=dispatch.DeliveryError('late', retryable=True)) == 'stale'
    assert state['task'].status == 'delivered'


def test_lease_starts_after_slow_snapshot_preparation(task_api, monkeypatch):
    client, db, _, state, factory = task_api
    create_task(client)
    build = dispatch.build_diagnosis_input
    def slow_build(db, attempt):
        data = build(db, attempt)
        state['now'] = 2000
        return data
    monkeypatch.setattr(dispatch, 'build_diagnosis_input', slow_build)
    assert dispatch.claim_next(factory, dispatch.configuration()) is not None
    assert state['task'].lease_expires_at == 2040 and state['task'].updated_at == 2000


def test_exhausted_crash_lease_becomes_failed_without_another_http_call(task_api, monkeypatch):
    client, db, _, state, factory = task_api
    create_task(client)
    monkeypatch.setattr(config, 'DIAGNOSIS_MAX_ATTEMPTS', 1)
    dispatch.claim_next(factory, dispatch.configuration())
    state['now'] = state['task'].lease_expires_at
    assert dispatch.claim_next(factory, dispatch.configuration()) is None
    assert state['task'].status == 'failed' and state['task'].lease_token is None


def test_task_input_requires_prepared_snapshot_and_d_course_scope(task_api, monkeypatch):
    client, db, _, state, factory = task_api
    task = create_task(client)
    path = f'/internal/diagnosis-tasks/{task["id"]}/input'
    assert client.get(path, headers=D_HEADERS).status_code == 409
    assert client.get('/internal/diagnosis-tasks/missing/input', headers=D_HEADERS).status_code == 404
    run(factory, ack)
    assert client.get(path, headers=D_HEADERS).status_code == 200
    monkeypatch.setattr(config, 'D_SERVICE_COURSE_IDS', 'other-course')
    assert client.get(path, headers=D_HEADERS).status_code == 404


@pytest.mark.parametrize('setting,value', [('DIAGNOSIS_URL', 'file:///tmp/service'),
    ('DIAGNOSIS_URL', 'http://user:secret@host'), ('DIAGNOSIS_URL', 'http://[broken'),
    ('DIAGNOSIS_URL', 'http://host:wrong'), ('DIAGNOSIS_TIMEOUT', 0), ('DIAGNOSIS_TIMEOUT', float('nan')),
    ('DIAGNOSIS_MAX_ATTEMPTS', 0), ('DIAGNOSIS_SERVICE_KEY', ''), ('DIAGNOSIS_SERVICE_KEY', 'd' * 40),
    ('D_SERVICE_KEY', 'c' * 40), ('D_SERVICE_COURSE_IDS', '')])
def test_invalid_dispatch_configuration_never_claims_a_task(task_api, monkeypatch, setting, value):
    client, db, _, state, factory = task_api
    create_task(client)
    monkeypatch.setattr(config, setting, value)
    before = db.commit.call_count
    with pytest.raises(dispatch.DispatchConfigurationError):
        run(factory, ack)
    assert state['task'].status == 'pending' and state['task'].attempt_count == 0
    assert db.commit.call_count == before


def test_worker_respects_d_course_scope(task_api, monkeypatch):
    client, db, _, state, factory = task_api
    create_task(client)
    monkeypatch.setattr(config, 'D_SERVICE_COURSE_IDS', 'other-course')
    run(factory, lambda _: pytest.fail('未授权课程不能交付'))
    assert state['task'].attempt_count == 0


def test_corrupt_frozen_snapshot_is_not_delivered(task_api):
    client, db, _, state, factory = task_api
    create_task(client)
    state['task'].input_snapshot, state['task'].input_hash = {'corrupt': True}, '0' * 64
    run(factory, lambda _: pytest.fail('不能投递损坏输入'))
    assert state['task'].status == 'failed'


def test_task_write_failures_roll_back_and_never_report_created(task_api):
    client, db, _, state, _ = task_api
    db.commit.side_effect = SQLAlchemyError('private connection')
    response = client.post('/attempts/attempt/diagnosis-task')
    assert response.status_code == 503 and 'private' not in response.text
    db.rollback.assert_called_once()


def test_task_mysql_ddl_has_uniqueness_lease_and_snapshot_constraints():
    ddl = str(CreateTable(DiagnosisTask.__table__).compile(dialect=mysql.dialect()))
    assert 'UNIQUE (attempt_id)' in ddl
    assert 'fk_diagnosis_task_attempt' in ddl and 'ck_diagnosis_task_lease' in ddl
    assert 'ck_diagnosis_task_input' in ddl and 'ck_diagnosis_task_receipt' in ddl
