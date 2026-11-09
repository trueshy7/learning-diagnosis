import hashlib
import hmac
import secrets
import time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import LoginSession, User, Course, TeacherCourse, StudentCourse

bearer = HTTPBearer(auto_error=False)

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
    return f'{salt}${digest}'

def check_password(password, stored):
    salt, digest = stored.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180000).hex()
    return hmac.compare_digest(actual, digest)

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(401, '请先登录')
    session = db.get(LoginSession, token_hash(credentials.credentials))
    if not session or session.expires_at < int(time.time()):
        raise HTTPException(401, '登录状态已失效')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, '用户不存在')
    return user

def teacher_user(user: User = Depends(current_user)):
    if user.role != 'teacher':
        raise HTTPException(403, '需要教师权限')
    return user

def teacher_course(db: Session, user: User, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, '课程不存在')
    if db.get(TeacherCourse, (user.id, course_id)) is None:
        raise HTTPException(403, '没有该课程的教师权限')
    return course

def course_access(db: Session, user: User, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, '课程不存在')
    if user.role == 'teacher':
        if db.get(TeacherCourse, (user.id, course_id)) is None:
            raise HTTPException(403, '没有该课程的教师权限')
    elif db.get(StudentCourse, (user.id, course_id)) is None:
        raise HTTPException(403, '尚未获得该课程的学习权限')
    return course
