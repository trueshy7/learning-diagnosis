"""从项目根目录运行 B/C 真 HTTP + 独立 MySQL 验证，不使用业务数据库。"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if not os.getenv('TEST_MYSQL_URL'):
        print('请设置 TEST_MYSQL_URL（具有建库/删库权限的独立 MySQL 测试连接）；不使用 DATABASE_URL。', file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    return subprocess.call([
        sys.executable, '-m', 'pytest', '-q',
        'tests/test_bc_integration.py', 'tests/test_mysql_internal.py',
    ], cwd=root / 'member-b-backend')


if __name__ == '__main__':
    raise SystemExit(main())
