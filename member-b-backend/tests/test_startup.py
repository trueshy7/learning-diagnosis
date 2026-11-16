"""启动时初始化表的回归测试，不连接业务数据库。"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main


def test_startup_creates_registered_tables_before_serving(monkeypatch):
    def initialize(*, bind):
        assert bind is main.engine
        assert {
            'users', 'login_sessions', 'email_verification_codes', 'courses', 'course_chapters',
            'knowledge_points', 'course_enrollments',
            'questions', 'question_options', 'question_knowledge_points', 'exams',
            'exam_questions', 'exam_attempts', 'exam_answers',
            'course_resources', 'resource_knowledge_points',
            'resource_files',
            'resource_index_states',
            'diagnosis_tasks',
        } <= set(main.Base.metadata.tables)

    create_all = Mock(side_effect=initialize)
    dispose = Mock()
    monkeypatch.setattr(main.Base.metadata, 'create_all', create_all)
    monkeypatch.setattr(main.engine, 'dispose', dispose)

    with TestClient(main.app) as client:
        create_all.assert_called_once_with(bind=main.engine)
        assert client.get('/health').status_code == 200
        dispose.assert_not_called()
    dispose.assert_called_once_with()


def test_database_initialization_failure_stops_startup(monkeypatch):
    create_all = Mock(side_effect=RuntimeError('database unavailable'))
    monkeypatch.setattr(main.Base.metadata, 'create_all', create_all)

    with pytest.raises(RuntimeError, match='database unavailable'):
        with TestClient(main.app):
            pytest.fail('应用不应在数据库初始化失败后启动')
