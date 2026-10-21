from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from .config import Settings
from .index import INDEX_VERSION, MODE, LocalIndex
from .schemas import IngestRequest, IngestResponse, ResourceList, RetrieveRequest, RetrieveResponse
from .seed import seed


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or Settings.from_env()
    index = LocalIndex(selected.data_path, selected.chunk_size, selected.chunk_overlap)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 只在尚无索引文件时自动导入。用户删除的资料不会在下次启动时复活。
        if selected.seed_on_start and not selected.data_path.exists():
            seed(index)
        yield

    app = FastAPI(title="成员 C · 资料与检索服务", version="0.1.0", lifespan=lifespan)
    app.state.index = index

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "rag", "mode": MODE}

    @app.post("/internal/ingest", response_model=IngestResponse)
    def ingest(request: IngestRequest):
        try:
            return index.ingest(request)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/retrieve", response_model=RetrieveResponse)
    def retrieve(request: RetrieveRequest):
        return index.retrieve(request)

    @app.get("/internal/resources", response_model=ResourceList)
    def resources(course_id: str = Query(default="course-ds", min_length=1, max_length=128)):
        return index.list_resources(course_id)

    @app.delete("/internal/resources/{resource_id}")
    def delete_resource(resource_id: str):
        if len(resource_id) > 128:
            raise HTTPException(status_code=422, detail="resource_id 最长 128 个字符")
        return index.delete_resource(resource_id)

    @app.post("/internal/rebuild")
    def rebuild():
        return index.rebuild()

    return app


app = create_app()
