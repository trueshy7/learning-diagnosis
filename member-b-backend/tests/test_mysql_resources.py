"""TEST_MYSQL_URL 显式启用的独立 MySQL 资料集成测试，不写入业务库。"""

import os
from pathlib import Path
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, main
from app.database import Base, get_db
from app.models import (Course, CourseChapter, CourseEnrollment, CourseResource,
                        KnowledgePoint, ResourceFile, ResourceKnowledgePoint, User)
from app.security import hash_password

pytestmark = pytest.mark.skipif(not os.getenv('TEST_MYSQL_URL'), reason='未配置独立 MySQL 集成测试连接')


@pytest.fixture
def mysql_resources(monkeypatch, tmp_path):
    url = make_url(os.environ['TEST_MYSQL_URL'])
    if url.get_backend_name() != 'mysql':
        pytest.fail('TEST_MYSQL_URL 必须使用 MySQL')
    name = 'ld_resource_test_' + uuid.uuid4().hex
    admin = create_engine(url.set(database=None), connect_args={'connect_timeout': 5})
    engine, created = None, False
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        created = True
        engine = create_engine(url.set(database=name), connect_args={'connect_timeout': 5})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            password_hash = hash_password('Example123!')
            db.add_all([User(id=1, username='student01', email='student@example.com', role='student', password_hash=password_hash),
                        User(id=2, username='teacher01', email='teacher@example.com', role='teacher', password_hash=password_hash),
                        User(id=3, username='teacher02', email='otherteacher@example.com', role='teacher', password_hash=password_hash),
                        User(id=4, username='student02', email='otherstudent@example.com', role='student', password_hash=password_hash)])
            db.flush()
            db.add_all([Course(id='course', name='本课程', teacher_id=2, status='published'),
                        Course(id='other-course', name='其他课程', teacher_id=3, status='published')])
            db.flush()
            db.add_all([CourseChapter(id='chapter', course_id='course', name='本章节'),
                        CourseChapter(id='other-chapter', course_id='other-course', name='其他章节')])
            db.flush()
            db.add_all([KnowledgePoint(id='kp1', course_id='course', chapter_id='chapter', name='知识点一'),
                        KnowledgePoint(id='kp2', course_id='course', chapter_id='chapter', name='知识点二'),
                        KnowledgePoint(id='other-point', course_id='other-course', chapter_id='other-chapter', name='其他知识点')])
            db.add(CourseEnrollment(course_id='course', student_id=1))
            db.commit()
        monkeypatch.setattr(main, 'engine', engine)
        monkeypatch.setattr(config, 'RESOURCE_UPLOAD_DIR', tmp_path / 'originals')

        def database():
            with Session(engine, autoflush=False) as db:
                yield db

        main.app.dependency_overrides[get_db] = database
        with TestClient(main.app) as client:
            def login(username):
                response = client.post('/user/login', json={'username': username, 'password': 'Example123!'})
                assert response.status_code == 200
                return {'Authorization': 'Bearer ' + response.json()['data']['access_token']}

            yield client, {name: login(name) for name in ('teacher01', 'teacher02', 'student01', 'student02')}, engine
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP DATABASE `{name}`')
        admin.dispose()


def create_material(client, teacher, **changes):
    response = client.post('/teacher/courses/course/resources', headers=teacher, json={
        'title': '栈资料', 'text': '栈遵循后进先出原则。', 'knowledge_point_ids': ['kp1', 'kp2'], **changes,
    })
    assert response.status_code == 201, response.text[:500]
    return response.json()['data']


def test_mysql_resource_crud_long_text_permissions_and_soft_deletion(mysql_resources):
    client, users, engine = mysql_resources
    material = create_material(client, users['teacher01'], text='长' * 40000)
    identity = material['id']
    assert len(material['text'].encode('utf-8')) > 65535
    assert material['knowledge_point_ids'] == ['kp1', 'kp2']
    response = client.get(f'/resources/{identity}', headers=users['student01'])
    assert response.status_code == 200 and response.json()['data']['text'] == '长' * 40000
    assert client.get(f'/resources/{identity}', headers=users['student02']).status_code == 404
    assert client.get(f'/teacher/resources/{identity}', headers=users['teacher02']).status_code == 404
    listing = client.get('/courses/course/resources?knowledge_point_id=kp1', headers=users['student01']).json()['data']
    assert listing['total'] == 1 and 'text' not in listing['items'][0]
    response = client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'], json={
        'expected_version': 1, 'text': '新版正文', 'knowledge_point_ids': ['kp2'],
    })
    assert response.status_code == 200 and response.json()['data']['version'] == 2
    assert response.json()['data']['knowledge_point_ids'] == ['kp2']
    assert client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'],
                        json={'expected_version': 1, 'title': '旧版本覆盖'}).status_code == 409
    assert client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'], json={
        'expected_version': 2, 'title': '不可部分保存', 'knowledge_point_ids': ['other-point'],
    }).status_code == 409
    detail = client.get(f'/teacher/resources/{identity}', headers=users['teacher01']).json()['data']
    assert detail['title'] == '栈资料' and detail['version'] == 2
    same = client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'],
                        json={'expected_version': 2, 'text': '新版正文'})
    assert same.json()['data']['version'] == 2
    deleted = client.delete(f'/teacher/resources/{identity}', headers=users['teacher01'])
    assert deleted.status_code == 200 and deleted.json()['data']['version'] == 3
    assert client.delete(f'/teacher/resources/{identity}', headers=users['teacher01']).json()['data'] == deleted.json()['data']
    assert client.get(f'/resources/{identity}', headers=users['student01']).status_code == 404
    assert client.get('/courses/course/resources', headers=users['student01']).json()['data']['total'] == 0
    assert client.get('/teacher/courses/course/resources?status=deleted', headers=users['teacher01']).json()['data']['total'] == 1
    with Session(engine) as db:
        stored = db.get(CourseResource, identity)
        assert stored.status == 'deleted' and stored.text == '新版正文'
        assert db.scalar(select(func.count()).select_from(ResourceKnowledgePoint)) == 1


def test_mysql_archived_material_stays_readable_and_withdrawal_revokes_access(mysql_resources):
    client, users, engine = mysql_resources
    material = create_material(client, users['teacher01'])
    identity = material['id']
    assert client.patch('/teacher/courses/course', headers=users['teacher01'], json={'status': 'archived'}).status_code == 200
    assert client.get(f'/resources/{identity}', headers=users['student01']).status_code == 200
    assert client.get('/courses/course/resources', headers=users['student01']).status_code == 200
    assert client.patch(f'/teacher/resources/{identity}', headers=users['teacher01'],
                        json={'expected_version': 1, 'title': '新标题'}).status_code == 409
    assert client.delete(f'/teacher/resources/{identity}', headers=users['teacher01']).status_code == 409
    assert client.delete('/courses/course/enrollment', headers=users['student01']).status_code == 200
    assert client.get(f'/resources/{identity}', headers=users['student01']).status_code == 404


def test_mysql_resource_composite_foreign_keys_prevent_cross_course_links(mysql_resources):
    client, users, engine = mysql_resources
    material = create_material(client, users['teacher01'])
    for course_id in ('course', 'other-course'):
        with Session(engine) as db:
            db.add(ResourceKnowledgePoint(resource_id=material['id'], course_id=course_id, knowledge_point_id='other-point'))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ResourceKnowledgePoint)) == 2


def test_mysql_resource_manual_schema_script_is_repeatable_and_usable(mysql_resources):
    client, users, engine = mysql_resources
    source = (Path(__file__).resolve().parents[1] / 'sql/create_course_resource_tables.sql').read_text()
    statements = '\n'.join(line for line in source.splitlines() if not line.strip().startswith('--')).split(';')
    # 只删除本测试新建的随机库中的空资料表，之后用交付 SQL 实际重建。
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('DROP TABLE resource_files')
        connection.exec_driver_sql('DROP TABLE resource_knowledge_points')
        connection.exec_driver_sql('DROP TABLE course_resources')
        for _ in range(2):
            for statement in statements:
                if statement.strip() and not statement.strip().upper().startswith('USE '):
                    connection.exec_driver_sql(statement)
    database = inspect(engine)
    columns = {column['name']: column for column in database.get_columns('course_resources')}
    assert columns['text']['type'].__class__.__name__ == 'MEDIUMTEXT'
    assert len(database.get_foreign_keys('resource_knowledge_points')) == 2
    assert {index['name'] for index in database.get_indexes('resource_knowledge_points')} >= {
        'ix_resource_points_course_resource', 'ix_resource_points_course_point'}
    created = create_material(client, users['teacher01'])
    assert client.get(f"/resources/{created['id']}", headers=users['student01']).status_code == 200


@pytest.mark.parametrize('kind', ['docx', 'pdf'])
def test_mysql_upload_original_text_and_download_permissions(mysql_resources, kind):
    from test_resource_files import docx_bytes, pdf_bytes
    client, users, engine = mysql_resources
    content = docx_bytes() if kind == 'docx' else pdf_bytes()
    response = client.post('/teacher/courses/course/resources/upload', headers=users['teacher01'],
                           data={'title': '上传测试', 'knowledge_point_ids': '["kp1"]'},
                           files={'file': ('资料.' + kind, content, 'application/octet-stream')})
    assert response.status_code == 201, response.text
    identity = response.json()['data']['id']
    assert response.json()['data']['text']
    with Session(engine) as db:
        original = db.scalar(select(ResourceFile).where(ResourceFile.resource_id == identity))
        assert original.resource_version == 1 and original.size_bytes == len(content)
        assert (config.RESOURCE_UPLOAD_DIR / original.storage_key).read_bytes() == content
    download = client.get(f'/resources/{identity}/file', headers=users['student01'])
    assert download.status_code == 200 and download.content == content
    assert client.get(f'/resources/{identity}/file', headers=users['student02']).status_code == 404
    assert client.get(f'/teacher/resources/{identity}/file', headers=users['teacher02']).status_code == 404
    assert client.delete(f'/teacher/resources/{identity}', headers=users['teacher01']).status_code == 200
    assert client.get(f'/resources/{identity}/file', headers=users['student01']).status_code == 404
    assert client.get(f'/teacher/resources/{identity}/file', headers=users['teacher01']).content == content
