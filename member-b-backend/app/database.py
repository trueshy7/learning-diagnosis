from sqlalchemy import create_engine
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
)

from .config import DATABASE_URL

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 创建数据库会话工厂
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ORM模型基类
Base = declarative_base()

# FastAPI数据库依赖
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
