"""主动消费 ts 分支 b-internal-1，不访问 B 数据库。"""
import logging
from urllib.parse import quote

import httpx

from .catalog import IndexUnavailable, b_content_hash, stable_document_id
from .contracts import ResourceRecord

logger = logging.getLogger(__name__)


class BackendSync:
    def __init__(self, index, base_url, service_key, *, transport=None):
        if len(service_key.encode()) < 32:
            raise ValueError("B_C_KEY 至少 32 字节 须与 B 的 C_SERVICE_KEY 相同")
        self.index = index
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=index.settings.timeout_seconds,
                                   headers={"Authorization": f"Bearer {service_key}"}, trust_env=False,
                                   transport=transport)

    def close(self):
        self.client.close()

    def _data(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0 or "data" not in payload:
            raise ValueError("B 响应不符合 b-internal-1 包装")
        return payload["data"]

    def _pages(self, path):
        cursor, seen = None, set()
        while True:
            data = self._data("GET", path, params={"limit": 100, **({"after_id": cursor} if cursor else {})})
            yield from data["items"]
            cursor = data["next_after_id"]
            if cursor is None:
                break
            if cursor in seen:
                raise ValueError("B 分页游标重复")
            seen.add(cursor)

    def _report(self, resource_id, body):
        return self._data("PUT", f"/internal/resources/{quote(resource_id, safe='')}/index-state", json=body)

    def sync_resource(self, resource_id, course_id):
        for attempt in range(3):
            detail = self._data("GET", f"/internal/resources/{quote(resource_id, safe='')}")
            if detail["id"] != resource_id or detail["course_id"] != course_id:
                raise ValueError("B 返回了不同课程或资料 ID")
            version = detail["version"]
            try:
                if detail["status"] == "deleted":
                    self.index.delete_version(resource_id, course_id, version)
                    body = {"resource_version": version, "status": "deleted"}
                else:
                    payload = {key: detail[key] for key in ("course_id", "title", "text", "source", "knowledge_point_ids")}
                    if b_content_hash(payload) != detail["content_hash"]:
                        raise ValueError("B 资料摘要校验失败")
                    state = detail.get("index_state", {})
                    document_id = (state.get("document_id") if state.get("indexed_version") == version else None)
                    document_id = document_id or stable_document_id(resource_id, version)
                    result = self.index.ingest_record(ResourceRecord(
                        **payload, resource_id=resource_id, resource_version=version,
                        document_id=document_id, content_hash=detail["content_hash"]))
                    body = {"resource_version": version, "status": "ready", "document_id": result["document_id"],
                            "content_hash": detail["content_hash"]}
            except Exception as exc:
                error = "storage_unavailable" if isinstance(exc, (IndexUnavailable, OSError)) else "index_failed"
                try:
                    self._report(resource_id, {"resource_version": version, "status": "failed", "error_code": error})
                except httpx.HTTPStatusError as report_error:
                    if report_error.response.status_code == 409 and attempt < 2:
                        continue
                    raise
                raise exc
            try:
                self._report(resource_id, body)
                return body["status"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409 and attempt < 2:
                    continue
                raise
        raise ValueError("B 资料连续变化 本轮停止 下轮从头扫描")

    def run_once(self):
        result = {"ready": 0, "deleted": 0, "failed": 0, "failed_resource_ids": []}
        for course in self._pages("/internal/courses"):
            course_id = course["id"]
            for item in self._pages(f"/internal/courses/{quote(course_id, safe='')}/resources"):
                resource_id = item["id"]
                try:
                    state = self.sync_resource(resource_id, course_id)
                    result[state] += 1
                except Exception as exc:
                    result["failed"] += 1
                    result["failed_resource_ids"].append(resource_id)
                    logger.warning("resource_sync_failed resource_id=%s error_type=%s", resource_id, type(exc).__name__)
        return result
