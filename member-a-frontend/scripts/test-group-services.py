"""Disposable real B/C/D services for frontend tests; never uses daily databases."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
children = []


def stop(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
with tempfile.TemporaryDirectory(prefix="learnmate-browser-") as temp:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{Path(temp) / 'test.db'}",
           "RAG_DATA_PATH": str(Path(temp) / "index.json"), "RAG_SEED_ON_START": "true",
           "RAG_MODE": "http", "RAG_BASE_URL": "http://127.0.0.1:19281",
           "AGENTS_MODE": "http", "AGENTS_URL": "http://127.0.0.1:19282",
           "RAG_URL": "http://127.0.0.1:19281"}
    try:
        with httpx.Client(timeout=2, trust_env=False) as http:
            for directory, module, port in [
                ("member-c-rag", "rag_service.main:app", 19281),
                ("member-d-agents", "diagnosis_service.main:app", 19282),
                ("member-b-backend", "backend_service.main:app", 19280),
            ]:
                # Refuse to reuse somebody else's running service or data.
                import socket
                with socket.socket() as check:
                    check.bind(("127.0.0.1", port))
                child = subprocess.Popen([sys.executable, "-m", "uvicorn", module,
                                          "--host", "127.0.0.1", "--port", str(port)],
                                         cwd=ROOT / directory, env=env,
                                         stdout=subprocess.DEVNULL)
                children.append(child)
                for _ in range(150):
                    if child.poll() is not None:
                        raise RuntimeError(f"service failed: {directory}")
                    try:
                        if http.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"service timed out: {directory}")
        while all(child.poll() is None for child in children):
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
