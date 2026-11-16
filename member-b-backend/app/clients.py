import httpx
from . import config


async def ingest(payload):
    async with httpx.AsyncClient(timeout=config.SERVICE_TIMEOUT, trust_env=False) as client:
        response = await client.post(config.RAG_URL+'/internal/ingest', json=payload)
        response.raise_for_status()
        return response.json()
