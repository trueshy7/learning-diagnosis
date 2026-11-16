"""测验结算事务中的任务记录及教师/学生可见状态；网络投递由 worker 完成。"""

from functools import wraps
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..models import DiagnosisTask
from . import exams


def operation(function):
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        try:
            return function(db, *args, **kwargs)
        except HTTPException:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(503, '诊断任务服务暂不可用，请稍后重试') from exc
    return wrapped


def ensure_task(db, attempt):
    """调用方先锁作答；与评分同事务，不发送 HTTP，不在此处提交。"""
    if attempt.status not in ('submitted', 'expired'):
        raise HTTPException(409, '测验尚未结束，不能发起诊断')
    task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.attempt_id == attempt.id)
                     .with_for_update().execution_options(populate_existing=True))
    if task is None:
        now = int(time.time())
        task = DiagnosisTask(id=uuid.uuid4().hex, attempt_id=attempt.id, status='pending', attempt_count=0,
                             next_retry_at=now, created_at=now, updated_at=now)
        db.add(task)
    return task


def task_data(task):
    return {key: getattr(task, key) for key in ('id', 'attempt_id', 'status', 'attempt_count', 'next_retry_at',
        'last_error', 'created_at', 'updated_at', 'delivered_at')}


@operation
def user_task(db, user, attempt_id, *, teacher=False, create=False):
    attempt = exams._teacher_attempt(db, user, attempt_id) if teacher else exams._attempt(db, attempt_id, user.id)
    changed = exams._expire_if_due(db, attempt)
    if attempt.status not in ('submitted', 'expired'):
        raise HTTPException(409, '测验尚未结束，不能发起诊断')
    if create:
        task = ensure_task(db, attempt)
        if task.status == 'failed':
            # 保留同一任务 ID 和冻结输入，确保 D 可用幂等键重放原接收回执。
            task.status, task.attempt_count = 'pending', 0
            task.last_error = task.lease_token = task.lease_expires_at = None
            task.next_retry_at = task.updated_at = int(time.time())
        db.flush()
    else:
        task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.attempt_id == attempt.id))
        if task is None:
            if changed:
                db.commit()  # 关闭自动入队时，404 也不能撤销已经发生的超时结算。
            raise HTTPException(404, '该测验尚未创建诊断任务')
    data = task_data(task)
    if create or changed:
        db.commit()
    return data
