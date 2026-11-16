"""资料索引版本、规范化摘要和事务内待同步标记，不进行网络调用。"""

from hashlib import sha256
import json
import time

from sqlalchemy import select

from ..models import ResourceIndexState


def content_hash(resource, point_ids):
    payload = {key: getattr(resource, key) for key in ('course_id', 'title', 'text', 'source')}
    payload['knowledge_point_ids'] = sorted(point_ids)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(canonical.encode('utf-8')).hexdigest()


def index_status(resource, state):
    if state is None or state.resource_version != resource.version:
        return 'pending'
    if state.status == 'ready' and (resource.status != 'active' or state.indexed_version != resource.version
                                  or not state.document_id or not state.indexed_hash):
        return 'pending'
    if state.status == 'deleted' and resource.status != 'deleted':
        return 'pending'
    return state.status


def mark_pending(db, resource, *, new=False):
    # 调用方已锁住资料；回报处理也先锁资料，避免旧回报和新版本交叉提交。
    state = None if new else db.scalar(select(ResourceIndexState).where(
        ResourceIndexState.resource_id == resource.id).with_for_update().execution_options(populate_existing=True))
    if state is None:
        state = ResourceIndexState(resource_id=resource.id)
        db.add(state)
    state.resource_version = resource.version
    state.status = 'pending'
    state.last_error = None
    state.acknowledged_at = None
    state.updated_at = int(time.time())
    return state
