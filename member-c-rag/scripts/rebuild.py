"""在项目根目录执行：python -m scripts.rebuild。保留原文并重新分段。"""
import json

from rag_service.config import Settings
from rag_service.index import LocalIndex


if __name__ == "__main__":
    settings = Settings.from_env()
    result = LocalIndex(settings.data_path, settings.chunk_size, settings.chunk_overlap).rebuild()
    print(json.dumps(result, ensure_ascii=False, indent=2))
