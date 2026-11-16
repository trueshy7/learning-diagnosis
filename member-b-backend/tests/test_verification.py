"""验证码生成服务回归测试，不连接业务数据库。"""

from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.models import EmailVerificationCode
from app.services import verification


@pytest.mark.parametrize(('number', 'expected'), [(0, '000000'), (7, '000007'), (999999, '999999')])
def test_code_preserves_six_digits(monkeypatch, number, expected):
    random_number = Mock(return_value=number)
    monkeypatch.setattr(verification.secrets, 'randbelow', random_number)
    assert verification.generate_verification_code() == expected
    random_number.assert_called_once_with(1_000_000)


@pytest.fixture
def code_db(monkeypatch):
    monkeypatch.setattr(verification.config, 'EMAIL_VERIFICATION_SECRET', 'test-secret-' * 4)
    monkeypatch.setattr(verification.time, 'time', lambda: 1000)
    monkeypatch.setattr(verification, 'generate_verification_code', lambda: '000007')
    db = Mock(spec=Session)
    db.scalar.return_value = EmailVerificationCode(
        email='student@example.com', purpose='register', code_hash='',
        created_at=0, expires_at=0, attempts=0,
    )
    return db


def test_issue_stores_digest_and_returns_code_for_mailer(code_db):
    result = verification.issue_registration_code(code_db, ' Student@Example.com ')
    assert result.email == 'student@example.com'
    assert result.code == '000007'
    assert result.code not in repr(result)
    assert result.expires_at == 1300
    record = code_db.scalar.return_value
    assert record.code_hash == verification.hash_verification_code(result.email, 'register', result.code)
    assert len(record.code_hash) == 64
    assert record.created_at == 1000
    assert record.expires_at == 1300
    code_db.commit.assert_called_once()
    code_db.rollback.assert_not_called()
    # 首次生成和重复生成都锁住邮箱对应的同一行。
    statement = code_db.execute.call_args.args[0].compile(dialect=mysql.dialect())
    assert 'ON DUPLICATE KEY UPDATE' in str(statement)
    lookup = code_db.scalar.call_args.args[0].compile(dialect=mysql.dialect())
    assert 'FOR UPDATE' in str(lookup)


def test_cooldown_does_not_replace_existing_code(code_db):
    record = code_db.scalar.return_value
    record.created_at = 941
    record.code_hash = 'existing-digest'
    with pytest.raises(verification.VerificationCodeTooFrequent) as exc:
        verification.issue_registration_code(code_db, record.email)
    assert exc.value.retry_after == 1
    assert record.code_hash == 'existing-digest'
    code_db.commit.assert_not_called()
    code_db.rollback.assert_called_once()


def test_resend_at_cooldown_boundary_replaces_old_code(code_db):
    record = code_db.scalar.return_value
    record.created_at = 940
    record.code_hash = 'old-digest'
    record.attempts = 4
    record.used_at = 950
    verification.issue_registration_code(code_db, record.email)
    assert record.code_hash != 'old-digest'
    assert record.attempts == 0
    assert record.used_at is None
    assert record.created_at == 1000


@pytest.mark.parametrize('email', ['', 'missing-domain', 'a@@example.com', 'a b@example.com', 'a' * 244 + '@example.com'])
def test_invalid_email_does_not_touch_database(code_db, email):
    with pytest.raises(ValueError, match='邮箱格式'):
        verification.issue_registration_code(code_db, email)
    code_db.execute.assert_not_called()
    code_db.commit.assert_not_called()


def test_hash_is_bound_to_email_purpose_and_secret(code_db, monkeypatch):
    original = verification.hash_verification_code('a@example.com', 'register', '000007')
    assert original != verification.hash_verification_code('b@example.com', 'register', '000007')
    assert original != verification.hash_verification_code('a@example.com', 'reset_password', '000007')
    monkeypatch.setattr(verification.config, 'EMAIL_VERIFICATION_SECRET', 'another-secret-' * 4)
    assert original != verification.hash_verification_code('a@example.com', 'register', '000007')


@pytest.mark.parametrize('secret', ['', 'short'])
def test_missing_or_short_secret_fails_before_database_access(code_db, monkeypatch, secret):
    monkeypatch.setattr(verification.config, 'EMAIL_VERIFICATION_SECRET', secret)
    with pytest.raises(RuntimeError, match='EMAIL_VERIFICATION_SECRET'):
        verification.issue_registration_code(code_db, 'student@example.com')
    code_db.execute.assert_not_called()


def test_database_error_rolls_back(code_db):
    code_db.commit.side_effect = RuntimeError('write failed')
    with pytest.raises(RuntimeError, match='write failed'):
        verification.issue_registration_code(code_db, 'student@example.com')
    code_db.rollback.assert_called_once()
