"""Optional OpenAI-compatible explanation adapter. It never computes grades or selects IDs."""

import json
import os
import re
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LLMClient(Protocol):
    async def generate(self, *, system: str, user: str) -> str: ...


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=10, max_length=400)
    evidence_ids: list[str] = Field(max_length=5)


class OpenAICompatibleClient:
    def __init__(self, *, base_url: str, model: str, api_key: str, timeout: float, deepseek: bool = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.deepseek = deepseek

    async def generate(self, *, system: str, user: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            body = {"model": self.model, "temperature": 0, "max_tokens": 350,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            if self.deepseek:
                body.update({"thinking": {"type": "disabled"},
                             "response_format": {"type": "json_object"}})
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError("模型输出被截断")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("模型输出为空")
            return content


def get_llm_client() -> LLMClient | None:
    mode = os.getenv("LLM_MODE", "disabled")
    if mode == "disabled":
        return None
    if mode == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
        if not key or timeout <= 0:
            raise ValueError("DeepSeek API 密钥未配置或超时无效")
        return OpenAICompatibleClient(base_url="https://api.deepseek.com",
                                      model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                                      api_key=key, timeout=timeout, deepseek=True)
    if mode != "openai_compatible":
        raise ValueError("LLM_MODE 仅支持 disabled、deepseek 或 openai_compatible")
    url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
    if not url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")) or not model or not key or timeout <= 0:
        raise ValueError("模型配置缺失或不安全：请检查 URL、模型名、密钥与超时")
    return OpenAICompatibleClient(base_url=url, model=model, api_key=key, timeout=timeout)


def validate_output(raw: str, allowed_evidence_ids: set[str]) -> tuple[str, list[str]]:
    """Accept a narrow suggestion only; verified diagnostic facts stay in rule fields."""
    try:
        parsed = ModelOutput.model_validate(json.loads(raw))
    except (ValueError, ValidationError, TypeError) as exc:
        raise ValueError("模型输出不是约定的 JSON") from exc
    if len(set(parsed.evidence_ids)) != len(parsed.evidence_ids) or not set(parsed.evidence_ids) <= allowed_evidence_ids:
        raise ValueError("模型引用了不存在或重复的证据")
    if not parsed.evidence_ids:
        raise ValueError("模型建议必须至少关联一条有效证据")
    if re.search(r"[0-9０-９]|正确率|分数|得分|已掌握|提高了|提升了|证明|保证|治愈", parsed.summary):
        raise ValueError("模型文本越过了建议的边界")
    return parsed.summary.strip(), parsed.evidence_ids
