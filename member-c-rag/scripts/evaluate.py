"""固定20题 Hit@5；参考证据按资源与原文摘句共同核验，未作人工复核标记。"""
import argparse
import json
import platform
import statistics
import time
import uuid
from dataclasses import replace
from pathlib import Path

from rag_service.catalog import KnowledgeIndex
from rag_service.config import Settings
from rag_service.contracts import ScopedRetrieve
from scripts.build_knowledge_index import build

ROOT = Path(__file__).resolve().parents[1]


def scopes(index, course_id):
    return [{k: d[k] for k in ("resource_id", "resource_version", "document_id", "content_hash")}
            for d in index.export_manifest()["documents"].values() if d["course_id"] == course_id]


def evaluate(index, questions, negatives):
    if len(questions) != 20:
        raise ValueError("固定评测必须为20条可回答问题 无答案另计")
    rows, durations, valid, total = [], [], 0, 0
    for question in questions:
        started = time.perf_counter()
        # 交替使用标签过滤与全课程检索，避免全部借助标签缩小到少数答案。
        result = index.retrieve_scoped(ScopedRetrieve(
            course_id=question["course_id"], query=question["query"],
            knowledge_point_ids=question.get("knowledge_point_ids", []),
            resource_scope=scopes(index, question["course_id"]), top_k=5))
        durations.append((time.perf_counter() - started) * 1000)
        hit = any(item["resource_id"] == reference["resource_id"] and reference["excerpt"] in item["text"]
                  for item in result["evidence"] for reference in question["expected"])
        for item in result["evidence"]:
            doc = index.export_manifest()["documents"].get(item["document_id"])
            location = item["location"]
            correct = bool(doc and doc["resource_id"] == item["resource_id"] and doc["course_id"] == question["course_id"]
                           and item["text"] == doc["text"][location["start"]:location["end"]])
            valid += int(correct)
            total += 1
        rows.append({"id": question["id"], "query": question["query"], "hit": hit,
                     "expected": question["expected"], "mode": result["mode"],
                     "retrieved": [{k: e[k] for k in ("resource_id", "chunk_id", "score", "location")} for e in result["evidence"]],
                     "elapsed_ms": round(durations[-1], 3)})
    no_answer = []
    for item in negatives:
        result = index.retrieve_scoped(ScopedRetrieve(course_id=item["course_id"], query=item["query"],
                                                     resource_scope=scopes(index, item["course_id"]), top_k=5))
        no_answer.append({"id": item["id"], "query": item["query"], "empty": not result["evidence"],
                          "top_score": result["evidence"][0]["score"] if result["evidence"] else None,
                          "mode": result["mode"]})
    hits = sum(row["hit"] for row in rows)
    return {"hits": hits, "denominator": 20, "hit_at_5": hits / 20, "target_passed": hits >= 16,
            "citation_valid": valid, "citation_total": total, "citation_valid_rate": valid / total if total else None,
            "latency_ms_mean": round(statistics.mean(durations), 3),
            "latency_ms_p95": round(sorted(durations)[18], 3), "questions": rows,
            "failed_question_ids": [row["id"] for row in rows if not row["hit"]], "unanswerable": no_answer}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["keyword", "chroma", "both"], default="keyword")
    parser.add_argument("--extended", action="store_true", help="包含待B确认的4个知识点 本地草案评测")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results.json")
    args = parser.parse_args()
    questions = json.loads((ROOT / "evaluation" / ("questions_extended.json" if args.extended else "questions.json")).read_text(encoding="utf-8"))
    negatives = json.loads((ROOT / "evaluation/unanswerable.json").read_text(encoding="utf-8"))
    configs = [(b, size, overlap) for b in (["keyword", "chroma"] if args.backend == "both" else [args.backend])
               for size, overlap in [(400, 60), (700, 100)]]
    report = {"generated_at": int(time.time()), "python": platform.python_version(),
              "dataset": "extended_proposal_20" if args.extended else "ts_confirmed_20",
              "review_status": "pending_peer_review", "results": []}
    for backend, size, overlap in configs:
        folder = ROOT / "data" / ("eval-" + uuid.uuid4().hex)
        settings = replace(Settings.from_env(), data_path=folder / "catalog.json", chroma_path=folder / "chroma",
                           seed_on_start=False, backend=backend, chunk_size=size, chunk_overlap=overlap, fallback=False)
        index = KnowledgeIndex(settings)
        started = time.perf_counter()
        build(index, include_proposed=args.extended)
        build_ms = round((time.perf_counter() - started) * 1000, 3)
        measured = evaluate(index, questions, negatives)
        result = {"backend": backend, "chunk_size": size, "chunk_overlap": overlap,
                  "build_ms": build_ms,
                  "index": index.status(), **measured}
        report["results"].append(result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{backend} {size}/{overlap}: Hit@5 {measured['hits']}/20; citations {measured['citation_valid']}/{measured['citation_total']}", flush=True)
    return report


if __name__ == "__main__":
    main()
