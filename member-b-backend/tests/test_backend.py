import os
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect

TEMP_DIR = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TEMP_DIR.name) / 'test.db')

from app import clients
from app.database import engine
from app.main import app
from app.schemas import AnswerIn
from app.services.scoring import grade


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c


def headers(client, name='student'):
    data = client.post('/api/v1/auth/login', json={
        'username': name, 'password': 'demo12345',
    }).json()['data']
    return {'Authorization': 'Bearer ' + data['access_token']}


def test_login_and_no_answer_leak(client):
    assert client.get('/api/v1/courses').status_code == 401
    assert client.post('/api/v1/auth/login', json={
        'username': 'student', 'password': 'wrong',
    }).status_code == 401
    auth = headers(client)
    assert client.get('/api/v1/courses', headers=auth).json()['data'][0]['id'] == 'course-ds'
    result = client.get('/api/v1/courses/course-ds/questions', headers=auth)
    assert result.status_code == 200
    assert len(result.json()['data']['questions']) == 6
    assert 'correct_option_ids' not in result.text
    assert result.headers['X-Request-ID'] == result.json()['request_id']
    assert client.get('/api/v1/courses/missing/questions', headers=auth).status_code == 404


def test_equal_scoring_and_blank():
    score, total, graded = grade([AnswerIn(question_id='q-stack-1', selected_option_ids=['A'])])
    assert (score, total) == (1, 6)
    assert len(graded) == 6 and sum(x['correct'] for x in graded) == 1
    assert grade([])[:2] == (0, 6)


@pytest.mark.parametrize('answers', [
    [AnswerIn(question_id='q-stack-1', selected_option_ids=['X'])],
    [AnswerIn(question_id='q-stack-1', selected_option_ids=['A', 'A'])],
    [AnswerIn(question_id='missing', selected_option_ids=['A'])],
    [AnswerIn(question_id='q-stack-1', selected_option_ids=['A'])] * 2,
])
def test_invalid_answers(answers):
    with pytest.raises(HTTPException) as exc:
        grade(answers)
    assert exc.value.status_code == 422


def test_teacher_overview_and_role_permissions(client):
    auth = headers(client)
    assert client.get('/api/v1/teacher/overview', headers=auth).status_code == 403
    assert client.post('/api/v1/teacher/resources', headers=auth, json=resource()).status_code == 403
    response = client.get('/api/v1/teacher/overview', headers=headers(client, 'teacher'))
    assert response.status_code == 200
    assert response.json()['data'] == {'user_count': 2, 'question_count': 6, 'resource_count': 2}


def resource(**overrides):
    return {
        'resource_id': 'res-new', 'document_id': 'doc-new',
        'course_id': 'course-ds', 'title': '栈资料', 'text': '栈遵循后进先出原则。',
        'knowledge_point_ids': ['kp-stack'], **overrides,
    }


def test_teacher_resource_ingest(client, monkeypatch):
    received = []

    async def ingest(payload):
        received.append(payload)
        return {'resource_id': payload['resource_id'], 'status': 'indexed'}

    monkeypatch.setattr(clients, 'ingest', ingest)
    auth = headers(client, 'teacher')
    response = client.post('/api/v1/teacher/resources', headers=auth, json=resource())
    assert response.status_code == 200
    assert response.json()['data'] == {'resource_id': 'res-new', 'status': 'indexed'}
    assert received[0]['text'] == resource()['text']
    assert client.post('/api/v1/teacher/resources', headers=auth,
                       json=resource(course_id='missing')).status_code == 404
    assert client.post('/api/v1/teacher/resources', headers=auth,
                       json=resource(knowledge_point_ids=['missing'])).status_code == 422
    assert len(received) == 1


def test_teacher_resource_service_failure(client, monkeypatch):
    async def ingest(payload):
        raise httpx.ConnectError('service unavailable')

    monkeypatch.setattr(clients, 'ingest', ingest)
    response = client.post('/api/v1/teacher/resources',
                           headers=headers(client, 'teacher'), json=resource())
    assert response.status_code == 502
    assert response.json()['code'] == 502


def test_validation_error_format(client):
    response = client.post('/api/v1/auth/login', json={'username': 'student', 'extra': True})
    assert response.status_code == 422
    assert response.json()['code'] == 422
    assert response.json()['data']['errors']
    assert response.headers['X-Request-ID'] == response.json()['request_id']


def test_logout_revokes_token(client):
    auth = headers(client)
    assert client.post('/api/v1/auth/logout', headers=auth).status_code == 200
    assert client.get('/api/v1/courses', headers=auth).status_code == 401


def test_removed_measurement_features(client):
    assert set(inspect(engine).get_table_names()) == {'users', 'login_sessions'}
    paths = client.get('/openapi.json').json()['paths']
    assert not any('/attempts' in path for path in paths)
    assert client.get('/api/v1/attempts', headers=headers(client)).status_code == 404
    assert client.post('/api/v1/attempts', headers=headers(client), json={}).status_code == 404


def test_health(client):
    assert client.get('/health').json() == {
        'status': 'ok', 'service': 'backend', 'mode': 'sqlite_demo',
    }
