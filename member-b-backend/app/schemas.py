import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict, StringConstraints, field_validator, model_validator

from .email_utils import normalize_email

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class LoginIn(StrictModel):
    username: str = Field(min_length=3, max_length=64, pattern=r'^[\w-]+$')
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        if not isinstance(value, str):
            raise ValueError('用户名必须是字符串')
        return value.strip()


class SendRegisterCodeIn(StrictModel):
    email: str = Field(max_length=255)

    @field_validator('email', mode='before')
    @classmethod
    def validate_email(cls, value):
        return normalize_email(value)


class RegisterIn(SendRegisterCodeIn):
    username: str = Field(...,min_length=3, max_length=64, pattern=r'^[\w-]+$')
    role: Literal['student', 'teacher'] = Field(default='student', description='用户角色：student 学生，teacher 教师')
    password: str = Field(...,min_length=8, max_length=128, repr=False)
    confirm_password: str = Field(...,min_length=8, max_length=128, repr=False)
    verification_code: str = Field(...,min_length=6, max_length=6, pattern=r'^[0-9]{6}$', repr=False)

    @field_validator('username', mode='before')
    @classmethod
    def normalize_username(cls, value):
        if not isinstance(value, str):
            raise ValueError('用户名必须是字符串')
        return value.strip()

    @field_validator('password')
    @classmethod
    def validate_password(cls, value):
        if not re.search(r'[A-Za-z]', value) or not re.search(r'[0-9]', value):
            raise ValueError('密码必须至少包含一个字母和一个数字')
        if any(not char.isprintable() for char in value):
            raise ValueError('密码不能包含控制字符')
        return value

    @model_validator(mode='after')
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError('两次输入的密码不一致')
        return self


class ResetPasswordIn(SendRegisterCodeIn):
    verification_code: str = Field(min_length=6, max_length=6, pattern=r'^[0-9]{6}$', repr=False)
    password: str = Field(min_length=8, max_length=128, repr=False)
    confirm_password: str = Field(min_length=8, max_length=128, repr=False)

    validate_password = field_validator('password')(RegisterIn.validate_password.__func__)
    passwords_match = model_validator(mode='after')(RegisterIn.passwords_match)

class AnswerIn(StrictModel):
    question_id: str
    selected_option_ids: list[str] = Field(max_length=10)


class ResourceIn(StrictModel):
    resource_id: str = Field(min_length=1, max_length=100)
    document_id: str = Field(min_length=1, max_length=100)
    course_id: str
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200000)
    knowledge_point_ids: list[str]
    source: str = '课程教师自编材料'


CourseStatus = Literal['draft', 'published', 'archived']
ContentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CourseCreateIn(StrictModel):
    name: ContentName
    description: str | None = Field(default=None, max_length=10000)


class CourseUpdateIn(StrictModel):
    name: ContentName | None = None
    description: str | None = Field(default=None, max_length=10000)
    status: CourseStatus | None = None

    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('至少提交一个需要修改的字段')
        for name in ('name', 'status'):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f'{name} 不能为 null')
        return self


class ChapterCreateIn(CourseCreateIn):
    sort_order: int = Field(default=0, ge=0, le=2147483647, strict=True)


class KnowledgePointCreateIn(ChapterCreateIn):
    status: Literal['active', 'disabled'] = 'active'
