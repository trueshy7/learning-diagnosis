from contextlib import asynccontextmanager
import asyncio
import logging
import os
import threading
from hmac import compare_digest
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .catalog import Conflict, IndexUnavailable, KnowledgeIndex
from .config import Settings
from .contracts import CitationRequest, ScopedRetrieve
from .schemas import Evidence, IngestRequest, IngestResponse, ResourceList, RetrieveRequest, RetrieveResponse
from .seed import seed


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or Settings.from_env()
    index = KnowledgeIndex(selected)

    @asynccontextmanager
    async def lifespan(app):
        if selected.seed_on_start and not selected.data_path.exists():
            seed(index)
        stop = threading.Event()
        worker = None
        if os.getenv("RAG_SYNC_ON_START", "false").lower() == "true":
            from .sync import BackendSync
            interval = float(os.getenv("RAG_SYNC_INTERVAL", "30"))
            if interval < 5:
                raise ValueError("RAG_SYNC_INTERVAL 至少 5 秒")
            sync = BackendSync(index, os.getenv("B_URL", "http://127.0.0.1:8000"), os.getenv("B_C_KEY", ""))

            def run_sync():
                try:
                    while not stop.is_set():
                        try:
                            sync.run_once()
                        except Exception as exc:
                            logging.getLogger(__name__).warning("backend_sync_failed error_type=%s", type(exc).__name__)
                        stop.wait(interval)
                finally:
                    sync.close()

            worker = threading.Thread(target=run_sync, name="rag-backend-sync", daemon=True)
            worker.start()
        try:
            yield
        finally:
            stop.set()
            if worker:
                await asyncio.to_thread(worker.join)

    app = FastAPI(title="成员 C 课程知识库与检索服务", version="0.2.0", lifespan=lifespan)
    app.state.index = index

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def authorize(request: Request):
        if selected.service_key:
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not compare_digest(token.encode(), selected.service_key.encode()):
                raise HTTPException(401, "内部服务凭证无效")

    def check_course(course_id):
        allowed = {item.strip() for item in selected.allowed_course_ids.split(",") if item.strip()}
        if "*" not in allowed and course_id not in allowed:
            raise HTTPException(404, "课程不存在或无权访问")

    @app.exception_handler(IndexUnavailable)
    async def unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": str(exc), "request_id": request.state.request_id})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc), "request_id": request.state.request_id})

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "rag", "mode": index.mode}

    dependencies = [Depends(authorize)]

    @app.post("/internal/ingest", response_model=IngestResponse, dependencies=dependencies)
    def ingest(request: IngestRequest):
        check_course(request.course_id)
        try:
            result = index.ingest(request)
            return {key: result[key] for key in IngestResponse.model_fields}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/internal/retrieve", response_model=RetrieveResponse, dependencies=dependencies)
    def retrieve(request: RetrieveRequest):
        check_course(request.course_id)
        result = index.retrieve(request)
        return {"mode": result["mode"], "index_version": result["index_version"],
                "evidence": [{key: item[key] for key in Evidence.model_fields} for item in result["evidence"]]}

    @app.post("/internal/retrieve-scoped", dependencies=dependencies)
    @app.post("/internal/v1/retrieve", dependencies=dependencies)
    def retrieve_scoped(request: ScopedRetrieve):
        check_course(request.course_id)
        return index.retrieve_scoped(request)

    @app.post("/internal/citations/validate", dependencies=dependencies)
    def citations(request: CitationRequest):
        course_id = index.citation_course(request.retrieval_id)
        if course_id:
            check_course(course_id)
        return index.validate_citations(request.retrieval_id, request.evidence_ids)

    @app.get("/internal/index-status", dependencies=dependencies)
    def status():
        return index.status()

    @app.get("/internal/resources", response_model=ResourceList, dependencies=dependencies)
    def resources(course_id: str = Query(default="course-ds", min_length=1, max_length=128)):
        check_course(course_id)
        return index.list_resources(course_id)

    @app.get("/internal/resources/{resource_id}/state", dependencies=dependencies)
    def resource_state(resource_id: str):
        state = index.resource_state(resource_id)
        if not state:
            raise HTTPException(404, "资料不存在")
        check_course(state["course_id"])
        return state

    @app.delete("/internal/resources/{resource_id}", dependencies=dependencies)
    def delete_resource(resource_id: str):
        if len(resource_id) > 128:
            raise HTTPException(422, "resource_id 最长 128 个字符")
        state = index.resource_state(resource_id)
        if state:
            check_course(state["course_id"])
        return index.delete_resource(resource_id)

    @app.post("/internal/rebuild", dependencies=dependencies)
    def rebuild():
        return index.rebuild()

    return app


app = create_app()
