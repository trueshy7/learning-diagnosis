import hashlib
import hmac
import secrets
import time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .database import get_db
from .models import LoginSession, User

bearer = HTTPBearer(auto_error=False)

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
    return f'{salt}${digest}'

def check_password(password, stored):
    try:
        salt, digest = stored.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, AttributeError, TypeError):
        return False

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(401, '请先登录')
    try:
        session = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == token_hash(credentials.credentials))
        )
        if not session or session.expires_at <= int(time.time()):
            raise HTTPException(401, '登录状态已失效')
        user = db.get(User, session.user_id)
        if not user:
            raise HTTPException(401, '用户不存在')
        return user
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, '登录凭证验证服务暂不可用，请稍后重试') from exc

def teacher_user(user: User = Depends(current_user)):
    if user.role != 'teacher':
        raise HTTPException(403, '需要教师权限')
    return user


def student_user(user: User = Depends(current_user)):
    if user.role != 'student':
        raise HTTPException(403, '需要学生权限')
    return user
