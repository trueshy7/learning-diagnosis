"""内部服务鉴权、版本回报、清单与历史测验诊断数据；不连接业务库。"""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from app import config
from app.models import Course, CourseResource, ExamAnswer, ExamAttempt, ExamQuestion, ResourceIndexState, ResourceKnowledgePoint
from app.services import exams, internal
from app.services.assessment import grade_paper
from app.services.resource_index import content_hash
from test_exams import POINTS, grade_input, make_paper
from test_resources import compile_query, resource_api, rows

C_HEADERS = {'Authorization': 'Bearer ' + 'c' * 40}
D_HEADERS = {'Authorization': 'Bearer ' + 'd' * 40}


@pytest.fixture
def internal_api(resource_api, monkeypatch):
    client, db, user, state = resource_api
    for name, key in [('C', 'c'), ('D', 'd')]:
        monkeypatch.setattr(config, f'{name}_SERVICE_KEY', key * 40)
        monkeypatch.setattr(config, f'{name}_SERVICE_COURSE_IDS', 'course')
    monkeypatch.setattr(exams.time, 'time', lambda: 1000)
    state['paper'] = make_paper()
    selections = {'q1': ['q1a'], 'q2': ['q2b']}
    score, grades, stats = grade_paper(grade_input(state['paper']), selections, POINTS)
    state['attempt'] = ExamAttempt(id='attempt', exam_id='exam', course_id='course', student_id=1,
        status='submitted', started_at=900, expires_at=1100, submitted_at=950, score=score,
        total_score=Decimal('15.25'), knowledge_snapshot=deepcopy(POINTS), knowledge_point_stats=stats)
    state['answers'] = [ExamAnswer(attempt_id='attempt', exam_id='exam', question_id=item['question_id'],
        selected_option_ids=selections.get(item['question_id'], []), correct=item['correct'],
        score=item['score'], revision=1, updated_at=950) for item in grades]
    state['baseline'] = None
    state['courses'] = [state['course']]
    original_scalar, original_scalars, original_execute = db.scalar.side_effect, db.scalars.side_effect, db.execute.side_effect

    def allowed(params, course_id):
        scope = params.get('course_id_1')
        return scope is None or (course_id == scope if isinstance(scope, str) else course_id in scope)

    def scalar(statement):
        description = statement.column_descriptions[0]
        entity, name = description.get('entity'), description.get('name')
        params = compile_query(statement).params
        if entity is CourseResource:
            item = state['resource']
            if item is None or params.get('id_1', item.id) != item.id or not allowed(params, item.course_id):
                return None
            return item.course_id if name == 'course_id' else item
        if entity is ExamAttempt:
            item = state['baseline'] if params.get('id_1') == 'baseline' else state['attempt']
            if item is None or params.get('id_1') != item.id or not allowed(params, item.course_id):
                return None
            return item.course_id if name == 'course_id' else item
        if entity is Course and name == 'id':
            return state['course'].id if params['id_1'] == state['course'].id else None
        return original_scalar(statement)

    def scalars(statement):
        description = statement.column_descriptions[0]
        entity, name = description.get('entity'), description.get('name')
        params = compile_query(statement).params
        if entity is Course:
            items = [item for item in state['courses'] if params.get('id_2', '') < item.id]
            scope = params.get('id_1')
            if isinstance(scope, (set, frozenset, list, tuple)):
                items = [item for item in items if item.id in scope]
            elif isinstance(scope, str):  # wildcard scope: after_id uses id_1
                items = [item for item in items if item.id > scope]
            return rows(sorted(items, key=lambda item: item.id)[:params.get('param_1', 101)])
        if entity is CourseResource:  # ready catalog candidate query
            resource, index = state['resource'], state['index_state']
            ready = resource and index and resource.status == 'active' and index.status == 'ready'
            ready = ready and resource.version == index.resource_version == index.indexed_version
            return rows([resource] if ready else [])
        if entity is ResourceKnowledgePoint and name == 'knowledge_point_id':
            return rows(sorted(link.knowledge_point_id for link in state['links']))
        if entity is ExamQuestion:
            return rows(state['paper'])
        if entity is ExamAnswer:
            return rows(state['answers'])
        return original_scalars(statement)

    def execute(statement):
        if getattr(statement, 'is_select', False) and statement.column_descriptions[0].get('entity') is CourseResource:
            params = compile_query(statement).params
            resource = state['resource']
            return rows([resource] if resource and resource.id > params.get('id_1', '') else [])
        return original_execute(statement)

    db.scalar.side_effect, db.scalars.side_effect, db.execute.side_effect = scalar, scalars, execute
    yield client, db, user, state


def ready_body(state, **changes):
    return {'resource_version': state['resource'].version, 'status': 'ready', 'document_id': 'document-1',
            'content_hash': content_hash(state['resource'], [link.knowledge_point_id for link in state['links']]),
            **changes}


def report(client, payload):
    return client.put('/internal/resources/resource/index-state', headers=C_HEADERS, json=payload)


def test_internal_requires_service_token_even_when_user_is_logged_in(internal_api):
    client, db, _, _ = internal_api
    for path in ['/internal/courses', '/internal/courses/course/resources', '/internal/resources/resource',
                 '/internal/attempts/attempt/diagnosis-input']:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'Authorization': 'Bearer a-user-token'}).status_code == 401
    db.scalar.assert_not_called()
    db.scalars.assert_not_called()


def test_c_and_d_cannot_use_each_others_capabilities(internal_api):
    client, db, _, _ = internal_api
    assert client.get('/internal/courses', headers=D_HEADERS).status_code == 401
    assert client.get('/internal/attempts/attempt/diagnosis-input', headers=C_HEADERS).status_code == 401
    assert report(client, {}).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize('setting,value', [('C_SERVICE_KEY', ''), ('C_SERVICE_KEY', 'short'),
                                         ('D_SERVICE_KEY', 'c' * 40)])
def test_unconfigured_short_or_shared_service_keys_fail_closed(internal_api, monkeypatch, setting, value):
    client, db, _, _ = internal_api
    monkeypatch.setattr(config, setting, value)
    assert client.get('/internal/courses', headers=C_HEADERS).status_code == 503
    db.scalars.assert_not_called()


@pytest.mark.parametrize('scope', ['', 'other-course'])
def test_c_course_allowlist_cannot_be_bypassed_by_resource_id(internal_api, monkeypatch, scope):
    client, db, _, _ = internal_api
    monkeypatch.setattr(config, 'C_SERVICE_COURSE_IDS', scope)
    assert client.get('/internal/courses', headers=C_HEADERS).json()['data']['items'] == []
    assert client.get('/internal/courses/course/resources', headers=C_HEADERS).status_code == 404
    assert client.get('/internal/resources/resource', headers=C_HEADERS).status_code == 404
    assert report(client, {'resource_version': 1, 'status': 'failed', 'error_code': 'timeout'}).status_code == 404
    db.commit.assert_not_called()


def test_d_course_allowlist_and_unknown_attempt(internal_api, monkeypatch):
    client, db, _, _ = internal_api
    monkeypatch.setattr(config, 'D_SERVICE_COURSE_IDS', 'other-course')
    assert client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS).status_code == 404
    monkeypatch.setattr(config, 'D_SERVICE_COURSE_IDS', '*')
    assert client.get('/internal/attempts/missing/diagnosis-input', headers=D_HEADERS).status_code == 404
    db.commit.assert_not_called()


def test_course_keyset_pagination_and_wildcard_scope(internal_api, monkeypatch):
    client, db, _, state = internal_api
    state['courses'].append(Course(id='z-course', name='另一课程', status='draft', updated_at=100))
    monkeypatch.setattr(config, 'C_SERVICE_COURSE_IDS', '*')
    first = client.get('/internal/courses?limit=1', headers=C_HEADERS).json()['data']
    assert [item['id'] for item in first['items']] == ['course']
    assert first['next_after_id'] == 'course'
    second = client.get('/internal/courses?limit=1&after_id=course', headers=C_HEADERS).json()['data']
    assert [item['id'] for item in second['items']] == ['z-course'] and second['next_after_id'] is None
    assert 'teacher_id' not in first['items'][0]


@pytest.mark.parametrize('status', ['active', 'deleted'])
def test_manifest_includes_tombstones_and_never_loads_large_body(internal_api, status):
    client, db, _, state = internal_api
    state['resource'].status = status
    data = client.get('/internal/courses/course/resources', headers=C_HEADERS).json()['data']
    assert data['items'][0]['status'] == status and data['items'][0]['index_status'] == 'pending'
    assert 'text' not in data['items'][0]
    assert 'course_resources.text' not in str(compile_query(db.execute.call_args.args[0]))
    assert client.get('/internal/courses/course/resources?after_id=resource', headers=C_HEADERS).json()['data']['items'] == []


def test_detail_has_canonical_hash_without_private_original_file_path(internal_api):
    client, db, _, state = internal_api
    data = client.get('/internal/resources/resource', headers=C_HEADERS).json()['data']
    payload = {key: data[key] for key in ('course_id', 'title', 'text', 'source', 'knowledge_point_ids')}
    expected = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert data['content_hash'] == expected
    assert data['index_state']['status'] == 'pending'
    assert 'storage_key' not in data and 'original_file' not in data
    assert all('LOCK IN SHARE MODE' in str(compile_query(call.args[0])) for call in db.scalar.call_args_list)
    state['resource'].status = 'deleted'
    tombstone = client.get('/internal/resources/resource', headers=C_HEADERS).json()['data']
    assert tombstone['status'] == 'deleted' and 'text' not in tombstone and 'content_hash' not in tombstone


def test_ready_report_is_idempotent_but_cannot_be_downgraded_or_rebound(internal_api):
    client, db, _, state = internal_api
    payload = ready_body(state)
    first = report(client, payload)
    assert first.status_code == 200, first.text
    assert first.json()['data']['status'] == 'ready'
    db.commit.assert_called_once()
    assert report(client, payload).json()['data'] == first.json()['data']
    db.commit.assert_called_once()
    assert report(client, {'resource_version': 1, 'status': 'failed', 'error_code': 'timeout'}).status_code == 409
    assert report(client, ready_body(state, document_id='different')).status_code == 409
    assert client.get('/teacher/resources/resource').json()['data']['index_status'] == 'ready'
    assert client.get('/teacher/courses/course/resources').json()['data']['items'][0]['index_status'] == 'ready'


def test_old_hash_old_version_and_premature_deletion_are_rejected(internal_api):
    client, db, _, state = internal_api
    for payload in [ready_body(state, content_hash='0' * 64), ready_body(state, resource_version=2),
                    {'resource_version': 1, 'status': 'deleted'}]:
        assert report(client, payload).status_code == 409
    db.commit.assert_not_called()


def test_failure_is_sanitized_idempotent_and_recoverable(internal_api):
    client, db, _, state = internal_api
    payload = {'resource_version': 1, 'status': 'failed', 'error_code': 'timeout'}
    first = report(client, payload)
    assert first.status_code == 200 and first.json()['data']['last_error'] == '索引处理超时'
    assert report(client, payload).json()['data'] == first.json()['data']
    db.commit.assert_called_once()
    assert report(client, ready_body(state)).json()['data']['status'] == 'ready'


def test_modify_invalidate_ready_and_late_callback_cannot_restore_old_index(internal_api):
    client, db, _, state = internal_api
    old = ready_body(state)
    assert report(client, old).status_code == 200
    noop = client.patch('/teacher/resources/resource', json={'expected_version': 1, 'title': '栈资料'})
    assert noop.json()['data']['index_status'] == 'ready'
    changed = client.patch('/teacher/resources/resource', json={'expected_version': 1, 'text': '新正文'})
    assert changed.json()['data']['version'] == 2 and changed.json()['data']['index_status'] == 'pending'
    assert state['index_state'].resource_version == 2 and state['index_state'].indexed_version == 1
    assert report(client, old).status_code == 409
    data = client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS).json()['data']
    assert data['resource_catalog'] == []
    assert report(client, ready_body(state, document_id='doc-v2')).status_code == 200


def test_delete_removes_catalog_immediately_and_acknowledges_tombstone(internal_api):
    client, db, _, state = internal_api
    assert report(client, ready_body(state)).status_code == 200
    assert client.delete('/teacher/resources/resource').status_code == 200
    assert state['index_state'].status == 'pending'
    assert report(client, ready_body(state)).status_code == 409
    assert client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS).json()['data']['resource_catalog'] == []
    failed = {'resource_version': 2, 'status': 'failed', 'error_code': 'storage_unavailable'}
    assert report(client, failed).status_code == 200
    deleted = {'resource_version': 2, 'status': 'deleted'}
    first = report(client, deleted)
    assert first.status_code == 200 and first.json()['data']['document_id'] is None
    assert report(client, deleted).json()['data'] == first.json()['data']
    assert report(client, failed).status_code == 409


def test_d_export_preserves_snapshot_grades_and_distinguishes_blank_from_wrong(internal_api):
    client, db, _, state = internal_api
    data = client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS).json()['data']
    assert data['contract_version'] == 'b-internal-1' and data['baseline'] is None
    assert len(data['graded_answers']) == 4 and data['score'] == 2.5
    assert data['graded_answers'][0]['answered'] is True and data['graded_answers'][0]['correct'] is True
    assert data['graded_answers'][1]['answered'] is True and data['graded_answers'][1]['correct'] is False
    assert data['graded_answers'][2]['answered'] is False and data['graded_answers'][2]['correct'] is False
    assert data['graded_answers'][0]['correct_option_ids'] == ['q1a']
    assert data['graded_answers'][0]['explanation'] == 'SECRET EXPLANATION'
    assert data['knowledge_points'] == POINTS and data['knowledge_point_stats'] == state['attempt'].knowledge_point_stats
    assert data['warnings'] and data['resource_catalog'] == []
    assert not {'student_id', 'email', 'password_hash'} & data.keys()


def test_catalog_filters_versions_hashes_and_knowledge_snapshot_intersection(internal_api):
    client, db, _, state = internal_api
    state['links'].append(ResourceKnowledgePoint(resource_id='resource', course_id='course', knowledge_point_id='later-point'))
    assert report(client, ready_body(state)).status_code == 200
    path = '/internal/attempts/attempt/diagnosis-input'
    data = client.get(path, headers=D_HEADERS).json()['data']
    assert data['resource_catalog'][0]['knowledge_point_ids'] == ['kp1'] and data['warnings'] == []
    assert data['resource_catalog'][0]['resource_version'] == 1
    state['index_state'].indexed_hash = '0' * 64
    assert client.get(path, headers=D_HEADERS).json()['data']['resource_catalog'] == []
    state['index_state'].indexed_hash = ready_body(state)['content_hash']
    state['attempt'].knowledge_snapshot = [{'id': 'unrelated', 'name': '另一知识点'}]
    assert client.get(path, headers=D_HEADERS).json()['data']['resource_catalog'] == []


def test_in_progress_d_export_does_not_reveal_correct_answers(internal_api):
    client, db, _, state = internal_api
    state['attempt'].status = 'in_progress'
    response = client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS)
    assert response.status_code == 409 and 'SECRET EXPLANATION' not in response.text
    db.commit.assert_not_called()


def test_overdue_d_export_finalizes_saved_answers_and_commits(internal_api):
    client, db, _, state = internal_api
    state['attempt'].status, state['attempt'].expires_at = 'in_progress', 999
    response = client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()['data']['attempt_status'] == 'expired'
    assert response.json()['data']['submitted_at'] == 999
    db.commit.assert_called_once()


def test_retest_includes_historical_baseline(internal_api):
    client, db, _, state = internal_api
    baseline = ExamAttempt(id='baseline', exam_id='old-exam', course_id='course', status='submitted',
        score=Decimal('0'), total_score=Decimal('10'), submitted_at=800,
        knowledge_point_stats=deepcopy(state['attempt'].knowledge_point_stats))
    state['baseline'] = baseline
    state['attempt'].baseline_attempt_id = 'baseline'
    data = client.get('/internal/attempts/attempt/diagnosis-input', headers=D_HEADERS).json()['data']
    assert data['baseline']['attempt_id'] == 'baseline' and data['baseline']['exam_id'] == 'old-exam'
    assert data['baseline']['knowledge_points'] == baseline.knowledge_point_stats


@pytest.mark.parametrize('payload', [
    {}, {'resource_version': True, 'status': 'deleted'}, {'resource_version': '1', 'status': 'deleted'},
    {'resource_version': 0, 'status': 'deleted'}, {'resource_version': 1, 'status': 'pending'},
    {'resource_version': 1, 'status': 'ready'},
    {'resource_version': 1, 'status': 'ready', 'document_id': ' ', 'content_hash': '0' * 64},
    {'resource_version': 1, 'status': 'ready', 'document_id': 'doc', 'content_hash': 'G' * 64},
    {'resource_version': 1, 'status': 'ready', 'document_id': 'doc', 'content_hash': '0' * 64, 'error_code': 'timeout'},
    {'resource_version': 1, 'status': 'failed'},
    {'resource_version': 1, 'status': 'failed', 'error_code': 'private connection password'},
    {'resource_version': 1, 'status': 'failed', 'error_code': 'timeout', 'document_id': 'doc'},
    {'resource_version': 1, 'status': 'deleted', 'error_code': 'timeout'},
    {'resource_version': 1, 'status': 'deleted', 'content_hash': '0' * 64},
    {'resource_version': 1, 'status': 'failed', 'error_code': 'timeout', 'last_error': 'secret'},
])
def test_invalid_callback_fields_are_rejected_before_database(internal_api, payload):
    client, db, _, _ = internal_api
    assert report(client, payload).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize('path', ['/internal/courses?limit=0', '/internal/courses?limit=101',
                                 '/internal/courses?after_id=', '/internal/courses/course/resources?after_id=' + 'x' * 65])
def test_invalid_keyset_query(internal_api, path):
    client, db, _, _ = internal_api
    assert client.get(path, headers=C_HEADERS).status_code == 422
    db.scalars.assert_not_called()


@pytest.mark.parametrize('stage', ['scalar', 'flush', 'commit'])
def test_callback_database_failures_roll_back_and_hide_details(internal_api, stage):
    client, db, _, state = internal_api
    getattr(db, stage).side_effect = SQLAlchemyError('private connection string')
    response = report(client, ready_body(state))
    assert response.status_code == 503 and 'private' not in response.text
    db.rollback.assert_called_once()


def test_index_state_mysql_constraints():
    ddl = str(CreateTable(ResourceIndexState.__table__).compile(dialect=mysql.dialect()))
    assert 'FOREIGN KEY(resource_id) REFERENCES course_resources (id)' in ddl
    assert 'ck_resource_index_ready' in ddl and 'ck_resource_index_indexed_version' in ddl
    assert 'ENGINE=InnoDB' in ddl
