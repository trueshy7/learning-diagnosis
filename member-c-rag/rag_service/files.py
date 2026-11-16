"""本地文件入库。B 当前同步直接使用已解析 text。"""
import hashlib
import json
import shutil
import time
from pathlib import Path

from .catalog import b_content_hash, stable_document_id
from .contracts import ResourceRecord
from .parsing import ParseError, parse_file


def ingest_file(index, resource_meta: dict, file_path: str | Path):
    audit_root = index.path.parent / "imports"
    audit_root.mkdir(parents=True, exist_ok=True)
    path = Path(file_path)
    log = {"resource_id": resource_meta.get("resource_id"), "time": int(time.time()), "filename": path.name}
    try:
        parsed = parse_file(path)
        raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        destination = audit_root / (raw_hash + path.suffix.lower())
        if not destination.exists():
            shutil.copyfile(path, destination)
        version = resource_meta.get("resource_version", 1)
        value = {key: resource_meta[key] for key in ("resource_id", "course_id", "title", "source", "knowledge_point_ids")}
        value |= {"text": parsed["text"], "pages": parsed["pages"], "resource_version": version,
                  "document_id": resource_meta.get("document_id") or stable_document_id(value["resource_id"], version),
                  "origin": "local_file", "license": resource_meta.get("license", "未登记 由资料提供方核实")}
        value["content_hash"] = b_content_hash(value)
        result = index.ingest_record(ResourceRecord(**value))
        log |= {"status": "ready", "raw_file_hash": raw_hash, "chunks": result["chunks"]}
        return result
    except Exception as exc:
        log |= {"status": "failed", "error_code": exc.code if isinstance(exc, ParseError) else type(exc).__name__}
        raise
    finally:
        with (audit_root / "parse_log.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(log, ensure_ascii=False) + "\n")
