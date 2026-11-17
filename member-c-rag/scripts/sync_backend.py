"""停止 HTTP 服务后独立执行一次同步。持续同步由 HTTP lifespan 内单进程执行。"""
import argparse
import json
import os

from rag_service.catalog import KnowledgeIndex
from rag_service.config import Settings
from rag_service.sync import BackendSync


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    sync = BackendSync(KnowledgeIndex(Settings.from_env()), os.getenv("B_URL", "http://127.0.0.1:8000"),
                       os.getenv("B_C_KEY", ""))
    try:
        result = sync.run_once()
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1 if result["failed"] else 0
    finally:
        sync.close()


if __name__ == "__main__":
    raise SystemExit(main())
