"""B 内部数据契约，不直接用作 C/D 原有严格请求模型。"""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .schemas import StrictModel

ERROR_MESSAGES = {
    'index_failed': '索引处理失败',
    'storage_unavailable': '索引存储暂不可用',
    'timeout': '索引处理超时',
    'unknown': '索引处理失败，详情请查看 C 服务日志',
}


class IndexStateIn(StrictModel):
    resource_version: int = Field(ge=1, le=2147483647, strict=True)
    status: Literal['ready', 'failed', 'deleted']
    document_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)] | None = None
    content_hash: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')] | None = None
    error_code: Literal['index_failed', 'storage_unavailable', 'timeout', 'unknown'] | None = None

    @model_validator(mode='after')
    def status_fields(self):
        if self.status == 'ready':
            if self.document_id is None or self.content_hash is None or self.error_code is not None:
                raise ValueError('ready 必须包含 document_id、content_hash，且不能包含 error_code')
        elif self.document_id is not None or self.content_hash is not None:
            raise ValueError('只有 ready 可以包含 document_id 和 content_hash')
        if self.status == 'failed' and self.error_code is None:
            raise ValueError('failed 必须包含 error_code')
        if self.status == 'deleted' and self.error_code is not None:
            raise ValueError('deleted 不能包含 error_code')
        return self


class DiagnosisReceipt(StrictModel):
    task_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    attempt_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    status: Literal['accepted']
