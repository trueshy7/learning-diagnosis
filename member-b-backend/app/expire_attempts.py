"""python -m app.expire_attempts --limit 100；可由系统定时任务周期调用。"""

import argparse

from .database import SessionLocal
from .services.exams import expire_due_attempts


def main():
    parser = argparse.ArgumentParser(description='结算已到截止时间的学生测验（MySQL 8+）')
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit 必须在 1～1000 之间')
    with SessionLocal() as db:
        count = expire_due_attempts(db, args.limit)
    print(f'已结算 {count} 条超时测验')


if __name__ == '__main__':
    main()
