"""测验请求模型，禁止客户端提交身份、成绩和试卷快照。"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StringConstraints, model_validator

from .schemas import ContentName, StrictModel

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=64)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
OptionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class OptionIn(StrictModel):
    label: Literal['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    text: OptionText
    is_correct: StrictBool


class QuestionIn(StrictModel):
    kind: Literal['single', 'multiple']
    stem: LongText
    explanation: str | None = Field(default=None, max_length=10000)
    status: Literal['draft', 'active', 'disabled'] = 'draft'
    knowledge_point_ids: list[Identifier] = Field(min_length=1, max_length=1)
    options: list[OptionIn] = Field(min_length=2, max_length=10)

    @model_validator(mode='after')
    def validate_options(self):
        if len({option.label for option in self.options}) != len(self.options):
            raise ValueError('选项标识不能重复')
        count = sum(option.is_correct for option in self.options)
        if (self.kind == 'single' and count != 1) or (self.kind == 'multiple' and count < 2):
            raise ValueError('单选题必须有一个正确选项，多选题至少有两个正确选项')
        return self


class ExamIn(StrictModel):
    title: ContentName
    duration_seconds: int = Field(default=1800, ge=60, le=14400, strict=True)


class PaperQuestionIn(StrictModel):
    question_id: Identifier
    score: Decimal = Field(gt=0, le=1000, max_digits=6, decimal_places=2, allow_inf_nan=False)


class PaperIn(StrictModel):
    questions: list[PaperQuestionIn] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def no_duplicate_questions(self):
        if len({question.question_id for question in self.questions}) != len(self.questions):
            raise ValueError('试卷中不能包含重复题目')
        return self


class AttemptStartIn(StrictModel):
    baseline_attempt_id: Identifier | None = None


class SavedAnswerIn(StrictModel):
    question_id: Identifier
    selected_option_ids: list[Identifier] = Field(max_length=10)
    revision: int = Field(ge=0, strict=True)

    @model_validator(mode='after')
    def unique_options(self):
        if len(set(self.selected_option_ids)) != len(self.selected_option_ids):
            raise ValueError('选项不能重复')
        return self


class SaveAnswersIn(StrictModel):
    answers: list[SavedAnswerIn] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_questions(self):
        if len({answer.question_id for answer in self.answers}) != len(self.answers):
            raise ValueError('同一批次不能重复提交题目')
        return self
