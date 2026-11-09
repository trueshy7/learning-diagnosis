import hashlib
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends, Request, HTTPException, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, SessionLocal, get_db
from .models import (User, LoginSession, Attempt, Course, StudentCourse, TeacherCourse,
                     KnowledgePoint, Question, QuestionState, Resource, ResourceMeta,
                     FullTask, FullDocument)
from .security import current_user, teacher_user, teacher_course, course_access, hash_password, check_password, token_hash
from .schemas import (LoginIn, AttemptIn, ResourceIn, ResourceFileIn, CourseIn, CourseUpdateIn,
                      KnowledgePointIn, KnowledgePointUpdateIn, QuestionIn, QuestionUpdateIn, QuestionStateIn, AskIn)
from .scoring import grade
from .catalog import (seed_demo, course_dict, point_dict, question_dict, course_questions,
                      course_points, question_active, resource_dict)
from .learning import snapshot_questions, wrong_questions, practice_questions, progress
from .uploads import extract_upload
from . import config, clients

@asynccontextmanager
async def lifespan(app):
    # 中期开发环境自动建表；生产部署需改用版本化迁移。
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for name, role in [('student','student'),('teacher','teacher')]:
            if not db.scalar(select(User).where(User.username == name)):
                db.add(User(id=f'{name}-1', username=name, password_hash=hash_password('demo12345'), role=role))
        db.commit()
        seed_demo(db)
        # 旧版只有演示教师；将已有课程归属补齐，避免升级后丢失管理权限。
        for course_id in db.scalars(select(Course.id)):
            if db.get(TeacherCourse, ('teacher-1', course_id)) is None:
                db.add(TeacherCourse(teacher_id='teacher-1', course_id=course_id))
            if db.get(StudentCourse, ('student-1', course_id)) is None:
                db.add(StudentCourse(student_id='student-1', course_id=course_id))
        for task in db.scalars(select(FullTask).where(FullTask.status.in_(['queued','running']))):
            task.status='failed';task.error_code='SERVICE_INTERRUPTED'
            task.error_message='服务重启中断了任务，可在任务页面重试。';task.updated_at=int(time.time())
            if task.document_id:
                document=db.get(FullDocument,task.document_id)
                if document:
                    document.status='failed';document.error_code=task.error_code
                    document.error_message=task.error_message
                    resource=db.get(Resource,document.resource_id)
                    if resource:resource.status='failed'
        db.commit()
    yield

app = FastAPI(title='成员B 课程业务后端', version='0.4.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=['GET','POST','PATCH','DELETE'], allow_headers=['Authorization','Content-Type','Idempotency-Key'])

@app.middleware('http')
async def request_id(request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    if request.url.path.startswith('/api/v2/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

def ok(request, data):
    return {'code':0, 'message':'ok', 'data':data, 'request_id':request.state.request_id}

@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    if request.url.path.startswith('/api/v2/'):
        detail=exc.detail if isinstance(exc.detail,dict) else None
        codes={401:'AUTH_REQUIRED',403:'FORBIDDEN',404:'NOT_FOUND',409:'REFERENCE_CONFLICT',
               410:'RESOURCE_REMOVED',413:'FILE_TOO_LARGE',415:'UNSUPPORTED_FILE_TYPE',
               422:'VALIDATION_ERROR',503:'SERVICE_UNAVAILABLE'}
        return JSONResponse(status_code=exc.status_code,content={
            'code':detail['code'] if detail else codes.get(exc.status_code,'SERVICE_UNAVAILABLE'),
            'message':detail['message'] if detail else str(exc.detail),
            'data':None,'request_id':getattr(request.state,'request_id','')})
    return JSONResponse(status_code=exc.status_code, content={'code':exc.status_code,'message':str(exc.detail),'data':None,'request_id':getattr(request.state,'request_id','')})

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors = [{'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]
    if request.url.path.startswith('/api/v2/'):
        return JSONResponse(status_code=422,content={'code':'VALIDATION_ERROR','message':'请检查填写内容',
            'data':None,'request_id':getattr(request.state,'request_id',''),
            'errors':[{'field':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in errors]})
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

@app.get('/api/v1/auth/me')
def auth_me(request:Request,user:User=Depends(current_user)):
    return ok(request,{'id':user.id,'username':user.username,'role':user.role})

@app.get('/api/v1/courses')
def courses(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    query=select(Course).order_by(Course.id)
    if user.role=='teacher':
        query=query.join(TeacherCourse,TeacherCourse.course_id==Course.id).where(TeacherCourse.teacher_id==user.id)
    else:
        query=query.join(StudentCourse,StudentCourse.course_id==Course.id).where(StudentCourse.student_id==user.id)
    return ok(request,[course_dict(row) for row in db.scalars(query)])

@app.get('/api/v1/courses/{course_id}')
def course_detail(course_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row=course_access(db,user,course_id)
    points=course_points(db,course_id)
    bank=[q for q in course_questions(db,course_id) if q.kind=='single']
    return ok(request,{**course_dict(row),'knowledge_points':[
        {**point_dict(point),'question_count':sum(point.id in q.knowledge_point_ids for q in bank)}
        for point in points],'question_count':len(bank)})

@app.get('/api/v1/courses/{course_id}/questions')
def questions(course_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    return ok(request,{'questions':[question_dict(q) for q in course_questions(db,course_id) if q.kind=='single']})

@app.get('/api/v1/courses/{course_id}/practice')
def practice(course_id:str,request:Request,knowledge_point_id:str|None=None,
             limit:int=Query(default=10,ge=1,le=50),user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    if knowledge_point_id and knowledge_point_id not in {p.id for p in course_points(db,course_id)}:
        raise HTTPException(422,'知识点不属于此课程')
    items=practice_questions(db,user.id,course_id,knowledge_point_id,limit)
    return ok(request,{'course_id':course_id,'knowledge_point_id':knowledge_point_id,
                       'question_ids':[item['id'] for item in items],'questions':items})

@app.get('/api/v1/courses/{course_id}/wrong-questions')
def wrong_book(course_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    return ok(request,{'course_id':course_id,'items':wrong_questions(db,user.id,course_id)})

@app.get('/api/v1/courses/{course_id}/progress')
def learning_progress(course_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    return ok(request,progress(db,user.id,course_id))

@app.post('/api/v1/courses/{course_id}/ask')
async def ask_course(course_id:str,body:AskIn,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    if not set(body.knowledge_point_ids) <= {p.id for p in course_points(db,course_id)}:
        raise HTTPException(422,'知识点不属于此课程')
    allowed=set(db.scalars(select(Resource.resource_id).where(
        Resource.course_id==course_id,Resource.status.in_(['seeded','indexed']))))
    allowed={resource_id for resource_id in allowed if (meta:=db.get(ResourceMeta,resource_id)) is None or meta.active}
    try:
        result=await clients.retrieve({'course_id':course_id,'query':body.query.strip(),
                                       'knowledge_point_ids':body.knowledge_point_ids,'top_k':body.top_k})
        raw=result['evidence']
        if not isinstance(raw,list):raise ValueError('检索证据格式错误')
        required={'evidence_id','document_id','resource_id','title','source','location','text'}
        evidence=[item for item in raw if isinstance(item,dict) and required <= item.keys()
                  and item['resource_id'] in allowed and isinstance(item['text'],str) and item['text'].strip()][:body.top_k]
    except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
        raise HTTPException(502,'检索服务暂不可用') from exc
    citations=[{'number':i,'evidence_id':item['evidence_id'],'document_id':item['document_id'],
                'resource_id':item['resource_id'],'title':item['title'],'source':item['source'],
                'location':item['location']} for i,item in enumerate(evidence,1)]
    answer='\n\n'.join(f'[{i}] {item["text"][:500]}' for i,item in enumerate(evidence,1)) if evidence else None
    return ok(request,{'status':'answered' if evidence else 'insufficient_evidence',
                       'mode':'extractive_retrieval','answer':answer,'citations':citations,
                       'index_version':result.get('index_version')})

@app.get('/api/v1/courses/{course_id}/knowledge-points')
def knowledge_points(course_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    course_access(db,user,course_id)
    rows=course_points(db,course_id)
    bank=[q for q in course_questions(db,course_id) if q.kind=='single']
    return ok(request,{'course_id':course_id,'items':[
        {**point_dict(p),'question_count':sum(p.id in q.knowledge_point_ids for q in bank)} for p in rows]})

@app.post('/api/v1/teacher/courses',status_code=201)
def create_course(body:CourseIn,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    if db.get(Course,body.id):raise HTTPException(409,'课程ID已存在')
    row=Course(**body.model_dump());db.add(row)
    db.add(TeacherCourse(teacher_id=user.id,course_id=body.id))
    for student_id in db.scalars(select(User.id).where(User.role=='student')):
        db.add(StudentCourse(student_id=student_id,course_id=body.id))
    db.commit()
    return ok(request,course_dict(row))

@app.get('/api/v1/teacher/courses')
def teacher_courses(request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Course).join(TeacherCourse,TeacherCourse.course_id==Course.id)
                    .where(TeacherCourse.teacher_id==user.id).order_by(Course.id))
    return ok(request,[course_dict(row) for row in rows])

@app.patch('/api/v1/teacher/courses/{course_id}')
def update_course(course_id:str,body:CourseUpdateIn,request:Request,
                  user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    row=teacher_course(db,user,course_id)
    row.name=body.name.strip();row.description=body.description
    db.commit()
    return ok(request,course_dict(row))

@app.post('/api/v1/teacher/courses/{course_id}/knowledge-points',status_code=201)
def create_point(course_id:str,body:KnowledgePointIn,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    if db.get(KnowledgePoint,body.id):raise HTTPException(409,'知识点ID已存在')
    row=KnowledgePoint(**body.model_dump(),course_id=course_id);db.add(row);db.commit()
    return ok(request,point_dict(row))

@app.patch('/api/v1/teacher/courses/{course_id}/knowledge-points/{point_id}')
def update_point(course_id:str,point_id:str,body:KnowledgePointUpdateIn,request:Request,
                 user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    row=db.get(KnowledgePoint,point_id)
    if row is None or row.course_id!=course_id:raise HTTPException(404,'知识点不存在')
    row.name=body.name.strip();db.commit()
    return ok(request,point_dict(row))

@app.post('/api/v1/teacher/courses/{course_id}/questions',status_code=201)
def create_question(course_id:str,body:QuestionIn,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    if db.get(Question,body.id):raise HTTPException(409,'题目ID已存在')
    point_ids={p.id for p in course_points(db,course_id)}
    if not set(body.knowledge_point_ids) <= point_ids:raise HTTPException(422,'知识点不属于此课程')
    row=Question(**body.model_dump(),course_id=course_id);db.add(row);db.commit()
    return ok(request,question_dict(row,include_answer=True))

@app.get('/api/v1/teacher/courses/{course_id}/questions')
def teacher_questions(course_id:str,request:Request,active:bool|None=None,knowledge_point_id:str|None=None,
                      user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    rows=course_questions(db,course_id,include_inactive=True)
    rows=[q for q in rows if (active is None or question_active(db,q.id)==active)
          and (knowledge_point_id is None or knowledge_point_id in q.knowledge_point_ids)]
    return ok(request,{'questions':[question_dict(q,include_answer=True,active=question_active(db,q.id)) for q in rows]})

@app.patch('/api/v1/teacher/courses/{course_id}/questions/{question_id}')
def update_question(course_id:str,question_id:str,body:QuestionUpdateIn,request:Request,
                    user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    row=db.get(Question,question_id)
    if row is None or row.course_id != course_id:raise HTTPException(404,'题目不存在')
    if not set(body.knowledge_point_ids) <= {p.id for p in course_points(db,course_id)}:
        raise HTTPException(422,'知识点不属于此课程')
    for key,value in body.model_dump().items():setattr(row,key,value)
    db.commit()
    return ok(request,question_dict(row,include_answer=True,active=question_active(db,row.id)))

@app.patch('/api/v1/teacher/courses/{course_id}/questions/{question_id}/status')
def set_question_status(course_id:str,question_id:str,body:QuestionStateIn,request:Request,
                        user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    teacher_course(db,user,course_id)
    row=db.get(Question,question_id)
    if row is None or row.course_id != course_id:raise HTTPException(404,'题目不存在')
    state=db.get(QuestionState,question_id)
    if state is None:db.add(QuestionState(question_id=question_id,active=body.active))
    else:state.active=body.active
    db.commit()
    return ok(request,question_dict(row,include_answer=True,active=body.active))

def get_owned(attempt_id, user, db):
    attempt=db.get(Attempt,attempt_id)
    if not attempt:raise HTTPException(404,'测验记录不存在')
    if attempt.user_id != user.id:raise HTTPException(403,'不能访问其他用户的测验记录')
    return attempt

def agent_input(attempt, db, baseline=None):
    resources=list(db.scalars(select(Resource).where(
        Resource.course_id==attempt.course_id, Resource.status.in_(['seeded','indexed']))))
    resources=[row for row in resources if (meta:=db.get(ResourceMeta,row.resource_id)) is None or meta.active]
    payload={'attempt_id':attempt.id,'course_id':attempt.course_id,'graded_answers':attempt.payload['_graded_answers'],
             'knowledge_points':[point_dict(p) for p in course_points(db,attempt.course_id)],
             'resource_catalog':[{'resource_id':r.resource_id,'title':r.title,
                                  'knowledge_point_ids':r.knowledge_point_ids} for r in resources]}
    if baseline and baseline.payload.get('report'):
        payload['baseline']={'knowledge_points':baseline.payload['report']['knowledge_points']}
    return payload

def public_attempt(attempt):
    return {'id':attempt.id,'course_id':attempt.course_id,'created_at':attempt.created_at,
            **{k:v for k,v in attempt.payload.items() if not k.startswith('_')}}

@app.post('/api/v1/attempts')
async def submit(body:AttemptIn,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db),idempotency_key:str|None=Header(default=None,max_length=200)):
    course_access(db,user,body.course_id)
    baseline=get_owned(body.baseline_attempt_id,user,db) if body.baseline_attempt_id else None
    if baseline and baseline.course_id != body.course_id:raise HTTPException(422,'基线测验不属于本课程')
    # 可选幂等键决定同一提交的稳定ID。真实前端应每次测验生成一次并在重试时沿用。
    canonical=json.dumps(body.model_dump(),sort_keys=True,ensure_ascii=False)
    fingerprint=hashlib.sha256(canonical.encode()).hexdigest()
    attempt_id='att-'+(hashlib.sha256((user.id+':'+idempotency_key).encode()).hexdigest()[:32] if idempotency_key else uuid.uuid4().hex)
    existing=db.get(Attempt,attempt_id)
    if existing:
        if existing.payload.get('_input_hash') != fingerprint:raise HTTPException(409,'同一幂等键不能用于不同答案')
        return ok(request,public_attempt(existing))
    available=[q for q in course_questions(db,body.course_id) if q.kind=='single']
    if body.question_ids is not None:
        by_id={row.id:row for row in available}
        if not set(body.question_ids) <= set(by_id):raise HTTPException(422,'练习包含不存在或已停用的题目')
        available=[by_id[question_id] for question_id in body.question_ids]
    bank=[question_dict(q,include_answer=True) for q in available]
    if not bank:raise HTTPException(422,'该课程尚未配置题目')
    score,max_score,graded=grade(body.answers,bank)
    attempt=Attempt(id=attempt_id,user_id=user.id,course_id=body.course_id,created_at=int(time.time()),payload={
        'score':score,'max_score':max_score,'percentage':round(100*score/max_score,2),'status':'completed',
        'kind':'practice' if body.question_ids is not None else 'quiz',
        'report':None,'ai_status':'processing','ai_message':None,'baseline_attempt_id':body.baseline_attempt_id,
        '_graded_answers':graded,'_question_snapshot':snapshot_questions(bank,body.answers,graded),
        '_submitted_at_ns':time.time_ns(),'_diagnosis_started_ns':time.time_ns(),
        '_input_hash':fingerprint})
    db.add(attempt)
    try:db.commit()  # 先保存成绩，外部AI失败不丢失已完成作答。
    except IntegrityError:
        db.rollback()
        existing=db.get(Attempt,attempt_id) if idempotency_key else None
        if existing and existing.payload.get('_input_hash')==fingerprint:
            return ok(request,public_attempt(existing))
        if existing:raise HTTPException(409,'同一幂等键不能用于不同答案') from None
        raise HTTPException(503,'测验保存冲突，请重试') from None
    report,ai_status,message=await clients.diagnose(agent_input(attempt,db,baseline))
    attempt.payload={**attempt.payload,'report':report,'ai_status':ai_status,'ai_message':message};db.commit()
    return ok(request,public_attempt(attempt))

@app.get('/api/v1/attempts')
def attempts(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=list(db.scalars(select(Attempt).where(Attempt.user_id==user.id)))
    rows.sort(key=lambda row:(row.created_at,row.payload.get('_submitted_at_ns',0),row.id),reverse=True)
    return ok(request,[public_attempt(row) for row in rows])

@app.get('/api/v1/attempts/{attempt_id}')
def attempt_detail(attempt_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return ok(request,public_attempt(get_owned(attempt_id,user,db)))

@app.get('/api/v1/attempts/{attempt_id}/review')
def attempt_review(attempt_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=get_owned(attempt_id,user,db)
    snapshot=attempt.payload.get('_question_snapshot')
    return ok(request,{'attempt_id':attempt.id,'course_id':attempt.course_id,
                       'snapshot_available':snapshot is not None,'questions':snapshot or []})

@app.post('/api/v1/attempts/{attempt_id}/report')
async def regenerate(attempt_id:str,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    attempt=get_owned(attempt_id,user,db)
    if attempt.payload.get('report') and attempt.payload.get('ai_status')=='completed':
        return ok(request,public_attempt(attempt))
    if (attempt.payload.get('ai_status')=='processing' and
        time.time_ns()-attempt.payload.get('_diagnosis_started_ns',0)<int(config.SERVICE_TIMEOUT*2*1e9)):
        raise HTTPException(409,'报告正在生成，请稍后查询')
    baseline_id=attempt.payload.get('baseline_attempt_id')
    baseline=get_owned(baseline_id,user,db) if baseline_id else None
    attempt.payload={**attempt.payload,'ai_status':'processing','_diagnosis_started_ns':time.time_ns()};db.commit()
    report,status,message=await clients.diagnose(agent_input(attempt,db,baseline))
    attempt.payload={**attempt.payload,'report':report,'ai_status':status,'ai_message':message};db.commit()
    return ok(request,public_attempt(attempt))

@app.get('/api/v1/teacher/overview')
def teacher_overview(request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    course_ids=list(db.scalars(select(TeacherCourse.course_id).where(TeacherCourse.teacher_id==user.id)))
    learners=set(db.scalars(select(Attempt.user_id).where(Attempt.course_id.in_(course_ids))))
    return ok(request,{'user_count':len(learners | {user.id}),
        'attempt_count':db.scalar(select(func.count()).select_from(Attempt).where(Attempt.course_id.in_(course_ids))),
        'question_count':db.scalar(select(func.count()).select_from(Question).where(Question.course_id.in_(course_ids))),
        'resource_count':db.scalar(select(func.count()).select_from(Resource).where(
            Resource.course_id.in_(course_ids),Resource.status!='deleted'))})

@app.post('/api/v1/teacher/resources')
async def teacher_ingest(body:ResourceIn,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    return ok(request,await ingest_resource(body,user,db))

@app.post('/api/v1/teacher/resources/file')
async def teacher_upload(body:ResourceFileIn,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    payload=extract_upload(body)
    return ok(request,await ingest_resource(ResourceIn(**payload),user,db))

async def ingest_resource(body:ResourceIn,user:User,db:Session) -> dict:
    teacher_course(db,user,body.course_id)
    if not set(body.knowledge_point_ids) <= {x.id for x in course_points(db,body.course_id)}:raise HTTPException(422,'知识点不属于此课程')
    row=db.get(Resource,body.resource_id)
    if row and row.course_id != body.course_id:raise HTTPException(409,'资源ID已属于其他课程')
    owner=db.scalar(select(Resource).where(Resource.document_id==body.document_id))
    if owner and owner.resource_id != body.resource_id:raise HTTPException(409,'文档ID已属于其他资源')
    try:
        result=await clients.ingest(body.model_dump())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code==409:raise HTTPException(409,'资料ID与C服务现有资料冲突') from exc
        if exc.response.status_code==422:raise HTTPException(422,'资料内容不符合检索服务要求') from exc
        raise HTTPException(502,'资料服务暂不可用，请确认C服务已启动') from exc
    except (httpx.HTTPError,ValueError) as exc:
        raise HTTPException(502,'资料服务暂不可用，请确认C服务已启动') from exc
    values={'document_id':body.document_id,'course_id':body.course_id,'title':body.title,
            'source':body.source,'knowledge_point_ids':body.knowledge_point_ids,
            'status':'indexed','index_version':result.get('index_version'),
            'chunk_count':result.get('chunks',0),'updated_at':int(time.time())}
    if row is None:
        row=Resource(resource_id=body.resource_id,**values);db.add(row)
    else:
        for key,value in values.items():setattr(row,key,value)
    db.commit()
    return {**result,'resource':resource_dict(row)}

@app.get('/api/v1/teacher/resources')
def teacher_resources(request:Request,course_id:str|None=None,include_deleted:bool=False,
                      user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    query=select(Resource).join(TeacherCourse,TeacherCourse.course_id==Resource.course_id).where(
        TeacherCourse.teacher_id==user.id).order_by(Resource.resource_id)
    if course_id is not None:
        teacher_course(db,user,course_id)
        query=query.where(Resource.course_id==course_id)
    if not include_deleted:query=query.where(Resource.status!='deleted')
    return ok(request,{'items':[resource_dict(row) for row in db.scalars(query)]})

@app.get('/api/v1/teacher/resources/{resource_id}/status')
def resource_status(resource_id:str,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    row=db.get(Resource,resource_id)
    if row is None:raise HTTPException(404,'资料不存在')
    teacher_course(db,user,row.course_id)
    return ok(request,resource_dict(row))

@app.delete('/api/v1/teacher/resources/{resource_id}')
async def teacher_delete_resource(resource_id:str,request:Request,user:User=Depends(teacher_user),db:Session=Depends(get_db)):
    row=db.get(Resource,resource_id)
    if row is None or row.status=='deleted':raise HTTPException(404,'资料不存在')
    teacher_course(db,user,row.course_id)
    try:
        result=await clients.delete_resource(resource_id)
    except (httpx.HTTPError,ValueError) as exc:
        raise HTTPException(502,'资料服务暂不可用，未删除本地记录') from exc
    row.status='deleted';row.chunk_count=0;row.updated_at=int(time.time());db.commit()
    return ok(request,{**result,'resource':resource_dict(row)})

# full-v1 与旧版直接提交协议存在同名路径冲突，独立挂载到 /api/v2。
from .full_quiz import router as full_quiz_router
from .full_teacher import router as full_teacher_router
app.include_router(full_quiz_router)
app.include_router(full_teacher_router)
