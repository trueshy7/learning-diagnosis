"""邮箱注册与密码重置验证码的生成、存储及校验。"""

from dataclasses import dataclass, field
from collections.abc import Callable
import hashlib
import hmac
import secrets
import time

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from .. import config
from ..email_utils import normalize_email
from ..models import EmailVerificationCode

CODE_TTL_SECONDS = 300
CODE_COOLDOWN_SECONDS = 60
REGISTER_PURPOSE = 'register'
RESET_PASSWORD_PURPOSE = 'reset_password'
MAX_CODE_ATTEMPTS = 5


class VerificationConfigurationError(RuntimeError):
    pass


class InvalidVerificationCode(ValueError):
    pass


class VerificationAttemptsExceeded(ValueError):
    pass


class VerificationCodeTooFrequent(ValueError):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f'请在 {retry_after} 秒后重新获取验证码')


@dataclass(frozen=True)
class GeneratedVerificationCode:
    email: str
    code: str = field(repr=False)
    expires_at: int


def generate_verification_code() -> str:
    """使用安全随机数生成六位数字，保留前导零。"""
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_verification_code(email: str, purpose: str, code: str) -> str:
    secret = config.EMAIL_VERIFICATION_SECRET
    if len(secret.encode('utf-8')) < 32:
        raise VerificationConfigurationError('请配置至少 32 字节的 EMAIL_VERIFICATION_SECRET')
    message = f'{email}\0{purpose}\0{code}'.encode('utf-8')
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def issue_registration_code(
    db: Session,
    email: str,
    *,
    deliver: Callable[[GeneratedVerificationCode], None] | None = None,
) -> GeneratedVerificationCode:
    return issue_email_code(db, email, REGISTER_PURPOSE, deliver=deliver)


def issue_email_code(
    db: Session, email: str, purpose: str,
    *, deliver: Callable[[GeneratedVerificationCode], None] | None = None,
) -> GeneratedVerificationCode:
    """生成指定用途验证码，发送成功后提交；失败则回滚，保留旧记录。"""
    if purpose not in (REGISTER_PURPOSE, RESET_PASSWORD_PURPOSE):
        raise ValueError('邮箱验证码用途不正确')
    email = normalize_email(email)
    code = generate_verification_code()
    digest = hash_verification_code(email, purpose, code)

    try:
        # 先获得唯一记录的写锁，避免并发首次请求绕过冷却时间。
        statement = insert(EmailVerificationCode).values(
            email=email,
            purpose=purpose,
            code_hash='',
            created_at=0,
            expires_at=0,
            attempts=0,
            used_at=None,
        )
        db.execute(statement.on_duplicate_key_update(id=EmailVerificationCode.id))
        record = db.scalar(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            ).with_for_update().execution_options(populate_existing=True)
        )
        now = int(time.time())
        if record.created_at and now < record.created_at + CODE_COOLDOWN_SECONDS:
            raise VerificationCodeTooFrequent(record.created_at + CODE_COOLDOWN_SECONDS - now)
        record.code_hash = digest
        record.created_at = now
        record.expires_at = now + CODE_TTL_SECONDS
        record.attempts = 0
        record.used_at = None
        generated = GeneratedVerificationCode(email=email, code=code, expires_at=now + CODE_TTL_SECONDS)
        if deliver is not None:
            deliver(generated)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return generated


def verify_email_code_for_update(db: Session, email: str, purpose: str, code: str) -> EmailVerificationCode:
    """锁定并校验邮箱码；调用方负责成功消费和事务，错误次数单独提交。"""
    digest = hash_verification_code(email, purpose, code)
    record = db.scalar(select(EmailVerificationCode).where(
        EmailVerificationCode.email == email,
        EmailVerificationCode.purpose == purpose,
    ).with_for_update().execution_options(populate_existing=True))
    now = int(time.time())
    if record is None or record.expires_at <= now or record.used_at is not None:
        raise InvalidVerificationCode('验证码无效或已过期，请重新获取')
    if record.attempts >= MAX_CODE_ATTEMPTS:
        raise VerificationAttemptsExceeded('验证码错误次数过多，请重新获取')
    if not hmac.compare_digest(record.code_hash, digest):
        record.attempts += 1
        exhausted = record.attempts >= MAX_CODE_ATTEMPTS
        db.commit()
        if exhausted:
            raise VerificationAttemptsExceeded('验证码错误次数过多，请重新获取')
        raise InvalidVerificationCode('验证码不正确')
    return record
