"""业务路由及统一成功响应。"""

from fastapi import Request


def ok(request: Request, data):
    return {
        'code': 0,
        'message': 'ok',
        'data': data,
        'request_id': request.state.request_id,
    }
