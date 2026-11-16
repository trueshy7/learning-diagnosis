"""在项目根目录执行：python -m scripts.rebuild。保留原文并重新分段。"""
import json

from rag_service.config import Settings
from rag_service.catalog import KnowledgeIndex


if __name__ == "__main__":
    settings = Settings.from_env()
    result = KnowledgeIndex(settings).rebuild()
    print(json.dumps(result, ensure_ascii=False, indent=2))
