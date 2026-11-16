import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models  # 注册模型，确保建表时 metadata 包含所有表。
from .api import auth, courses, diagnosis_tasks, exams, internal, resources, teacher, user
from .database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 仅创建缺失的表；连接或建表失败时让启动失败，避免接口带病运行。
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        engine.dispose()

app = FastAPI(
    title='AI学习诊断系统',
    version='0.1.0',
    lifespan=lifespan,
)

@app.middleware('http')
async def request_id(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={
        'code': exc.status_code, 'message': str(exc.detail), 'data': None,
        'request_id': getattr(request.state, 'request_id', ''),
    })


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors = [
        {'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={
        'code': 422, 'message': '请求参数不符合接口约定',
        'data': {'errors': errors},
        'request_id': getattr(request.state, 'request_id', ''),
    })


@app.get('/health')
def health():
    return {
        'status': 'ok', 'service': 'backend',
        'mode': 'sql_database',
    }


# app.include_router(auth.router)
app.include_router(auth.user_router)
app.include_router(courses.router)
app.include_router(teacher.router)
app.include_router(user.router)
app.include_router(exams.router)
app.include_router(resources.router)
app.include_router(internal.router)
app.include_router(diagnosis_tasks.router)
