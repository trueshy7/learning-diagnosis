"""python -m app.dispatch_diagnoses [--watch]；独立于 Web 进程的持久化通知 worker。"""

import argparse
import json
import time

from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .services.diagnosis_dispatch import DispatchConfigurationError, dispatch_batch


def main():
    parser = argparse.ArgumentParser(description='向 D 交付已评分测验的诊断任务 ID')
    parser.add_argument('--limit', type=int, default=10, help='每轮最多交付数量，1～1000')
    parser.add_argument('--watch', action='store_true', help='持续轮询，Ctrl+C 停止')
    parser.add_argument('--poll-interval', type=float, default=2, help='轮询间隔秒数，0.1～60')
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 0.1 <= args.poll_interval <= 60:
        parser.error('limit 必须在 1～1000，poll-interval 必须在 0.1～60 之间')
    try:
        while True:
            try:
                counts = dispatch_batch(SessionLocal, args.limit)
                print(json.dumps(counts, ensure_ascii=False), flush=True)
            except SQLAlchemyError:
                if not args.watch:
                    parser.exit(1, '诊断任务数据库暂不可用，请检查连接和表结构\n')
                print('诊断任务数据库暂不可用，将稍后重试', flush=True)
            if not args.watch:
                break
            time.sleep(args.poll_interval)
    except DispatchConfigurationError as exc:
        parser.exit(1, str(exc) + '\n')
    except KeyboardInterrupt:
        print('诊断任务交付 worker 已停止')


if __name__ == '__main__':
    main()
