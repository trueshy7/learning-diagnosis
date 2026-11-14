import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from diagnosis_service.diagnosis import diagnose
from diagnosis_service.main import app
from diagnosis_service.models import DiagnoseRequest
from diagnosis_service.rag_client import HttpRetriever, MockRetriever, get_retriever
from diagnosis_service.llm_client import get_llm_client


@pytest.fixture(autouse=True)
def mock_mode():
    app.dependency_overrides[get_retriever] = lambda: MockRetriever()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def payload():
    return {
        "attempt_id": "attempt-test",
        "course_id": "course-ds",
        "graded_answers": [],
        "knowledge_points": [{"id": "kp-stack", "name": "栈"}, {"id": "kp-queue", "name": "队列"}],
        "resource_catalog": [
            {"resource_id": "res-stack", "title": "栈示例材料", "knowledge_point_ids": ["kp-stack"]},
            {"resource_id": "res-queue", "title": "队列示例材料", "knowledge_point_ids": ["kp-queue"]},
        ],
    }


def answers(correct_count, sample_count, point="kp-stack"):
    return [
        {"question_id": f"{point}-{index}", "knowledge_point_ids": [point], "correct": index < correct_count}
        for index in range(sample_count)
    ]


@pytest.mark.parametrize("correct,samples,expected", [
    (0, 0, "insufficient_evidence"), (0, 2, "insufficient_evidence"),
    (2, 2, "insufficient_evidence"), (1, 3, "weak"),
    (2, 5, "weak"), (3, 5, "needs_practice"),
    (4, 5, "mastered"), (3, 3, "mastered"),
])
def test_thresholds(payload, correct, samples, expected):
    payload["graded_answers"] = answers(correct, samples)
    result = diagnose(DiagnoseRequest.model_validate(payload))[0]
    assert result.status == expected
    assert result.accuracy == (round(correct / samples, 6) if samples else None)


def test_health_and_small_samples_do_not_recommend(payload):
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "service": "agents", "mode": "rule_template_demo"}
    payload["graded_answers"] = answers(0, 2)
    report = client.post("/internal/diagnose-and-recommend", json=payload).json()
    assert report["mode"] == "rule_template_demo"
    assert report["recommendations"] == []
    assert report["evidence"] == []
    assert report["comparison"] == []


def test_exact_duplicates_count_once_and_multi_point_equal_weight(payload):
    answer = {"question_id": "same", "knowledge_point_ids": ["kp-stack", "kp-queue"], "correct": True}
    payload["graded_answers"] = [answer, {**answer, "knowledge_point_ids": ["kp-queue", "kp-stack"]}]
    result = diagnose(DiagnoseRequest.model_validate(payload))
    assert [(point.correct_count, point.sample_count) for point in result] == [(1, 1), (1, 1)]


@pytest.mark.parametrize("conflict", [
    {"question_id": "same", "knowledge_point_ids": ["kp-stack"], "correct": False},
    {"question_id": "same", "knowledge_point_ids": ["kp-queue"], "correct": True},
])
def test_conflicting_duplicate_rejected(payload, conflict):
    payload["graded_answers"] = [
        {"question_id": "same", "knowledge_point_ids": ["kp-stack"], "correct": True}, conflict,
    ]
    assert TestClient(app).post("/internal/diagnose-and-recommend", json=payload).status_code == 422


def test_recommendations_use_catalog_and_mock_is_explicit(payload):
    payload["graded_answers"] = answers(0, 3)
    client = TestClient(app)
    report = client.post("/internal/diagnose-and-recommend", json=payload).json()
    assert {item["resource_id"] for item in report["recommendations"]} == {"res-stack"}
    assert all(item["source"] == "builtin_mock_fixture" for item in report["evidence"])
    assert report["trace"][1]["status"] == "mock_fixture"
    payload["resource_catalog"] = []
    empty = client.post("/internal/diagnose-and-recommend", json=payload).json()
    assert empty["recommendations"] == []
    assert empty["evidence"] == []


def test_retest_compares_only_sufficient_same_points(payload):
    payload["graded_answers"] = answers(3, 3)
    payload["baseline"] = {"knowledge_points": [
        {"knowledge_point_id": "kp-stack", "name": "栈", "correct_count": 1, "sample_count": 3, "accuracy": 0.333333, "status": "weak"},
        {"knowledge_point_id": "kp-queue", "name": "队列", "correct_count": 0, "sample_count": 0, "accuracy": None, "status": "insufficient_evidence"},
    ]}
    client = TestClient(app)
    report = client.post("/internal/diagnose-and-recommend", json=payload).json()
    assert report["comparison"] == [{"knowledge_point_id": "kp-stack", "before_accuracy": 0.333333, "after_accuracy": 1.0, "delta": 0.666667}]
    payload["baseline"]["knowledge_points"][0].update(correct_count=1, sample_count=2, accuracy=0.5, status="insufficient_evidence")
    assert client.post("/internal/diagnose-and-recommend", json=payload).json()["comparison"] == []


def test_unknown_points_and_incoherent_baseline_rejected(payload):
    payload["graded_answers"] = answers(1, 3, point="unknown")
    assert TestClient(app).post("/internal/diagnose-and-recommend", json=payload).status_code == 422
    payload["graded_answers"] = []
    payload["baseline"] = {"knowledge_points": [
        {"knowledge_point_id": "kp-stack", "name": "栈", "correct_count": 3, "sample_count": 3, "accuracy": 0.5, "status": "mastered"},
    ]}
    assert TestClient(app).post("/internal/diagnose-and-recommend", json=payload).status_code == 422


def test_http_timeout_returns_empty_evidence_and_explicit_fallback(payload, monkeypatch):
    async def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("test timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", timeout)
    app.dependency_overrides[get_retriever] = lambda: HttpRetriever("http://127.0.0.1:8001")
    payload["graded_answers"] = answers(0, 3)
    response = TestClient(app).post("/internal/diagnose-and-recommend", json=payload)
    assert response.status_code == 200
    report = response.json()
    assert report["fallback_status"] == "rag_timeout"
    assert report["evidence"] == []
    assert report["trace"][1]["status"] == "failed"
    assert "尚无匹配检索证据" in report["recommendations"][0]["reason"]


def test_http_unavailable_does_not_switch_to_mock(payload, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", unavailable)
    app.dependency_overrides[get_retriever] = lambda: HttpRetriever("http://127.0.0.1:8001")
    payload["graded_answers"] = answers(0, 3)
    report = TestClient(app).post("/internal/diagnose-and-recommend", json=payload).json()
    assert report["fallback_status"] == "rag_unavailable"
    assert report["evidence"] == []
    assert "mock_fixture" not in [step["status"] for step in report["trace"]]


def test_http_rejects_evidence_outside_catalog(payload, monkeypatch):
    calls = []
    evidence = {
        "evidence_id": "ev-real", "document_id": "doc-real", "resource_id": "not-in-catalog",
        "chunk_id": "chunk-real", "knowledge_point_ids": ["kp-stack"], "text": "课程材料片段",
        "score": 0.75, "location": {"section": 1}, "source": "test-http-fixture", "title": "测试响应",
    }

    async def post(self, url, *, json):
        calls.append((url, json))
        return httpx.Response(200, json={"mode": "test_fixture", "index_version": "v1", "evidence": [evidence]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    app.dependency_overrides[get_retriever] = lambda: HttpRetriever("http://example.test")
    payload["graded_answers"] = answers(0, 3)
    report = TestClient(app).post("/internal/diagnose-and-recommend", json=payload).json()
    assert calls[0][0] == "http://example.test/internal/retrieve"
    assert calls[0][1]["knowledge_point_ids"] == ["kp-stack"]
    assert report["evidence"] == []
    assert report["recommendations"][0]["resource_id"] == "res-stack"
    assert report["fallback_status"] == "rag_invalid_evidence"
    assert report["trace"][1]["status"] == "filtered_invalid_evidence"


@pytest.mark.parametrize("body,status,expected", [
    ({"nonsense": True}, 200, "rag_invalid_response"),
    ({"detail": "offline"}, 503, "rag_http_503"),
])
def test_invalid_or_failed_http_response(payload, monkeypatch, body, status, expected):
    async def post(*args, **kwargs):
        return httpx.Response(status, json=body, request=httpx.Request("POST", "http://example.test/internal/retrieve"))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    request = DiagnoseRequest.model_validate(payload)
    result = asyncio.run(HttpRetriever("http://example.test").retrieve(request, []))
    assert result.fallback_status == expected
    assert result.evidence == []


class FixedRetriever:
    async def retrieve(self, request, targets):
        from diagnosis_service.models import Evidence
        from diagnosis_service.rag_client import RetrievalResult
        return RetrievalResult(evidence=[Evidence(evidence_id="ev-1", document_id="doc-1", chunk_id="chunk-1",
            resource_id="res-stack", knowledge_point_ids=["kp-stack"], text="栈的基本操作及适用场景。",
            score=0.7, source="course-fixture", title="示例", location="第1节")], status="completed:fixture:v1")

class FixedLLM:
    def __init__(self, response):
        self.response = response
        self.calls = 0
    async def generate(self, *, system, user):
        self.calls += 1
        return self.response

def test_model_prose_separate_from_diagnostic_facts(payload):
    from diagnosis_service.orchestrator import run_pipeline
    payload["graded_answers"] = answers(0, 3)
    llm = FixedLLM('{"summary":"先对照课程材料复习栈的基本操作，再用新题检验理解。","evidence_ids":["ev-1"]}')
    report = asyncio.run(run_pipeline(DiagnoseRequest.model_validate(payload), FixedRetriever(), llm))
    assert report.mode == "grounded_llm" and report.knowledge_points[0].correct_count == 0
    assert report.model_explanation.startswith("先对照")
    assert report.recommendations[0].evidence_ids == ["ev-1"]

@pytest.mark.parametrize("raw", [
    '{"summary":"先复习课程基本概念，再完成新练习任务。","evidence_ids":["invented"]}',
    '{"summary":"正确率提高了50%，证明教学有效。","evidence_ids":[]}',
    'not json',
])
def test_invalid_model_output_falls_back(payload, raw):
    from diagnosis_service.orchestrator import run_pipeline
    payload["graded_answers"] = answers(0, 3)
    report = asyncio.run(run_pipeline(DiagnoseRequest.model_validate(payload), FixedRetriever(), FixedLLM(raw)))
    assert report.mode == "rule_template_demo" and report.model_explanation is None
    assert report.fallback_status == "llm_invalid_or_unavailable"
    assert report.knowledge_points[0].status == "weak"

def test_resources_filtered_and_recent_deprioritized(payload):
    from diagnosis_service.orchestrator import run_pipeline
    payload["graded_answers"] = answers(0, 3)
    payload["recent_resource_ids"] = ["res-stack"]
    payload["resource_catalog"] += [
        {"resource_id": "res-new", "title": "新材料", "knowledge_point_ids": ["kp-stack"], "course_id": "course-ds", "estimated_minutes": 15},
        {"resource_id": "res-off", "title": "失效", "knowledge_point_ids": ["kp-stack"], "available": False},
        {"resource_id": "res-other", "title": "他课", "knowledge_point_ids": ["kp-stack"], "course_id": "other"},
    ]
    report = asyncio.run(run_pipeline(DiagnoseRequest.model_validate(payload), FixedRetriever()))
    assert [r.resource_id for r in report.recommendations] == ["res-new", "res-stack"]
    assert report.recommendations[0].estimated_minutes == 15

def test_mock_evidence_not_sent_to_model(payload):
    from diagnosis_service.orchestrator import run_pipeline
    payload["graded_answers"] = answers(0, 3)
    llm = FixedLLM('{"summary":"先复习已有材料再完成新练习任务。","evidence_ids":[]}')
    report = asyncio.run(run_pipeline(DiagnoseRequest.model_validate(payload), MockRetriever(), llm))
    assert llm.calls == 0 and report.mode == "rule_template_demo"

def test_deepseek_config_and_json_request(monkeypatch):
    from diagnosis_service.llm_client import OpenAICompatibleClient, get_llm_client
    monkeypatch.setenv("LLM_MODE", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    client = get_llm_client()
    assert isinstance(client, OpenAICompatibleClient) and client.deepseek
    calls = []
    async def post(self, url, *, headers, json):
        calls.append((url, headers, json))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"先复习资料，再做新练习任务。","evidence_ids":["ev-1"]}'}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    raw = asyncio.run(client.generate(system="请返回 JSON", user="测试"))
    assert raw.startswith('{')
    assert calls[0][0] == "https://api.deepseek.com/chat/completions"
    assert calls[0][1]["Authorization"] == "Bearer test-only-key"
    assert calls[0][2]["response_format"] == {"type": "json_object"}
    assert calls[0][2]["thinking"] == {"type": "disabled"}
    assert calls[0][2]["model"] == "deepseek-flash"
