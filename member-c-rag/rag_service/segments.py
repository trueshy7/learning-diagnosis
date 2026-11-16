"""在原始正文上切片；不修改 B 用于计算摘要的字符。"""
import hashlib
import re


def split_document(document_id: str, text: str, size: int, overlap: int, pages: list[dict]) -> list[dict]:
    if not text.strip() or size <= overlap or overlap < 0:
        raise ValueError("正文为空或切分配置无效")
    boundaries = {len(text)}
    boundaries.update(match.end() for match in re.finditer(r"\n\s*\n|\n(?=#{1,6} )", text))
    boundaries.update(page["end"] for page in pages)
    headings = [(m.start(), m.group(1).strip()) for m in re.finditer(r"^#{1,6}\s+(.+)$", text, re.M)]
    chunks, start = [], 0
    while start < len(text):
        limit = min(start + size, len(text))
        options = [b for b in boundaries if start + size // 2 <= b <= limit]
        end = max(options) if options else limit
        value = text[start:end]
        if value.strip():
            digest = hashlib.sha256(f"{document_id}:{start}:{end}:{value}".encode()).hexdigest()[:24]
            chapter = next((title for offset, title in reversed(headings) if offset <= start), "正文")
            location = {"kind": "text", "start": start, "end": end, "chapter": chapter}
            numbers = [p["page"] for p in pages if p["start"] < end and p["end"] > start]
            if numbers:
                location |= {"kind": "pdf", "pages": numbers}
            chunks.append({"chunk_id": "chunk-" + digest, "text": value, "start": start, "end": end,
                           "location": location, "content_hash": hashlib.sha256(value.encode()).hexdigest()})
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
