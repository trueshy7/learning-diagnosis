from pydantic import BaseModel, Field, ConfigDict, model_validator

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
    question_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode='after')
    def validate_question_ids(self):
        if self.question_ids is not None and len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError('练习题目ID不能重复')
        return self

class ResourceIn(StrictModel):
    resource_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    document_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    course_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)
    knowledge_point_ids: list[str] = Field(min_length=1, max_length=50)
    source: str = Field(default='课程教师自编材料', min_length=1, max_length=1000)

    @model_validator(mode='after')
    def validate_text(self):
        if not self.text.strip() or not self.source.strip():
            raise ValueError('资料正文和来源不能为空')
        return self

class ResourceFileIn(StrictModel):
    resource_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    document_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    course_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=3_000_000)
    knowledge_point_ids: list[str] = Field(min_length=1, max_length=50)
    source: str = Field(default='课程教师上传材料', min_length=1, max_length=1000)

class CourseIn(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=1000)

class CourseUpdateIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=1000)

class KnowledgePointIn(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    name: str = Field(min_length=1, max_length=200)

class KnowledgePointUpdateIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)

class OptionIn(StrictModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=1000)

class QuestionFields(StrictModel):
    stem: str = Field(min_length=1, max_length=1000)
    kind: str = 'single'
    options: list[OptionIn] = Field(min_length=2, max_length=10)
    correct_option_ids: list[str] = Field(min_length=1, max_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def validate_question(self):
        if self.kind != 'single':
            raise ValueError('当前只支持单选题')
        option_ids = [option.id for option in self.options]
        if len(set(option_ids)) != len(option_ids) or self.correct_option_ids[0] not in option_ids:
            raise ValueError('选项ID必须唯一，正确答案必须属于选项')
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError('知识点ID不能重复')
        return self

class QuestionIn(QuestionFields):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

class QuestionUpdateIn(QuestionFields):
    pass

class QuestionStateIn(StrictModel):
    active: bool

class AskIn(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_point_ids: list[str] = Field(default_factory=list, max_length=10)
    top_k: int = Field(default=3, ge=1, le=5)

    @model_validator(mode='after')
    def validate_query(self):
        if not self.query.strip() or len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError('问题不能为空，知识点ID不能重复')
        return self
