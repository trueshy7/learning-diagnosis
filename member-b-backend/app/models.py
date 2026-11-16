import time
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from .database import Base


# 用户表
class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(username) BETWEEN 3 AND 64",
            name="ck_users_username_length"
        ),
        CheckConstraint(
            "role IN ('student', 'teacher')",
            name="ck_users_role",
        ),
    )

    # 整数主键，自增
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    # 用户名，唯一，非空
    username: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False
    )

    # 密码哈希
    password_hash: Mapped[str] = mapped_column(
        String(256),
        nullable=False
    )

    # 邮箱，唯一
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )

    # 用户角色
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="student",
        server_default="student",
    )
    login_sessions: Mapped[list["LoginSession"]] = relationship(
        "LoginSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Course(Base):
    """教师创建的课程，名称允许重复，归档时保留业务关联。"""

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_courses_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft",
    )
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(time.time()),
    )
    updated_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        default=lambda: int(time.time()), onupdate=lambda: int(time.time()),
    )

    teacher: Mapped["User"] = relationship("User")


class CourseEnrollment(Base):
    """学生选课关系；退课修改状态，重新加入复用同一联合主键记录。"""

    __tablename__ = "course_enrollments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'withdrawn')", name="ck_course_enrollments_status",
        ),
        Index("ix_course_enrollments_student_status", "student_id", "status"),
    )

    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="RESTRICT"),
        primary_key=True, nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True, nullable=False, autoincrement=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active",
    )
    enrolled_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(time.time()),
    )
    updated_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        default=lambda: int(time.time()), onupdate=lambda: int(time.time()),
    )

    course: Mapped["Course"] = relationship("Course")
    student: Mapped["User"] = relationship("User")


class CourseChapter(Base):
    """课程章节：名称在课程内唯一，排序独立于主键和创建时间。"""

    __tablename__ = "course_chapters"
    __table_args__ = (
        UniqueConstraint("course_id", "name", name="uq_course_chapters_course_name"),
        UniqueConstraint("course_id", "id", name="uq_course_chapters_course_id"),
        Index("ix_course_chapters_course_sort", "course_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex,
    )
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=lambda: int(time.time()),
    )
    updated_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        default=lambda: int(time.time()), onupdate=lambda: int(time.time()),
    )

    course: Mapped["Course"] = relationship("Course")


class KnowledgePoint(Base):
    """课程知识点，使用复合外键保证章节与课程一致。"""

    __tablename__ = "knowledge_points"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "chapter_id"],
            ["course_chapters.course_id", "course_chapters.id"],
            name="fk_knowledge_points_course_chapter",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("chapter_id", "name", name="uq_knowledge_points_chapter_name"),
        UniqueConstraint("course_id", "id", name="uq_knowledge_points_course_id"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_knowledge_points_status"),
        Index("ix_knowledge_points_course_chapter_sort", "course_id", "chapter_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex,
    )
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False,
    )
    chapter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active",
    )

    # chapter 关系同步两个外键字段；course 仅作查询，避免重复写入 course_id。
    chapter: Mapped["CourseChapter"] = relationship("CourseChapter")
    course: Mapped["Course"] = relationship("Course", viewonly=True)


# 登录会话表
class LoginSession(Base):
    __tablename__ = "login_sessions"

    # 会话主键，自增
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # 关联用户ID
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Token的SHA-256哈希值
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    # 创建时间（Unix时间戳）
    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=lambda: int(time.time()),
    )

    # 过期时间（Unix时间戳）
    expires_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # 用户与登录会话的关系
    user: Mapped["User"] = relationship(
        "User",
        back_populates="login_sessions",
    )

    __table_args__ = (
        Index("ix_login_sessions_expires_at", "expires_at"),
    )


class EmailVerificationCode(Base):
    """每个邮箱、用途保留一条记录，重新生成时替换旧验证码。"""

    __tablename__ = "email_verification_codes"
    __table_args__ = (
        UniqueConstraint("email", "purpose", name="uq_email_verification_purpose"),
        Index("ix_email_verification_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Question(Base):
    __tablename__ = 'questions'
    __table_args__ = (
        UniqueConstraint('course_id', 'id', name='uq_questions_course_id'),
        CheckConstraint("kind IN ('single', 'multiple')", name='ck_questions_kind'),
        CheckConstraint("status IN ('draft', 'active', 'disabled')", name='ck_questions_status'),
        Index('ix_questions_course_status', 'course_id', 'status'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id', ondelete='RESTRICT'), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft', server_default='draft')
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()), onupdate=lambda: int(time.time()))


class QuestionOption(Base):
    __tablename__ = 'question_options'
    __table_args__ = (UniqueConstraint('question_id', 'label', name='uq_question_options_label'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    question_id: Mapped[str] = mapped_column(ForeignKey('questions.id', ondelete='RESTRICT'), nullable=False)
    label: Mapped[str] = mapped_column(String(2), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class QuestionKnowledgePoint(Base):
    __tablename__ = 'question_knowledge_points'
    __table_args__ = (
        ForeignKeyConstraint(['course_id', 'question_id'], ['questions.course_id', 'questions.id'],
                             name='fk_question_points_question', ondelete='RESTRICT'),
        ForeignKeyConstraint(['course_id', 'knowledge_point_id'], ['knowledge_points.course_id', 'knowledge_points.id'],
                             name='fk_question_points_point', ondelete='RESTRICT'),
        Index('ix_question_points_course_question', 'course_id', 'question_id'),
        Index('ix_question_points_course_point', 'course_id', 'knowledge_point_id'),
    )
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False)


class Exam(Base):
    __tablename__ = 'exams'
    __table_args__ = (
        UniqueConstraint('course_id', 'id', name='uq_exams_course_id'),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name='ck_exams_status'),
        CheckConstraint('duration_seconds BETWEEN 60 AND 14400', name='ck_exams_duration'),
        Index('ix_exams_course_status', 'course_id', 'status'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id', ondelete='RESTRICT'), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft', server_default='draft')
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal('0'))
    knowledge_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()), onupdate=lambda: int(time.time()))


class ExamQuestion(Base):
    __tablename__ = 'exam_questions'
    __table_args__ = (
        ForeignKeyConstraint(['course_id', 'exam_id'], ['exams.course_id', 'exams.id'],
                             name='fk_exam_questions_exam', ondelete='RESTRICT'),
        ForeignKeyConstraint(['course_id', 'question_id'], ['questions.course_id', 'questions.id'],
                             name='fk_exam_questions_question', ondelete='RESTRICT'),
        CheckConstraint('score > 0 AND score <= 1000', name='ck_exam_questions_score'),
        Index('ix_exam_questions_course_exam', 'course_id', 'exam_id'),
        Index('ix_exam_questions_course_question', 'course_id', 'question_id'),
    )
    exam_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ExamAttempt(Base):
    __tablename__ = 'exam_attempts'
    __table_args__ = (
        UniqueConstraint('exam_id', 'student_id', name='uq_exam_attempts_student_exam'),
        UniqueConstraint('id', 'exam_id', name='uq_exam_attempts_id_exam'),
        ForeignKeyConstraint(['course_id', 'exam_id'], ['exams.course_id', 'exams.id'],
                             name='fk_exam_attempts_course_exam', ondelete='RESTRICT'),
        CheckConstraint("status IN ('in_progress', 'submitted', 'expired')", name='ck_exam_attempts_status'),
        Index('ix_exam_attempts_course_exam', 'course_id', 'exam_id'),
        Index('ix_exam_attempts_status_deadline', 'status', 'expires_at'),
        Index('ix_exam_attempts_student_started', 'student_id', 'started_at'),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    exam_id: Mapped[str] = mapped_column(String(64), nullable=False)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    baseline_attempt_id: Mapped[str | None] = mapped_column(ForeignKey('exam_attempts.id', ondelete='RESTRICT'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='in_progress')
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    submitted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    total_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    knowledge_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    knowledge_point_stats: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ExamAnswer(Base):
    __tablename__ = 'exam_answers'
    __table_args__ = (
        ForeignKeyConstraint(['attempt_id', 'exam_id'], ['exam_attempts.id', 'exam_attempts.exam_id'],
                             name='fk_exam_answers_attempt', ondelete='RESTRICT'),
        ForeignKeyConstraint(['exam_id', 'question_id'], ['exam_questions.exam_id', 'exam_questions.question_id'],
                             name='fk_exam_answers_paper', ondelete='RESTRICT'),
        Index('ix_exam_answers_attempt_exam', 'attempt_id', 'exam_id'),
        Index('ix_exam_answers_exam_question', 'exam_id', 'question_id'),
        CheckConstraint('revision >= 0', name='ck_exam_answers_revision'),
    )
    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exam_id: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_option_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))


class CourseResource(Base):
    """B 保存的纯文本课程资料；删除保留正文和知识点关系。"""

    __tablename__ = 'course_resources'
    __table_args__ = (
        UniqueConstraint('course_id', 'id', name='uq_course_resources_course_id'),
        CheckConstraint("status IN ('active', 'deleted')", name='ck_course_resources_status'),
        CheckConstraint('version >= 1', name='ck_course_resources_version'),
        Index('ix_course_resources_course_status_updated', 'course_id', 'status', 'updated_at'),
        {'mysql_engine': 'InnoDB'},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id', ondelete='RESTRICT'), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False)
    source: Mapped[str] = mapped_column(String(1000), nullable=False,
                                       default='课程教师自编材料', server_default='课程教师自编材料')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active', server_default='active')
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False,
                                          default=lambda: int(time.time()), onupdate=lambda: int(time.time()))


class ResourceKnowledgePoint(Base):
    __tablename__ = 'resource_knowledge_points'
    __table_args__ = (
        ForeignKeyConstraint(['course_id', 'resource_id'], ['course_resources.course_id', 'course_resources.id'],
                             name='fk_resource_points_resource', ondelete='RESTRICT'),
        ForeignKeyConstraint(['course_id', 'knowledge_point_id'], ['knowledge_points.course_id', 'knowledge_points.id'],
                             name='fk_resource_points_point', ondelete='RESTRICT'),
        Index('ix_resource_points_course_resource', 'course_id', 'resource_id'),
        Index('ix_resource_points_course_point', 'course_id', 'knowledge_point_id'),
        {'mysql_engine': 'InnoDB'},
    )

    resource_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False)


class ResourceFile(Base):
    """私有原文件元数据；正文仍由 CourseResource 保存。"""

    __tablename__ = 'resource_files'
    __table_args__ = (
        CheckConstraint('resource_version >= 1', name='ck_resource_files_version'),
        CheckConstraint('size_bytes > 0 AND size_bytes <= 10485760', name='ck_resource_files_size'),
        {'mysql_engine': 'InnoDB'},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    resource_id: Mapped[str] = mapped_column(ForeignKey('course_resources.id', ondelete='RESTRICT'),
                                          nullable=False, unique=True)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    extraction_info: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))


class ResourceIndexState(Base):
    """C 回报的索引状态，与资料业务状态及原文件信息分开保存。"""

    __tablename__ = 'resource_index_states'
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ready', 'failed', 'deleted')", name='ck_resource_index_status'),
        CheckConstraint('resource_version >= 1', name='ck_resource_index_version'),
        CheckConstraint('indexed_version IS NULL OR (indexed_version >= 1 AND indexed_version <= resource_version)',
                        name='ck_resource_index_indexed_version'),
        CheckConstraint("status <> 'ready' OR (indexed_version IS NOT NULL AND indexed_version = resource_version "
                        "AND document_id IS NOT NULL AND indexed_hash IS NOT NULL)", name='ck_resource_index_ready'),
        {'mysql_engine': 'InnoDB'},
    )
    resource_id: Mapped[str] = mapped_column(ForeignKey('course_resources.id', name='fk_resource_index_resource',
                                                      ondelete='RESTRICT'), primary_key=True)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', server_default='pending')
    indexed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    indexed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=lambda: int(time.time()))


class DiagnosisTask(Base):
    """一次测验对应一个可重试的 D 任务通知；delivered 仅代表 D 确认接收。"""

    __tablename__ = 'diagnosis_tasks'
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'dispatching', 'delivered', 'failed')", name='ck_diagnosis_task_status'),
        CheckConstraint('attempt_count >= 0', name='ck_diagnosis_task_count'),
        CheckConstraint("(status = 'dispatching' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
                        "(status <> 'dispatching' AND lease_token IS NULL AND lease_expires_at IS NULL)",
                        name='ck_diagnosis_task_lease'),
        CheckConstraint('(input_snapshot IS NULL AND input_hash IS NULL) OR '
                        '(input_snapshot IS NOT NULL AND input_hash IS NOT NULL)', name='ck_diagnosis_task_input'),
        CheckConstraint("status <> 'delivered' OR (receipt IS NOT NULL AND delivered_at IS NOT NULL)",
                        name='ck_diagnosis_task_receipt'),
        Index('ix_diagnosis_tasks_due', 'status', 'next_retry_at'),
        Index('ix_diagnosis_tasks_lease', 'status', 'lease_expires_at'),
        {'mysql_engine': 'InnoDB'},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('exam_attempts.id', name='fk_diagnosis_task_attempt',
                                                     ondelete='RESTRICT'), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', server_default='pending')
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    next_retry_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivered_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
