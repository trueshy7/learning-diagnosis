"""单进程版本化资料目录。多次轮询和重启使用同一份最高版本与删除墓碑。"""
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path

from .chunking import query_terms
from .chroma_store import ChromaStore
from .contracts import ResourceRecord, ScopedRetrieve
from .segments import split_document


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def b_content_hash(value):
    payload = {key: value[key] for key in ("course_id", "title", "text", "source")}
    payload["knowledge_point_ids"] = sorted(value["knowledge_point_ids"])
    return digest(payload)


def stable_document_id(resource_id, version):
    return "doc-" + digest([resource_id, version])[:32]


class IndexUnavailable(RuntimeError):
    pass


class Conflict(ValueError):
    pass


class KnowledgeIndex:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.data_path
        self.lock = threading.RLock()
        self.vector = ChromaStore(settings) if settings.backend == "chroma" else None
        self.receipts = OrderedDict()

    def _empty(self):
        return {"format": "catalog-2", "documents": {}, "tombstones": {},
                "index_version": "rag-empty", "storage_signature": self.signature, "built_at": 0}

    @property
    def signature(self):
        return self.vector.embeddings.signature if self.vector else "keyword-v2"

    def _read(self):
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (data["format"] != "catalog-2" or not isinstance(data["documents"], dict)
                    or not isinstance(data["tombstones"], dict) or not isinstance(data["index_version"], str)
                    or not isinstance(data["storage_signature"], str) or "built_at" not in data):
                raise ValueError("格式不支持")
            required = {"resource_id", "resource_version", "document_id", "course_id", "text", "source", "title",
                        "knowledge_point_ids", "content_hash", "input_hash", "chunks", "origin", "pages"}
            for doc in data["documents"].values():
                if not isinstance(doc, dict) or not required.issubset(doc) or not isinstance(doc["chunks"], list):
                    raise ValueError("文档目录不完整")
            return data
        except (OSError, ValueError, KeyError) as exc:
            raise IndexUnavailable("索引目录不可读取 请备份后从 B 全量同步或从资源清单重建") from exc

    def _commit(self, data):
        data["storage_signature"] = self.signature
        data["index_version"] = "rag-" + digest({"documents": data["documents"], "tombstones": data["tombstones"],
                                                 "signature": self.signature})[:20]
        # 模型/构建失败时不切换活动目录。
        if self.vector:
            try:
                self.vector.build(data)
            except Exception as exc:
                raise IndexUnavailable("向量索引构建失败 请检查依赖 模型文件或嵌入服务配置") from exc
        data["built_at"] = int(time.time())
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError as exc:
            raise IndexUnavailable("索引目录无法持久化 请检查磁盘空间和目录权限") from exc
        if self.vector:
            try:
                self.vector.cleanup(data)
            except Exception:
                pass  # 清理失败只遗留不可达集合，不影响活动目录。

    def _find(self, data, resource_id):
        return next((doc for doc in data["documents"].values() if doc["resource_id"] == resource_id), None)

    def _receipt(self, doc, data, state="ready"):
        return {"resource_id": doc["resource_id"], "course_id": doc["course_id"],
                "resource_version": doc["resource_version"], "document_id": doc.get("document_id"),
                "content_hash": doc.get("content_hash"), "state": state, "chunks": len(doc.get("chunks", [])),
                "index_version": data["index_version"], "mode": self.mode}

    @property
    def mode(self):
        if not self.vector:
            return "keyword_demo"
        return "vector_hash_test" if self.settings.embedding_provider == "hash_test" else "vector_rag"

    def ingest_record(self, record: ResourceRecord):
        incoming = record.model_dump()
        if b_content_hash(incoming) != record.content_hash:
            raise ValueError("content_hash 与 B 的规范 JSON 摘要不一致")
        with self.lock:
            data = self._read()
            previous = self._find(data, record.resource_id)
            tombstone = data["tombstones"].get(record.resource_id)
            owner = previous or tombstone
            if owner and owner["course_id"] != record.course_id:
                raise Conflict("resource_id 已属于其他课程")
            if tombstone:
                raise Conflict("资料已删除 迟到的入库不能使其复活 请使用新 resource_id")
            if previous:
                if record.resource_version < previous["resource_version"]:
                    raise Conflict("STALE_RESOURCE_VERSION")
                if record.resource_version == previous["resource_version"]:
                    if previous["input_hash"] != digest(incoming):
                        raise Conflict("RESOURCE_VERSION_CONFLICT 同版本请求不一致")
                    if data["storage_signature"] != self.signature:
                        raise IndexUnavailable("模型或后端配置已改变 请先 rebuild")
                    if self.vector:
                        self.vector.build(data)
                    return self._receipt(previous, data)
            occupied = data["documents"].get(record.document_id)
            if occupied and occupied["resource_id"] != record.resource_id:
                raise Conflict("document_id 已属于其他资源")
            if previous:
                del data["documents"][previous["document_id"]]
            incoming["input_hash"] = digest(incoming)
            incoming["chunks"] = split_document(record.document_id, record.text, self.settings.chunk_size,
                                                 self.settings.chunk_overlap, record.pages)
            data["documents"][record.document_id] = incoming
            self._commit(data)
            return self._receipt(incoming, data)

    def ingest(self, request):
        """兼容旧样例；B 同步对象必须走 ingest_record。"""
        value = request.model_dump()
        with self.lock:
            previous = self._find(self._read(), request.resource_id)
            if previous and previous["origin"] != "legacy":
                raise Conflict("受版本管理资料不能通过旧导入接口覆盖")
            content_hash = b_content_hash(value)
            version = previous["resource_version"] if previous and previous["content_hash"] == content_hash else (
                previous["resource_version"] + 1 if previous else 1)
            value |= {"resource_version": version, "content_hash": content_hash, "origin": "legacy"}
            return self.ingest_record(ResourceRecord(**value))

    def delete_version(self, resource_id, course_id, version):
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("删除版本必须为正整数")
        with self.lock:
            data = self._read()
            doc = self._find(data, resource_id)
            old = data["tombstones"].get(resource_id)
            previous = doc or old
            if previous and previous["course_id"] != course_id:
                raise Conflict("课程归属不符")
            if previous and (version < previous["resource_version"] or (doc and version == doc["resource_version"])):
                raise Conflict("STALE_RESOURCE_VERSION")
            if old and version == old["resource_version"]:
                return self._receipt(old, data, "deleted")
            if doc:
                del data["documents"][doc["document_id"]]
            tombstone = {"resource_id": resource_id, "course_id": course_id, "resource_version": version}
            data["tombstones"][resource_id] = tombstone
            self._commit(data)
            return self._receipt(tombstone, data, "deleted")

    def delete_resource(self, resource_id):
        with self.lock:
            doc = self._find(self._read(), resource_id)
            if not doc:
                return {"resource_id": resource_id, "deleted_documents": 0, "deleted_chunks": 0}
            if doc["origin"] != "legacy":
                raise Conflict("B 同步资料须由 B 删除并同步版本墓碑")
            self.delete_version(resource_id, doc["course_id"], doc["resource_version"] + 1)
            return {"resource_id": resource_id, "deleted_documents": 1, "deleted_chunks": len(doc["chunks"])}

    def resource_state(self, resource_id):
        with self.lock:
            data = self._read()
            doc = self._find(data, resource_id)
            if doc:
                return self._receipt(doc, data)
            old = data["tombstones"].get(resource_id)
            return self._receipt(old, data, "deleted") if old else None

    def list_resources(self, course_id):
        with self.lock:
            return {"resources": sorted([{key: doc[key] for key in
                                          ("resource_id", "title", "knowledge_point_ids", "source")}
                                         for doc in self._read()["documents"].values() if doc["course_id"] == course_id],
                                        key=lambda value: value["resource_id"])}

    def rebuild(self):
        with self.lock:
            data = self._read()
            for doc in data["documents"].values():
                doc["chunks"] = split_document(doc["document_id"], doc["text"], self.settings.chunk_size,
                                                 self.settings.chunk_overlap, doc["pages"])
            self._commit(data)
            return self.status()

    def status(self):
        with self.lock:
            data = self._read()
            return {"documents": len(data["documents"]), "chunks": sum(len(d["chunks"]) for d in data["documents"].values()),
                    "tombstones": len(data["tombstones"]), "index_version": data["index_version"],
                    "mode": self.mode, "storage_signature": data["storage_signature"], "built_at": data["built_at"],
                    "requires_rebuild": data["storage_signature"] != self.signature,
                    "chunk_size": self.settings.chunk_size, "chunk_overlap": self.settings.chunk_overlap}

    def export_manifest(self):
        with self.lock:
            return deepcopy(self._read())

    def retrieve(self, request):
        """旧入口仅供本机兼容联调；新调用应显式给出 resource_scope。"""
        with self.lock:
            data = self._read()
            if any(doc["origin"] == "b_sync" and doc["course_id"] == request.course_id
                   for doc in data["documents"].values()):
                raise Conflict("B 同步课程必须使用 retrieve-scoped 并传入 B 的资源版本目录")
            scopes = [{key: doc[key] for key in ("resource_id", "resource_version", "document_id", "content_hash")}
                      for doc in data["documents"].values() if doc["course_id"] == request.course_id]
            return self.retrieve_scoped(ScopedRetrieve(**request.model_dump(), resource_scope=scopes))

    def retrieve_scoped(self, request: ScopedRetrieve):
        started = time.perf_counter()
        with self.lock:
            data = self._read()
            if request.index_version and request.index_version != data["index_version"]:
                raise Conflict("INDEX_VERSION_CHANGED")
            available, unavailable, known_points = {}, [], set()
            for scope in request.resource_scope:
                doc = self._find(data, scope.resource_id)
                reason = None
                if not doc or doc["course_id"] != request.course_id:
                    reason = "not_available"
                elif (doc["resource_version"] != scope.resource_version or doc["document_id"] != scope.document_id
                      or (scope.content_hash and doc["content_hash"] != scope.content_hash)):
                    reason = "version_changed"
                if reason:
                    unavailable.append(scope.model_dump() | {"reason": reason})
                    continue
                known_points.update(doc["knowledge_point_ids"])
                if request.knowledge_point_ids and not set(request.knowledge_point_ids).intersection(doc["knowledge_point_ids"]):
                    continue
                for chunk in doc["chunks"]:
                    available[chunk["chunk_id"]] = (doc, chunk)
            mode, fallback_reason = self.mode, None
            try:
                if self.vector:
                    if data["storage_signature"] != self.signature:
                        raise IndexUnavailable("嵌入模型或维度变化 须重建")
                    ranking = self.vector.rank(data, request.query, available, request.top_k)
                    ranking = [(cid, score) for cid, score in ranking if score >= self.settings.min_score]
                else:
                    ranking = self._keyword_rank(request.query, available)
            except Exception as exc:
                if not self.settings.fallback:
                    raise IndexUnavailable("向量检索不可用 请检查配置或重建索引") from exc
                mode, fallback_reason = "keyword_fallback", "vector_unavailable"
                ranking = self._keyword_rank(request.query, available)
            evidence, length = [], 0
            for cid, score in ranking:
                doc, chunk = available[cid]
                if length + len(chunk["text"]) > self.settings.max_evidence_chars:
                    continue  # 不截断原文，保留精确定位。
                evidence.append({"evidence_id": "ev-" + digest([doc["resource_version"], cid])[:24],
                                 **{k: doc[k] for k in ("document_id", "resource_id", "resource_version", "course_id",
                                                        "knowledge_point_ids", "source", "title")},
                                 "chunk_id": cid, "text": chunk["text"], "score": round(score, 6),
                                 "location": chunk["location"], "index_version": data["index_version"]})
                length += len(chunk["text"])
                if len(evidence) == request.top_k:
                    break
            retrieval_id = "ret-" + digest([time.time_ns(), request.model_dump(), evidence])[:24]
            self.receipts[retrieval_id] = {"course_id": request.course_id,
                                           "evidence": deepcopy(evidence), "expires": time.monotonic() + 1800}
            while len(self.receipts) > 256:
                self.receipts.popitem(last=False)
            reason = None if evidence else ("empty_resource_scope" if not request.resource_scope else
                                           "unknown_knowledge_point" if request.knowledge_point_ids and
                                           not set(request.knowledge_point_ids).intersection(known_points) else "no_relevant_evidence")
            return {"course_id": request.course_id, "mode": mode, "index_version": data["index_version"],
                    "evidence": evidence, "unavailable_resources": unavailable, "insufficient_evidence": not bool(evidence),
                    "reason": reason, "fallback_reason": fallback_reason, "retrieval_id": retrieval_id,
                    "candidate_count": len(available), "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}

    def _keyword_rank(self, query, available):
        terms = query_terms(query)
        if not terms:
            return []
        ranking = []
        for cid, (doc, chunk) in available.items():
            searchable = (doc["title"] + "\n" + chunk["text"]).lower()
            matched = sum(term in searchable for term in terms)
            if matched and matched / len(terms) >= self.settings.keyword_min_score:
                ranking.append((cid, matched / len(terms)))
        return sorted(ranking, key=lambda item: (-item[1], item[0]))

    def citation_course(self, retrieval_id):
        receipt = self.receipts.get(retrieval_id)
        return receipt["course_id"] if receipt and receipt["expires"] >= time.monotonic() else None

    def validate_citations(self, retrieval_id, evidence_ids):
        with self.lock:
            receipt = self.receipts.get(retrieval_id)
            if not receipt or receipt["expires"] < time.monotonic():
                return {"valid": False, "reason": "retrieval_missing_or_expired", "invalid_ids": evidence_ids}
            returned = {item["evidence_id"]: item for item in receipt["evidence"]}
            invalid = []
            for eid in evidence_ids:
                item = returned.get(eid)
                current = self.resource_state(item["resource_id"]) if item else None
                if not item or not current or current["state"] != "ready" or current["document_id"] != item["document_id"] or current["resource_version"] != item["resource_version"]:
                    invalid.append(eid)
            return {"valid": not invalid, "invalid_ids": invalid, "reason": "invalid_or_stale_citation" if invalid else None}
