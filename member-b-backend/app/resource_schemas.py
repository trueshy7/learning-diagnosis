"""纯文本课程资料请求模型，身份、归属、版本由服务管理。"""

import json
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator, model_validator

from .schemas import StrictModel

ResourceId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
ResourceTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ResourceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200000)]
ResourceSource = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
KnowledgePointIds = Annotated[list[ResourceId], Field(min_length=1, max_length=50)]


class ResourceCreateIn(StrictModel):
    title: ResourceTitle
    text: ResourceText
    knowledge_point_ids: KnowledgePointIds
    source: ResourceSource = '课程教师自编材料'

    @field_validator('knowledge_point_ids')
    @classmethod
    def unique_points(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError('关联知识点不能重复')
        return value


class ResourceUpdateIn(StrictModel):
    expected_version: int = Field(ge=1, le=2147483647, strict=True)
    title: ResourceTitle | None = None
    text: ResourceText | None = None
    knowledge_point_ids: KnowledgePointIds | None = None
    source: ResourceSource | None = None

    unique_points = field_validator('knowledge_point_ids')(ResourceCreateIn.unique_points.__func__)

    @model_validator(mode='after')
    def require_changes(self):
        editable = self.model_fields_set - {'expected_version'}
        if not editable:
            raise ValueError('至少提交一个需要修改的资料字段')
        if any(getattr(self, field) is None for field in editable):
            raise ValueError('提交的资料字段不能为 null')
        return self


class ResourceUploadIn(StrictModel):
    title: ResourceTitle
    knowledge_point_ids: KnowledgePointIds
    source: ResourceSource = '课程教师自编材料'

    @field_validator('knowledge_point_ids', mode='before')
    @classmethod
    def normalize_form_points(cls, value):
        """multipart 数组可表现为重复字段、单值、CSV 或旧 JSON 数组文本。"""
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return value  # 交给列表类型校验，不能将 null 等值解释为知识点。
        result = []
        for item in value:
            if not isinstance(item, str):
                result.append(item)
                continue
            item = item.strip()
            if item.startswith('['):
                try:
                    points = json.loads(item)
                except ValueError as exc:
                    raise ValueError('知识点 JSON 数组格式不正确，请使用英文双引号和完整方括号') from exc
                result.extend(points)
            elif item.startswith(('{', '"', "'")) or item in ('null', 'true', 'false'):
                raise ValueError('请填写知识点 ID、英文逗号分隔的 ID，或 JSON 数组')
            else:
                result.extend(part.strip() for part in item.split(','))
            if len(result) > 50:
                raise ValueError('最多关联 50 个知识点')
        return [item.strip() if isinstance(item, str) else item for item in result]

    unique_points = field_validator('knowledge_point_ids')(ResourceCreateIn.unique_points.__func__)
