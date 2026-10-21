import hashlib
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends, Request, HTTPException, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import Base, engine, SessionLocal, get_db
from .models import User, LoginSession, Attempt
from .security import current_user, teacher_user, hash_password, check_password, token_hash
from .schemas import LoginIn, AttemptIn, ResourceIn
from .fixtures import COURSE, KNOWLEDGE_POINTS, QUESTIONS, RESOURCES, public_question
from .scoring import grade
from . import config, clients

@asynccontextmanager
async def lifespan(app):
    # 初始骨架只建少量业务表；正式迭代使用迁移工具，不以create_all替代迁移。
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, role in [('student','student'),('teacher','teacher')]:
            if not db.scalar(select(User).where(User.username == name)):
                db.add(User(id=f'{name}-1', username=name, password_hash=hash_password('demo12345'), role=role))
        db.commit()
    yield

app = FastAPI(title='成员B 课程业务后端骨架', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=['GET','POST','DELETE'], allow_headers=['Authorization','Content-Type','Idempotency-Key'])

@app.middleware('http')
async def request_id(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    return response

def ok(request, data):
    return {'code':0, 'message':'ok', 'data':data, 'request_id':request.state.request_id}

@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={'code':exc.status_code,'message':str(exc.detail),'data':None,'request_id':getattr(request.state,'request_id','')})

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors = [{'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]
    return JSONResponse(status_code=422, content={'code':422,'message':'请求参数不符合接口约定','data':{'errors':errors},'request_id':getattr(request.state,'request_id','')})

@app.get('/health')
def health():
    return {'status':'ok', 'service':'backend', 'mode':'sqlite_demo' if config.DATABASE_URL.startswith('sqlite') else 'sql_database'}

@app.post('/api/v1/auth/login')
def login(body:LoginIn, request:Request, db:Session=Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not check_password(body.password,user.password_hash):
        raise HTTPException(401,'用户名或密码错误')
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token),user_id=user.id,expires_at=int(time.time())+86400));db.commit()
    return ok(request,{'access_token':token,'token_type':'bearer','user':{'id':user.id,'username':user.username,'role':user.role}})

@app.post('/api/v1/auth/logout')
def logout(request:Request, authorization:str=Header(), user:User=Depends(current_user), db:Session=Depends(get_db)):
    session = db.get(LoginSession,token_hash(authorization.split(' ',1)[1]))
    if session:db.delete(session);db.commit()
    return ok(request,{'logged_out':True})

@app.get('/api/v1/courses')
def courses(request:Request,user:User=Depends(current_user)):
    return ok(request,[COURSE])

@app.get('/api/v1/courses/{course_id}/questions')
def questions(course_id:str,request:Request,user:User=Depends(current_user)):
    if course_id != COURSE['id']:raise HTTPException(404,'课程不存在')
    return ok(request,{'questions':[public_question(q) for q in QUESTIONS]})

def get_owned(attempt_id, user, db):
    attempt=db.get(Attempt,attempt_id)
    if not attempt:raise HTTPException(404,'测验记录不存在')
    if attempt.user_id != user.id:raise HTTPException(403,'不能访问其他用户的测验记录')
    return attempt

def agent_input(attempt, baseline=None):
    payload={'attempt_id':attempt.id,'course_id':attempt.course_id,'graded_answers':attempt.payload['_graded_answers'],
             'knowledge_points':KNOWLEDGE_POINTS,'resource_catalog':RESOURCES}
    if baseline and baseline.payload.get('report'):
        payload['baseline']={'knowledge_points':baseline.payload['report']['knowledge_points']}
    return payload

def public_attempt(attempt):
    return {'id':attempt.id,'course_id':attempt.course_id,'created_at':attempt.created_at,
            **{k:v for k,v in attempt.payload.items() if not k.startswith('_')}}

@app.post('/api/v1/attempts')
async def submit(body:AttemptIn,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db),idempotency_key:str|None=Header(default=None,max_length=200)):
    if body.course_id != COURSE['id']:raise HTTPException(404,'课程不存在')
    baseline=get_owned(body.baseline_attempt_id,user,db) if body.baseline_attempt_id else None
    # 可选幂等键决定同一提交的稳定ID。真实前端应每次测验生成一次并在重试时沿用。
    canonical=json.dumps(body.model_dump(),sort_keys=True,ensure_ascii=False)
    fingerprint=hashlib.sha256(canonical.encode()).hexdigest()
    attempt_id='att-'+(hashlib.sha256((user.id+':'+idempotency_key).encode()).hexdigest()[:32] if idempotency_key else uuid.uuid4().hex)
    existing=db.get(Attempt,attempt_id)
    if existing:
        if existing.payload.get('_input_hash') != fingerprint:raise HTTPException(409,'同一幂等键不能用于不同答案')
        return ok(request,public_attempt(existing))
    score,max_score,graded=grade(body.answers)
    attempt=Attempt(id=attempt_id,user_id=user.id,course_id=body.course_id,created_at=int(time.time()),payload={
        'score':score,'max_score':max_score,'percentage':round(100*score/max_score,2),'status':'completed',
        'report':None,'ai_status':'processing','ai_message':None,'baseline_attempt_id':body.baseline_attempt_id,
        '_graded_answers':graded,'_input_hash':fingerprint})
    db.add(attempt);db.commit()  # 先保存成绩，外部AI失败不丢失已完成作答。
    report,ai_status,message=await clients.diagnose(agent_input(attempt,baseline))
    attempt.payload={**attempt.payload,'report':report,'ai_status':ai_status,'ai_message':message};db.commit()
    return ok(request,public_attempt(attempt))

@app.get('/api/v1/attempts')
def attempts(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Attempt).where(Attempt.user_id==user.id).order_by(Attempt.created_at.desc())).all()
    return ok(request,[public_attempt(row) for row in rows])

@app.get('/api/v1/attempts/{attempt_id}')
def attempt_detail(attempt_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return ok(request,public_attempt(get_owned(attempt_id,user,db)))

@app.post('/api/v1/attempts/{attempt_id}/report')
async def regenerate(attempt_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=get_owned(attempt_id,user,db)
    baseline_id=attempt.payload.get('baseline_attempt_id')
    baseline=get_owned(baseline_id,user,db) if baseline_id else None
    report,status,message=await clients.diagnose(agent_input(attempt,baseline))
    attempt.payload={**attempt.payload,'report':report,'ai_status':status,'ai_message':message};db.commit()
    return ok(request,public_attempt(attempt))

@app.get('/api/v1/teacher/overview')
def teacher_overview(request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    return ok(request,{'user_count':db.scalar(select(func.count()).select_from(User)),
        'attempt_count':db.scalar(select(func.count()).select_from(Attempt)),
        'question_count':len(QUESTIONS),'resource_count':len(RESOURCES)})

@app.post('/api/v1/teacher/resources')
async def teacher_ingest(body:ResourceIn,request:Request,user:User=Depends(teacher_user)):
    if body.course_id != COURSE['id']:raise HTTPException(404,'课程不存在')
    if not set(body.knowledge_point_ids) <= {x['id'] for x in KNOWLEDGE_POINTS}:raise HTTPException(422,'知识点不属于此课程')
    try:result=await clients.ingest(body.model_dump())
    except (httpx.HTTPError,ValueError):raise HTTPException(502,'资料服务暂不可用，请确认C服务已启动')
    return ok(request,result)
