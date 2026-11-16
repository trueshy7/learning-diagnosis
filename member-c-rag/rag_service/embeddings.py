"""可替换的显式嵌入，绝不隐式启用 Chroma 默认模型。"""
import hashlib
import math
import os
from functools import cached_property

from .chunking import query_terms


class Embeddings:
    def __init__(self, settings):
        self.settings = settings

    @property
    def signature(self):
        s = self.settings
        # URL 标识远程模型空间，密钥不进入索引/日志。
        return f"{s.embedding_provider}:{s.embedding_model}:{s.embedding_revision}:{s.embedding_dimension}:{s.embedding_url}"

    @cached_property
    def model(self):
        os.environ.setdefault("HF_HOME", str(self.settings.model_cache.resolve() / "hf"))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=self.settings.embedding_model,
                             cache_dir=str(self.settings.model_cache), threads=2,
                             **({"specific_model_path": self.settings.model_path} if self.settings.model_path else {}))

    def _validate(self, vectors, count):
        values = [list(map(float, vector)) for vector in vectors]
        if len(values) != count:
            raise ValueError("嵌入数量不匹配")
        for vector in values:
            if len(vector) != self.settings.embedding_dimension or not all(math.isfinite(x) for x in vector):
                raise ValueError("嵌入维度不匹配或含非有限数字 请核对模型后重建")
            if not any(vector):
                raise ValueError("嵌入返回零向量")
        return values

    def embed(self, texts: list[str], query=False):
        s = self.settings
        if s.embedding_provider == "fastembed":
            vectors = self.model.query_embed(texts[0]) if query else self.model.embed(texts, batch_size=s.batch_size)
        elif s.embedding_provider == "http":
            if not s.embedding_key or not s.embedding_url:
                raise ValueError("未配置 RAG_EMBEDDING_KEY 或 RAG_EMBEDDING_URL")
            import httpx
            with httpx.Client(timeout=s.timeout_seconds, trust_env=False) as client:
                response = client.post(s.embedding_url, headers={"Authorization": f"Bearer {s.embedding_key}"},
                                       json={"model": s.embedding_model, "input": texts})
                response.raise_for_status()
                rows = sorted(response.json()["data"], key=lambda item: item["index"])
                if [row["index"] for row in rows] != list(range(len(texts))):
                    raise ValueError("嵌入响应索引不完整")
                vectors = [row["embedding"] for row in rows]
        else:
            # 仅用于无需模型下载的持久化/故障测试，不能称为语义检索。
            vectors = []
            for text in texts:
                vector = [0.] * s.embedding_dimension
                for term in query_terms(text):
                    bucket = int(hashlib.sha256(term.encode()).hexdigest(), 16) % len(vector)
                    vector[bucket] += 1.
                vectors.append(vector)
        return self._validate(vectors, len(texts))
