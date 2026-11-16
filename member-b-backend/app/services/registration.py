"""用户注册事务：校验验证码、保存密码哈希并一次性消费验证码。"""

from dataclasses import dataclass
import time

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import User
from ..schemas import RegisterIn
from ..security import hash_password
from .verification import (
    REGISTER_PURPOSE, InvalidVerificationCode, VerificationAttemptsExceeded,
    verify_email_code_for_update,
)


class AccountAlreadyExists(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredUser:
    id: int
    username: str
    email: str
    role: str


def register_user(db: Session, body: RegisterIn) -> RegisteredUser:
    """使用独立会话调用；错误尝试单独提交，注册与消费验证码一起提交。"""
    try:
        record = verify_email_code_for_update(db, body.email, REGISTER_PURPOSE, body.verification_code)
        now = int(time.time())
        existing_id = db.scalar(
            select(User.id).where(or_(User.username == body.username, User.email == body.email)).limit(1)
        )
        if existing_id is not None:
            raise AccountAlreadyExists('用户名或邮箱已被注册')

        user = User(
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
            role=body.role,
        )
        db.add(user)
        record.used_at = now
        db.flush()
        # 在提交前提取返回字段，避免提交后触发额外查询。
        result = RegisteredUser(id=user.id, username=user.username, email=user.email, role=user.role)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        # MySQL 唯一键冲突也可能来自两个并发注册请求。
        if getattr(exc.orig, 'args', ()) and exc.orig.args[0] == 1062:
            raise AccountAlreadyExists('用户名或邮箱已被注册') from exc
        raise
    except Exception:
        db.rollback()
        raise
