"""课程 HTTP 与事务边界回归测试；不连接业务数据库。"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import main
from app.database import get_db
from app.models import Course, CourseChapter, CourseEnrollment, KnowledgePoint, User
from app.security import current_user
from app.services import courses


def course(status='draft'):
    return Course(id='course', teacher_id=7, name='数据结构', description=None,
                  status=status, created_at=100, updated_at=100)


def chapter():
    return CourseChapter(id='chapter', course_id='course', name='栈', description=None,
                         sort_order=0, created_at=100, updated_at=100)


def point(status='active'):
    return KnowledgePoint(id='point', course_id='course', chapter_id='chapter', name='入栈',
                          description=None, sort_order=0, status=status)


def enrollment(status='active'):
    return CourseEnrollment(course_id='course', student_id=7, status=status, enrolled_at=100, updated_at=100)


def rows(values):
    result = Mock()
    result.all.return_value = values
    return result


def compiled(call):
    return call.args[0].compile(dialect=mysql.dialect())


@pytest.fixture
def course_api(monkeypatch):
    monkeypatch.setattr(main.Base.metadata, 'create_all', Mock())
    monkeypatch.setattr(main.engine, 'dispose', Mock())
    monkeypatch.setattr(courses.time, 'time', lambda: 1000)
    db = Mock(spec=Session)
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.execute.return_value.all.return_value = []
    user = User(id=7, username='user001', role='teacher', email='user@example.com')
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(main.app) as client:
            yield client, db, user
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(current_user, None)


def test_create_course_uses_current_teacher_and_draft_default(course_api):
    client, db, user = course_api
    response = client.post('/teacher/courses', json={'name': ' 数据结构 '})
    assert response.status_code == 201
    data = response.json()['data']
    assert data['teacher_id'] == user.id and data['status'] == 'draft'
    assert data['name'] == '数据结构' and data['enrollment_count'] == 0
    assert data['created_at'] == data['updated_at'] == 1000
    assert len(data['id']) == 32
    db.commit.assert_called_once()
    assert response.headers['X-Request-ID'] == response.json()['request_id']


@pytest.mark.parametrize('body', [
    {}, {'name': '  '}, {'name': 'a' * 101}, {'name': '课程', 'teacher_id': 8},
    {'name': '课程', 'status': 'published'}, {'name': '课程', 'enrollment_count': 100},
    {'name': '课程', 'description': 'a' * 10001},
])
def test_create_course_rejects_invalid_or_server_managed_fields(course_api, body):
    client, db, user = course_api
    assert client.post('/teacher/courses', json=body).status_code == 422
    db.add.assert_not_called()


@pytest.mark.parametrize(('method', 'path', 'body'), [
    ('GET', '/teacher/courses', None), ('POST', '/teacher/courses', {'name': '课程'}),
    ('GET', '/teacher/courses/course', None), ('PATCH', '/teacher/courses/course', {'name': '新课程'}),
    ('POST', '/teacher/courses/course/chapters', {'name': '章节'}),
    ('POST', '/teacher/courses/course/chapters/chapter/knowledge-points', {'name': '知识点'}),
])
def test_student_cannot_use_teacher_routes(course_api, method, path, body):
    client, db, user = course_api
    user.role = 'student'
    assert client.request(method, path, json=body).status_code == 403
    db.scalar.assert_not_called()


@pytest.mark.parametrize(('method', 'path', 'body'), [
    ('GET', '/teacher/courses/course', None),
    ('PATCH', '/teacher/courses/course', {'name': '新名称'}),
    ('POST', '/teacher/courses/course/chapters', {'name': '章节'}),
    ('POST', '/teacher/courses/course/chapters/chapter/knowledge-points', {'name': '知识点'}),
])
def test_teacher_queries_are_scoped_to_owner(course_api, method, path, body):
    client, db, user = course_api
    response = client.request(method, path, json=body)
    assert response.status_code == 404
    query = compiled(db.scalar.call_args)
    assert query.params['teacher_id_1'] == user.id
    assert query.params['id_1'] == 'course'
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_teacher_list_filters_paginates_and_counts_only_active_enrollments(course_api):
    client, db, user = course_api
    db.scalar.return_value = 3
    db.scalars.return_value.all.return_value = [course('published')]
    db.execute.return_value.all.return_value = [('course', 2)]
    response = client.get('/teacher/courses?page=2&page_size=1&keyword=栈%&status=published')
    assert response.status_code == 200
    data = response.json()['data']
    assert (data['total'], data['page'], data['page_size']) == (3, 2, 1)
    assert data['items'][0]['enrollment_count'] == 2
    query = compiled(db.scalars.call_args)
    assert query.params['teacher_id_1'] == user.id
    assert query.params['status_1'] == 'published'
    assert query.params['name_1'] == '栈/%'
    count_query = compiled(db.execute.call_args)
    assert count_query.params['status_1'] == 'active'


def test_teacher_detail_includes_chapters_disabled_points_and_derived_count(course_api):
    client, db, user = course_api
    db.scalar.side_effect = [course(), 2]
    db.scalars.side_effect = [rows([chapter()]), rows([point('disabled')])]
    response = client.get('/teacher/courses/course')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['enrollment_count'] == 2
    assert data['chapters'][0]['knowledge_points'][0]['status'] == 'disabled'
    assert 'active' not in compiled(db.scalars.call_args).params.values()


def test_update_course_can_clear_description_and_never_accepts_count(course_api):
    client, db, user = course_api
    item = course()
    item.description = 'old'
    db.scalar.side_effect = [item, 2]
    response = client.patch('/teacher/courses/course', json={'name': ' 新名称 ', 'description': None})
    assert response.status_code == 200
    assert response.json()['data']['name'] == '新名称'
    assert response.json()['data']['description'] is None
    assert response.json()['data']['updated_at'] == 1000
    assert 'FOR UPDATE' in str(compiled(db.scalar.call_args_list[0]))
    db.commit.assert_called_once()


@pytest.mark.parametrize('body', [{}, {'name': None}, {'status': None}, {'status': 'invalid'},
                                  {'enrollment_count': 10}, {'teacher_id': 8}, {'name': ' '}])
def test_invalid_course_patch_is_rejected_before_database(course_api, body):
    client, db, user = course_api
    assert client.patch('/teacher/courses/course', json=body).status_code == 422
    db.scalar.assert_not_called()


def test_publish_requires_active_knowledge_point(course_api):
    client, db, user = course_api
    db.scalar.side_effect = [course(), None]
    response = client.patch('/teacher/courses/course', json={'status': 'published'})
    assert response.status_code == 409
    assert 'active' in compiled(db.scalar.call_args).params.values()
    assert 'FOR UPDATE' in str(compiled(db.scalar.call_args))
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_publish_with_content_and_archive_keep_records(course_api):
    client, db, user = course_api
    item = course()
    db.scalar.side_effect = [item, 'point', 0, item, 2]
    assert client.patch('/teacher/courses/course', json={'status': 'published'}).status_code == 200
    assert item.status == 'published'
    response = client.patch('/teacher/courses/course', json={'status': 'archived'})
    assert response.status_code == 200
    assert item.status == 'archived'
    assert response.json()['data']['enrollment_count'] == 2
    db.delete.assert_not_called()


@pytest.mark.parametrize(('before', 'after'), [('published', 'draft'), ('archived', 'draft'), ('archived', 'published')])
def test_disallowed_status_transition(course_api, before, after):
    client, db, user = course_api
    db.scalar.return_value = course(before)
    assert client.patch('/teacher/courses/course', json={'status': after}).status_code == 409
    db.commit.assert_not_called()


def test_create_chapter_and_point_use_path_course_and_chapter(course_api):
    client, db, user = course_api
    db.scalar.side_effect = [course(), course(), chapter()]
    response = client.post('/teacher/courses/course/chapters', json={'name': ' 栈 ', 'sort_order': 2})
    assert response.status_code == 201
    assert response.json()['data']['sort_order'] == 2
    response = client.post('/teacher/courses/course/chapters/chapter/knowledge-points', json={'name': ' 入栈 '})
    assert response.status_code == 201
    assert response.json()['data']['course_id'] == 'course'
    assert response.json()['data']['chapter_id'] == 'chapter'
    assert response.json()['data']['status'] == 'active'
    lookup = compiled(db.scalar.call_args)
    assert lookup.params['course_id_1'] == 'course'
    assert lookup.params['id_1'] == 'chapter'


@pytest.mark.parametrize('body', [{'name': '章节', 'sort_order': -1}, {'name': '章节', 'sort_order': 1.5},
                                  {'name': '章节', 'sort_order': '1'}, {'name': '章节', 'course_id': 'other'}])
def test_chapter_validation(course_api, body):
    client, db, user = course_api
    assert client.post('/teacher/courses/course/chapters', json=body).status_code == 422
    db.add.assert_not_called()


def test_cross_course_chapter_is_rejected(course_api):
    client, db, user = course_api
    db.scalar.side_effect = [course(), None]
    assert client.post('/teacher/courses/course/chapters/other/knowledge-points', json={'name': '知识点'}).status_code == 404
    db.add.assert_not_called()


@pytest.mark.parametrize('path', ['/teacher/courses/course/chapters',
                                 '/teacher/courses/course/chapters/chapter/knowledge-points'])
def test_archived_course_rejects_new_content(course_api, path):
    client, db, user = course_api
    db.scalar.return_value = course('archived')
    assert client.post(path, json={'name': '内容'}).status_code == 409
    db.add.assert_not_called()


def test_student_catalog_lists_published_courses_and_own_enrollment(course_api):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.return_value = 1
    db.scalars.side_effect = [rows([course('published')]), rows([enrollment()])]
    db.execute.return_value.all.return_value = [('course', 2)]
    response = client.get('/courses')
    assert response.status_code == 200
    item = response.json()['data']['items'][0]
    assert item['is_enrolled'] is True and item['enrolled_at'] == 100
    assert compiled(db.scalars.call_args_list[0]).params['status_1'] == 'published'
    assert compiled(db.scalars.call_args_list[1]).params['student_id_1'] == user.id


def test_my_courses_includes_archived_and_only_active_own_enrollments(course_api):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.return_value = 1
    db.scalars.side_effect = [rows([course('archived')]), rows([enrollment()])]
    db.execute.return_value.all.return_value = [('course', 1)]
    response = client.get('/courses/mine?status=archived')
    assert response.status_code == 200
    assert response.json()['data']['items'][0]['status'] == 'archived'
    query = compiled(db.scalars.call_args_list[0])
    assert 'JOIN course_enrollments' in str(query)
    assert query.params['student_id_1'] == user.id
    assert {'active', 'archived'} <= set(query.params.values())


def test_public_course_detail_hides_content_until_enrolled(course_api):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.side_effect = [course('published'), None, 2]
    data = client.get('/courses/course').json()['data']
    assert data['chapters'] is None and data['is_enrolled'] is False
    db.scalars.assert_not_called()


def test_enrolled_student_can_read_archived_course_active_content(course_api):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.side_effect = [course('archived'), enrollment(), 1]
    db.scalars.side_effect = [rows([chapter()]), rows([point()])]
    response = client.get('/courses/course')
    assert response.status_code == 200
    assert response.json()['data']['chapters'][0]['knowledge_points'][0]['name'] == '入栈'
    assert 'active' in compiled(db.scalars.call_args).params.values()


@pytest.mark.parametrize('status', ['draft', 'archived'])
def test_private_course_not_visible_to_unenrolled_student(course_api, status):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.side_effect = [course(status), None]
    assert client.get('/courses/course').status_code == 404
    db.scalars.assert_not_called()


def test_student_join_repeat_withdraw_and_rejoin_keep_one_record(course_api):
    client, db, user = course_api
    user.role = 'student'
    item = course('published')
    db.scalar.side_effect = [item, None]
    response = client.put('/courses/course/enrollment')
    assert response.status_code == 200
    relation = db.add.call_args.args[0]
    assert response.json()['data']['student_id'] == user.id
    assert relation.enrolled_at == 1000
    relation.enrolled_at = relation.updated_at = 100
    db.scalar.side_effect = [item, relation, item, relation, item, relation]
    assert client.put('/courses/course/enrollment').status_code == 200
    assert relation.enrolled_at == relation.updated_at == 100
    assert client.delete('/courses/course/enrollment').status_code == 200
    assert relation.status == 'withdrawn' and relation.enrolled_at == 100
    assert client.put('/courses/course/enrollment').status_code == 200
    assert relation.status == 'active' and relation.enrolled_at == 1000
    db.add.assert_called_once()
    db.delete.assert_not_called()
    for call in db.scalar.call_args_list:
        assert 'FOR UPDATE' in str(compiled(call))


@pytest.mark.parametrize('status', ['draft', 'archived'])
def test_student_can_only_join_published_course(course_api, status):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.return_value = course(status)
    assert client.put('/courses/course/enrollment').status_code == 409
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_withdraw_archived_course_keeps_record_and_repeat_is_idempotent(course_api):
    client, db, user = course_api
    user.role = 'student'
    relation = enrollment()
    db.scalar.side_effect = [course('archived'), relation, course('archived'), relation]
    assert client.delete('/courses/course/enrollment').status_code == 200
    assert client.delete('/courses/course/enrollment').status_code == 200
    assert relation.status == 'withdrawn' and relation.enrolled_at == 100
    db.delete.assert_not_called()


def test_withdraw_without_record_returns_404(course_api):
    client, db, user = course_api
    user.role = 'student'
    db.scalar.side_effect = [course('published'), None]
    assert client.delete('/courses/course/enrollment').status_code == 404


@pytest.mark.parametrize(('method', 'path'), [('GET', '/courses/mine'), ('PUT', '/courses/course/enrollment'),
                                            ('DELETE', '/courses/course/enrollment')])
def test_teacher_cannot_use_student_only_routes(course_api, method, path):
    client, db, user = course_api
    assert client.request(method, path).status_code == 403
    db.scalar.assert_not_called()


@pytest.mark.parametrize('path', ['/courses?page=0', '/courses?page_size=101',
                                 '/teacher/courses?status=invalid', '/teacher/courses?keyword=' + 'a' * 101])
def test_list_query_validation(course_api, path):
    client, db, user = course_api
    assert client.get(path).status_code == 422
    db.scalar.assert_not_called()


@pytest.mark.parametrize('path', ['/courses', '/teacher/courses'])
def test_courses_require_login(course_api, path):
    client, db, user = course_api
    main.app.dependency_overrides.pop(current_user)
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(('stage', 'error', 'status'), [
    ('flush', IntegrityError('insert', {}, Exception(1062, 'private duplicate')), 409),
    ('flush', IntegrityError('insert', {}, Exception(1452, 'private FK')), 409),
    ('commit', SQLAlchemyError('private commit failure'), 503),
])
def test_write_errors_roll_back_without_reporting_success(course_api, stage, error, status):
    client, db, user = course_api
    getattr(db, stage).side_effect = error
    response = client.post('/teacher/courses', json={'name': '课程'})
    assert response.status_code == status
    assert 'private' not in response.text
    db.rollback.assert_called_once()


def test_read_database_error_returns_503(course_api):
    client, db, user = course_api
    db.scalar.side_effect = SQLAlchemyError('private connection failure')
    response = client.get('/teacher/courses')
    assert response.status_code == 503
    assert 'private' not in response.text
    db.rollback.assert_called_once()
