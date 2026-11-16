"""真实 PDF、DOCX 字节解析，上传、原件权限及存储失败回归。"""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from fastapi import HTTPException, UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy.exc import SQLAlchemyError

from app import config
from app.services import resource_files
from test_resources import resource_api  # 复用已覆盖课程、选课和所有权的数据库替身。


def docx_bytes(body=None, *, xml=None, extra=None):
    if xml is None:
        body = body or '<w:p><w:r><w:t>栈遵循后进先出原则。</w:t></w:r></w:p>'
        xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document '
               'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               f'<w:body>{body}</w:body></w:document>').encode()
    stream = BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        def write(name, value):
            entry = ZipInfo(name, date_time=(2025, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, value)
        write('[Content_Types].xml',
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        write('_rels/.rels',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
        write('word/document.xml', xml)
        for name, value in (extra or {}).items():
            write(name, value)
    return stream.getvalue()


def pdf_bytes(text='Stack is LIFO.', *, empty=False, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if not empty:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = DecodedStreamObject()
        content.set_data(f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(content)
    if encrypted:
        writer.encrypt('password')
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def upload(data, filename):
    return UploadFile(file=BytesIO(data), filename=filename, size=len(data))


@pytest.fixture
def upload_api(resource_api, monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'RESOURCE_UPLOAD_DIR', tmp_path / 'private_files')
    yield (*resource_api, tmp_path / 'private_files')


def post_upload(client, data=None, filename='资料.docx', fields=None):
    return client.post('/teacher/courses/course/resources/upload',
        data={'title': '上传资料', 'knowledge_point_ids': '["kp1"]', **(fields or {})},
        files={'file': (filename, data if data is not None else docx_bytes(), 'application/octet-stream')})


def test_docx_extraction_preserves_paragraph_and_table_order():
    data = docx_bytes('<w:p><w:r><w:t>开始</w:t><w:tab/><w:t>段落</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>左列</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:r><w:t>右列</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '<w:p><w:r><w:t>结束</w:t></w:r></w:p>')
    parsed = resource_files.parse_upload(upload(data, '资料.docx'))
    assert parsed.text == '开始\t段落\n左列\t右列\n结束'
    assert parsed.info == {'format': 'docx', 'text_characters': len(parsed.text)}


def test_real_pdf_extracts_text_and_reports_empty_pages():
    data = pdf_bytes()
    parsed = resource_files.parse_upload(upload(data, '课程.PDF'))
    assert parsed.text == 'Stack is LIFO.' and parsed.extension == '.pdf'
    assert parsed.info['page_count'] == 1 and parsed.info['empty_text_pages'] == []


@pytest.mark.parametrize(('name', 'data', 'status'), [
    ('old.doc', b'old word', 415), ('bad.exe', b'file', 415), ('empty.pdf', b'', 422),
    ('fake.pdf', b'not pdf', 422), ('broken.pdf', b'%PDF-1.4\nbroken', 422),
    ('fake.docx', b'not zip', 422), ('scan.pdf', pdf_bytes(empty=True), 422),
    ('locked.pdf', pdf_bytes(encrypted=True), 422), ('bad\nname.docx', docx_bytes(), 422),
])
def test_bad_files_are_rejected_without_saving(name, data, status):
    with pytest.raises(HTTPException) as failure:
        resource_files.parse_upload(upload(data, name))
    assert failure.value.status_code == status


def test_docx_macro_and_xml_entities_rejected():
    for data, expected in [
        (docx_bytes(extra={'word/vbaProject.bin': b'macro'}), 415),
        (docx_bytes(xml=b'<!DOCTYPE doc [<!ENTITY test "value">]><doc/>'), 422),
        (docx_bytes(xml='<!DOCTYPE doc [<!ENTITY test "value">]><doc/>'.encode('utf-16')), 422),
    ]:
        with pytest.raises(HTTPException) as failure:
            resource_files.parse_upload(upload(data, 'bad.docx'))
        assert failure.value.status_code == expected


def test_upload_bounds_before_and_after_extraction(monkeypatch):
    monkeypatch.setattr(resource_files, 'MAX_FILE_BYTES', 32)
    with pytest.raises(HTTPException) as failure:
        resource_files.parse_upload(upload(b'x' * 33, 'big.pdf'))
    assert failure.value.status_code == 413
    monkeypatch.setattr(resource_files, 'MAX_FILE_BYTES', 10 * 1024 * 1024)
    monkeypatch.setattr(resource_files, 'MAX_TEXT_CHARACTERS', 5)
    with pytest.raises(HTTPException) as failure:
        resource_files.parse_upload(upload(docx_bytes(), 'long.docx'))
    assert failure.value.status_code == 413


def test_docx_zip_expansion_and_pdf_pages_are_bounded(monkeypatch):
    monkeypatch.setattr(resource_files, 'MAX_DOCX_UNPACKED_BYTES', 10)
    with pytest.raises(HTTPException) as failure:
        resource_files.parse_upload(upload(docx_bytes(), 'big.docx'))
    assert failure.value.status_code == 413
    monkeypatch.setattr(resource_files, 'MAX_PDF_PAGES', 0)
    with pytest.raises(HTTPException) as failure:
        resource_files.parse_upload(upload(pdf_bytes(), 'big.pdf'))
    assert failure.value.status_code == 413


@pytest.mark.parametrize(('name', 'content', 'kind'), [('资料.docx', docx_bytes(), 'docx'), ('资料.pdf', pdf_bytes(), 'pdf')], ids=['docx', 'pdf'])
def test_upload_saves_text_private_original_and_authorized_download(upload_api, name, content, kind):
    client, db, user, state, directory = upload_api
    response = post_upload(client, content, name)
    assert response.status_code == 201, response.text
    data = response.json()['data']
    original = data['original_file']
    assert original['original_filename'] == name and original['resource_version'] == 1
    assert original['size_bytes'] == len(content) and original['sha256'] == sha256(content).hexdigest()
    assert original['extraction_info']['format'] == kind and data['text']
    assert 'storage_key' not in response.text and str(directory) not in response.text
    stored = list(directory.iterdir())
    assert len(stored) == 1 and stored[0].read_bytes() == content and stored[0].name != name
    identity = data['id']
    detail = client.get(f'/teacher/resources/{identity}').json()['data']
    assert detail['original_file'] == original
    download = client.get(f'/teacher/resources/{identity}/file')
    assert download.status_code == 200 and download.content == content
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert download.headers['cache-control'] == 'private, no-store'
    assert 'attachment;' in download.headers['content-disposition']
    user.role = 'student'
    assert client.get(f'/resources/{identity}/file').content == content
    assert client.get('/courses/course/resources').json()['data']['items'][0]['original_file'] == original
    state['enrollment'] = None
    assert client.get(f'/resources/{identity}/file').status_code == 404


@pytest.mark.parametrize('fields', [
    {'knowledge_point_ids': '[]'}, {'knowledge_point_ids': '["kp1","kp1"]'},
    {'knowledge_point_ids': 'null'}, {'title': ' '}, {'source': ''}, {'version': '5'},
    {'knowledge_point_ids': '["kp1"'}, {'knowledge_point_ids': "['kp1']"},
    {'knowledge_point_ids': '{"id":"kp1"}'}, {'knowledge_point_ids': '[1]'},
    {'knowledge_point_ids': 'kp1,'}, {'knowledge_point_ids': 'kp1,kp1'},
    {'knowledge_point_ids': ['kp1', 'kp1']}, {'knowledge_point_ids': ['kp1', ' ']},
    {'knowledge_point_ids': ','.join('kp' + str(i) for i in range(51))},
])
def test_upload_rejects_bad_form_fields(upload_api, fields):
    client, db, user, state, directory = upload_api
    assert post_upload(client, fields=fields).status_code == 422
    assert not directory.exists()
    db.add.assert_not_called()


@pytest.mark.parametrize(('value', 'expected'), [
    ('kp1', ['kp1']),  # 用户贴出的 curl 实际提交值，没有方括号。
    ('["kp1"]', ['kp1']),
    ('["kp1", "kp2"]', ['kp1', 'kp2']),
    (['kp1', 'kp2'], ['kp1', 'kp2']),  # 原生 multipart 重复同名字段。
    ('kp1,kp2', ['kp1', 'kp2']),  # Swagger 表单数组的逗号编码。
    (' kp1, kp2 ', ['kp1', 'kp2']),
])
def test_upload_accepts_form_arrays_and_legacy_json(upload_api, value, expected):
    client, db, user, state, directory = upload_api
    response = post_upload(client, fields={'knowledge_point_ids': value})
    assert response.status_code == 201, response.text
    assert response.json()['data']['knowledge_point_ids'] == expected
    assert len(list(directory.iterdir())) == 1


def test_upload_form_array_still_checks_knowledge_point_course(upload_api):
    client, db, user, state, directory = upload_api
    response = post_upload(client, fields={'knowledge_point_ids': ['kp1', 'other']})
    assert response.status_code == 409
    db.add.assert_not_called()
    assert not directory.exists()


@pytest.mark.parametrize('field', ['title', 'source'])
def test_scalar_upload_fields_still_reject_duplicates(upload_api, field):
    client, db, user, state, directory = upload_api
    response = post_upload(client, fields={field: ['one', 'two']})
    assert response.status_code == 422
    db.add.assert_not_called()


@pytest.mark.parametrize('condition', ['student', 'other_teacher', 'archived', 'other_point'])
def test_upload_permission_checked_before_parsing(upload_api, condition, monkeypatch):
    client, db, user, state, directory = upload_api
    fields, expected = {}, 409
    if condition == 'student':
        user.role, expected = 'student', 403
    elif condition == 'other_teacher':
        state['course'].teacher_id, expected = 8, 404
    elif condition == 'archived':
        state['course'].status = 'archived'
    else:
        fields['knowledge_point_ids'] = '["other"]'
    parser = Mock()
    monkeypatch.setattr(resource_files, 'parse_upload', parser)
    assert post_upload(client, fields=fields).status_code == expected
    parser.assert_not_called()
    assert not directory.exists()


def test_text_edit_and_soft_delete_preserve_original_version(upload_api):
    client, db, user, state, directory = upload_api
    data = post_upload(client).json()['data']
    identity = data['id']
    updated = client.patch(f'/teacher/resources/{identity}', json={'expected_version': 1, 'text': '人工修改后的正文'})
    assert updated.status_code == 200 and updated.json()['data']['version'] == 2
    assert updated.json()['data']['original_file']['resource_version'] == 1
    assert client.delete(f'/teacher/resources/{identity}').status_code == 200
    assert client.get(f'/teacher/resources/{identity}/file').status_code == 200
    user.role = 'student'
    assert client.get(f'/resources/{identity}/file').status_code == 404
    assert len(list(directory.iterdir())) == 1


def test_failed_precommit_removes_original_and_returns_503(upload_api):
    client, db, user, state, directory = upload_api
    db.flush.side_effect = SQLAlchemyError('private failure')
    response = post_upload(client)
    assert response.status_code == 503 and 'private' not in response.text
    assert list(directory.iterdir()) == []


def test_uncertain_commit_keeps_original_for_reconciliation(upload_api):
    client, db, user, state, directory = upload_api
    db.commit.side_effect = SQLAlchemyError('commit connection lost')
    response = post_upload(client)
    assert response.status_code == 503
    assert len(list(directory.iterdir())) == 1


def test_missing_original_or_invalid_storage_key_returns_sanitized_error(upload_api):
    client, db, user, state, directory = upload_api
    identity = post_upload(client).json()['data']['id']
    file = state['files'][0]
    original = file.storage_key
    file.storage_key = '../../outside.pdf'
    assert client.get(f'/teacher/resources/{identity}/file').status_code == 503
    file.storage_key = original
    next(directory.iterdir()).unlink()
    assert client.get(f'/teacher/resources/{identity}/file').status_code == 503


def test_plain_text_material_has_no_original_file(upload_api):
    client, db, user, state, directory = upload_api
    assert client.get('/teacher/resources/resource/file').status_code == 404
    assert client.get('/teacher/resources/resource').json()['data']['original_file'] is None
