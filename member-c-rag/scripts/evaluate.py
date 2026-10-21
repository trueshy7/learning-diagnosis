"""对随包附带的少量演示问题进行命中评估；并非完整课程效果评估。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rag_service.index import LocalIndex
from rag_service.schemas import RetrieveRequest
from rag_service.seed import seed


if __name__ == "__main__":
    questions_path = Path(__file__).resolve().parents[1] / "evaluation" / "questions.json"
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    with TemporaryDirectory() as temporary:
        index = LocalIndex(Path(temporary) / "index.json")
        seed(index)
        hits = 0
        for item in questions:
            response = index.retrieve(RetrieveRequest(course_id="course-ds", query=item["query"], top_k=3))
            resource_ids = {evidence["resource_id"] for evidence in response["evidence"]}
            success = item["expected_resource_id"] in resource_ids
            hits += int(success)
            print(f"{'PASS' if success else 'FAIL'} {item['id']}: {item['query']}")
        print(f"示例命中率@3: {hits}/{len(questions)}；仅 {len(questions)} 条演示题，无泛化结论。")
