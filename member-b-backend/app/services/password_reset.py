"""找回密码：消费邮箱验证码、更新哈希、撤销所有旧会话。"""

import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import LoginSession, User
from ..schemas import ResetPasswordIn
from ..security import hash_password
from .verification import RESET_PASSWORD_PURPOSE, verify_email_code_for_update


class EmailNotRegistered(ValueError):
    pass


def reset_password(db: Session, body: ResetPasswordIn) -> None:
    try:
        record = verify_email_code_for_update(
            db, body.email, RESET_PASSWORD_PURPOSE, body.verification_code,
        )
        # 登录也锁定该用户，保证并发登录不会在重置完成后写入旧密码会话。
        user = db.scalar(select(User).where(User.email == body.email).with_for_update())
        if user is None:
            raise EmailNotRegistered('该邮箱尚未注册')
        user.password_hash = hash_password(body.password)
        record.used_at = int(time.time())
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.commit()
    except Exception:
        db.rollback()
        raise
