"""B b-internal-1 同步对象和 D 的受限检索合同。"""
from typing import Literal

from pydantic import Field, StringConstraints, model_validator
from typing_extensions import Annotated

from .schemas import Identifier, StrictModel

BodyText = Annotated[str, StringConstraints(min_length=1, max_length=200_000)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ResourceRecord(StrictModel):
    resource_id: Identifier
    document_id: Identifier
    course_id: Identifier
    resource_version: int = Field(ge=1, le=2147483647, strict=True)
    title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    text: BodyText
    source: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    knowledge_point_ids: list[Identifier] = Field(min_length=1, max_length=50)
    content_hash: Digest
    origin: Literal["b_sync", "local_file", "legacy"] = "b_sync"
    pages: list[dict] = Field(default_factory=list, max_length=500)
    license: str = "未登记 由资料提供方核实"

    @model_validator(mode="after")
    def valid_content(self):
        if not self.text.strip() or not self.source.strip() or not self.title.strip():
            raise ValueError("正文 标题 来源不能全为空白")
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("知识点 ID 不得重复")
        return self


class ResourceScope(StrictModel):
    resource_id: Identifier
    resource_version: int = Field(ge=1, strict=True)
    document_id: Identifier
    content_hash: Digest | None = None


class ScopedRetrieve(StrictModel):
    course_id: Identifier
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    knowledge_point_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    resource_scope: list[ResourceScope] = Field(max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10, strict=True)
    index_version: Identifier | None = None


class CitationRequest(StrictModel):
    retrieval_id: Identifier
    evidence_ids: list[Identifier] = Field(max_length=10)
