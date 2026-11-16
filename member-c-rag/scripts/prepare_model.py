"""显式下载固定版本中文 ONNX 模型，并校验官方 LFS SHA256。"""
import argparse
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
MODEL_SHA256 = "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38"
MODEL_BYTES = 94781076
BASE = f"https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/{REVISION}"


def prepare(destination: Path, workers=4):
    destination.mkdir(parents=True, exist_ok=True)
    model = destination / "model_optimized.onnx"
    if model.exists() and hashlib.sha256(model.read_bytes()).hexdigest() == MODEL_SHA256:
        print("模型已存在且摘要正确", flush=True)
    else:
        # 分段可重试，避免部分网络环境下长连接下载大文件停滞。
        chunk_size = 1024 * 1024
        ranges = [(i, start, min(start + chunk_size, MODEL_BYTES) - 1)
                  for i, start in enumerate(range(0, MODEL_BYTES, chunk_size))]

        def fetch(item):
            i, start, end = item
            path = destination / f"model.part-{i:03}"
            if path.exists() and path.stat().st_size == end - start + 1:
                return path
            for attempt in range(3):
                try:
                    with httpx.Client(timeout=25, follow_redirects=True, trust_env=False) as client:
                        response = client.get(BASE + f"/model_optimized.onnx?download=true&part={i}",
                                              headers={"Range": f"bytes={start}-{end}"})
                        response.raise_for_status()
                        if response.status_code != 206 or len(response.content) != end - start + 1:
                            raise ValueError("服务器未按范围返回模型")
                        path.write_bytes(response.content)
                    if i % 10 == 0:
                        print(f"downloaded part {i + 1}/{len(ranges)}", flush=True)
                    return path
                except Exception:
                    if attempt == 2:
                        raise

        with ThreadPoolExecutor(max_workers=workers) as executor:
            parts = list(executor.map(fetch, ranges))
        temporary = destination / "model.complete.tmp"
        with temporary.open("wb") as stream:
            for part in parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, stream)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("模型 SHA256 不匹配 不启用此文件 请清理分段后重新下载")
        temporary.replace(model)
        for part in parts:
            part.unlink()
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
        with httpx.Client(timeout=30, follow_redirects=True, trust_env=False) as client:
            response = client.get(BASE + "/" + name)
            response.raise_for_status()
            (destination / name).write_bytes(response.content)
    print(f"模型就绪 {model.resolve()} SHA256={MODEL_SHA256}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path("data/models/bge-local"))
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    prepare(args.destination, args.workers)
