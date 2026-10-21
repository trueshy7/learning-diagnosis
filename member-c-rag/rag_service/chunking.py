import hashlib
import re


def normalize_text(text: str) -> str:
    """保留段落；索引内的位置以此标准化文本为准。"""
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def split_text(document_id: str, text: str, size: int, overlap: int) -> list[dict]:
    """使用固定字符窗口；偏移为从 0 开始、左闭右开的 Unicode 字符位置。"""
    text = normalize_text(text)
    if not text:
        raise ValueError("资料内容不能为空")
    if size <= overlap or overlap < 0:
        raise ValueError("分段大小必须大于重叠长度，且重叠长度非负")
    chunks = []
    for start in range(0, len(text), size - overlap):
        end = min(start + size, len(text))
        value = text[start:end]
        digest = hashlib.sha256(f"{document_id}:{start}:{end}:{value}".encode()).hexdigest()[:20]
        chunks.append({"chunk_id": f"chunk-{digest}", "text": value, "start": start, "end": end})
        if end == len(text):
            break
    return chunks


def query_terms(query: str) -> set[str]:
    """中文二元字组和英文单词；仅供关键词演示，不使用向量或大模型。"""
    result = set()
    for segment in re.findall(r"[\u3400-\u9fff]+|[a-zA-Z0-9_]+", query.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", segment):
            result.update(segment[i:i + 2] for i in range(max(1, len(segment) - 1)))
        else:
            result.add(segment)
    return result
