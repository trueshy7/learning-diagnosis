"""用户账户 HTTP 回归测试；MySQL、SMTP 均使用替身。"""

import smtplib
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import config, main
from app.database import get_db
from app.models import EmailVerificationCode, LoginSession, User
from app.security import check_password, hash_password, token_hash
from app.services import mail, verification

EMAIL = 'student@example.com'
OLD_PASSWORD = 'OldPassword123!'
NEW_PASSWORD = 'NewPassword456!'
RESET_CODE = '082391'


def reset_payload(**overrides):
    return {'email': EMAIL, 'verification_code': RESET_CODE,
            'password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD, **overrides}


@pytest.fixture
def account_api(monkeypatch):
    for key, value in {
        'EMAIL_VERIFICATION_SECRET': 'test-secret-' * 4,
        'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': 465,
        'SMTP_USERNAME': 'sender@example.com', 'SMTP_PASSWORD': 'smtp-secret',
        'SMTP_FROM': 'sender@example.com', 'SMTP_SECURITY': 'ssl', 'SMTP_TIMEOUT': 10,
    }.items():
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(verification.time, 'time', lambda: 1000)
    monkeypatch.setattr(verification, 'generate_verification_code', lambda: '654321')
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    smtp_factory = MagicMock()
    smtp = smtp_factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', smtp_factory)
    user = User(id=7, username='student', email=EMAIL, role='student', password_hash=hash_password(OLD_PASSWORD))
    codes = {purpose: EmailVerificationCode(
        email=EMAIL, purpose=purpose, code_hash=verification.hash_verification_code(EMAIL, purpose, RESET_CODE),
        created_at=900, expires_at=1200, attempts=0,
    ) for purpose in ('register', 'reset_password')}
    sessions = {token_hash(value): LoginSession(user_id=uid, token_hash=token_hash(value), expires_at=2000)
                for value, uid in [('old-token', 7), ('second-token', 7), ('other-user-token', 8)]}
    state = {'user': user, 'codes': codes, 'sessions': sessions, 'pending': [], 'smtp': smtp}
    db = Mock(spec=Session)

    def lookup(statement):
        entity = statement.column_descriptions[0]['entity']
        params = statement.compile(dialect=mysql.dialect()).params
        if entity is User:
            if params.get('email_1', EMAIL) != user.email or params.get('username_1', user.username) != user.username:
                return None
            return user.id if statement.column_descriptions[0]['name'] == 'id' else user
        if entity is EmailVerificationCode:
            if params.get('email_1') != EMAIL:
                return None
            return codes.get(params.get('purpose_1'))
        if entity is LoginSession:
            return sessions.get(params.get('token_hash_1'))
        raise AssertionError(f'Unexpected entity {entity}')

    def execute(statement):
        if statement.is_delete and statement.table.name == 'login_sessions':
            params = statement.compile(dialect=mysql.dialect()).params
            for key, session in list(sessions.items()):
                if (session.user_id == params.get('user_id_1')
                        or session.expires_at <= params.get('expires_at_1', -1)):
                    del sessions[key]

    def commit():
        for session in state['pending']:
            sessions[session.token_hash] = session
        state['pending'].clear()

    db.scalar.side_effect = lookup
    db.execute.side_effect = execute
    db.get.side_effect = lambda cls, identity: user if cls is User and identity == user.id else None
    db.add.side_effect = state['pending'].append
    db.delete.side_effect = lambda session: sessions.pop(session.token_hash, None)
    db.commit.side_effect = commit
    main.app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(main.app) as client:
            yield client, db, state
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_login_creates_hashed_session_and_info_returns_only_public_fields(account_api):
    client, db, state = account_api
    response = client.post('/user/login', json={'username': ' student ', 'password': OLD_PASSWORD})
    assert response.status_code == 200
    data = response.json()['data']
    token = data['access_token']
    assert token_hash(token) in state['sessions']
    assert token not in state['sessions']
    assert state['sessions'][token_hash(token)].expires_at == 87400
    lookup = db.scalar.call_args.args[0].compile(dialect=mysql.dialect())
    assert 'FOR UPDATE' in str(lookup)
    response = client.get('/user/info', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.json()['data'] == {'username': 'student', 'role': 'student', 'email': EMAIL}
    assert 'password' not in response.text
    assert response.headers['X-Request-ID'] == response.json()['request_id']


@pytest.mark.parametrize('path', ['/user/login'])
@pytest.mark.parametrize('overrides', [{'username': 'missing'}, {'password': 'WrongPassword123!'}])
def test_login_wrong_credentials_rejected(account_api, path, overrides):
    client, db, state = account_api
    response = client.post(path, json={'username': 'student', 'password': OLD_PASSWORD, **overrides})
    assert response.status_code == 401
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('payload', [
    {}, {'username': 'ab', 'password': OLD_PASSWORD},
    {'username': 'student', 'password': 'short'},
    {'username': 'has space', 'password': OLD_PASSWORD},
    {'username': 'student', 'password': OLD_PASSWORD, 'captcha_code': '123456'},
])
def test_login_validation_rejects_bad_fields(account_api, payload):
    client, db, state = account_api
    assert client.post('/user/login', json=payload).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize('path', ['/user/info', '/user/exit'])
@pytest.mark.parametrize('token', [None, 'unknown', 'expired'])
def test_info_and_exit_require_active_session(account_api, path, token):
    client, db, state = account_api
    if token == 'expired':
        state['sessions'][token_hash(token)] = LoginSession(user_id=7, token_hash=token_hash(token), expires_at=1000)
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    response = client.request('GET' if path.endswith('info') else 'POST', path, headers=headers)
    assert response.status_code == 401


def test_exit_deletes_only_current_session(account_api):
    client, db, state = account_api
    headers = {'Authorization': 'Bearer old-token'}
    response = client.post('/user/exit', headers=headers)
    assert response.status_code == 200
    assert response.json()['data'] == {'logged_out': True}
    assert token_hash('old-token') not in state['sessions']
    assert token_hash('second-token') in state['sessions']
    assert client.get('/user/info', headers=headers).status_code == 401
    assert client.get('/user/info', headers={'Authorization': 'Bearer second-token'}).status_code == 200


def test_send_reset_code_uses_independent_purpose_and_mail_subject(account_api):
    client, db, state = account_api
    registration_digest = state['codes']['register'].code_hash
    response = client.post('/user/send-reset-password-code', json={'email': ' Student@Example.com '})
    assert response.status_code == 200
    assert response.json()['data']['sent'] is True
    assert '654321' not in response.text
    message = state['smtp'].send_message.call_args.args[0]
    assert '重置密码' in message['Subject']
    assert '654321' in message.get_content()
    assert state['codes']['register'].code_hash == registration_digest
    assert state['codes']['reset_password'].code_hash == verification.hash_verification_code(EMAIL, 'reset_password', '654321')
    response = client.post('/user/send-reset-password-code', json={'email': EMAIL})
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'
    state['smtp'].send_message.assert_called_once()


@pytest.mark.parametrize(('email', 'status'), [('unknown@example.com', 404), ('not-email', 422)])
def test_send_reset_requires_existing_valid_email(account_api, email, status):
    client, db, state = account_api
    assert client.post('/user/send-reset-password-code', json={'email': email}).status_code == status
    state['smtp'].send_message.assert_not_called()
    db.commit.assert_not_called()


def test_reset_updates_hash_consumes_code_revokes_sessions_and_accepts_new_password(account_api):
    client, db, state = account_api
    old_digest = state['user'].password_hash
    response = client.post('/user/resetPassword', json=reset_payload())
    assert response.status_code == 200
    assert response.json()['data'] == {'password_reset': True}
    assert NEW_PASSWORD not in response.text and RESET_CODE not in response.text
    assert state['user'].password_hash != old_digest
    assert check_password(NEW_PASSWORD, state['user'].password_hash)
    assert not check_password(OLD_PASSWORD, state['user'].password_hash)
    assert state['codes']['reset_password'].used_at == 1000
    assert state['codes']['register'].used_at is None
    assert set(state['sessions']) == {token_hash('other-user-token')}
    db.commit.assert_called_once()
    user_query = db.scalar.call_args.args[0].compile(dialect=mysql.dialect())
    assert 'FOR UPDATE' in str(user_query)
    assert client.get('/user/info', headers={'Authorization': 'Bearer old-token'}).status_code == 401
    assert client.post('/user/login', json={'username': 'student', 'password': OLD_PASSWORD}).status_code == 401
    assert client.post('/user/login', json={'username': 'student', 'password': NEW_PASSWORD}).status_code == 200
    assert client.post('/user/resetPassword', json=reset_payload()).status_code == 400


@pytest.mark.parametrize('overrides', [
    {'email': 'invalid'}, {'verification_code': '12345'}, {'verification_code': 82391},
    {'password': 'onlyletters', 'confirm_password': 'onlyletters'},
    {'password': '12345678', 'confirm_password': '12345678'},
    {'password': 'Short1', 'confirm_password': 'Short1'},
    {'password': 'A1' * 65, 'confirm_password': 'A1' * 65},
    {'password': 'Abcd123\n', 'confirm_password': 'Abcd123\n'},
    {'confirm_password': 'Mismatch123!'}, {'captcha_id': 'not-required'},
])
def test_reset_input_rejected_before_database(account_api, overrides):
    client, db, state = account_api
    response = client.post('/user/resetPassword', json=reset_payload(**overrides))
    assert response.status_code == 422
    assert NEW_PASSWORD not in response.text
    db.scalar.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize('condition', ['missing', 'expired', 'used', 'register_only', 'other_email'])
def test_reset_unusable_or_wrong_purpose_code_cannot_change_password(account_api, condition):
    client, db, state = account_api
    record = state['codes']['reset_password']
    if condition in ('missing', 'register_only'):
        del state['codes']['reset_password']
    elif condition == 'expired':
        record.expires_at = 1000
    elif condition == 'used':
        record.used_at = 999
    else:
        record.code_hash = verification.hash_verification_code('other@example.com', 'reset_password', RESET_CODE)
    response = client.post('/user/resetPassword', json=reset_payload())
    assert response.status_code == 400
    assert check_password(OLD_PASSWORD, state['user'].password_hash)
    assert len(state['sessions']) == 3


def test_five_wrong_reset_codes_persist_attempts_and_lock_correct_code(account_api):
    client, db, state = account_api
    for attempt in range(1, 6):
        response = client.post('/user/resetPassword', json=reset_payload(verification_code='000000'))
        assert response.status_code == (400 if attempt < 5 else 429)
    assert state['codes']['reset_password'].attempts == 5
    assert client.post('/user/resetPassword', json=reset_payload()).status_code == 429
    assert db.commit.call_count == 5
    assert check_password(OLD_PASSWORD, state['user'].password_hash)


def test_reset_account_deleted_after_code_was_sent(account_api):
    client, db, state = account_api
    original = db.scalar.side_effect
    db.scalar.side_effect = lambda query: None if query.column_descriptions[0]['entity'] is User else original(query)
    assert client.post('/user/resetPassword', json=reset_payload()).status_code == 404
    db.commit.assert_not_called()
    assert state['codes']['reset_password'].used_at is None


@pytest.mark.parametrize('stage', ['query', 'delete_sessions', 'commit'])
def test_reset_database_failure_returns_503_and_rolls_back(account_api, stage):
    client, db, state = account_api
    if stage == 'query':
        db.scalar.side_effect = SQLAlchemyError('private DB error')
    elif stage == 'delete_sessions':
        db.execute.side_effect = SQLAlchemyError('private DB error')
    else:
        db.commit.side_effect = SQLAlchemyError('private DB error')
    response = client.post('/user/resetPassword', json=reset_payload())
    assert response.status_code == 503
    assert 'private DB error' not in response.text
    db.rollback.assert_called_once()


def test_reset_missing_secret_returns_503(account_api, monkeypatch):
    client, db, state = account_api
    monkeypatch.setattr(config, 'EMAIL_VERIFICATION_SECRET', '')
    assert client.post('/user/resetPassword', json=reset_payload()).status_code == 503
    db.scalar.assert_not_called()


def test_reset_mail_failure_rolls_back(account_api):
    client, db, state = account_api
    state['smtp'].send_message.side_effect = smtplib.SMTPException('private SMTP details')
    response = client.post('/user/send-reset-password-code', json={'email': EMAIL})
    assert response.status_code == 502
    assert 'private SMTP details' not in response.text
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('path', ['/user/login', '/user/info', '/user/exit'])
def test_account_database_errors_are_hidden(account_api, path):
    client, db, state = account_api
    db.scalar.side_effect = SQLAlchemyError('private error')
    response = client.request('GET' if path.endswith('info') else 'POST', path,
                              headers={'Authorization': 'Bearer old-token'},
                              json={'username': 'student', 'password': OLD_PASSWORD} if path.endswith('login') else None)
    assert response.status_code == 503
    assert 'private error' not in response.text


def test_malformed_stored_password_does_not_crash_login(account_api):
    client, db, state = account_api
    state['user'].password_hash = 'invalid-hash-format'
    response = client.post('/user/login', json={'username': 'student', 'password': OLD_PASSWORD})
    assert response.status_code == 401


@pytest.mark.parametrize('path', ['/auth/login', '/auth/logout'])
def test_unmounted_legacy_auth_routes_return_404(account_api, path):
    client, db, state = account_api
    assert client.post(path).status_code == 404
