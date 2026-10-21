from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from rag_service.config import Settings
from rag_service.main import create_app
from rag_service.seed import SEED_DOCUMENTS


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(Path(self.temporary.name) / "index.json")
        self.client = self.enterContext(TestClient(create_app(self.settings)))

    def test_health_and_seed_retrieval_contract(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok", "service": "rag", "mode": "keyword_demo"})
        resources = self.client.get("/internal/resources", params={"course_id": "course-ds"})
        self.assertEqual({item["resource_id"] for item in resources.json()["resources"]}, {"res-stack", "res-queue"})
        response = self.client.post("/internal/retrieve", json={
            "course_id": "course-ds", "query": "栈后进先出", "knowledge_point_ids": ["kp-stack"], "top_k": 1,
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mode"], "keyword_demo")
        self.assertEqual(data["index_version"], "demo-1")
        self.assertEqual(len(data["evidence"]), 1)
        self.assertEqual(set(data["evidence"][0]), {
            "evidence_id", "document_id", "resource_id", "chunk_id", "knowledge_point_ids",
            "text", "score", "location", "source", "title",
        })
        self.assertEqual(data["evidence"][0]["resource_id"], "res-stack")

    def test_http_ingest_replaces_old_resource_without_duplicates(self):
        document = dict(SEED_DOCUMENTS[0], resource_id="res-extra", document_id="doc-extra", text="撤销操作可以使用栈实现。")
        first = self.client.post("/internal/ingest", json=document)
        second = self.client.post("/internal/ingest", json=document)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["chunks"], 1)
        resources = self.client.get("/internal/resources").json()["resources"]
        self.assertEqual(len(resources), 3)
        conflict = dict(document, resource_id="res-wrong-owner")
        self.assertEqual(self.client.post("/internal/ingest", json=conflict).status_code, 409)

    def test_delete_then_restart_does_not_restore_seed(self):
        deleted = self.client.delete("/internal/resources/res-stack")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_documents"], 1)
        self.assertGreater(deleted.json()["deleted_chunks"], 0)
        self.assertEqual(self.client.delete("/internal/resources/res-stack").json()["deleted_chunks"], 0)
        with TestClient(create_app(self.settings)) as restarted:
            response = restarted.post("/internal/retrieve", json={
                "course_id": "course-ds", "query": "栈", "knowledge_point_ids": ["kp-stack"], "top_k": 5,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["evidence"], [])

    def test_rebuild_preserves_resources_and_course_filter(self):
        before = self.client.post("/internal/retrieve", json={"query": "队列"}).json()
        rebuilt = self.client.post("/internal/rebuild")
        self.assertEqual(rebuilt.status_code, 200)
        self.assertEqual(rebuilt.json()["documents"], 2)
        self.assertEqual(before, self.client.post("/internal/retrieve", json={"query": "队列"}).json())
        other_course = self.client.post("/internal/retrieve", json={"course_id": "missing-course", "query": "队列"})
        self.assertEqual(other_course.json()["evidence"], [])

    def test_invalid_http_requests_are_rejected(self):
        invalid_queries = [
            {}, {"query": " "}, {"query": "x" * 1001},
            {"query": "栈", "top_k": 0}, {"query": "栈", "top_k": 11},
            {"query": "栈", "unknown": "discarding fields hides contract errors"},
        ]
        for payload in invalid_queries:
            with self.subTest(payload_keys=list(payload)):
                self.assertEqual(self.client.post("/internal/retrieve", json=payload).status_code, 422)
        invalid_document = dict(SEED_DOCUMENTS[0], text="x" * 200001)
        self.assertEqual(self.client.post("/internal/ingest", json=invalid_document).status_code, 422)
        self.assertEqual(self.client.get("/internal/resources", params={"course_id": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
