"""真实 MySQL + B/C HTTP 联调；仅通过 TEST_MYSQL_URL 启用随机测试库。"""
from contextlib import contextmanager
from pathlib import Path
import os
import socket
import sys
from threading import Thread
import time

import httpx
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'member-c-rag'))

from rag_service.catalog import Conflict, KnowledgeIndex
from rag_service.config import Settings
from rag_service.contracts import ResourceRecord
from rag_service.main import create_app
from rag_service.sync import BackendSync
from app import main
from test_mysql_internal import C_HEADERS, D_HEADERS, mysql_internal
from test_mysql_resources import mysql_resources

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MYSQL_URL'), reason='需要独立 MySQL 测试连接')


@contextmanager
def live_server(app):
    """绑定随机回环端口；测试结束先关闭 HTTP，再释放测试数据库。"""
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
    thread = Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        with httpx.Client(trust_env=False, timeout=1) as client:
            while time.monotonic() < deadline:
                if not thread.is_alive():
                    pytest.fail('HTTP 服务提前退出')
                if server.started:
                    assert client.get(url + '/health').status_code == 200
                    break
                time.sleep(.05)
            else:
                pytest.fail('HTTP 服务启动超时')
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        assert not thread.is_alive(), 'HTTP 服务未正常关闭'


def test_b_c_real_http_resource_lifecycle(mysql_internal, tmp_path, monkeypatch):
    _, users, _ = mysql_internal
    # 单次同步驱动与 HTTP 使用同一进程中的索引，禁止启动第二个写进程。
    monkeypatch.setenv('RAG_SYNC_ON_START', 'false')
    settings = Settings(tmp_path / 'catalog.json', seed_on_start=False,
                        service_key='r' * 40, allowed_course_ids='course')
    c_app = create_app(settings)
    c_headers = {'Authorization': 'Bearer ' + settings.service_key}
    with live_server(main.app) as b_url, live_server(c_app) as c_url, \
            httpx.Client(base_url=b_url, trust_env=False, timeout=10) as b, \
            httpx.Client(base_url=c_url, headers=c_headers, trust_env=False, timeout=10) as c:
        def call(method, path, *, headers=users['teacher01'], **kwargs):
            response = b.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()['data']

        sync = BackendSync(c_app.state.index, b_url, 'c' * 40)
        try:
            assert b.get('/internal/courses').status_code == 401
            assert b.get('/internal/courses', headers=D_HEADERS).status_code == 401
            assert b.get('/internal/courses/other-course/resources', headers=C_HEADERS).status_code == 404
            resource = call('POST', '/teacher/courses/course/resources', json={
                'title': '联调栈资料', 'text': '栈遵循后进先出原则。入栈和出栈均发生在栈顶。',
                'source': '联调自编材料', 'knowledge_point_ids': ['kp1'],
            })
            rid = resource['id']
            assert resource['index_status'] == 'pending'
            assert sync.run_once() == {'ready': 1, 'deleted': 0, 'failed': 0, 'failed_resource_ids': []}
            detail = call('GET', f'/internal/resources/{rid}', headers=C_HEADERS)
            assert detail['index_state']['status'] == 'ready'
            old_ack = {'resource_version': 1, 'status': 'ready',
                       'document_id': detail['index_state']['document_id'], 'content_hash': detail['content_hash']}
            old_record = ResourceRecord(**{key: detail[key] for key in
                ('course_id', 'title', 'text', 'source', 'knowledge_point_ids', 'content_hash')},
                resource_id=rid, resource_version=1, document_id=old_ack['document_id'])
            scope = [{key: old_ack[key] for key in ('resource_version', 'document_id', 'content_hash')} | {'resource_id': rid}]

            def retrieve(resource_scope):
                response = c.post('/internal/retrieve-scoped', json={
                    'course_id': 'course', 'query': '栈', 'knowledge_point_ids': ['kp1'],
                    'resource_scope': resource_scope, 'top_k': 3,
                })
                response.raise_for_status()
                return response.json()

            evidence = retrieve(scope)
            assert evidence['evidence'] and evidence['mode'] == 'keyword_demo'
            assert all(item['resource_id'] == rid and item['resource_version'] == 1 for item in evidence['evidence'])
            assert not retrieve([])['evidence']
            citation = {'retrieval_id': evidence['retrieval_id'],
                        'evidence_ids': [item['evidence_id'] for item in evidence['evidence']]}
            assert c.post('/internal/citations/validate', json=citation).json()['valid']

            # 重复扫描幂等；索引丢失时即使 B 为 ready，也能恢复原 document_id。
            first_state = c_app.state.index.status()
            assert sync.run_once()['failed'] == 0
            assert c_app.state.index.status() == first_state
            settings.data_path.unlink()
            assert sync.run_once()['ready'] == 1
            assert call('GET', f'/internal/resources/{rid}', headers=C_HEADERS)['index_state'] == detail['index_state']

            # 已完成测验的正式目录只包含 C 实际持久化并确认的资料。
            question = call('POST', '/teacher/courses/course/questions', json={
                'kind': 'single', 'stem': '栈访问顺序？', 'explanation': '后进先出', 'status': 'active',
                'knowledge_point_ids': ['kp1'], 'options': [
                    {'label': 'A', 'text': '后进先出', 'is_correct': True},
                    {'label': 'B', 'text': '先进先出', 'is_correct': False}],
            })
            exam = call('POST', '/teacher/courses/course/exams', json={'title': 'BC联调', 'duration_seconds': 600})
            eid = exam['id']
            call('PUT', f'/teacher/exams/{eid}/questions', json={'questions': [{'question_id': question['id'], 'score': 10}]})
            call('POST', f'/teacher/exams/{eid}/publish')
            attempt = call('POST', f'/exams/{eid}/attempts', headers=users['student01'])
            aid = attempt['id']
            call('POST', f'/attempts/{aid}/submit', headers=users['student01'])

            def catalog():
                return call('GET', f'/internal/attempts/{aid}/diagnosis-input', headers=D_HEADERS)['resource_catalog']

            exported = catalog()
            assert exported[0]['resource_id'] == rid
            assert retrieve([{key: item[key] for key in scope[0]} for item in exported])['evidence']

            changed = call('PATCH', f'/teacher/resources/{rid}', json={
                'expected_version': 1, 'text': '栈新版正文：栈采用后进先出，栈顶用于压栈和弹栈。'})
            assert changed['version'] == 2 and changed['index_status'] == 'pending'
            assert catalog() == []
            assert b.put(f'/internal/resources/{rid}/index-state', headers=C_HEADERS, json=old_ack).status_code == 409
            assert sync.run_once()['ready'] == 1
            stale = retrieve(scope)
            assert not stale['evidence'] and stale['unavailable_resources'][0]['reason'] == 'version_changed'
            assert not c.post('/internal/citations/validate', json=citation).json()['valid']
            current_scope = [{key: item[key] for key in scope[0]} for item in catalog()]
            assert retrieve(current_scope)['evidence'][0]['resource_version'] == 2
            with pytest.raises(Conflict):
                c_app.state.index.ingest_record(old_record)

            call('DELETE', f'/teacher/resources/{rid}')
            assert catalog() == []
            assert sync.run_once()['deleted'] == 1
            assert not retrieve(current_scope)['evidence']
            assert call('GET', f'/internal/resources/{rid}', headers=C_HEADERS)['index_state']['status'] == 'deleted'
            reopened = KnowledgeIndex(settings)
            assert reopened.resource_state(rid)['state'] == 'deleted'
            with pytest.raises(Conflict):
                reopened.ingest_record(old_record)
            assert sync.run_once()['deleted'] == 1
        finally:
            sync.close()


def test_c_startup_worker_pulls_b_and_propagates_deletion(mysql_internal, tmp_path, monkeypatch):
    _, users, _ = mysql_internal
    with live_server(main.app) as b_url, httpx.Client(base_url=b_url, trust_env=False, timeout=10) as b:
        response = b.post('/teacher/courses/course/resources', headers=users['teacher01'], json={
            'title': '自动同步栈', 'text': '栈遵循后进先出原则。', 'knowledge_point_ids': ['kp1']})
        response.raise_for_status()
        rid = response.json()['data']['id']
        monkeypatch.setenv('RAG_SYNC_ON_START', 'true')
        monkeypatch.setenv('RAG_SYNC_INTERVAL', '5')
        monkeypatch.setenv('B_URL', b_url)
        monkeypatch.setenv('B_C_KEY', 'c' * 40)
        c_app = create_app(Settings(tmp_path / 'worker.json', seed_on_start=False, allowed_course_ids='course'))

        def wait_state(expected):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                detail = b.get(f'/internal/resources/{rid}', headers=C_HEADERS)
                detail.raise_for_status()
                if detail.json()['data']['index_state']['status'] == expected:
                    return
                time.sleep(.1)
            pytest.fail(f'C 自动同步未在期限内回报 {expected}')

        with live_server(c_app) as c_url, httpx.Client(base_url=c_url, trust_env=False, timeout=10) as c:
            wait_state('ready')
            state = c.get(f'/internal/resources/{rid}/state').json()
            assert state['state'] == 'ready' and state['resource_version'] == 1
            assert b.delete(f'/teacher/resources/{rid}', headers=users['teacher01']).status_code == 200
            wait_state('deleted')
            assert c.get(f'/internal/resources/{rid}/state').json()['state'] == 'deleted'
