import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_path: Path
    seed_on_start: bool = True
    chunk_size: int = 400
    chunk_overlap: int = 60
    backend: str = "keyword"
    chroma_path: Path = Path("data/chroma")
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    embedding_revision: str = "v1"
    model_cache: Path = Path("data/models")
    model_path: str = ""
    embedding_url: str = ""
    embedding_key: str = ""
    batch_size: int = 32
    timeout_seconds: float = 30
    max_evidence_chars: int = 6000
    min_score: float = 0.45
    keyword_min_score: float = 0.20
    fallback: bool = True
    service_key: str = ""
    allowed_course_ids: str = "*"

    def __post_init__(self) -> None:
        if self.chunk_size < 80 or self.chunk_size > 2000:
            raise ValueError("RAG_CHUNK_SIZE 必须在 80–2000 之间")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP 必须非负且小于分段长度")
        if self.backend not in {"keyword", "chroma"}:
            raise ValueError("RAG_BACKEND 仅支持 keyword 或 chroma")
        if self.embedding_provider not in {"fastembed", "http", "hash_test"}:
            raise ValueError("未知 Embedding 提供方")
        if self.embedding_dimension < 1 or not 1 <= self.batch_size <= 256 or self.timeout_seconds <= 0:
            raise ValueError("Embedding 维度 批大小 超时配置无效")
        if self.max_evidence_chars < self.chunk_size or not -1 <= self.min_score <= 1:
            raise ValueError("证据预算或相似度阈值无效")
        if not 0 <= self.keyword_min_score <= 1:
            raise ValueError("关键词最低覆盖率须在0到1之间")
        if self.service_key and len(self.service_key.encode()) < 32:
            raise ValueError("RAG_SERVICE_KEY 至少 32 字节")

    @classmethod
    def from_env(cls) -> "Settings":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        return cls(
            data_path=Path(os.getenv("RAG_DATA_PATH", "data/catalog.json")),
            seed_on_start=os.getenv("RAG_SEED_ON_START", "true").lower() == "true",
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "400")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "60")),
            backend=os.getenv("RAG_BACKEND", "keyword"),
            chroma_path=Path(os.getenv("RAG_CHROMA_PATH", "data/chroma")),
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "fastembed"),
            embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
            embedding_dimension=int(os.getenv("RAG_EMBEDDING_DIMENSION", "512")),
            embedding_revision=os.getenv("RAG_EMBEDDING_REVISION", "v1"),
            model_cache=Path(os.getenv("RAG_MODEL_CACHE", "data/models")),
            model_path=os.getenv("RAG_MODEL_PATH", ""),
            embedding_url=os.getenv("RAG_EMBEDDING_URL", ""),
            embedding_key=os.getenv("RAG_EMBEDDING_KEY", ""),
            batch_size=int(os.getenv("RAG_BATCH_SIZE", "32")),
            timeout_seconds=float(os.getenv("RAG_TIMEOUT_SECONDS", "30")),
            max_evidence_chars=int(os.getenv("RAG_MAX_EVIDENCE_CHARS", "6000")),
            min_score=float(os.getenv("RAG_MIN_SCORE", "0.45")),
            keyword_min_score=float(os.getenv("RAG_KEYWORD_MIN_SCORE", "0.20")),
            fallback=os.getenv("RAG_FALLBACK", "true").lower() == "true",
            service_key=os.getenv("RAG_SERVICE_KEY", ""),
            allowed_course_ids=os.getenv("RAG_ALLOWED_COURSE_IDS", "*"),
        )
