import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("RAG_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("初始项目仅允许回环地址；部署前请先与成员 B 完成服务鉴权")
    port = int(os.getenv("RAG_PORT", "8001"))
    if not 1 <= port <= 65535:
        raise ValueError("RAG_PORT 必须在 1–65535 之间")
    uvicorn.run("rag_service.main:app", host=host, port=port, workers=1)
