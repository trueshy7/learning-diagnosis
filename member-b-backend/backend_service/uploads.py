"""把教师提交的文本或 PDF 转换为 C 服务可索引的纯文本。"""
import base64
import binascii
from io import BytesIO

from fastapi import HTTPException

from .schemas import ResourceFileIn


def extract_upload(body: ResourceFileIn) -> dict:
    filename = body.filename.replace('\\', '/').split('/')[-1]
    suffix = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if suffix not in {'txt', 'md', 'pdf'}:
        raise HTTPException(422, '仅支持 .txt、.md、.pdf 文件')
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, '文件内容不是有效的 Base64') from None
    if not raw or len(raw) > 2_000_000:
        raise HTTPException(422, '文件大小须为 1 字节至 2 MB')
    if suffix == 'pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(raw))
            if len(reader.pages) > 100:
                raise HTTPException(422, 'PDF 页数不能超过 100 页')
            text = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, 'PDF 无法解析') from None
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeError:
            raise HTTPException(422, '文本文件须使用 UTF-8 编码') from None
    text = text.strip()
    if not text or len(text) > 200_000:
        raise HTTPException(422, '文件需包含可提取的正文，长度不超过 20 万字符')
    source = f'{body.source}/{filename}'
    if len(source) > 1000:
        raise HTTPException(422, '资料来源和文件名合计不能超过 1000 字符')
    return {'resource_id': body.resource_id, 'document_id': body.document_id,
            'course_id': body.course_id, 'title': body.title, 'text': text,
            'knowledge_point_ids': body.knowledge_point_ids,
            'source': source}
