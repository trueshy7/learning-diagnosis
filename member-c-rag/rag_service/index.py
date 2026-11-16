import json
import os
from pathlib import Path
import threading

from .chunking import normalize_text, query_terms, split_text
from .schemas import IngestRequest, RetrieveRequest


MODE = "keyword_demo"
INDEX_VERSION = "demo-1"  # 索引格式版本，不是每次修改的流水号。


class LocalIndex:
    """单进程 JSON 索引。线程安全和原子写入不等同于多进程数据库事务。"""

    def __init__(self, path: Path, chunk_size: int = 360, chunk_overlap: int = 60):
        self.path = path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.lock = threading.RLock()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"index_version": INDEX_VERSION, "documents": {}}
        with self.path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if data.get("index_version") != INDEX_VERSION or not isinstance(data.get("documents"), dict):
            raise ValueError("索引格式不受支持；请备份索引后迁移或重建")
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)

    def ingest(self, request: IngestRequest) -> dict:
        with self.lock:
            data = self._read()
            documents = data["documents"]
            previous = documents.get(request.document_id)
            if previous and previous["resource_id"] != request.resource_id:
                raise ValueError("document_id 已属于其他资源；请使用全局唯一的文档 ID")
            # 演示约定：一项资源对应一份文本。同 resource_id 的重导入是替换。
            for document_id in list(documents):
                if documents[document_id]["resource_id"] == request.resource_id:
                    if documents[document_id]["course_id"] != request.course_id:
                        raise ValueError("resource_id 已属于其他课程；请使用全局唯一的资源 ID")
                    del documents[document_id]
            normalized = normalize_text(request.text)
            document = request.model_dump()
            document["text"] = normalized
            document["knowledge_point_ids"] = list(dict.fromkeys(request.knowledge_point_ids))
            document["chunks"] = split_text(request.document_id, normalized, self.chunk_size, self.chunk_overlap)
            documents[request.document_id] = document
            self._write(data)
            return {"document_id": request.document_id, "chunks": len(document["chunks"]),
                    "index_version": INDEX_VERSION, "mode": MODE}

    def list_resources(self, course_id: str) -> dict:
        with self.lock:
            values = [
                {key: doc[key] for key in ("resource_id", "title", "knowledge_point_ids", "source")}
                for doc in self._read()["documents"].values() if doc["course_id"] == course_id
            ]
        return {"resources": sorted(values, key=lambda item: item["resource_id"])}

    def delete_resource(self, resource_id: str) -> dict:
        with self.lock:
            data = self._read()
            keys = [key for key, value in data["documents"].items() if value["resource_id"] == resource_id]
            removed = sum(len(data["documents"][key]["chunks"]) for key in keys)
            for key in keys:
                del data["documents"][key]
            if keys:
                self._write(data)
        return {"resource_id": resource_id, "deleted_documents": len(keys), "deleted_chunks": removed,
                "index_version": INDEX_VERSION, "mode": MODE}

    def rebuild(self) -> dict:
        """从已保存原文重建片段；不删除文档，也不下载任何内容。"""
        with self.lock:
            data = self._read()
            count = 0
            for doc in data["documents"].values():
                doc["chunks"] = split_text(doc["document_id"], doc["text"], self.chunk_size, self.chunk_overlap)
                count += len(doc["chunks"])
            self._write(data)
        return {"documents": len(data["documents"]), "chunks": count, "index_version": INDEX_VERSION, "mode": MODE}

    def retrieve(self, request: RetrieveRequest) -> dict:
        terms = query_terms(request.query)
        evidence = []
        with self.lock:
            for doc in self._read()["documents"].values():
                if doc["course_id"] != request.course_id:
                    continue
                if request.knowledge_point_ids and not set(request.knowledge_point_ids).intersection(doc["knowledge_point_ids"]):
                    continue
                for chunk in doc["chunks"]:
                    searchable = (doc["title"] + "\n" + chunk["text"]).lower()
                    matched = sum(term in searchable for term in terms)
                    if not matched:
                        continue
                    evidence.append({
                        "evidence_id": "ev-" + chunk["chunk_id"][6:],
                        "document_id": doc["document_id"], "resource_id": doc["resource_id"],
                        "chunk_id": chunk["chunk_id"], "knowledge_point_ids": doc["knowledge_point_ids"],
                        "text": chunk["text"], "score": round(matched / len(terms), 4),
                        "location": f"chars:{chunk['start']}-{chunk['end']}",
                        "source": doc["source"], "title": doc["title"],
                    })
        evidence.sort(key=lambda item: (-item["score"], item["document_id"], item["chunk_id"]))
        return {"mode": MODE, "index_version": INDEX_VERSION, "evidence": evidence[:request.top_k]}
