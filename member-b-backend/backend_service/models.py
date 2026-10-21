from sqlalchemy import String, JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20))

class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[int] = mapped_column(Integer)

class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    course_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(Integer)

# TODO B: 将当前自编静态课程、题库与资源目录迁移为关系表和正式迁移版本。
