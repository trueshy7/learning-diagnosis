"""演示同义查询、证据回溯和无答案；不生成模型解释。"""
import json

from rag_service.catalog import KnowledgeIndex
from rag_service.config import Settings
from rag_service.contracts import ScopedRetrieve


if __name__ == "__main__":
    index = KnowledgeIndex(Settings.from_env())
    course_id = "demo-course-ds-teacher-2"
    scope = [{key: doc[key] for key in ("resource_id", "resource_version", "document_id", "content_hash")}
             for doc in index.export_manifest()["documents"].values() if doc["course_id"] == course_id]
    for query in ("排队等待时较早到达的人先处理，对应哪种顺序原则？", "本班期末考试具体时间及教室"):
        result = index.retrieve_scoped(ScopedRetrieve(course_id=course_id, query=query, resource_scope=scope, top_k=3))
        print(json.dumps({"query": query, **result}, ensure_ascii=False))
