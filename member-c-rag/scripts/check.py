"""把测试临时文件放在本模块下，适配 Windows 受限临时目录。"""
import tempfile
import unittest
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    temp_root = root / "data" / "test-temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    previous = tempfile.tempdir
    try:
        with tempfile.TemporaryDirectory(dir=temp_root) as scratch:
            tempfile.tempdir = scratch
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(root / "tests")))
    finally:
        tempfile.tempdir = previous
    raise SystemExit(not result.wasSuccessful())
