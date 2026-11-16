import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import httpx

from rag_service.catalog import KnowledgeIndex, b_content_hash
from rag_service.config import Settings
from rag_service.sync import BackendSync


class SyncTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.index = KnowledgeIndex(Settings(Path(self.temp.name) / "index.json", seed_on_start=False))
        self.detail = {"id": "r1", "course_id": "c1", "version": 1, "status": "active", "title": "栈",
                       "text": "栈遵循后进先出原则。", "source": "测试自编", "knowledge_point_ids": ["k1"],
                       "index_state": {"status": "pending", "indexed_version": None, "document_id": None}}
        self.detail["content_hash"] = b_content_hash(self.detail)
        self.reports = []
        self.conflict_once = False
        self.bad_hash = False
        self.visits = []
        self.sync = BackendSync(self.index, "http://backend", "x" * 32, transport=httpx.MockTransport(self.handler))
        self.addCleanup(self.sync.close)

    def response(self, value):
        return httpx.Response(200, json={"code": 0, "message": "ok", "data": value, "request_id": "fixture"})

    def handler(self, request):
        self.assertEqual(request.headers["Authorization"], "Bearer " + "x" * 32)
        path = request.url.path
        self.visits.append((path, str(request.url.query)))
        if path == "/internal/courses":
            return self.response({"items": [{"id": "c1"}], "next_after_id": None})
        if path == "/internal/courses/c1/resources":
            return self.response({"items": [{"id": "r1", "version": self.detail["version"],
                                             "status": self.detail["status"], "index_status": "pending"}],
                                  "next_after_id": None})
        if path == "/internal/resources/r1":
            return self.response(self.detail)
        if path == "/internal/resources/r1/index-state":
            body = json.loads(request.content)
            if self.conflict_once:
                self.conflict_once = False
                self.detail["version"] = 2
                self.detail["text"] = "栈的新正文。"
                self.detail["content_hash"] = b_content_hash(self.detail)
                return httpx.Response(409, json={"code": 409, "message": "资料变化"})
            self.reports.append(body)
            state = self.index.resource_state("r1")
            if body["status"] == "ready":
                self.assertEqual(state["state"], "ready")
                self.assertEqual(state["content_hash"], body["content_hash"])
            elif body["status"] == "deleted":
                self.assertEqual(state["state"], "deleted")
            return self.response(body)
        return httpx.Response(404)

    def test_ts_pull_contract_repeated_full_scan_and_ready_ack(self):
        self.assertEqual(self.sync.run_once()["ready"], 1)
        first = self.index.status()
        self.assertEqual(self.sync.run_once()["ready"], 1)
        self.assertEqual(first, self.index.status())
        self.assertEqual(self.reports[0], self.reports[1])
        self.assertEqual(sum(path == "/internal/courses" for path, _ in self.visits), 2)

    def test_conflict_rereads_current_version_before_ack(self):
        self.conflict_once = True
        self.assertEqual(self.sync.run_once()["ready"], 1)
        self.assertEqual(self.reports[-1]["resource_version"], 2)
        self.assertEqual(self.index.resource_state("r1")["resource_version"], 2)

    def test_deleted_detail_without_text_and_local_recovery(self):
        self.sync.run_once()
        previous_id = self.index.resource_state("r1")["document_id"]
        self.index.path.unlink()
        self.detail["index_state"] = {"status": "ready", "indexed_version": 1, "document_id": previous_id}
        self.assertEqual(self.sync.run_once()["ready"], 1)
        self.assertEqual(self.index.resource_state("r1")["document_id"], previous_id)
        self.detail = {"id": "r1", "course_id": "c1", "version": 2, "status": "deleted", "title": "栈",
                       "index_state": {"status": "pending"}}
        self.assertEqual(self.sync.run_once()["deleted"], 1)
        self.assertEqual(self.reports[-1], {"resource_version": 2, "status": "deleted"})

    def test_bad_hash_only_reports_supported_error_enum(self):
        self.detail["content_hash"] = "0" * 64
        self.assertEqual(self.sync.run_once()["failed"], 1)
        self.assertIsNone(self.index.resource_state("r1"))
        self.assertEqual(self.reports[-1], {"resource_version": 1, "status": "failed", "error_code": "index_failed"})

    def test_pagination_and_repeated_cursor_rejected(self):
        calls = []
        def handler(request):
            calls.append(request.url.params.get("after_id"))
            return self.response({"items": [{"id": str(len(calls))}], "next_after_id": "cursor"})
        sync = BackendSync(self.index, "http://b", "x" * 32, transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(ValueError):
                list(sync._pages("/internal/courses"))
            self.assertEqual(calls, [None, "cursor"])
        finally:
            sync.close()
