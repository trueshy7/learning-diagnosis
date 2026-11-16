"""检索边界：mock 是固定演示材料，http 才调用 C 服务。"""

import os
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from .models import DiagnoseRequest, Evidence, KnowledgePointStat


class RetrievalResponse(BaseModel):
    mode: str
    index_version: str
    evidence: list[Evidence]


@dataclass
class RetrievalResult:
    evidence: list[Evidence] = field(default_factory=list)
    status: str = "completed"
    fallback_status: str | None = None


class Retriever(Protocol):
    async def retrieve(self, request: DiagnoseRequest, targets: list[KnowledgePointStat]) -> RetrievalResult: ...


class MockRetriever:
    async def retrieve(self, request: DiagnoseRequest, targets: list[KnowledgePointStat]) -> RetrievalResult:
        evidence = []
        for target in targets:
            resource = next((r for r in request.resource_catalog if target.knowledge_point_id in r.knowledge_point_ids), None)
            if resource is None:
                continue
            evidence.append(Evidence(
                evidence_id=f"mock:{resource.resource_id}:1",
                document_id=f"mock-doc:{resource.resource_id}",
                resource_id=resource.resource_id,
                chunk_id=f"mock-chunk:{resource.resource_id}:1",
                knowledge_point_ids=[target.knowledge_point_id],
                text=f"【内置演示证据】围绕“{target.name}”复习基本概念、操作步骤，并完成示例练习。此段文本不来自成员 C 的知识库。",
                score=1.0,
                location="builtin://mock-fixture/1",
                source="builtin_mock_fixture",
                title=f"演示片段：{resource.title}",
            ))
        return RetrievalResult(evidence=evidence, status="mock_fixture")


class HttpRetriever:
    def __init__(self, base_url: str, timeout: float = 5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def retrieve(self, request: DiagnoseRequest, targets: list[KnowledgePointStat]) -> RetrievalResult:
        payload = {
            "query": "、".join(target.name for target in targets) + " 概念与练习",
            "course_id": request.course_id,
            "knowledge_point_ids": [target.knowledge_point_id for target in targets],
            "top_k": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(f"{self.base_url}/internal/retrieve", json=payload)
                response.raise_for_status()
                parsed = RetrievalResponse.model_validate(response.json())
            return RetrievalResult(evidence=parsed.evidence, status=f"completed:{parsed.mode}:{parsed.index_version}")
        except httpx.TimeoutException:
            return RetrievalResult(status="failed", fallback_status="rag_timeout")
        except httpx.HTTPStatusError as error:
            return RetrievalResult(status="failed", fallback_status=f"rag_http_{error.response.status_code}")
        except httpx.RequestError:
            return RetrievalResult(status="failed", fallback_status="rag_unavailable")
        except (ValidationError, ValueError):
            return RetrievalResult(status="failed", fallback_status="rag_invalid_response")


def get_retriever() -> Retriever:
    mode = os.getenv("RAG_MODE", "mock").lower()
    if mode == "mock":
        return MockRetriever()
    if mode == "http":
        timeout = float(os.getenv("RAG_TIMEOUT_SECONDS", "5"))
        if timeout <= 0:
            raise ValueError("RAG_TIMEOUT_SECONDS 必须大于 0")
        return HttpRetriever(os.getenv("RAG_BASE_URL", "http://127.0.0.1:8001"), timeout)
    raise ValueError("RAG_MODE 仅支持 mock 或 http")

