"""使用临时端口、数据库和索引执行真实HTTP联调。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]

def free_ports(count):
    sockets=[socket.socket() for _ in range(count)]
    try:
        for s in sockets:s.bind(('127.0.0.1',0))
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:s.close()

def main():
    children=[];logs=[]
    with tempfile.TemporaryDirectory(prefix='learning-integration-') as temp:
        folder=Path(temp);c_port,d_port,b_port=free_ports(3)
        env={**os.environ,'DATABASE_URL':f'sqlite:///{folder / "business.db"}',
             'RAG_DATA_PATH':str(folder/'index.json'),'RAG_SEED_ON_START':'true',
             'RAG_MODE':'http','RAG_BASE_URL':f'http://127.0.0.1:{c_port}',
             'AGENTS_MODE':'http','AGENTS_URL':f'http://127.0.0.1:{d_port}',
             'RAG_URL':f'http://127.0.0.1:{c_port}'}
        try:
            with httpx.Client(timeout=10,trust_env=False) as http:
                for name,dirname,module,port in [('C','member-c-rag','rag_service.main:app',c_port),('D','member-d-agents','diagnosis_service.main:app',d_port),('B','member-b-backend','backend_service.main:app',b_port)]:
                    log=open(folder/f'{name}.log','w+');logs.append(log)
                    process=subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',str(port)],cwd=ROOT/dirname,env=env,stdout=log,stderr=log)
                    children.append(process)
                    for _ in range(100):
                        if process.poll() is not None:raise RuntimeError(f'{name}启动失败')
                        try:
                            if http.get(f'http://127.0.0.1:{port}/health').status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.1)
                    else:raise RuntimeError(f'{name}启动超时')
                base=f'http://127.0.0.1:{b_port}/api/v1'
                def get(path,auth):
                    response=http.get(base+path,headers=auth);response.raise_for_status();return response.json()['data']
                def post(path,body,auth=None):
                    response=http.post(base+path,json=body,headers=auth);response.raise_for_status();return response.json()['data']
                login=post('/auth/login',{'username':'student','password':'demo12345'})
                auth={'Authorization':'Bearer '+login['access_token']}
                assert get('/courses',auth)[0]['id']=='course-ds'
                questions=get('/courses/course-ds/questions',auth)['questions']
                assert len(questions)==6 and all('correct_option_ids' not in q for q in questions)
                first=post('/attempts',{'course_id':'course-ds','answers':[{'question_id':q['id'],'selected_option_ids':['B']} for q in questions]},auth)
                assert first['score']==0 and first['max_score']==6 and first['ai_status']=='completed',first
                report=first['report'];assert report and len(report['trace'])==3
                assert len(report['evidence'])>=1 and report['fallback_status'] is None,report
                assert all(e['document_id'] in {'doc-stack','doc-queue'} for e in report['evidence'])
                assert all(not e['source'].startswith('builtin_mock') for e in report['evidence'])
                assert {r['resource_id'] for r in report['recommendations']} <= {'res-stack','res-queue'}
                second=post('/attempts',{'course_id':'course-ds','answers':[{'question_id':q['id'],'selected_option_ids':['A']} for q in questions],'baseline_attempt_id':first['id']},auth)
                assert second['score']==6 and len(second['report']['comparison'])==2
                assert all(row['delta']==1 for row in second['report']['comparison'])
                assert len(get('/attempts',auth))==2
                assert http.get(base+'/teacher/overview',headers=auth).status_code==403
                teacher=post('/auth/login',{'username':'teacher','password':'demo12345'})
                t_auth={'Authorization':'Bearer '+teacher['access_token']}
                assert get('/teacher/overview',t_auth)['attempt_count']==2
                ingested=post('/teacher/resources',{'course_id':'course-ds','resource_id':'res-test','document_id':'doc-test','title':'联调自编文本','knowledge_point_ids':['kp-stack'],'text':'栈是后进先出的线性结构。压栈与弹栈均在栈顶进行。','source':'集成测试自编资料'},t_auth)
                assert ingested['chunks']>=1
                assert http.get(base+'/attempts/'+first['id'],headers=t_auth).status_code==403
                print(json.dumps({'result':'passed','checks':['login','answer_hiding','scoring','real_c_http_evidence','catalog_recommendations','retest_comparison','history','teacher_permission','teacher_ingest','record_ownership'],'evidence_count':len(report['evidence']),'comparison_count':len(second['report']['comparison'])},ensure_ascii=False))
        except Exception:
            for log in logs:
                log.flush();log.seek(0);print(log.read(),file=sys.stderr)
            raise
        finally:
            for p in children:
                if p.poll() is None:p.terminate()
            for p in children:
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            for log in logs:log.close()

if __name__=='__main__':main()
