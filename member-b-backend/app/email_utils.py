"""本项目使用的普通 ASCII 邮箱地址校验与规范化。"""

import re


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('邮箱格式不正确')
    email = value.strip().lower()
    if len(email) > 255 or email.count('@') != 1:
        raise ValueError('邮箱格式不正确')
    local, domain = email.split('@')
    if (
        not 1 <= len(local) <= 64
        or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
        or local.startswith('.') or local.endswith('.') or '..' in local
        or len(domain.split('.')) < 2
        or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part)
               for part in domain.split('.'))
    ):
        raise ValueError('邮箱格式不正确')
    return email
