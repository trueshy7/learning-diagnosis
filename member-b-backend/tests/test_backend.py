import os
import tempfile
from pathlib import Path
import pytest

TEMP_DIR=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(TEMP_DIR.name)/'test.db')
os.environ['AGENTS_MODE']='disabled'
from fastapi.testclient import TestClient
from backend_service.main import app
from backend_service.schemas import AnswerIn
from backend_service.scoring import grade

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:yield c

def headers(client,name='student'):
    data=client.post('/api/v1/auth/login',json={'username':name,'password':'demo12345'}).json()['data']
    return {'Authorization':'Bearer '+data['access_token']}

def test_login_and_no_answer_leak(client):
    assert client.get('/api/v1/courses').status_code==401
    assert client.post('/api/v1/auth/login',json={'username':'student','password':'wrong'}).status_code==401
    result=client.get('/api/v1/courses/course-ds/questions',headers=headers(client))
    assert result.status_code==200
    assert len(result.json()['data']['questions'])==6
    assert 'correct_option_ids' not in result.text

def test_equal_scoring_and_blank():
    score,total,graded=grade([AnswerIn(question_id='q-stack-1',selected_option_ids=['A'])])
    assert (score,total)==(1,6)
    assert len(graded)==6 and sum(x['correct'] for x in graded)==1

def test_idempotency_and_ai_failure_preserves_score(client):
    auth={**headers(client),'Idempotency-Key':'unique-submission'}
    body={'course_id':'course-ds','answers':[{'question_id':'q-stack-1','selected_option_ids':['A']}]}
    first=client.post('/api/v1/attempts',json=body,headers=auth)
    assert first.status_code==200
    data=first.json()['data'];assert data['score']==1 and data['report'] is None
    assert data['ai_status']=='disabled'
    second=client.post('/api/v1/attempts',json=body,headers=auth).json()['data']
    assert first.json()['data']['id']==second['id']
    conflict=client.post('/api/v1/attempts',json={'course_id':'course-ds','answers':[]},headers=auth)
    assert conflict.status_code==409
    assert client.get('/api/v1/attempts/'+data['id'],headers=headers(client,'teacher')).status_code==403

def test_invalid_answer_and_role_permissions(client):
    auth=headers(client)
    assert client.get('/api/v1/teacher/overview',headers=auth).status_code==403
    assert client.get('/api/v1/teacher/overview',headers=headers(client,'teacher')).status_code==200
    invalid={'course_id':'course-ds','answers':[{'question_id':'q-stack-1','selected_option_ids':['X']}]}
    assert client.post('/api/v1/attempts',json=invalid,headers=auth).status_code==422
    invalid['answers']=[{'question_id':'q-stack-1','selected_option_ids':['A']}]*2
    assert client.post('/api/v1/attempts',json=invalid,headers=auth).status_code==422

def test_logout_revokes_token(client):
    auth=headers(client)
    assert client.post('/api/v1/auth/logout',headers=auth).status_code==200
    assert client.get('/api/v1/courses',headers=auth).status_code==401
