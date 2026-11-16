"""资料 HTTP、权限、版本及事务边界；使用数据库替身和 MySQL 方言。"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateTable

from app import config, main
from app.database import get_db
from app.models import (Course, CourseEnrollment, CourseResource, KnowledgePoint, ResourceFile,
                        ResourceIndexState, ResourceKnowledgePoint, User)
from app.security import current_user
from app.services import resources


def body(**changes):
    return {'title': '栈资料', 'text': '栈遵循后进先出原则。', 'knowledge_point_ids': ['kp1'], **changes}


def compile_query(statement):
    return statement.compile(dialect=mysql.dialect())


def rows(values):
    result = Mock()
    result.all.return_value = values
    return result


@pytest.fixture
def resource_api(monkeypatch):
    monkeypatch.setattr(config, 'DIAGNOSIS_AUTO_ENQUEUE', False)
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    monkeypatch.setattr(resources.time, 'time', lambda: 1000)
    user = User(id=7, username='teacher01', email='teacher@example.com', role='teacher')
    course = Course(id='course', teacher_id=7, name='课程', status='published')
    resource = CourseResource(id='resource', course_id='course', title='栈资料', text='原始正文', source='自编材料',
                              version=1, status='active', created_at=100, updated_at=100)
    enrollment = CourseEnrollment(course_id='course', student_id=7, status='active')
    state = {'course': course, 'resource': resource, 'enrollment': enrollment, 'files': [], 'index_state': None,
             'links': [ResourceKnowledgePoint(resource_id='resource', course_id='course', knowledge_point_id='kp1')],
             'points': {'kp1': ('course', 'active'), 'kp2': ('course', 'active'),
                        'other': ('other-course', 'active'), 'disabled': ('course', 'disabled')}}
    db = Mock(spec=Session)

    def scalar(statement):
        description = statement.column_descriptions[0]
        entity, name = description.get('entity'), description.get('name')
        params = compile_query(statement).params
        item = state['resource']
        if entity is Course:
            if params.get('teacher_id_1', state['course'].teacher_id) != state['course'].teacher_id:
                return None
            return state['course']
        if entity is CourseEnrollment:
            enrolled = state['enrollment']
            return enrolled if (enrolled and enrolled.status == 'active' and enrolled.student_id == user.id) else None
        if entity is CourseResource:
            if item is None or params.get('status_1', item.status) != item.status:
                return None
            return item.course_id if name == 'course_id' else item
        if entity is ResourceFile:
            return state['files'][0] if state['files'] else None
        if entity is ResourceIndexState:
            return state['index_state']
        if name == 'count':
            return int(item is not None and params.get('status_1', item.status) == item.status)
        raise AssertionError(str(statement))

    def scalars(statement):
        entity = statement.column_descriptions[0].get('entity')
        params = compile_query(statement).params
        if entity is KnowledgePoint:
            ids = params['id_1']
            return rows([key for key in ids if state['points'].get(key) == (params['course_id_1'], 'active')])
        if entity is ResourceKnowledgePoint:
            wanted = params.get('resource_id_1')
            return rows([link for link in state['links'] if wanted is None
                         or link.resource_id in (wanted if isinstance(wanted, list) else [wanted])])
        if entity is ResourceFile:
            wanted = params.get('resource_id_1')
            return rows([file for file in state['files'] if wanted is None
                         or file.resource_id in (wanted if isinstance(wanted, list) else [wanted])])
        if entity is ResourceIndexState:
            return rows([state['index_state']] if state['index_state'] else [])
        raise AssertionError(str(statement))

    def execute(statement):
        if getattr(statement, 'is_delete', False):
            state['links'] = []
            return Mock()
        item = state['resource']
        params = compile_query(statement).params
        return rows([item] if item is not None and params.get('status_1', item.status) == item.status else [])

    db.scalar.side_effect = scalar
    db.scalars.side_effect = scalars
    db.execute.side_effect = execute
    def add(item):
        if isinstance(item, CourseResource):
            state['resource'] = item
        elif isinstance(item, ResourceFile):
            state['files'].append(item)
        elif isinstance(item, ResourceIndexState):
            state['index_state'] = item
        else:
            raise AssertionError(type(item))
    db.add.side_effect = add
    db.add_all.side_effect = lambda values: state['links'].extend(values)
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(main.app) as client:
            yield client, db, user, state
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(current_user, None)


def test_create_resource_has_server_managed_identity_version_and_parent_flush(resource_api):
    client, db, user, state = resource_api
    state['resource'], state['links'] = None, []
    response = client.post('/teacher/courses/course/resources', json=body(title=' 栈资料 '))
    assert response.status_code == 201, response.text
    data = response.json()['data']
    assert data['title'] == '栈资料' and len(data['id']) == 32
    assert data['version'] == 1 and data['status'] == 'active'
    assert data['source'] == '课程教师自编材料'
    assert data['created_at'] == data['updated_at'] == 1000
    assert data['knowledge_point_ids'] == ['kp1'] and data['text'] == body()['text']
    methods = [call[0] for call in db.method_calls]
    assert methods.index('add') < methods.index('flush') < methods.index('add_all') < methods.index('commit')
    assert 'FOR UPDATE' in str(compile_query(db.scalar.call_args_list[0].args[0]))
    db.commit.assert_called_once()


@pytest.mark.parametrize('change', [
    {'title': ''}, {'title': ' '}, {'title': 'a' * 201}, {'text': ' '}, {'text': 'a' * 200001},
    {'source': ''}, {'source': None}, {'source': 'a' * 1001}, {'knowledge_point_ids': []},
    {'knowledge_point_ids': ['kp1', 'kp1']}, {'knowledge_point_ids': ['a' * 65]},
    {'knowledge_point_ids': [str(i) for i in range(51)]}, {'knowledge_point_ids': None},
    {'id': 'injected'}, {'version': 2}, {'status': 'deleted'}, {'teacher_id': 8}, {'course_id': 'other'},
    {'document_id': 'not-yet-supported'}, {'sync_status': 'ready'},
])
def test_create_rejects_invalid_or_server_managed_fields(resource_api, change):
    client, db, user, state = resource_api
    assert client.post('/teacher/courses/course/resources', json=body(**change)).status_code == 422
    db.add.assert_not_called()


@pytest.mark.parametrize('point_id', ['missing', 'other', 'disabled'])
def test_point_must_be_active_and_in_course_before_creation(resource_api, point_id):
    client, db, user, state = resource_api
    assert client.post('/teacher/courses/course/resources', json=body(knowledge_point_ids=[point_id])).status_code == 409
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(('method', 'path', 'data'), [
    ('POST', '/teacher/courses/course/resources', body()),
    ('GET', '/teacher/courses/course/resources', None), ('GET', '/teacher/resources/resource', None),
    ('PATCH', '/teacher/resources/resource', {'expected_version': 1, 'title': '新标题'}),
    ('DELETE', '/teacher/resources/resource', None),
])
def test_student_cannot_manage_teacher_resources(resource_api, method, path, data):
    client, db, user, state = resource_api
    user.role = 'student'
    assert client.request(method, path, json=data).status_code == 403
    db.scalar.assert_not_called()


@pytest.mark.parametrize(('method', 'path', 'data'), [
    ('POST', '/teacher/courses/course/resources', body()),
    ('GET', '/teacher/courses/course/resources', None), ('GET', '/teacher/resources/resource', None),
    ('PATCH', '/teacher/resources/resource', {'expected_version': 1, 'title': '新标题'}),
    ('DELETE', '/teacher/resources/resource', None),
])
def test_teacher_cannot_access_other_owners_resources(resource_api, method, path, data):
    client, db, user, state = resource_api
    state['course'].teacher_id = 8
    assert client.request(method, path, json=data).status_code == 404
    calls = [compile_query(call.args[0]) for call in db.scalar.call_args_list]
    assert any(query.params.get('teacher_id_1') == user.id for query in calls)
    db.commit.assert_not_called()


def test_teacher_list_filters_paginates_without_loading_body(resource_api):
    client, db, user, state = resource_api
    response = client.get('/teacher/courses/course/resources?page=2&page_size=1&keyword=栈%&knowledge_point_id=kp1')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['total'] == 1 and data['page'] == 2 and data['page_size'] == 1
    assert 'text' not in data['items'][0] and data['items'][0]['knowledge_point_ids'] == ['kp1']
    query = compile_query(db.execute.call_args.args[0])
    assert 'course_resources.text' not in str(query)
    assert query.params['title_1'] == '栈/%'
    assert query.params['knowledge_point_id_1'] == 'kp1'
    assert query.params['status_1'] == 'active'
    assert 'updated_at DESC' in str(query)


def test_teacher_can_read_deleted_but_default_list_excludes_it(resource_api):
    client, db, user, state = resource_api
    state['resource'].status = 'deleted'
    assert client.get('/teacher/resources/resource').json()['data']['text'] == '原始正文'
    assert client.get('/teacher/courses/course/resources').json()['data']['total'] == 0
    response = client.get('/teacher/courses/course/resources?status=deleted')
    assert response.json()['data']['total'] == 1


@pytest.mark.parametrize('data', [
    {}, {'title': '标题'}, {'expected_version': 1}, {'expected_version': 0, 'title': '标题'},
    {'expected_version': '1', 'title': '标题'}, {'expected_version': True, 'title': '标题'},
    {'expected_version': 1, 'title': None}, {'expected_version': 1, 'text': None},
    {'expected_version': 1, 'source': None}, {'expected_version': 1, 'knowledge_point_ids': None},
    {'expected_version': 1, 'knowledge_point_ids': []},
    {'expected_version': 1, 'knowledge_point_ids': ['kp1', 'kp1']},
    {'expected_version': 1, 'course_id': 'other'}, {'expected_version': 1, 'status': 'active'},
])
def test_patch_validation(resource_api, data):
    client, db, user, state = resource_api
    assert client.patch('/teacher/resources/resource', json=data).status_code == 422
    db.scalar.assert_not_called()


def test_patch_replaces_tags_and_increments_version_once(resource_api):
    client, db, user, state = resource_api
    response = client.patch('/teacher/resources/resource', json={
        'expected_version': 1, 'title': ' 新资料 ', 'text': ' 新正文 ', 'knowledge_point_ids': ['kp2'],
    })
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['version'] == 2 and data['updated_at'] == 1000 and data['created_at'] == 100
    assert data['title'] == '新资料' and data['text'] == '新正文' and data['knowledge_point_ids'] == ['kp2']
    assert state['links'][0].knowledge_point_id == 'kp2'
    assert client.patch('/teacher/resources/resource', json={'expected_version': 1, 'title': '旧页面覆盖'}).status_code == 409
    assert state['resource'].title == '新资料'


def test_patch_same_values_and_reordered_tags_do_not_change_version(resource_api):
    client, db, user, state = resource_api
    state['links'].append(ResourceKnowledgePoint(resource_id='resource', course_id='course', knowledge_point_id='kp2'))
    response = client.patch('/teacher/resources/resource', json={
        'expected_version': 1, 'title': '栈资料', 'knowledge_point_ids': ['kp2', 'kp1'],
    })
    assert response.status_code == 200
    assert response.json()['data']['version'] == 1 and response.json()['data']['updated_at'] == 100
    db.execute.assert_not_called()
    db.flush.assert_not_called()


def test_invalid_new_tag_does_not_partially_change_content(resource_api):
    client, db, user, state = resource_api
    response = client.patch('/teacher/resources/resource', json={
        'expected_version': 1, 'title': '不能部分保存', 'knowledge_point_ids': ['other'],
    })
    assert response.status_code == 409
    assert state['resource'].title == '栈资料' and state['resource'].version == 1
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_delete_is_idempotent_keeps_body_and_links_and_blocks_patch(resource_api):
    client, db, user, state = resource_api
    first = client.delete('/teacher/resources/resource')
    assert first.status_code == 200
    assert first.json()['data']['status'] == 'deleted' and first.json()['data']['version'] == 2
    assert client.delete('/teacher/resources/resource').json()['data'] == first.json()['data']
    assert state['resource'].text == '原始正文' and len(state['links']) == 1
    assert client.patch('/teacher/resources/resource', json={'expected_version': 2, 'title': '恢复'}).status_code == 409
    db.delete.assert_not_called()


@pytest.mark.parametrize(('method', 'path', 'data'), [
    ('POST', '/teacher/courses/course/resources', body()),
    ('PATCH', '/teacher/resources/resource', {'expected_version': 1, 'title': '标题'}),
    ('DELETE', '/teacher/resources/resource', None),
])
def test_archived_course_is_read_only(resource_api, method, path, data):
    client, db, user, state = resource_api
    state['course'].status = 'archived'
    assert client.request(method, path, json=data).status_code == 409
    db.commit.assert_not_called()
    assert client.get('/teacher/resources/resource').status_code == 200


@pytest.mark.parametrize('course_status', ['published', 'archived'])
def test_enrolled_student_reads_original_text_without_teacher_access(resource_api, course_status):
    client, db, user, state = resource_api
    user.role = 'student'
    state['course'].status = course_status
    response = client.get('/resources/resource')
    assert response.status_code == 200 and response.json()['data']['text'] == '原始正文'
    assert client.get('/courses/course/resources').status_code == 200
    enrollment_queries = [compile_query(call.args[0]) for call in db.scalar.call_args_list
                          if call.args[0].column_descriptions[0].get('entity') is CourseEnrollment]
    assert all(query.params['student_id_1'] == user.id for query in enrollment_queries)


@pytest.mark.parametrize('condition', ['draft', 'not_enrolled', 'withdrawn', 'deleted', 'other_student'])
def test_student_cannot_access_unavailable_material(resource_api, condition):
    client, db, user, state = resource_api
    user.role = 'student'
    if condition == 'draft':
        state['course'].status = 'draft'
    elif condition == 'not_enrolled':
        state['enrollment'] = None
    elif condition == 'withdrawn':
        state['enrollment'].status = 'withdrawn'
    elif condition == 'deleted':
        state['resource'].status = 'deleted'
    else:
        user.id = 99
    assert client.get('/resources/resource').status_code == 404
    if condition != 'deleted':
        assert client.get('/courses/course/resources').status_code == 404
    else:
        assert client.get('/courses/course/resources').json()['data']['total'] == 0


@pytest.mark.parametrize('path', ['/courses/course/resources', '/resources/resource'])
def test_teacher_cannot_use_student_only_resource_routes(resource_api, path):
    client, db, user, state = resource_api
    assert client.get(path).status_code == 403
    db.scalar.assert_not_called()


@pytest.mark.parametrize('path', ['/teacher/resources/resource', '/resources/resource'])
def test_resource_routes_require_login(resource_api, path):
    client, db, user, state = resource_api
    main.app.dependency_overrides.pop(current_user)
    assert client.get(path).status_code == 401


@pytest.mark.parametrize('path', [
    '/teacher/courses/course/resources?page=0', '/teacher/courses/course/resources?page_size=101',
    '/teacher/courses/course/resources?status=ready', '/teacher/courses/course/resources?knowledge_point_id=',
    '/teacher/courses/course/resources?keyword=' + 'a' * 101,
])
def test_resource_list_query_validation(resource_api, path):
    client, db, user, state = resource_api
    assert client.get(path).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize(('stage', 'error', 'status'), [
    ('flush', IntegrityError('insert', {}, Exception(1062, 'private duplicate')), 409),
    ('flush', IntegrityError('insert', {}, Exception(1452, 'private FK')), 409),
    ('commit', SQLAlchemyError('private DB error'), 503),
])
def test_resource_write_errors_roll_back_and_never_report_success(resource_api, stage, error, status):
    client, db, user, state = resource_api
    getattr(db, stage).side_effect = error
    response = client.post('/teacher/courses/course/resources', json=body())
    assert response.status_code == status and 'private' not in response.text
    db.rollback.assert_called_once()


def test_resource_read_error_returns_sanitized_503(resource_api):
    client, db, user, state = resource_api
    db.scalar.side_effect = SQLAlchemyError('private DB error')
    response = client.get('/teacher/resources/resource')
    assert response.status_code == 503 and 'private' not in response.text
    db.rollback.assert_called_once()


def test_resource_mysql_ddl_uses_mediumtext_and_cross_course_foreign_keys():
    configure_mappers()
    resource_sql = str(CreateTable(CourseResource.__table__).compile(dialect=mysql.dialect()))
    link_sql = str(CreateTable(ResourceKnowledgePoint.__table__).compile(dialect=mysql.dialect()))
    assert 'text MEDIUMTEXT NOT NULL' in resource_sql
    assert 'UNIQUE (course_id, id)' in resource_sql and 'ENGINE=InnoDB' in resource_sql
    assert 'FOREIGN KEY(course_id, resource_id) REFERENCES course_resources (course_id, id)' in link_sql
    assert 'FOREIGN KEY(course_id, knowledge_point_id) REFERENCES knowledge_points (course_id, id)' in link_sql
