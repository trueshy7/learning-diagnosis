from pydantic import BaseModel, Field, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class LoginIn(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class AnswerIn(StrictModel):
    question_id: str
    selected_option_ids: list[str] = Field(max_length=10)

class AttemptIn(StrictModel):
    course_id: str
    answers: list[AnswerIn] = Field(max_length=100)
    baseline_attempt_id: str | None = None

class ResourceIn(StrictModel):
    resource_id: str = Field(min_length=1, max_length=100)
    document_id: str = Field(min_length=1, max_length=100)
    course_id: str
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)
    knowledge_point_ids: list[str]
    source: str = '课程教师自编材料'
