"""可恢复的 D 任务通知：先提交输入快照和租约，再执行 HTTP，最后按租约令牌确认。"""

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import json
import math
import time
from urllib.parse import urlsplit
import uuid

import httpx
from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from .. import config
from ..internal_schemas import DiagnosisReceipt
from ..internal_security import ServicePrincipal
from ..models import DiagnosisTask, ExamAttempt
from .internal import build_diagnosis_input


class DispatchConfigurationError(ValueError):
    pass


class DeliveryError(Exception):
    def __init__(self, message, *, retryable):
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class Delivery:
    task_id: str
    attempt_id: str
    lease_token: str
    payload: dict


def snapshot_hash(data):
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(canonical.encode('utf-8')).hexdigest()


def configuration():
    try:
        httpx.URL(config.DIAGNOSIS_URL)
        url = urlsplit(config.DIAGNOSIS_URL)
        port = url.port
    except (ValueError, httpx.InvalidURL) as exc:
        raise DispatchConfigurationError('DIAGNOSIS_URL 不是有效的服务地址') from exc
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username is not None
            or url.password is not None or url.query or url.fragment or port == 0):
        raise DispatchConfigurationError('DIAGNOSIS_URL 必须是无账号、查询参数和片段的 HTTP(S) 服务地址')
    keys = (config.DIAGNOSIS_SERVICE_KEY, config.D_SERVICE_KEY)
    if any(len(key.encode()) < 32 for key in keys):
        raise DispatchConfigurationError('配置至少 32 字节的 DIAGNOSIS_SERVICE_KEY 和 D_SERVICE_KEY')
    if compare_digest(keys[0].encode(), keys[1].encode()):
        raise DispatchConfigurationError('B→D 与 D→B 必须使用不同密钥')
    if config.C_SERVICE_KEY and any(compare_digest(key.encode(), config.C_SERVICE_KEY.encode()) for key in keys):
        raise DispatchConfigurationError('诊断服务密钥不能与 C_SERVICE_KEY 相同')
    if not math.isfinite(config.DIAGNOSIS_TIMEOUT) or not 1 <= config.DIAGNOSIS_TIMEOUT <= 300:
        raise DispatchConfigurationError('DIAGNOSIS_TIMEOUT 必须在 1～300 秒之间')
    if not 1 <= config.DIAGNOSIS_MAX_ATTEMPTS <= 100:
        raise DispatchConfigurationError('DIAGNOSIS_MAX_ATTEMPTS 必须在 1～100 之间')
    scope = frozenset(item.strip() for item in config.D_SERVICE_COURSE_IDS.split(',') if item.strip())
    if not scope:
        raise DispatchConfigurationError('D_SERVICE_COURSE_IDS 为空，没有可交付的课程')
    return ServicePrincipal('D', scope)


def _due(now):
    return or_(and_(DiagnosisTask.status == 'pending', DiagnosisTask.next_retry_at <= now),
               and_(DiagnosisTask.status == 'dispatching', DiagnosisTask.lease_expires_at <= now))


def _clear_lease(task):
    task.lease_token = task.lease_expires_at = None


def claim_next(session_factory, service):
    now = int(time.time())
    with session_factory() as db:
        query = select(DiagnosisTask.id, DiagnosisTask.attempt_id).join(ExamAttempt).where(_due(now))
        if '*' not in service.course_ids:
            query = query.where(ExamAttempt.course_id.in_(service.course_ids))
        candidates = db.execute(query.order_by(DiagnosisTask.next_retry_at, DiagnosisTask.id).limit(20)).all()
        for candidate in candidates:
            # 所有路径保持 作答→任务 的锁顺序，避免与结算、手动重试形成锁循环。
            attempt = db.scalar(select(ExamAttempt).where(ExamAttempt.id == candidate.attempt_id)
                                .with_for_update(skip_locked=True).execution_options(populate_existing=True))
            if attempt is None or not service.allows(attempt.course_id):
                db.rollback()
                continue
            task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.id == candidate.id, _due(now))
                             .with_for_update(skip_locked=True).execution_options(populate_existing=True))
            if task is None:
                db.rollback()
                continue
            if task.attempt_count >= config.DIAGNOSIS_MAX_ATTEMPTS:
                task.status, task.last_error = 'failed', '交付次数已达上限，请核对 D 接收记录后手动重试'
                task.updated_at = now
                _clear_lease(task)
                db.commit()
                continue
            if attempt.status not in ('submitted', 'expired'):
                task.status, task.last_error = 'failed', '测验尚未结束，不能交付诊断任务'
                task.updated_at = now
                _clear_lease(task)
                db.commit()
                continue
            if task.input_snapshot is None:
                from fastapi import HTTPException
                try:
                    task.input_snapshot = build_diagnosis_input(db, attempt)
                    task.input_hash = snapshot_hash(task.input_snapshot)
                except HTTPException:
                    task.input_snapshot = task.input_hash = None
                    task.status, task.last_error = 'failed', '诊断输入不完整，请检查测验快照'
                    task.updated_at = now
                    _clear_lease(task)
                    db.commit()
                    continue
            if task.input_hash != snapshot_hash(task.input_snapshot):
                task.status, task.last_error = 'failed', '冻结输入摘要不匹配，请检查任务数据'
                task.updated_at = now
                _clear_lease(task)
                db.commit()
                continue
            claimed_at = int(time.time())  # 输入准备可能较慢，租约从准备完成后开始计时。
            task.status, task.lease_token = 'dispatching', uuid.uuid4().hex
            task.lease_expires_at = claimed_at + math.ceil(config.DIAGNOSIS_TIMEOUT) + 30
            task.attempt_count += 1
            task.updated_at = claimed_at
            payload = {'contract_version': 'b-d-task-1', 'task_id': task.id, 'attempt_id': task.attempt_id,
                       'course_id': attempt.course_id, 'input_contract': 'b-internal-1',
                       'input_path': f'/internal/diagnosis-tasks/{task.id}/input', 'input_hash': task.input_hash}
            delivery = Delivery(task.id, task.attempt_id, task.lease_token, payload)
            db.commit()
            return delivery
    return None


def notify_d(client, delivery):
    headers = {'Authorization': 'Bearer ' + config.DIAGNOSIS_SERVICE_KEY,
               'Idempotency-Key': delivery.task_id, 'X-Request-ID': delivery.task_id}
    try:
        with client.stream('POST', config.DIAGNOSIS_URL + '/internal/diagnosis-tasks',
                           headers=headers, json=delivery.payload) as response:
            if response.status_code not in (200, 202):
                if response.status_code == 404:
                    raise DeliveryError('D 尚未提供任务接收接口，请按交付契约接入', retryable=False)
                if response.status_code in (408, 425, 429) or response.status_code >= 500:
                    raise DeliveryError('D 暂时无法接收任务，将稍后重试', retryable=True)
                raise DeliveryError('D 拒绝接收任务，请检查服务凭证及契约', retryable=False)
            content = bytearray()
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > 65536:
                    raise DeliveryError('D 接收回执超出大小限制', retryable=False)
            try:
                receipt = DiagnosisReceipt.model_validate_json(bytes(content))
            except (ValidationError, ValueError) as exc:
                raise DeliveryError('D 接收回执不符合交付契约', retryable=False) from exc
            if receipt.task_id != delivery.task_id or receipt.attempt_id != delivery.attempt_id:
                raise DeliveryError('D 接收回执的任务或测验 ID 不匹配', retryable=False)
            return receipt.model_dump()
    except httpx.HTTPError as exc:
        # 超时可能发生在 D 已接收之后；重试仍使用同一 task_id 和冻结输入。
        raise DeliveryError('D 连接失败或超时，将使用同一任务 ID 重试', retryable=True) from exc


def finish_delivery(session_factory, delivery, *, receipt=None, error=None):
    now = int(time.time())
    with session_factory() as db:
        task = db.scalar(select(DiagnosisTask).where(DiagnosisTask.id == delivery.task_id)
                         .with_for_update().execution_options(populate_existing=True))
        if task is None or task.status != 'dispatching' or task.lease_token != delivery.lease_token:
            return 'stale'
        _clear_lease(task)
        task.updated_at = now
        if receipt is not None:
            task.status, task.receipt, task.last_error = 'delivered', receipt, None
            task.delivered_at = now
        else:
            task.last_error = str(error)
            if error.retryable and task.attempt_count < config.DIAGNOSIS_MAX_ATTEMPTS:
                task.status = 'pending'
                task.next_retry_at = now + min(300, 5 * 2 ** (task.attempt_count - 1))
            else:
                task.status = 'failed'
        status = task.status
        db.commit()
        return status


def dispatch_batch(session_factory, limit=10, *, client=None):
    service = configuration()  # 配置失败不领取任务、不消耗重试次数。
    if not 1 <= limit <= 1000:
        raise ValueError('limit 必须在 1～1000 之间')
    if client is None:
        with httpx.Client(timeout=config.DIAGNOSIS_TIMEOUT, trust_env=False, follow_redirects=False) as http:
            return _dispatch(session_factory, service, limit, http)
    return _dispatch(session_factory, service, limit, client)


def _dispatch(session_factory, service, limit, client):
    counts = {'delivered': 0, 'pending': 0, 'failed': 0, 'stale': 0}
    for _ in range(limit):
        delivery = claim_next(session_factory, service)
        if delivery is None:
            break
        try:
            receipt = notify_d(client, delivery)
        except DeliveryError as exc:
            status = finish_delivery(session_factory, delivery, error=exc)
        else:
            status = finish_delivery(session_factory, delivery, receipt=receipt)
        counts[status] += 1
    return counts
