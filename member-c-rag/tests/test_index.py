import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError

from rag_service.index import LocalIndex
from rag_service.schemas import IngestRequest, RetrieveRequest
from rag_service.seed import SEED_DOCUMENTS, seed


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "index.json"
        self.index = LocalIndex(self.path, chunk_size=100, chunk_overlap=20)
        seed(self.index)

    def test_reimport_is_idempotent_and_citation_is_stable(self):
        request = RetrieveRequest(query="栈 后进先出", knowledge_point_ids=["kp-stack"])
        before = self.index.retrieve(request)
        seed(self.index)
        after = self.index.retrieve(request)
        self.assertEqual(before, after)
        self.assertEqual(len(self.index.list_resources("course-ds")["resources"]), 2)
        self.assertTrue(after["evidence"])

    def test_course_and_knowledge_point_filters_apply_before_ranking(self):
        response = self.index.retrieve(RetrieveRequest(query="入队 出队 栈", knowledge_point_ids=["kp-queue"]))
        self.assertTrue(response["evidence"])
        self.assertEqual({item["resource_id"] for item in response["evidence"]}, {"res-queue"})
        self.assertEqual(self.index.retrieve(RetrieveRequest(course_id="other-course", query="栈"))["evidence"], [])
        self.assertEqual(self.index.retrieve(RetrieveRequest(query="栈", knowledge_point_ids=["kp-missing"]))["evidence"], [])

    def test_delete_removes_all_resource_chunks_and_is_idempotent(self):
        result = self.index.delete_resource("res-stack")
        self.assertEqual(result["deleted_documents"], 1)
        self.assertGreater(result["deleted_chunks"], 1)
        self.assertEqual(self.index.retrieve(RetrieveRequest(query="栈", knowledge_point_ids=["kp-stack"]))["evidence"], [])
        self.assertEqual(self.index.delete_resource("res-stack")["deleted_chunks"], 0)
        self.assertEqual(len(self.index.list_resources("course-ds")["resources"]), 1)

    def test_evidence_traces_to_exact_normalized_source_range(self):
        response = self.index.retrieve(RetrieveRequest(query="栈 入栈"))
        stored = json.loads(self.path.read_text(encoding="utf-8"))["documents"]
        for item in response["evidence"]:
            start, end = map(int, item["location"].removeprefix("chars:").split("-"))
            document = stored[item["document_id"]]
            self.assertEqual(item["text"], document["text"][start:end])
            self.assertEqual(item["source"], document["source"])
            self.assertTrue(item["chunk_id"].startswith("chunk-"))

    def test_replacement_removes_old_text_and_persists(self):
        document = dict(SEED_DOCUMENTS[0], text="替换后的资料只讲二叉树。")
        self.index.ingest(IngestRequest(**document))
        reopened = LocalIndex(self.path)
        response = reopened.retrieve(RetrieveRequest(query="二叉树", knowledge_point_ids=["kp-stack"]))
        self.assertEqual(len(response["evidence"]), 1)
        self.assertEqual(response["evidence"][0]["text"], document["text"])

    def test_document_id_cannot_overwrite_another_resource(self):
        request = IngestRequest(**dict(SEED_DOCUMENTS[0], resource_id="other-resource"))
        with self.assertRaisesRegex(ValueError, "document_id"):
            self.index.ingest(request)

    def test_rebuild_retains_sources(self):
        before = self.index.retrieve(RetrieveRequest(query="栈"))
        summary = self.index.rebuild()
        self.assertEqual(summary["documents"], 2)
        self.assertEqual(before, self.index.retrieve(RetrieveRequest(query="栈")))

    def test_request_limits_and_no_match(self):
        for value in (0, 11):
            with self.assertRaises(ValidationError):
                RetrieveRequest(query="栈", top_k=value)
        with self.assertRaises(ValidationError):
            RetrieveRequest(query="x" * 1001)
        self.assertEqual(self.index.retrieve(RetrieveRequest(query="xyzunmatched"))["evidence"], [])
        self.assertLessEqual(len(self.index.retrieve(RetrieveRequest(query="栈", top_k=1))["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
