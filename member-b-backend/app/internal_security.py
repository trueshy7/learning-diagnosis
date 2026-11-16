"""C/D 服务身份和显式课程授权，配置错误时关闭访问。"""

from dataclasses import dataclass
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

bearer = HTTPBearer(auto_error=False, scheme_name='InternalServiceBearer',
                    description='C 或 D 的独立服务密钥，不是用户登录 Token')


@dataclass(frozen=True)
class ServicePrincipal:
    name: str
    course_ids: frozenset[str]

    def allows(self, course_id):
        return '*' in self.course_ids or course_id in self.course_ids


def _authenticate(name, credentials):
    if credentials is None:
        raise HTTPException(401, '需要内部服务凭证', headers={'WWW-Authenticate': 'Bearer'})
    key = getattr(config, f'{name}_SERVICE_KEY')
    other = config.D_SERVICE_KEY if name == 'C' else config.C_SERVICE_KEY
    if len(key.encode('utf-8')) < 32 or (other and compare_digest(key.encode(), other.encode())):
        raise HTTPException(503, '内部服务凭证未正确配置')
    if not compare_digest(credentials.credentials.encode(), key.encode()):
        raise HTTPException(401, '内部服务凭证无效', headers={'WWW-Authenticate': 'Bearer'})
    ids = frozenset(item.strip() for item in getattr(config, f'{name}_SERVICE_COURSE_IDS').split(',') if item.strip())
    return ServicePrincipal(name, ids)


def c_service(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    return _authenticate('C', credentials)


def d_service(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    return _authenticate('D', credentials)


CService = Annotated[ServicePrincipal, Depends(c_service)]
DService = Annotated[ServicePrincipal, Depends(d_service)]
