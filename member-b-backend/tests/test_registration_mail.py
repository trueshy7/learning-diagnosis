"""HTTP 至 SMTP 的验证码流程测试，不连接真实数据库或邮件服务。"""

import smtplib
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import config, main
from app.database import get_db
from app.models import EmailVerificationCode
from app.services import mail, verification


@pytest.fixture
def mail_api(monkeypatch):
    settings = {
        'EMAIL_VERIFICATION_SECRET': 'test-secret-' * 4,
        'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': 465,
        'SMTP_USERNAME': 'sender@example.com', 'SMTP_PASSWORD': 'smtp-secret',
        'SMTP_FROM': 'sender@example.com', 'SMTP_SECURITY': 'ssl', 'SMTP_TIMEOUT': 10,
    }
    for key, value in settings.items():
        monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(verification.time, 'time', lambda: 1000)
    monkeypatch.setattr(verification, 'generate_verification_code', lambda: '082391')
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    smtp_factory = MagicMock()
    smtp = smtp_factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(mail.smtplib, 'SMTP_SSL', smtp_factory)
    db = Mock(spec=Session)
    db.scalar.return_value = EmailVerificationCode(
        email='student@example.com', purpose='register', code_hash='',
        created_at=0, expires_at=0, attempts=0,
    )
    main.app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(main.app) as client:
            yield client, db, smtp_factory, smtp
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_http_sends_mail_without_exposing_code(mail_api):
    client, db, smtp_factory, smtp = mail_api
    response = client.post('/user/send-register-code', json={'email': ' Student@Example.com '})
    assert response.status_code == 200
    assert response.json()['data'] == {
        'sent': True, 'email': 'student@example.com', 'expires_in': 300, 'retry_after': 60,
    }
    assert '082391' not in response.text
    assert 'code_hash' not in response.text
    assert response.headers['X-Request-ID'] == response.json()['request_id']
    smtp_factory.assert_called_once()
    smtp.login.assert_called_once_with('sender@example.com', 'smtp-secret')
    message = smtp.send_message.call_args.args[0]
    assert message['To'] == 'student@example.com'
    assert message['From'] == 'sender@example.com'
    assert '082391' in message.get_content()
    assert '082391' != db.scalar.return_value.code_hash
    db.commit.assert_called_once()


def test_second_http_request_is_rate_limited(mail_api):
    client, db, smtp_factory, smtp = mail_api
    assert client.post('/user/send-register-code', json={'email': 'student@example.com'}).status_code == 200
    response = client.post('/user/send-register-code', json={'email': 'STUDENT@example.com'})
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'
    smtp.send_message.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('payload', [
    {}, {'email': None}, {'email': 123}, {'email': 'not-an-email'},
    {'email': 'a..b@example.com'}, {'email': 'a@-example.com'},
    {'email': 'a@example..com'}, {'email': 'a@example.com\r\nBcc:b@example.com'},
    {'email': 'student@example.com', 'code': '123456'},
])
def test_invalid_input_never_sends_mail(mail_api, payload):
    client, db, smtp_factory, smtp = mail_api
    response = client.post('/user/send-register-code', json=payload)
    assert response.status_code == 422
    db.execute.assert_not_called()
    smtp_factory.assert_not_called()


@pytest.mark.parametrize('failure', [smtplib.SMTPException('private server error'), TimeoutError('timeout')])
def test_mail_failure_rolls_back_and_hides_server_details(mail_api, failure):
    client, db, smtp_factory, smtp = mail_api
    smtp.send_message.side_effect = failure
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 502
    assert 'private server error' not in response.text
    assert '082391' not in response.text
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_recipient_refusal_is_not_reported_as_sent(mail_api):
    client, db, smtp_factory, smtp = mail_api
    smtp.send_message.return_value = {'student@example.com': (550, b'refused')}
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 502
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize(('key', 'value'), [
    ('SMTP_HOST', ''), ('SMTP_PASSWORD', ''), ('SMTP_FROM', 'invalid'),
    ('SMTP_SECURITY', 'plain'), ('SMTP_PORT', 0), ('SMTP_TIMEOUT', 0),
    ('EMAIL_VERIFICATION_SECRET', ''),
])
def test_incomplete_configuration_returns_unavailable(mail_api, monkeypatch, key, value):
    client, db, smtp_factory, smtp = mail_api
    monkeypatch.setattr(config, key, value)
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 503
    db.execute.assert_not_called()
    smtp_factory.assert_not_called()


def test_database_failure_never_sends_mail(mail_api):
    client, db, smtp_factory, smtp = mail_api
    db.execute.side_effect = SQLAlchemyError('private database error')
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 503
    assert 'private database error' not in response.text
    db.rollback.assert_called_once()
    smtp_factory.assert_not_called()


def test_starttls_is_required_before_authentication(mail_api, monkeypatch):
    client, db, smtp_ssl, _ = mail_api
    monkeypatch.setattr(config, 'SMTP_SECURITY', 'starttls')
    monkeypatch.setattr(config, 'SMTP_PORT', 587)
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(mail.smtplib, 'SMTP', factory)
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 200
    smtp_ssl.assert_not_called()
    operations = [call[0] for call in smtp.method_calls]
    assert operations == ['ehlo', 'starttls', 'ehlo', 'login', 'send_message']
    assert smtp.starttls.call_args.kwargs['context'].check_hostname


def test_mail_is_sent_before_database_commit(mail_api):
    client, db, smtp_factory, smtp = mail_api
    events = []
    smtp.send_message.side_effect = lambda message: events.append('send') or {}
    db.commit.side_effect = lambda: events.append('commit')
    assert client.post('/user/send-register-code', json={'email': 'student@example.com'}).status_code == 200
    assert events == ['send', 'commit']


def test_commit_failure_does_not_report_success(mail_api):
    client, db, smtp_factory, smtp = mail_api
    db.commit.side_effect = SQLAlchemyError('commit failed')
    response = client.post('/user/send-register-code', json={'email': 'student@example.com'})
    assert response.status_code == 503
    smtp.send_message.assert_called_once()
    db.rollback.assert_called_once()
