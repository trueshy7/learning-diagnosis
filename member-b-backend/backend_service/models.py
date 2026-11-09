from sqlalchemy import String, JSON, ForeignKey, Integer, LargeBinary, UniqueConstraint
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

class Course(Base):
    __tablename__ = 'courses'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(3000), default='')

class TeacherCourse(Base):
    __tablename__ = 'teacher_courses'
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), primary_key=True)

class StudentCourse(Base):
    __tablename__ = 'student_courses'
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), primary_key=True)

class KnowledgePoint(Base):
    __tablename__ = 'knowledge_points'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))

class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    stem: Mapped[str] = mapped_column(String(2000))
    kind: Mapped[str] = mapped_column(String(20), default='single')
    options: Mapped[list] = mapped_column(JSON)
    correct_option_ids: Mapped[list] = mapped_column(JSON)
    knowledge_point_ids: Mapped[list] = mapped_column(JSON)

class QuestionState(Base):
    __tablename__ = 'question_states'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    active: Mapped[bool] = mapped_column(default=True)

class Resource(Base):
    __tablename__ = 'resources'
    resource_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(100), unique=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(1000))
    knowledge_point_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    index_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer)

class KnowledgeMeta(Base):
    __tablename__ = 'knowledge_meta'
    point_id: Mapped[str] = mapped_column(ForeignKey('knowledge_points.id'), primary_key=True)
    description: Mapped[str] = mapped_column(String(3000), default='')
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=True)

class QuestionMeta(Base):
    __tablename__ = 'question_meta'
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    difficulty: Mapped[str] = mapped_column(String(20), default='easy')
    explanation: Mapped[str] = mapped_column(String(3000), default='')
    version: Mapped[int] = mapped_column(Integer, default=1)

class ResourceMeta(Base):
    __tablename__ = 'resource_meta'
    resource_id: Mapped[str] = mapped_column(ForeignKey('resources.resource_id'), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default='document')
    description: Mapped[str] = mapped_column(String(3000), default='')
    difficulty: Mapped[str] = mapped_column(String(20), default='easy')
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    text_content: Mapped[str | None] = mapped_column(String(200000), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ingestion_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

class FullAttempt(Base):
    __tablename__ = 'full_attempts'
    __table_args__ = (UniqueConstraint('user_id', 'client_request_id'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    client_request_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    snapshot_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)

class FullTask(Base):
    __tablename__ = 'full_tasks'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

class FullReport(Base):
    __tablename__ = 'full_reports'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    generated_at: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)

class FullDocument(Base):
    __tablename__ = 'full_documents'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey('resources.resource_id'), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'), index=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True)
    version: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    text: Mapped[str | None] = mapped_column(String(200000), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

# TODO B: 引入正式数据库迁移版本。
