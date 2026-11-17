"""显式资源清单导入；默认不导入待 B 确认的知识点。"""
import argparse
import json
from pathlib import Path

from rag_service.catalog import KnowledgeIndex
from rag_service.config import Settings
from rag_service.files import ingest_file

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "data/knowledge/resources.json"


def build(index, manifest_path=DEFAULT_MANIFEST, include_proposed=False):
    path = Path(manifest_path).resolve()
    rows = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for row in rows:
        if row.get("status") == "proposed" and not include_proposed:
            continue
        local_path = (path.parent / row["file"]).resolve()
        if not local_path.is_relative_to(path.parent):
            raise ValueError("清单路径超出资料根目录")
        results.append(ingest_file(index, row, local_path))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--include-proposed", action="store_true", help="仅用于本地草案演示 不创建 B 业务知识点")
    parser.add_argument("--export", type=Path, default=Path("data/chunks_manifest.json"))
    args = parser.parse_args()
    index = KnowledgeIndex(Settings.from_env())
    results = build(index, args.manifest, args.include_proposed)
    args.export.parent.mkdir(parents=True, exist_ok=True)
    args.export.write_text(json.dumps(index.export_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"imported": len(results), **index.status()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
