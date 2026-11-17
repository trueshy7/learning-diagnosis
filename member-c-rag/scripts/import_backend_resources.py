"""把已确认知识点的教学资料提交到 B 现有教师接口，保留 B 生成的业务 ID。"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

import httpx

from rag_service.parsing import parse_file
from scripts.build_knowledge_index import DEFAULT_MANIFEST


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--course-id", default="demo-course-ds-teacher-2")
    parser.add_argument("--apply", action="store_true", help="实际写入 B 默认仅打印资料清单")
    args = parser.parse_args()
    rows = [row for row in json.loads(args.manifest.read_text(encoding="utf-8")) if row["status"] == "confirmed"]
    if not args.apply:
        print(json.dumps({"mode": "preview", "course_id": args.course_id,
                          "resources": [{"title": r["title"], "knowledge_point_ids": r["knowledge_point_ids"]} for r in rows]},
                         ensure_ascii=False, indent=2))
        return
    token = os.getenv("B_TEACHER_TOKEN", "")
    if not token:
        raise ValueError("请先设置 B_TEACHER_TOKEN 教师登录令牌")
    base_url = os.getenv("B_URL", "http://127.0.0.1:8000")
    course_path = quote(args.course_id, safe="")
    mapping_path = Path("data/backend_resource_map.json")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8")) if mapping_path.exists() else {}
    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30, trust_env=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()["data"]
        page, existing = 1, []
        while True:
            data = call("GET", f"/teacher/courses/{course_path}/resources", params={"page": page, "page_size": 100})
            existing.extend(data["items"])
            if len(existing) >= data["total"]:
                break
            page += 1
        for row in rows:
            file_path = (args.manifest.parent / row["file"]).resolve()
            if not file_path.is_relative_to(args.manifest.parent.resolve()):
                raise ValueError("资料文件超出清单根目录")
            body = {"title": row["title"], "source": row["source"], "knowledge_point_ids": row["knowledge_point_ids"],
                    "text": parse_file(file_path)["text"]}
            matches = [r for r in existing if r["title"] == body["title"] and r["source"] == body["source"]]
            if len(matches) > 1:
                raise ValueError("同来源同标题存在多个资料 请先在 B 核对 再重试")
            if matches:
                current = call("GET", f"/teacher/resources/{quote(matches[0]['id'], safe='')}")
                if any(current[k] != body[k] for k in ("title", "text", "source")) or set(current["knowledge_point_ids"]) != set(body["knowledge_point_ids"]):
                    raise ValueError("B 已有同来源资料但内容不同 请使用 B 的带版本 PATCH 人工处理")
            else:
                current = call("POST", f"/teacher/courses/{course_path}/resources", json=body)
                existing.append(current)
            mapping[row["resource_id"]] = {"resource_id": current["id"], "course_id": args.course_id, "version": current["version"]}
            mapping_path.parent.mkdir(parents=True, exist_ok=True)
            mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"ready_for_sync {row['resource_id']} -> {current['id']}", flush=True)


if __name__ == "__main__":
    main()
