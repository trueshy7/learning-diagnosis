"""SQL 文件整体执行回归；真实 MySQL 测试仅使用新建的随机测试库。"""

import json
import os
from pathlib import Path
import re
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import Base
from app.exam_schemas import AttemptStartIn, QuestionIn, SaveAnswersIn
from app.models import (Course, Exam, ExamAnswer, ExamAttempt, ExamQuestion,
                        KnowledgePoint, Question, QuestionKnowledgePoint, QuestionOption, User)
from app.services import exams
from app.services.assessment import grade_paper

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'sql/seed_teacher_questions_exams.sql'
SEED_TABLES = (Question, QuestionOption, QuestionKnowledgePoint, Exam, ExamQuestion)


def script_statements(source):
    """按本项目脚本的 DELIMITER 行拆分，保留存储过程内的分号。"""
    delimiter, pending = ';', []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        if stripped.upper().startswith('DELIMITER '):
            assert not pending
            delimiter = stripped.split(None, 1)[1]
            continue
        pending.append(line)
        if stripped.endswith(delimiter):
            yield '\n'.join(pending).rstrip()[:-len(delimiter)].strip()
            pending = []
    assert not pending, 'SQL 文件末尾存在未结束语句'


def execute_script(engine, path):
    # 只在调用方创建的随机库执行，跳过文件中的业务库 USE。
    assert engine.url.database.startswith('ld_sql_seed_test_')
    connection = engine.raw_connection()
    driver = connection.driver_connection
    previous = driver.get_autocommit()
    try:
        driver.autocommit(True)
        with driver.cursor() as cursor:
            for statement in script_statements(path.read_text()):
                if statement.upper().startswith('USE '):
                    continue
                cursor.execute(statement)
                if cursor.description:
                    cursor.fetchall()
                while cursor.nextset():
                    if cursor.description:
                        cursor.fetchall()
    finally:
        driver.rollback()
        driver.autocommit(previous)
        connection.close()


@pytest.fixture
def seed_database():
    value = os.getenv('TEST_MYSQL_URL')
    if not value:
        pytest.skip('未配置独立 MySQL 集成测试连接')
    url = make_url(value)
    if url.get_backend_name() != 'mysql':
        pytest.fail('TEST_MYSQL_URL 必须为 MySQL')
    name = 'ld_sql_seed_test_' + uuid.uuid4().hex
    admin = create_engine(url.set(database=None), connect_args={'connect_timeout': 5})
    engine, created = None, False
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        created = True
        engine = create_engine(url.set(database=name), connect_args={'connect_timeout': 5})
        Base.metadata.create_all(engine)
        execute_script(engine, ROOT / 'sql/seed_teacher_student_courses.sql')
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP DATABASE `{name}`')
        admin.dispose()


def test_sql_seed_payload_and_full_script_structure():
    source = SEED.read_text()
    # 直接校验交付 SQL 中的 JSON，而非校验生成器的内存数据。
    rows = [json.loads(value.replace("''", "'")) for value in
            re.findall(r"CAST\('((?:[^']|'')*)' AS JSON\)", source)]
    assert len(rows) == 20
    assert len({row['id'] for row in rows}) == 20
    assert len({option['id'] for row in rows for option in row['options']}) == 80
    for row in rows:
        QuestionIn.model_validate({
            'kind': row['kind'], 'stem': row['stem'], 'explanation': row['explanation'],
            'knowledge_point_ids': [row['knowledge_point_id']], 'status': 'active',
            'options': [{key: option[key] for key in ('label', 'text', 'is_correct')}
                        for option in row['options']],
        })
    for exam_id in {row['exam_id'] for row in rows}:
        items = [row for row in rows if row['exam_id'] == exam_id]
        assert len(items) == 10 and sorted(row['sort_order'] for row in items) == list(range(10))
        points = [{'id': key, 'name': key} for key in {row['knowledge_point_id'] for row in items}]
        paper = [{'question_id': row['id'], 'score': 10, 'snapshot': {
            'options': row['options'],
            'knowledge_points': [{'id': row['knowledge_point_id'], 'name': row['knowledge_point_id']}],
        }} for row in items]
        answers = {row['id']: [option['id'] for option in row['options'] if option['is_correct']] for row in items}
        assert grade_paper(paper, answers, points)[0] == 100
        assert grade_paper(paper, {}, points)[0] == 0
    statements = list(script_statements(source))
    assert sum(statement.startswith('CREATE PROCEDURE') for statement in statements) == 1
    assert sum(statement.startswith('CALL ') for statement in statements) == 1
    assert len([statement for statement in statements if statement.startswith('SELECT ')]) == 2


def test_mysql_sql_seed_executes_repeats_and_preserves_published_history(seed_database):
    engine = seed_database
    execute_script(engine, SEED)
    with Session(engine, autoflush=False) as db:
        assert [db.scalar(select(func.count()).select_from(model)) for model in SEED_TABLES] == [20, 80, 20, 2, 20]
        snapshots = {row.question_id: row.snapshot for row in db.scalars(select(ExamQuestion))}
        assert all(len(snapshot['options']) == 4 for snapshot in snapshots.values())
        assert all(type(option['is_correct']) is bool for snapshot in snapshots.values() for option in snapshot['options'])
        assert {option.id: option.is_correct for option in db.scalars(select(QuestionOption))} == {
            option['id']: option['is_correct'] for snapshot in snapshots.values() for option in snapshot['options']}
        student = db.get(User, 1)
        started = exams.start_attempt(db, student, 'demo-exam-ds-teacher-2', AttemptStartIn())
        paper = db.scalars(select(ExamQuestion).where(ExamQuestion.exam_id == started['exam_id'])).all()
        body = SaveAnswersIn(answers=[{
            'question_id': row.question_id, 'revision': 0,
            'selected_option_ids': [option['id'] for option in row.snapshot['options'] if option['is_correct']],
        } for row in paper])
        exams.save_answers(db, student, started['id'], body)
        assert exams.submit_attempt(db, student, started['id'])['score'] == 100
        db.get(Question, 'demo-q-ds-01').stem = '发布后修改题库'
        db.get(Exam, 'demo-exam-ds-teacher-2').status = 'archived'
        db.commit()
    execute_script(engine, SEED)
    with Session(engine) as db:
        assert [db.scalar(select(func.count()).select_from(model)) for model in SEED_TABLES] == [20, 80, 20, 2, 20]
        assert {row.question_id: row.snapshot for row in db.scalars(select(ExamQuestion))} == snapshots
        assert db.get(Question, 'demo-q-ds-01').stem == '发布后修改题库'
        assert db.get(Exam, 'demo-exam-ds-teacher-2').status == 'archived'
        assert db.get(ExamAttempt, started['id']).score == 100
        assert db.scalar(select(func.count()).select_from(ExamAnswer)) == 10


def test_mysql_sql_seed_rolls_back_both_courses_on_second_course_failure(seed_database):
    engine = seed_database
    with Session(engine) as db:
        db.get(KnowledgePoint, 'demo-kp-python-loops').status = 'disabled'
        db.commit()
    with pytest.raises(Exception, match='Missing active knowledge points'):
        execute_script(engine, SEED)
    with Session(engine) as db:
        assert [db.scalar(select(func.count()).select_from(model)) for model in SEED_TABLES] == [0, 0, 0, 0, 0]
        assert db.scalar(select(func.count()).select_from(Course)) == 2


def test_mysql_repair_missing_attempt_snapshot_preserves_history_and_allows_start(seed_database):
    engine = seed_database
    execute_script(engine, SEED)
    with Session(engine, autoflush=False) as db:
        student = db.get(User, 1)
        original = exams.start_attempt(db, student, 'demo-exam-ds-teacher-2', AttemptStartIn())
        expected = db.get(Exam, original['exam_id']).knowledge_snapshot
    # 模拟开发早期已经建表，后来模型加列而 create_all 不会迁移的情况。
    with engine.begin() as connection:
        connection.exec_driver_sql('ALTER TABLE exam_attempts DROP COLUMN knowledge_snapshot')
    with Session(engine, autoflush=False) as db:
        student = db.get(User, 1)
        with pytest.raises(HTTPException) as failure:
            exams.start_attempt(db, student, 'demo-exam-python-teacher-2', AttemptStartIn())
        assert failure.value.status_code == 503
        assert failure.value.__cause__.orig.args[0] == 1054
    repair = ROOT / 'sql/repair_exam_attempt_knowledge_snapshot.sql'
    execute_script(engine, repair)
    with Session(engine, autoflush=False) as db:
        assert db.get(ExamAttempt, original['id']).knowledge_snapshot == expected
        assert db.scalar(select(func.count()).select_from(ExamAnswer)) == 10
        student = db.get(User, 1)
        created = exams.start_attempt(db, student, 'demo-exam-python-teacher-2', AttemptStartIn())
        assert created['status'] == 'in_progress'
    execute_script(engine, repair)
    with Session(engine) as db:
        assert db.get(ExamAttempt, original['id']).knowledge_snapshot == expected
        assert db.scalar(select(func.count()).select_from(ExamAttempt)) == 2
        assert db.scalar(select(func.count()).select_from(ExamAnswer)) == 20
