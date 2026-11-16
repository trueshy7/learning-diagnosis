"""PDF/DOCX 正文提取、私有原件保存及鉴权下载。"""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import logging
import os
from pathlib import Path
import re
import time
import uuid
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from sqlalchemy import select

from .. import config
from ..models import ResourceFile
from ..resource_schemas import ResourceCreateIn
from . import resources

logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARACTERS = 200000
MAX_PDF_PAGES = 300
MAX_PDF_STREAM_BYTES = 20 * 1024 * 1024
MAX_DOCX_UNPACKED_BYTES = 30 * 1024 * 1024
MAX_DOCX_XML_BYTES = 8 * 1024 * 1024
MAX_DOCX_ENTRIES = 2000
MEDIA_TYPES = {'.pdf': 'application/pdf',
               '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


@dataclass(frozen=True)
class ParsedFile:
    filename: str
    extension: str
    content: bytes
    text: str
    info: dict


def _joined(parts):
    collected, count = [], 0
    for part in parts:
        part = part.strip()
        if part:
            count += len(part) + (1 if collected else 0)
            if count > MAX_TEXT_CHARACTERS:
                raise HTTPException(413, '提取正文超过 200000 字符，请拆分资料后上传')
            collected.append(part)
    text = '\n'.join(collected)
    if not text:
        raise HTTPException(422, '未提取到可读文字；扫描件或纯图片文件需先进行 OCR')
    return text


def _pdf(content):
    if not content.lstrip(b' \r\n\t').startswith(b'%PDF-'):
        raise HTTPException(422, '文件内容不是有效的 PDF')
    try:
        from pypdf import PdfReader, apply_configuration
        from pypdf.errors import LimitReachedError
    except ImportError as exc:
        raise HTTPException(503, 'PDF 解析依赖未安装，请安装 requirements.txt 后重启') from exc
    try:
        with apply_configuration(maximum_declared_stream_length=MAX_PDF_STREAM_BYTES,
                                 zlib_maximum_output_length=MAX_PDF_STREAM_BYTES,
                                 lzw_maximum_output_length=MAX_PDF_STREAM_BYTES,
                                 run_length_maximum_output_length=MAX_PDF_STREAM_BYTES,
                                 array_based_stream_maximum_output_length=MAX_PDF_STREAM_BYTES,
                                 disable_legacy_handling=True):
            return _pdf_pages(PdfReader(BytesIO(content), strict=False))
    except LimitReachedError as exc:
        raise HTTPException(413, 'PDF 内部结构或解压内容过大，请拆分后上传') from exc


def _pdf_pages(reader):
    if reader.is_encrypted:
        raise HTTPException(422, '暂不支持加密 PDF，请解除密码保护后上传')
    pages = len(reader.pages)
    if pages > MAX_PDF_PAGES:
        raise HTTPException(413, 'PDF 超过 300 页，请拆分后上传')
    empty = []

    def parts():
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ''
            if not text.strip():
                empty.append(index)
            yield text

    text = _joined(parts())
    return text, {'format': 'pdf', 'page_count': pages, 'empty_text_pages': empty,
                  'text_characters': len(text)}


def _paragraph(element):
    parts = []

    def walk(node):
        for child in node:
            if child.tag == W + 'p':
                continue
            if child.tag == W + 't':
                parts.append(child.text or '')
            elif child.tag == W + 'tab':
                parts.append('\t')
            elif child.tag in (W + 'br', W + 'cr'):
                parts.append('\n')
            else:
                walk(child)
    walk(element)
    return ''.join(parts)


def _word_blocks(container):
    for child in container:
        if child.tag == W + 'p':
            yield _paragraph(child)
        elif child.tag == W + 'tbl':
            for row in child.findall(W + 'tr'):
                yield '\t'.join('\n'.join(_word_blocks(cell)) for cell in row.findall(W + 'tc'))
        else:
            yield from _word_blocks(child)


def _docx(content):
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if (len(entries) > MAX_DOCX_ENTRIES
                    or sum(item.file_size for item in entries) > MAX_DOCX_UNPACKED_BYTES):
                raise HTTPException(413, 'Word 解压后内容过大，请拆分文件后上传')
            names = {item.filename for item in entries}
            if 'word/document.xml' not in names or '[Content_Types].xml' not in names:
                raise HTTPException(422, '文件不是有效的 DOCX Word 文档')
            if any(item.flag_bits & 1 for item in entries):
                raise HTTPException(422, '暂不支持加密 Word 文档')
            if any(name.lower().endswith('vbaproject.bin') for name in names):
                raise HTTPException(415, '暂不支持包含宏的 Word 文档')
            if archive.getinfo('word/document.xml').file_size > MAX_DOCX_XML_BYTES:
                raise HTTPException(413, 'Word 正文结构过大，请拆分后上传')
            xml = archive.read('word/document.xml')
    except BadZipFile as exc:
        raise HTTPException(422, '文件不是有效的 DOCX Word 文档') from exc
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', xml, re.IGNORECASE):
        raise HTTPException(422, 'Word 正文包含不支持的 XML 声明')
    class SafeTreeBuilder(ET.TreeBuilder):
        def doctype(self, name, pubid, system):
            raise HTTPException(422, 'Word 正文包含不支持的 XML 声明')

    document = ET.fromstring(xml, parser=ET.XMLParser(target=SafeTreeBuilder()))
    body = document.find(W + 'body')
    if body is None:
        raise HTTPException(422, 'Word 文档缺少正文')
    text = _joined(_word_blocks(body))
    return text, {'format': 'docx', 'text_characters': len(text)}


def parse_upload(upload):
    filename = (upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not filename or len(filename) > 255 or any(not char.isprintable() for char in filename):
        raise HTTPException(422, '文件名不能为空、包含控制字符或超过 255 字符')
    extension = Path(filename).suffix.lower()
    if extension not in MEDIA_TYPES:
        raise HTTPException(415, '仅支持 PDF、DOCX；旧版 DOC 请先另存为 DOCX')
    if upload.size is not None and upload.size > MAX_FILE_BYTES:
        raise HTTPException(413, '文件不能超过 10 MiB')
    content = upload.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, '文件不能超过 10 MiB')
    if not content:
        raise HTTPException(422, '不能上传空文件')
    try:
        text, info = _pdf(content) if extension == '.pdf' else _docx(content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, '文件损坏或无法提取正文，请检查文件后重试') from exc
    return ParsedFile(filename, extension, content, text, info)


def _root():
    return Path(config.RESOURCE_UPLOAD_DIR).resolve()


def _remove(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning('Could not remove uncommitted resource file %s', path.name)


def _store(key, content):
    root = _root()
    path = root / key
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        # 随机键碰撞时不能删除原本已存在的文件。
        if not isinstance(exc, FileExistsError):
            _remove(path)
        raise HTTPException(503, '原文件保存失败，请检查资料存储目录') from exc
    return path


@resources.operation
def create_uploaded_resource(db, teacher, course_id, metadata, upload):
    teacher_id = teacher.id
    # 先鉴权，再解析文件；解析期间不持有数据库事务或课程写锁。
    course = resources._course(db, course_id, teacher_id=teacher_id)
    resources._editable(course)
    resources._validate_points(db, course_id, metadata.knowledge_point_ids, lock=False)
    db.rollback()
    parsed = parse_upload(upload)
    body = ResourceCreateIn(**metadata.model_dump(), text=parsed.text)
    identity = uuid.uuid4().hex
    key = identity + parsed.extension
    path = _store(key, parsed.content)
    committing = False
    try:
        # 解析结束后重新锁课程、校验标签，防止期间课程归档或归属变化。
        resource = resources._create_record(db, teacher_id, course_id, body)
        file = ResourceFile(id=identity, resource_id=resource.id, resource_version=resource.version,
                            original_filename=parsed.filename, media_type=MEDIA_TYPES[parsed.extension],
                            size_bytes=len(parsed.content), sha256=sha256(parsed.content).hexdigest(),
                            storage_key=key, extraction_info=parsed.info, created_at=int(time.time()))
        db.add(file)
        db.flush()
        data = resources._summary(resource, body.knowledge_point_ids) | {
            'text': resource.text, 'original_file': resources._file_data(file),
        }
        committing = True
        db.commit()
        return data
    except Exception:
        # commit 异常可能是“已提交但响应丢失”；此时保留原件供核对，避免破坏已提交引用。
        if not committing:
            _remove(path)
        raise


def _download(db, resource_id):
    file = db.scalar(select(ResourceFile).where(ResourceFile.resource_id == resource_id))
    if file is None:
        raise HTTPException(404, '该资料没有上传的原文件')
    if not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|docx)', file.storage_key):
        raise HTTPException(503, '原文件存储记录异常')
    root = _root()
    path = (root / file.storage_key).resolve()
    if path.parent != root:
        raise HTTPException(503, '原文件存储记录异常')
    try:
        if not path.is_file() or path.stat().st_size != file.size_bytes:
            raise HTTPException(503, '原文件缺失或大小不一致，请联系管理员核对存储')
    except OSError as exc:
        raise HTTPException(503, '原文件暂不可用，请联系管理员核对存储') from exc
    if file.media_type not in MEDIA_TYPES.values():
        raise HTTPException(503, '原文件类型记录异常')
    return path, file.media_type, file.original_filename


@resources.operation
def teacher_download(db, teacher, resource_id):
    resources._teacher_resource(db, teacher, resource_id)
    return _download(db, resource_id)


@resources.operation
def student_download(db, student, resource_id):
    resources._student_resource(db, student, resource_id)
    return _download(db, resource_id)
