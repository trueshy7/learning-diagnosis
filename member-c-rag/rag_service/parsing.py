"""受控本地文件导入。不执行内容、不访问来源 URL、不提供 OCR。"""
import re
from collections import Counter
from pathlib import Path


class ParseError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "\n".join(re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_file(file_path: str | Path, max_bytes: int = 20 * 1024 * 1024) -> dict:
    path = Path(file_path)
    if not path.is_file():
        raise ParseError("file_missing", "文件不存在")
    if path.stat().st_size == 0:
        raise ParseError("empty_file", "文件为空")
    if path.stat().st_size > max_bytes:
        raise ParseError("file_too_large", "文件超过 20 MiB")
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        raw = path.read_bytes()
        try:
            value = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                value = raw.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ParseError("invalid_encoding", "文本必须为 UTF-8 或 GB18030") from exc
        if "\x00" in value or value.count("\ufffd") > max(3, len(value) // 100):
            raise ParseError("invalid_text", "文本含异常控制字符或大量乱码")
        text = clean_text(value)
        pages = []
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ParseError("encrypted_pdf", "加密 PDF 请先提供合法可读取文本版")
            if len(reader.pages) > 500:
                raise ParseError("too_many_pages", "PDF 最多 500 页")
            raw_pages = [clean_text(page.extract_text() or "") for page in reader.pages]
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError("pdf_parse_failed", "PDF 解析失败 请检查文件格式") from exc
        # 仅移除多数页面重复出现的第一/末行，避免把正文中重复定义当页眉。
        edges = Counter()
        if len(raw_pages) >= 3:
            for value in raw_pages:
                lines = value.splitlines()
                edges.update(set(lines[:1] + lines[-1:]))
        repeated = {line for line, count in edges.items() if count >= max(3, len(raw_pages) * .6)}
        text, pages = "", []
        for number, value in enumerate(raw_pages, 1):
            lines = value.splitlines()
            if lines and lines[0] in repeated:
                lines = lines[1:]
            if lines and lines[-1] in repeated:
                lines = lines[:-1]
            value = "\n".join(lines).strip()
            if not value:
                continue
            if text:
                text += "\n\n"
            start = len(text)
            text += value
            pages.append({"page": number, "start": start, "end": len(text)})
        if not text:
            raise ParseError("no_extractable_text", "PDF 无可提取文字 可能为扫描件 本模块不做 OCR")
    else:
        raise ParseError("unsupported_type", "仅支持 TXT Markdown 和文本型 PDF")
    if not text:
        raise ParseError("empty_text", "未提取到有效正文")
    if len(text) > 200_000:
        raise ParseError("text_too_long", "提取正文超过 200000 字符")
    return {"text": text, "pages": pages, "filename": path.name, "format": suffix.lstrip(".")}
