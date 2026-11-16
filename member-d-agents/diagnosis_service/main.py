from fastapi import Depends, FastAPI
from dotenv import load_dotenv

from .models import DiagnoseRequest, Report
from .orchestrator import run_pipeline
from .rag_client import get_retriever


load_dotenv(dotenv_path=".env", override=False)
app = FastAPI(title="成员 D · 学习诊断与规则协作服务", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "agents", "mode": "rule_template_demo"}


@app.post("/internal/diagnose-and-recommend", response_model=Report)
async def diagnose_and_recommend(request: DiagnoseRequest, retriever=Depends(get_retriever)):
    return await run_pipeline(request, retriever)

