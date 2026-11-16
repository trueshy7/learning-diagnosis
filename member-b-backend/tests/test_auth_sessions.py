"""认证回归测试：使用 MySQL 方言和模拟会话，不访问业务数据库。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.api import auth
from app.models import LoginSession, User
from app.security import current_user, token_hash


def assert_token_lookup(statement, raw_token):
    compiled = statement.compile(dialect=mysql.dialect())
    assert 'WHERE login_sessions.token_hash =' in str(compiled)
    assert token_hash(raw_token) in compiled.params.values()
    assert raw_token not in compiled.params.values()


def test_current_user_looks_up_token_hash(monkeypatch):
    monkeypatch.setattr('app.security.time.time', lambda: 100)
    user = User(id=7, username='student')
    db = Mock(spec=Session)
    db.scalar.return_value = LoginSession(user_id=7, expires_at=101)
    db.get.return_value = user
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials='raw-token')

    assert current_user(credentials, db) is user
    assert_token_lookup(db.scalar.call_args.args[0], 'raw-token')
    db.get.assert_called_once_with(User, 7)


@pytest.mark.parametrize('expires_at', [99, 100, None])
def test_expired_or_missing_session_is_rejected(monkeypatch, expires_at):
    monkeypatch.setattr('app.security.time.time', lambda: 100)
    db = Mock(spec=Session)
    db.scalar.return_value = (
        LoginSession(user_id=7, expires_at=expires_at) if expires_at is not None else None
    )
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials='raw-token')

    with pytest.raises(HTTPException) as exc:
        current_user(credentials, db)
    assert exc.value.status_code == 401
    db.get.assert_not_called()


def test_logout_deletes_only_matching_session():
    db = Mock(spec=Session)
    session = LoginSession(id=12, user_id=7)
    db.scalar.return_value = session
    request = SimpleNamespace(state=SimpleNamespace(request_id='test'))

    response = auth.logout(request, User(id=7), db, 'Bearer raw-token')

    assert response['data'] == {'logged_out': True}
    assert_token_lookup(db.scalar.call_args.args[0], 'raw-token')
    db.delete.assert_called_once_with(session)
    db.commit.assert_called_once()


def test_login_cleans_expired_sessions_and_stores_hash(monkeypatch):
    monkeypatch.setattr(auth.time, 'time', lambda: 100)
    monkeypatch.setattr(auth, 'check_password', lambda password, stored: True)
    monkeypatch.setattr(auth.secrets, 'token_urlsafe', lambda size: 'raw-token')
    db = Mock(spec=Session)
    db.scalar.return_value = User(id=7, username='student', role='student', password_hash='hash')
    request = SimpleNamespace(state=SimpleNamespace(request_id='test'))

    response = auth.login(SimpleNamespace(username='student', password='password'), request, db)

    compiled = db.execute.call_args.args[0].compile(dialect=mysql.dialect())
    assert 'DELETE FROM login_sessions WHERE login_sessions.expires_at <=' in str(compiled)
    assert list(compiled.params.values()) == [100]
    session = db.add.call_args.args[0]
    assert session.user_id == 7
    assert session.token_hash == token_hash('raw-token')
    assert session.expires_at == 86500
    assert response['data']['access_token'] == 'raw-token'
    db.commit.assert_called_once()


def test_failed_login_does_not_change_sessions(monkeypatch):
    monkeypatch.setattr(auth, 'check_password', lambda password, stored: False)
    db = Mock(spec=Session)
    db.scalar.return_value = User(password_hash='hash')
    request = SimpleNamespace(state=SimpleNamespace(request_id='test'))

    with pytest.raises(HTTPException) as exc:
        auth.login(SimpleNamespace(username='student', password='wrong'), request, db)
    assert exc.value.status_code == 401
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
