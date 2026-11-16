"""服务内部契约；评分由成员 B 完成，D 不接收标准答案。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


Status = Literal["insufficient_evidence", "weak", "needs_practice", "mastered"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgePoint(Model):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class GradedAnswer(Model):
    question_id: str = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)
    correct: StrictBool

    @model_validator(mode="after")
    def validate_points(self):
        if any(not item.strip() for item in self.knowledge_point_ids):
            raise ValueError("knowledge_point_ids 不能包含空值")
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("一题的 knowledge_point_ids 不能重复")
        return self


class Resource(Model):
    resource_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    knowledge_point_ids: list[str]


def classify(sample_count: int, correct_count: int) -> Status:
    if sample_count < 3:
        return "insufficient_evidence"
    accuracy = correct_count / sample_count
    if accuracy < 0.6:
        return "weak"
    if accuracy < 0.8:
        return "needs_practice"
    return "mastered"


class KnowledgePointStat(Model):
    knowledge_point_id: str = Field(min_length=1)
    name: str
    correct_count: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0, le=1)
    status: Status

    @model_validator(mode="after")
    def validate_statistics(self):
        if self.correct_count > self.sample_count:
            raise ValueError("correct_count 不能超过 sample_count")
        expected = self.correct_count / self.sample_count if self.sample_count else None
        if (expected is None) != (self.accuracy is None):
            raise ValueError("零样本 accuracy 必须为 null，非零样本必须提供准确率")
        if expected is not None and abs(expected - self.accuracy) > 0.000001:
            raise ValueError("accuracy 必须与作答统计一致")
        if self.status != classify(self.sample_count, self.correct_count):
            raise ValueError("status 必须与规则和作答统计一致")
        return self


class Baseline(Model):
    knowledge_points: list[KnowledgePointStat]


class DiagnoseRequest(Model):
    attempt_id: str = Field(min_length=1)
    course_id: str = "course-ds"
    graded_answers: list[GradedAnswer]
    knowledge_points: list[KnowledgePoint]
    resource_catalog: list[Resource]
    baseline: Baseline | None = None

    @model_validator(mode="after")
    def validate_relations(self):
        ids = [point.id for point in self.knowledge_points]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge_points 的 id 不能重复")
        resource_ids = [resource.resource_id for resource in self.resource_catalog]
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("resource_catalog 的 resource_id 不能重复")
        known = set(ids)
        seen = {}
        for answer in self.graded_answers:
            if not set(answer.knowledge_point_ids) <= known:
                raise ValueError("作答包含未知知识点")
            signature = (tuple(sorted(answer.knowledge_point_ids)), answer.correct)
            if answer.question_id in seen and seen[answer.question_id] != signature:
                raise ValueError("重复 question_id 的评分或知识点矛盾")
            seen[answer.question_id] = signature
        for resource in self.resource_catalog:
            if not set(resource.knowledge_point_ids) <= known:
                raise ValueError("资源包含未知知识点")
        if self.baseline:
            baseline_ids = [point.knowledge_point_id for point in self.baseline.knowledge_points]
            if len(baseline_ids) != len(set(baseline_ids)):
                raise ValueError("baseline 的知识点不能重复")
        return self


class Evidence(BaseModel):
    """保留 C 的证据引用字段；未识别的上游字段忽略。"""

    evidence_id: str
    document_id: str
    resource_id: str
    chunk_id: str
    knowledge_point_ids: list[str]
    text: str
    score: float
    location: str | dict = ""
    source: str = ""
    title: str = ""


class Recommendation(Model):
    knowledge_point_id: str
    resource_id: str
    title: str
    reason: str


class Comparison(Model):
    knowledge_point_id: str
    before_accuracy: float
    after_accuracy: float
    delta: float


class TraceStep(Model):
    agent: str
    status: str


class Report(Model):
    attempt_id: str
    mode: Literal["rule_template_demo"] = "rule_template_demo"
    knowledge_points: list[KnowledgePointStat]
    evidence: list[Evidence]
    recommendations: list[Recommendation]
    explanation: str
    comparison: list[Comparison]
    trace: list[TraceStep]
    fallback_status: str | None

