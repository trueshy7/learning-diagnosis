import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_path: Path
    seed_on_start: bool = True
    chunk_size: int = 360
    chunk_overlap: int = 60

    def __post_init__(self) -> None:
        if self.chunk_size < 80 or self.chunk_size > 2000:
            raise ValueError("RAG_CHUNK_SIZE 必须在 80–2000 之间")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP 必须非负且小于分段长度")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_path=Path(os.getenv("RAG_DATA_PATH", "data/index.json")),
            seed_on_start=os.getenv("RAG_SEED_ON_START", "true").lower() == "true",
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "360")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "60")),
        )
