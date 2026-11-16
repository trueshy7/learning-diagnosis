import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from . import ok
from ..dependencies import CurrentUser, DbSession
from ..models import LoginSession, User
from ..schemas import LoginIn
from ..security import check_password, token_hash

router = APIRouter(prefix='/auth', tags=['认证'])
user_router = APIRouter(prefix='/user', tags=['用户认证'])


@router.post('/login', deprecated=True)
@user_router.post('/login')
def login(body: LoginIn, request: Request, db: DbSession):
    try:
        user = db.scalar(select(User).where(User.username == body.username).with_for_update())
        if not user or not check_password(body.password, user.password_hash):
            db.rollback()
            raise HTTPException(401, '用户名或密码错误')
        now = int(time.time())
        db.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
        token = secrets.token_urlsafe(32)
        db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=now + 86400))
        result = {
            'access_token': token,
            'token_type': 'bearer',
            'user': {'id': user.id, 'username': user.username, 'role': user.role},
        }
        db.commit()
        return ok(request, result)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, '登录服务暂不可用，请稍后重试') from exc


@router.post('/logout', deprecated=True)
@user_router.post('/exit')
def logout(request: Request, user: CurrentUser, db: DbSession, authorization: str = Header()):
    try:
        hashed_token = token_hash(authorization.split(' ', 1)[1])
        session = db.scalar(select(LoginSession).where(LoginSession.token_hash == hashed_token))
        if session:
            db.delete(session)
            db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, '退出服务暂不可用，请稍后重试') from exc
    return ok(request, {'logged_out': True})


@user_router.get('/info')
def info(request: Request, user: CurrentUser):
    return ok(request, {'username': user.username, 'role': user.role, 'email': user.email})
