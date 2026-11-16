from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IngestRequest(StrictModel):
    resource_id: Identifier
    document_id: Identifier
    course_id: Identifier
    title: ShortText
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200_000)]
    knowledge_point_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    source: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class IngestResponse(StrictModel):
    document_id: str
    chunks: int
    index_version: str
    mode: str


class RetrieveRequest(StrictModel):
    course_id: Identifier = "course-ds"
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    knowledge_point_ids: list[Identifier] = Field(default_factory=list, max_length=50)
    top_k: int = Field(default=5, ge=1, le=10)


class Evidence(StrictModel):
    evidence_id: str
    document_id: str
    resource_id: str
    chunk_id: str
    knowledge_point_ids: list[str]
    text: str
    score: float
    location: str
    source: str
    title: str


class RetrieveResponse(StrictModel):
    mode: str
    index_version: str
    evidence: list[Evidence]


class Resource(StrictModel):
    resource_id: str
    title: str
    knowledge_point_ids: list[str]
    source: str


class ResourceList(StrictModel):
    resources: list[Resource]
