"""注册接口回归测试，数据库会话使用替身，不连接业务数据库。"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import config, main
from app.database import get_db
from app.models import EmailVerificationCode, LoginSession, User
from app.security import check_password
from app.services import registration
from app.services.verification import hash_verification_code


def payload(**overrides):
    return {
        'username': 'student01', 'email': 'student@example.com',
        'password': 'Example123!', 'confirm_password': 'Example123!',
        'verification_code': '082391', **overrides,
    }


@pytest.fixture
def register_api(monkeypatch):
    monkeypatch.setattr(config, 'EMAIL_VERIFICATION_SECRET', 'test-secret-' * 4)
    monkeypatch.setattr(registration.time, 'time', lambda: 1000)
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    record = EmailVerificationCode(
        email='student@example.com', purpose='register',
        code_hash=hash_verification_code('student@example.com', 'register', '082391'),
        created_at=900, expires_at=1200, attempts=0,
    )
    state = {'record': record, 'existing_id': None, 'user': None}
    db = Mock(spec=Session)

    def lookup(statement):
        if statement.column_descriptions[0]['entity'] is EmailVerificationCode:
            return state['record']
        return state['existing_id']

    def add(user):
        state['user'] = user

    def flush():
        state['user'].id = 42

    db.scalar.side_effect = lookup
    db.add.side_effect = add
    db.flush.side_effect = flush
    main.app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(main.app) as client:
            yield client, db, state
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_register_hashes_password_and_consumes_code_in_same_transaction(register_api):
    client, db, state = register_api
    events = []

    def commit():
        assert state['record'].used_at == 1000
        assert state['user'].id == 42
        events.append('commit')

    db.commit.side_effect = commit
    response = client.post('/user/register', json=payload(username=' student01 ', email=' Student@Example.com '))
    assert response.status_code == 201
    assert response.json()['data'] == {
        'id': 42, 'username': 'student01', 'email': 'student@example.com', 'role': 'student',
    }
    user = state['user']
    assert user.password_hash != payload()['password']
    assert check_password(payload()['password'], user.password_hash)
    assert not hasattr(user, 'confirm_password')
    for secret in ('Example123!', '082391', user.password_hash, 'password_hash'):
        assert secret not in response.text
    assert events == ['commit']
    assert response.headers['X-Request-ID'] == response.json()['request_id']
    query = db.scalar.call_args_list[0].args[0].compile(dialect=mysql.dialect())
    assert 'FOR UPDATE' in str(query)
    assert 'student@example.com' in query.params.values()
    assert 'register' in query.params.values()


@pytest.mark.parametrize('overrides', [
    {'username': 'ab'}, {'username': 'a' * 65}, {'username': 'has space'},
    {'username': None}, {'username': 123}, {'email': 'not-email'},
    {'password': 'Abc1234', 'confirm_password': 'Abc1234'},
    {'password': 'abcdefgh', 'confirm_password': 'abcdefgh'},
    {'password': '12345678', 'confirm_password': '12345678'},
    {'password': 'A1' * 65, 'confirm_password': 'A1' * 65},
    {'password': 'Abc1234\n', 'confirm_password': 'Abc1234\n'},
    {'confirm_password': 'Different123'}, {'verification_code': '12345'},
    {'verification_code': '１２３４５６'}, {'verification_code': 82391},
    {'role': 'admin'}, {'role': ''}, {'role': 'Teacher'}, {'role': None}, {'role': 1}, {'id': 42},
])
def test_invalid_input_never_touches_database(register_api, overrides):
    client, db, state = register_api
    response = client.post('/user/register', json=payload(**overrides))
    assert response.status_code == 422
    assert 'Example123!' not in response.text
    db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_code_cannot_be_reused(register_api):
    client, db, state = register_api
    assert client.post('/user/register', json=payload()).status_code == 201
    response = client.post('/user/register', json=payload(username='anotheruser'))
    assert response.status_code == 400
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.parametrize('code_state', ['missing', 'expired', 'expiry_boundary', 'used', 'wrong_purpose', 'other_email'])
def test_unusable_code_rejected(register_api, code_state):
    client, db, state = register_api
    record = state['record']
    if code_state == 'missing':
        state['record'] = None
    elif code_state == 'expired':
        record.expires_at = 999
    elif code_state == 'expiry_boundary':
        record.expires_at = 1000
    elif code_state == 'used':
        record.used_at = 999
    elif code_state == 'wrong_purpose':
        record.code_hash = hash_verification_code(record.email, 'reset_password', '082391')
    else:
        record.code_hash = hash_verification_code('other@example.com', 'register', '082391')
    response = client.post('/user/register', json=payload())
    assert response.status_code == 400
    db.add.assert_not_called()


def test_wrong_attempts_persist_and_fifth_failure_locks_code(register_api):
    client, db, state = register_api
    saved_attempts = []
    db.commit.side_effect = lambda: saved_attempts.append(state['record'].attempts)
    for attempt in range(1, 6):
        response = client.post('/user/register', json=payload(verification_code='000000'))
        assert response.status_code == (429 if attempt == 5 else 400)
    assert saved_attempts == [1, 2, 3, 4, 5]
    assert client.post('/user/register', json=payload()).status_code == 429
    assert db.commit.call_count == 5
    db.add.assert_not_called()


def test_duplicate_account_does_not_consume_code(register_api):
    client, db, state = register_api
    state['existing_id'] = 7
    response = client.post('/user/register', json=payload())
    assert response.status_code == 409
    assert state['record'].used_at is None
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_concurrent_unique_key_conflict_returns_conflict(register_api):
    client, db, state = register_api
    db.flush.side_effect = IntegrityError('insert', {}, Exception(1062, 'private duplicate error'))
    response = client.post('/user/register', json=payload())
    assert response.status_code == 409
    assert 'private duplicate error' not in response.text
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('stage', ['query', 'flush', 'commit', 'other_integrity_error'])
def test_database_failures_do_not_report_success(register_api, stage):
    client, db, state = register_api
    if stage == 'query':
        db.scalar.side_effect = SQLAlchemyError('private DB error')
    elif stage == 'other_integrity_error':
        db.flush.side_effect = IntegrityError('insert', {}, Exception(1048, 'private DB error'))
    else:
        getattr(db, stage).side_effect = SQLAlchemyError('private DB error')
    response = client.post('/user/register', json=payload())
    assert response.status_code == 503
    assert 'private DB error' not in response.text
    assert 'Example123!' not in response.text
    db.rollback.assert_called_once()


def test_missing_secret_returns_unavailable(register_api, monkeypatch):
    client, db, state = register_api
    monkeypatch.setattr(config, 'EMAIL_VERIFICATION_SECRET', '')
    assert client.post('/user/register', json=payload()).status_code == 503
    db.scalar.assert_not_called()


def test_registered_password_can_be_used_to_login(register_api):
    client, db, state = register_api
    assert client.post('/user/register', json=payload()).status_code == 201
    user = state['user']
    db.scalar.side_effect = None
    db.scalar.return_value = user
    response = client.post('/user/login', json={
        'username': 'student01', 'password': 'Example123!',
    })
    assert response.status_code == 200
    assert response.json()['data']['user']['id'] == 42
    assert isinstance(state['user'], LoginSession)


@pytest.mark.parametrize('role', ['student', 'teacher'])
def test_selected_role_is_saved_and_returned_by_login_and_info(register_api, role):
    client, db, state = register_api
    response = client.post('/user/register', json=payload(role=role))
    assert response.status_code == 201
    user = state['user']
    assert user.role == role
    assert response.json()['data']['role'] == role
    assert state['record'].used_at == 1000
    db.commit.assert_called_once()

    db.scalar.side_effect = None
    db.scalar.return_value = user
    response = client.post('/user/login', json={'username': user.username, 'password': payload()['password']})
    assert response.status_code == 200
    assert response.json()['data']['user']['role'] == role
    session = state['user']
    db.scalar.return_value = session
    db.get.return_value = user
    response = client.get('/user/info', headers={'Authorization': 'Bearer ' + response.json()['data']['access_token']})
    assert response.status_code == 200
    assert response.json()['data']['role'] == role


def test_password_spaces_are_preserved(register_api):
    client, db, state = register_api
    password = ' Example123! '
    response = client.post('/user/register', json=payload(password=password, confirm_password=password))
    assert response.status_code == 201
    assert check_password(password, state['user'].password_hash)
    assert not check_password(password.strip(), state['user'].password_hash)
