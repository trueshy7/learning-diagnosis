import httpx
from . import config

async def diagnose(payload):
    if config.AGENTS_MODE == 'disabled':
        return None, 'disabled', '诊断服务未启用；成绩已保存。'
    try:
        async with httpx.AsyncClient(timeout=config.SERVICE_TIMEOUT, trust_env=False) as client:
            response = await client.post(config.AGENTS_URL+'/internal/diagnose-and-recommend', json=payload)
            response.raise_for_status()
            report = response.json()
            if report.get('attempt_id') != payload['attempt_id'] or not isinstance(report.get('knowledge_points'),list):
                raise ValueError('诊断响应与测验不匹配')
            # TODO B/D: 接入共享完整Report模型，补充字段和引用关系校验。
            return report, 'completed', None
    except (httpx.HTTPError, ValueError, TypeError):
        return None, 'unavailable', '诊断服务暂不可用；成绩已保存，启动D服务后可重新生成。'

async def ingest(payload):
    async with httpx.AsyncClient(timeout=config.SERVICE_TIMEOUT, trust_env=False) as client:
        response = await client.post(config.RAG_URL+'/internal/ingest', json=payload)
        response.raise_for_status()
        return response.json()
