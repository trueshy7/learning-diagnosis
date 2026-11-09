import os
import tempfile
import base64
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest

TEMP_DIR=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(TEMP_DIR.name)/'test.db')
os.environ['AGENTS_MODE']='disabled'
from fastapi.testclient import TestClient
from backend_service.main import app
from backend_service.schemas import AnswerIn
from backend_service.scoring import grade
from backend_service.database import SessionLocal
from backend_service.models import Course, KnowledgePoint, Question, Resource, User, FullTask
from backend_service.security import hash_password

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:yield c

def headers(client,name='student'):
    data=client.post('/api/v1/auth/login',json={'username':name,'password':'demo12345'}).json()['data']
    return {'Authorization':'Bearer '+data['access_token']}

def full_headers(client,name='student'):
    response=client.post('/api/v2/auth/login',json={'username':name,'password':'demo12345'})
    assert response.status_code==200 and response.json()['code']=='OK'
    return {'Authorization':'Bearer '+response.json()['data']['access_token']}

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
    invalid['answers']=[{'question_id':'q-stack-1','selected_option_ids':['A','B']}]
    assert client.post('/api/v1/attempts',json=invalid,headers=auth).status_code==422

def test_logout_revokes_token(client):
    auth=headers(client)
    assert client.post('/api/v1/auth/logout',headers=auth).status_code==200
    assert client.get('/api/v1/courses',headers=auth).status_code==401

def test_teacher_catalog_to_student_attempt(client):
    teacher=headers(client,'teacher')
    student=headers(client)
    course={'id':'course-midterm','name':'算法基础','description':'成员 B 中期测试课程'}
    assert client.post('/api/v1/teacher/courses',json=course,headers=student).status_code==403
    created=client.post('/api/v1/teacher/courses',json=course,headers=teacher)
    assert created.status_code==201
    assert created.json()['data']==course
    assert client.post('/api/v1/teacher/courses',json=course,headers=teacher).status_code==409

    empty={'course_id':course['id'],'answers':[]}
    assert client.post('/api/v1/attempts',json=empty,headers=student).status_code==422
    point={'id':'kp-sort','name':'排序'}
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/knowledge-points",json=point,headers=teacher).status_code==201
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/knowledge-points",json=point,headers=teacher).status_code==409

    question={'id':'q-sort-1','stem':'以下哪种排序稳定？','kind':'single',
              'options':[{'id':'A','text':'归并排序'},{'id':'B','text':'快速排序'}],
              'correct_option_ids':['A'],'knowledge_point_ids':['kp-sort']}
    bad={**question,'id':'q-sort-bad','knowledge_point_ids':['kp-stack']}
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/questions",json=bad,headers=teacher).status_code==422
    bad={**question,'id':'q-sort-bad','correct_option_ids':['Z']}
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/questions",json=bad,headers=teacher).status_code==422
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/questions",json=question,headers=student).status_code==403
    created=client.post(f"/api/v1/teacher/courses/{course['id']}/questions",json=question,headers=teacher)
    assert created.status_code==201
    assert created.json()['data']['correct_option_ids']==['A']
    assert client.post(f"/api/v1/teacher/courses/{course['id']}/questions",json=question,headers=teacher).status_code==409
    teacher_list=client.get(f"/api/v1/teacher/courses/{course['id']}/questions",headers=teacher)
    assert teacher_list.json()['data']['questions'][0]['correct_option_ids']==['A']
    assert client.get(f"/api/v1/teacher/courses/{course['id']}/questions",headers=student).status_code==403

    listed=client.get(f"/api/v1/courses/{course['id']}/questions",headers=student)
    assert listed.status_code==200
    assert len(listed.json()['data']['questions'])==1
    assert 'correct_option_ids' not in listed.text
    points=client.get(f"/api/v1/courses/{course['id']}/knowledge-points",headers=student).json()['data']['items']
    assert points==[{'id':'kp-sort','name':'排序','question_count':1}]
    assert any(x['id']==course['id'] for x in client.get('/api/v1/courses',headers=student).json()['data'])

    attempt=client.post('/api/v1/attempts',json={
        'course_id':course['id'],'answers':[{'question_id':'q-sort-1','selected_option_ids':['A']}]},headers=student)
    assert attempt.status_code==200
    data=attempt.json()['data']
    assert (data['score'],data['max_score'],data['percentage'])==(1,1,100.0)
    assert data['ai_status']=='disabled'
    assert any(x['id']==data['id'] for x in client.get('/api/v1/attempts',headers=student).json()['data'])
    wrong_baseline={'course_id':'course-ds','answers':[], 'baseline_attempt_id':data['id']}
    assert client.post('/api/v1/attempts',json=wrong_baseline,headers=student).status_code==422
    assert client.get('/api/v1/teacher/overview',headers=teacher).json()['data']['question_count']==7
    with SessionLocal() as db:
        assert db.get(Course,course['id']).name==course['name']
        assert db.get(KnowledgePoint,point['id']).course_id==course['id']
        assert db.get(Question,question['id']).correct_option_ids==['A']

def test_review_wrong_book_practice_progress_and_question_status(client):
    teacher=headers(client,'teacher');student=headers(client)
    course_id='course-learning';point_id='kp-learning'
    assert client.post('/api/v1/teacher/courses',json={'id':course_id,'name':'练习课程'},headers=teacher).status_code==201
    assert client.post(f'/api/v1/teacher/courses/{course_id}/knowledge-points',
                       json={'id':point_id,'name':'基础概念'},headers=teacher).status_code==201
    question={'id':'q-learning-1','stem':'原题干','kind':'single',
              'options':[{'id':'A','text':'原正确'},{'id':'B','text':'原错误'}],
              'correct_option_ids':['A'],'knowledge_point_ids':[point_id]}
    path=f'/api/v1/teacher/courses/{course_id}/questions'
    assert client.post(path,json=question,headers=teacher).status_code==201
    first=client.post('/api/v1/attempts',json={'course_id':course_id,
        'answers':[{'question_id':question['id'],'selected_option_ids':['B']}]},headers=student).json()['data']
    assert (first['score'],first['max_score'])==(0,1)
    review=client.get(f"/api/v1/attempts/{first['id']}/review",headers=student).json()['data']
    assert review['snapshot_available'] is True
    assert review['questions'][0]['stem']=='原题干'
    assert review['questions'][0]['correct_option_ids']==['A']
    assert review['questions'][0]['selected_option_ids']==['B']
    assert client.get(f"/api/v1/attempts/{first['id']}/review",headers=teacher).status_code==403
    book=client.get(f'/api/v1/courses/{course_id}/wrong-questions',headers=student).json()['data']['items']
    assert len(book)==1 and book[0]['available_for_practice'] is True
    assert client.get(f'/api/v1/courses/{course_id}/wrong-questions',headers=teacher).json()['data']['items']==[]

    changed={key:value for key,value in question.items() if key!='id'}
    changed['stem']='修改后的题干';changed['correct_option_ids']=['B']
    assert client.patch(f'{path}/{question["id"]}',json=changed,headers=student).status_code==403
    assert client.patch(f'{path}/{question["id"]}',json=changed,headers=teacher).status_code==200
    assert client.get(f"/api/v1/attempts/{first['id']}/review",headers=student).json()['data']['questions'][0]['stem']=='原题干'
    assert client.get(f"/api/v1/attempts/{first['id']}",headers=student).json()['data']['score']==0
    assert client.patch(f'{path}/{question["id"]}/status',json={'active':False},headers=teacher).status_code==200
    assert client.get(f'/api/v1/courses/{course_id}/questions',headers=student).json()['data']['questions']==[]
    assert client.get(path+'?active=false',headers=teacher).json()['data']['questions'][0]['active'] is False
    book=client.get(f'/api/v1/courses/{course_id}/wrong-questions',headers=student).json()['data']['items']
    assert book[0]['available_for_practice'] is False
    assert client.post('/api/v1/attempts',json={'course_id':course_id,'question_ids':[question['id']],
        'answers':[{'question_id':question['id'],'selected_option_ids':['B']}]},headers=student).status_code==422

    assert client.patch(f'{path}/{question["id"]}/status',json={'active':True},headers=teacher).status_code==200
    practice=client.get(f'/api/v1/courses/{course_id}/practice?knowledge_point_id={point_id}&limit=1',headers=student)
    assert practice.json()['data']['question_ids']==[question['id']]
    assert 'correct_option_ids' not in practice.text
    second=client.post('/api/v1/attempts',json={'course_id':course_id,'question_ids':[question['id']],
        'answers':[{'question_id':question['id'],'selected_option_ids':['B']}]},headers=student).json()['data']
    assert second['kind']=='practice' and (second['score'],second['max_score'])==(1,1)
    assert client.get(f'/api/v1/courses/{course_id}/wrong-questions',headers=student).json()['data']['items']==[]
    progress=client.get(f'/api/v1/courses/{course_id}/progress',headers=student).json()['data']
    assert progress['attempt_count']==2
    assert [item['kind'] for item in progress['timeline']]==['quiz','practice']
    assert progress['knowledge_points'][0]['accuracy']==0.5

def test_teacher_resource_catalog_and_upload(client,monkeypatch):
    import httpx
    from backend_service import clients
    teacher=headers(client,'teacher');student=headers(client)
    course_id='course-resources';point_id='kp-resources'
    client.post('/api/v1/teacher/courses',json={'id':course_id,'name':'资料课程'},headers=teacher)
    client.post(f'/api/v1/teacher/courses/{course_id}/knowledge-points',
                json={'id':point_id,'name':'资料知识点'},headers=teacher)
    ingested_payloads=[]
    async def fake_ingest(payload):
        ingested_payloads.append(payload)
        return {'document_id':payload['document_id'],'chunks':2,'index_version':'test-v1','mode':'keyword_demo'}
    async def fake_delete(resource_id):
        return {'resource_id':resource_id,'deleted_documents':1,'deleted_chunks':2}
    monkeypatch.setattr(clients,'ingest',fake_ingest)
    monkeypatch.setattr(clients,'delete_resource',fake_delete)
    body={'resource_id':'res-learning','document_id':'doc-learning','course_id':course_id,
          'title':'排序讲义','text':'排序可以比较元素的大小。','knowledge_point_ids':[point_id],'source':'教师自编'}
    assert client.post('/api/v1/teacher/resources',json=body,headers=student).status_code==403
    response=client.post('/api/v1/teacher/resources',json=body,headers=teacher)
    assert response.status_code==200 and response.json()['data']['resource']['status']=='indexed'
    assert client.get('/api/v1/teacher/resources',headers=student).status_code==403
    listed=client.get(f'/api/v1/teacher/resources?course_id={course_id}',headers=teacher).json()['data']['items']
    assert len(listed)==1 and listed[0]['chunk_count']==2
    assert client.get('/api/v1/teacher/resources/res-learning/status',headers=teacher).json()['data']['index_version']=='test-v1'
    assert client.post('/api/v1/teacher/resources',json={**body,'resource_id':'res-collision'},headers=teacher).status_code==409

    uploaded={key:value for key,value in body.items() if key!='text'}
    uploaded.update({'resource_id':'res-file','document_id':'doc-file','filename':'lesson.md',
                     'content_base64':base64.b64encode('队列先进先出。'.encode()).decode()})
    assert client.post('/api/v1/teacher/resources/file',json=uploaded,headers=teacher).status_code==200
    assert client.post('/api/v1/teacher/resources/file',json={**uploaded,'filename':'bad.exe'},headers=teacher).status_code==422
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=300,height=300)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),
                           NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (Study notes) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    buffer=BytesIO();writer.write(buffer)
    pdf={**uploaded,'resource_id':'res-pdf','document_id':'doc-pdf','filename':'notes.pdf',
         'content_base64':base64.b64encode(buffer.getvalue()).decode()}
    assert client.post('/api/v1/teacher/resources/file',json=pdf,headers=teacher).status_code==200
    assert ingested_payloads[-1]['text']=='Study notes'
    with SessionLocal() as db:
        assert db.get(Resource,'res-file').status=='indexed'
    deleted=client.delete('/api/v1/teacher/resources/res-file',headers=teacher)
    assert deleted.status_code==200 and deleted.json()['data']['resource']['status']=='deleted'
    assert len(client.get(f'/api/v1/teacher/resources?course_id={course_id}',headers=teacher).json()['data']['items'])==2

    async def offline(payload):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(clients,'ingest',offline)
    failed=client.post('/api/v1/teacher/resources',json={**body,'resource_id':'res-offline','document_id':'doc-offline'},headers=teacher)
    assert failed.status_code==502
    async def delete_offline(resource_id):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(clients,'delete_resource',delete_offline)
    assert client.delete('/api/v1/teacher/resources/res-pdf',headers=teacher).status_code==502
    with SessionLocal() as db:
        assert db.get(Resource,'res-offline') is None
        assert db.get(Resource,'res-pdf').status=='indexed'

def test_course_ask_uses_only_cataloged_citations(client,monkeypatch):
    from backend_service import clients
    student=headers(client)
    async def fake_retrieve(payload):
        assert payload['course_id']=='course-ds'
        return {'index_version':'test-v1','evidence':[
            {'evidence_id':'ev-1','document_id':'doc-stack','resource_id':'res-stack',
             'title':'栈讲义','source':'教师讲义','location':'p.1','text':'栈后进先出。'},
            {'evidence_id':'ev-2','document_id':'doc-hidden','resource_id':'res-hidden',
             'title':'未知资料','source':'未知','location':'p.2','text':'不应出现'}]}
    monkeypatch.setattr(clients,'retrieve',fake_retrieve)
    response=client.post('/api/v1/courses/course-ds/ask',json={'query':'栈是什么？'},headers=student)
    assert response.status_code==200
    data=response.json()['data']
    assert data['status']=='answered' and data['mode']=='extractive_retrieval'
    assert data['answer']=='[1] 栈后进先出。'
    assert len(data['citations'])==1 and data['citations'][0]['resource_id']=='res-stack'
    assert client.post('/api/v1/courses/course-ds/ask',
                       json={'query':'栈','knowledge_point_ids':['kp-resources']},headers=student).status_code==422
    async def no_evidence(payload):return {'index_version':'test-v1','evidence':[]}
    monkeypatch.setattr(clients,'retrieve',no_evidence)
    data=client.post('/api/v1/courses/course-ds/ask',json={'query':'没有相关资料的问题'},headers=student).json()['data']
    assert data['status']=='insufficient_evidence' and data['answer'] is None

def test_full_v1_auth_course_snapshot_submission_and_failure_task(client):
    auth=full_headers(client)
    assert client.get('/api/v2/auth/me',headers=auth).json()['data']['user_id']=='student-1'
    course=client.get('/api/v2/courses/course-ds',headers=auth).json()['data']
    assert course['course_id']=='course-ds' and len(course['knowledge_points'])==2
    assert course['latest_attempt_id'] is None
    body={'course_id':'course-ds','kind':'initial','client_request_id':'full-create-1'}
    created=client.post('/api/v2/attempts',json=body,headers=auth)
    assert created.status_code==201 and created.json()['code']=='OK'
    attempt=created.json()['data']
    assert attempt['status']=='in_progress' and len(attempt['questions'])==6
    assert attempt['result'] is None and attempt['diagnosis_task_id'] is None
    assert all(set(q)=={'question_id','type','stem','options','knowledge_point_ids','difficulty'} for q in attempt['questions'])
    assert client.post('/api/v2/attempts',json=body,headers=auth).json()['data']['attempt_id']==attempt['attempt_id']
    assert client.post('/api/v2/attempts',json={**body,'course_id':'course-midterm'},headers=auth).status_code==409
    assert client.get(f"/api/v2/attempts/{attempt['attempt_id']}/result",headers=auth).status_code==409
    answers=[{'question_id':q['question_id'],'selected_option_ids':['A']} for q in attempt['questions']]
    submit={'snapshot_version':attempt['snapshot_version'],'answers':answers}
    path=f"/api/v2/attempts/{attempt['attempt_id']}/submit"
    result=client.post(path,json=submit,headers={**auth,'Idempotency-Key':'full-submit-1'})
    assert result.status_code==200
    data=result.json()['data']
    assert data['result']['score']['correct_count']==6
    assert data['result']['score']['total_count']==6
    assert client.post(path,json=submit,headers={**auth,'Idempotency-Key':'full-submit-1'}).json()['data']==data
    assert client.post(path,json={**submit,'snapshot_version':'stale'},
                       headers={**auth,'Idempotency-Key':'different'}).status_code==409
    assert client.post(path,json={**submit,'answers':answers[:-1]},
                       headers={**auth,'Idempotency-Key':'different'}).status_code==409
    stored=client.get(f"/api/v2/attempts/{attempt['attempt_id']}",headers=auth).json()['data']
    assert stored['status']=='submitted' and stored['result']==data['result']
    task=client.get(f"/api/v2/tasks/{data['diagnosis_task_id']}",headers=auth).json()['data']
    assert task['status']=='failed' and task['can_retry'] is True
    assert client.get('/api/v2/reports',headers=auth).json()['data']['total']>=1
    retry=client.post(f"/api/v2/tasks/{task['task_id']}/retry",json={},
                      headers={**auth,'Idempotency-Key':'retry-one'})
    assert retry.status_code==202 and retry.json()['data']['retry_count']==1
    assert client.post(f"/api/v2/tasks/{task['task_id']}/retry",json={},
                       headers={**auth,'Idempotency-Key':'retry-one'}).json()['data']['retry_count']==1
    assert client.get(f"/api/v2/attempts/{attempt['attempt_id']}",headers=full_headers(client,'teacher')).status_code==403

def test_full_v1_teacher_maintenance_and_upload(client,monkeypatch):
    from backend_service import clients
    from pypdf import PdfWriter
    teacher=full_headers(client,'teacher');student=full_headers(client)
    course_id='course-fullteacher'
    assert client.post('/api/v1/teacher/courses',json={'id':course_id,'name':'全量接口课程'},
                       headers=headers(client,'teacher')).status_code==201
    changed=client.patch(f'/api/v2/teacher/courses/{course_id}',
                         json={'title':'新版课程','description':'接口联调'},headers=teacher)
    assert changed.status_code==200 and changed.json()['data']['title']=='新版课程'
    point_body={'course_id':course_id,'name':'图论','description':'图基础','sort_order':1,'active':True}
    point=client.post('/api/v2/teacher/knowledge-points',json=point_body,headers=teacher)
    assert point.status_code==201
    point_id=point.json()['data']['knowledge_point_id']
    assert client.post('/api/v2/teacher/knowledge-points',json=point_body,headers=teacher).status_code==409
    assert client.get(f'/api/v2/teacher/knowledge-points?course_id={course_id}',headers=teacher).json()['data']['total']==1
    question_body={'course_id':course_id,'type':'multiple_choice','stem':'哪些是图的遍历？',
                   'options':[{'option_id':None,'client_key':'a','label':'A','text':'DFS'},
                              {'option_id':None,'client_key':'b','label':'B','text':'BFS'},
                              {'option_id':None,'client_key':'c','label':'C','text':'快排'}],
                   'correct_option_keys':['a','b'],'knowledge_point_ids':[point_id],
                   'difficulty':'medium','explanation':'深度与广度优先','active':True}
    question=client.post('/api/v2/teacher/questions',json=question_body,headers=teacher)
    assert question.status_code==201
    q=question.json()['data'];assert q['type']=='multiple_choice' and len(q['correct_option_ids'])==2
    assert client.get(f'/api/v2/teacher/questions?course_id={course_id}&type=multiple_choice',
                      headers=teacher).json()['data']['total']==1
    question_body['options']=[{**item,'option_id':q['options'][i]['option_id']} for i,item in enumerate(question_body['options'])]
    question_body['stem']='修改后的图遍历题'
    assert client.patch(f"/api/v2/teacher/questions/{q['question_id']}",
                        json=question_body,headers=teacher).status_code==200
    attempt=client.post('/api/v2/attempts',json={'course_id':course_id,'kind':'initial',
        'client_request_id':'multi-initial'},headers=student).json()['data']
    assert attempt['questions'][0]['type']=='multiple_choice'
    selected=q['correct_option_ids']
    result=client.post(f"/api/v2/attempts/{attempt['attempt_id']}/submit",json={
        'snapshot_version':attempt['snapshot_version'],
        'answers':[{'question_id':q['question_id'],'selected_option_ids':list(reversed(selected))}]},
        headers={**student,'Idempotency-Key':'multi-submit'})
    assert result.status_code==200 and result.json()['data']['result']['score']['correct_count']==1
    assert client.get(f'/api/v2/teacher/overview?course_id={course_id}',headers=teacher).json()['data']['student_count']==1
    people=client.get(f'/api/v2/teacher/students?course_id={course_id}',headers=teacher).json()['data']
    assert people['items'][0]['user_id']=='student-1'
    assert client.get(f'/api/v2/teacher/students/student-1/attempts?course_id={course_id}',
                      headers=teacher).json()['data']['total']==1
    assert client.patch(f'/api/v2/teacher/knowledge-points/{point_id}',
                        json={**point_body,'active':False},headers=teacher).status_code==409

    async def fake_ingest(payload):
        return {'document_id':payload['document_id'],'chunks':1,'index_version':'test-v1','mode':'keyword_demo'}
    monkeypatch.setattr(clients,'ingest',fake_ingest)
    note={'course_id':course_id,'title':'图论笔记','description':'教师自编','kind':'note',
          'knowledge_point_ids':[point_id],'difficulty':'easy','active':True,
          'text_content':'图可以使用 DFS 与 BFS 遍历。','external_url':None}
    created=client.post('/api/v2/teacher/resources',json=note,headers=teacher)
    assert created.status_code==201
    resource_id=created.json()['data']['resource_id']
    assert client.get(f'/api/v2/resources/{resource_id}',headers=student).json()['data']['text_content']==note['text_content']
    assert client.get(f'/api/v2/teacher/resources?course_id={course_id}',headers=teacher).json()['data']['total']==1
    upload=client.post('/api/v2/teacher/documents',headers=teacher,
        data={'course_id':course_id,'title':'图论讲义','knowledge_point_ids':f'["{point_id}"]'},
        files={'file':('graph.md',b'# Graph\nDFS and BFS','text/markdown')})
    assert upload.status_code==202
    document=upload.json()['data']['document']
    task=client.get(f"/api/v2/tasks/{document['task_id']}",headers=teacher).json()['data']
    assert task['status']=='completed' and task['kind']=='document_ingestion'
    assert client.get(f"/api/v2/teacher/documents/{document['document_id']}",headers=teacher).json()['data']['status']=='completed'
    downloaded=client.get(f"/api/v2/resources/{document['resource_id']}/file",headers=student)
    assert downloaded.status_code==200 and downloaded.content==b'# Graph\nDFS and BFS'
    assert downloaded.headers['content-type'].startswith('text/markdown')
    assert client.get(f"/api/v2/resources/{document['resource_id']}?resource_version=old",headers=student).status_code==410
    blank=PdfWriter();blank.add_blank_page(width=100,height=100)
    empty_pdf=BytesIO();blank.write(empty_pdf)
    failed_upload=client.post('/api/v2/teacher/documents',headers=teacher,
        data={'course_id':course_id,'title':'扫描件','knowledge_point_ids':f'["{point_id}"]'},
        files={'file':('blank.pdf',empty_pdf.getvalue(),'application/pdf')})
    assert failed_upload.status_code==202
    failed_doc=failed_upload.json()['data']['document']
    failed_task=client.get(f"/api/v2/tasks/{failed_doc['task_id']}",headers=teacher).json()['data']
    assert failed_task['status']=='failed' and failed_task['error_code']=='NO_TEXT'
    assert client.get(f"/api/v2/resources/{failed_doc['resource_id']}/file",headers=student).status_code==409
    with SessionLocal() as db:
        db.add(User(id='teacher-2',username='teacher2',password_hash=hash_password('demo12345'),role='teacher'))
        db.add(User(id='student-2',username='student2',password_hash=hash_password('demo12345'),role='student'))
        db.commit()
    other=full_headers(client,'teacher2')
    assert client.get(f'/api/v2/teacher/overview?course_id={course_id}',headers=other).status_code==403
    assert client.get(f'/api/v2/teacher/resources?course_id={course_id}',headers=other).status_code==403
    assert client.get('/api/v2/courses',headers=other).json()['data']==[]
    other_student=full_headers(client,'student2')
    assert client.get('/api/v2/courses',headers=other_student).json()['data']==[]
    assert client.get(f'/api/v2/courses/{course_id}',headers=other_student).status_code==403
    assert client.get(f'/api/v2/resources/{resource_id}',headers=other_student).status_code==403

def test_full_v1_concurrent_same_submission_is_single_task(client):
    auth=full_headers(client)
    attempt=client.post('/api/v2/attempts',json={'course_id':'course-ds','kind':'initial',
        'client_request_id':'concurrent-create'},headers=auth).json()['data']
    body={'snapshot_version':attempt['snapshot_version'],'answers':[
        {'question_id':q['question_id'],'selected_option_ids':['A']} for q in attempt['questions']]}
    path=f"/api/v2/attempts/{attempt['attempt_id']}/submit"
    def send():
        return client.post(path,json=body,headers={**auth,'Idempotency-Key':'concurrent-submit'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:send(),range(2)))
    assert [response.status_code for response in responses]==[200,200]
    assert responses[0].json()['data']==responses[1].json()['data']
    with SessionLocal() as db:
        assert db.query(FullTask).filter(FullTask.attempt_id==attempt['attempt_id']).count()==1
