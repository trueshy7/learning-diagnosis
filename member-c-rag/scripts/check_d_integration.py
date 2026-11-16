"""启动真实 C HTTP 服务，调用仓库内 D 的实际 HttpRetriever；不使用 mock 检索。"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from rag_service.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    Settings.from_env()  # 与服务一致地加载本机 .env，记录实际选择的后端。
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    temp_root = ROOT / "data" / "test-temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    # Windows 上 Rust/杀毒软件可能短暂保留刚终止进程的文件句柄。
    # 临时文件清理不改变已经核验的 HTTP 调用结果。
    with tempfile.TemporaryDirectory(dir=temp_root, ignore_cleanup_errors=True) as scratch:
        env = os.environ.copy()
        env.update(RAG_PORT=str(port), RAG_HOST="127.0.0.1", RAG_SEED_ON_START="true", RAG_SYNC_ON_START="false",
                   RAG_DATA_PATH=str(Path(scratch) / "catalog.json"), RAG_CHROMA_PATH=str(Path(scratch) / "chroma"),
                   RAG_SERVICE_KEY="", RAG_ALLOWED_COURSE_IDS="*")
        output = (Path(scratch) / "server.log").open("w", encoding="utf-8")
        process = subprocess.Popen([sys.executable, "-m", "rag_service"], cwd=ROOT, env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            base_url = f"http://127.0.0.1:{port}"
            with httpx.Client(timeout=2, trust_env=False) as client:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError("C 服务启动失败 请查看 data/test-temp 临时日志")
                    try:
                        if client.get(base_url + "/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.5)
                else:
                    raise RuntimeError("C 服务启动超时")
            sys.path.insert(0, str(ROOT.parent / "member-d-agents"))
            from diagnosis_service.main import app
            previous = {key: os.environ.get(key) for key in ("RAG_MODE", "RAG_BASE_URL", "RAG_TIMEOUT_SECONDS")}
            os.environ.update(RAG_MODE="http", RAG_BASE_URL=base_url, RAG_TIMEOUT_SECONDS="30")
            try:
                request = json.loads((ROOT.parent / "member-d-agents/examples/request.json").read_text(encoding="utf-8-sig"))
                with TestClient(app) as client:
                    response = client.post("/internal/diagnose-and-recommend", json=request)
                    response.raise_for_status()
                    result = response.json()
                if not result["evidence"] or any(e["evidence_id"].startswith("mock:") for e in result["evidence"]):
                    raise AssertionError("D 未获得 C 的真实证据")
                report = {"generated_at": int(time.time()), "transport": "real_loopback_http",
                          "backend": env.get("RAG_BACKEND", "keyword"),
                          "llm_called": False, "note": "D 当前为规则模板 不代表已完成真实 LLM 闭环",
                          "request": request, "response": result}
                path = ROOT / "evaluation" / f"d_http_integration_{report['backend']}.json"
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"D -> C HTTP 通过 证据数={len(result['evidence'])} backend={report['backend']}")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            output.close()


if __name__ == "__main__":
    main()
