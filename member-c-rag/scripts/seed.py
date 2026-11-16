"""在项目根目录执行：python -m scripts.seed。会覆盖两个同 ID 样例。"""
import json

from rag_service.config import Settings
from rag_service.catalog import KnowledgeIndex
from rag_service.seed import seed


if __name__ == "__main__":
    settings = Settings.from_env()
    result = seed(KnowledgeIndex(settings))
    print(json.dumps(result, ensure_ascii=False, indent=2))
