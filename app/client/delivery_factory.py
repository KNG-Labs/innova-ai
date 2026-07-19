import os
from typing import Any

import httpx

from app.client.crm_client import (
    AmoCrmLeadDeliveryClient,
    CrmClient,
    FakeCrmClient,
    WebhookLeadDeliveryClient,
)
from app.client.queue_client import FakeQueueClient, QueueClient


def get_delivery_provider() -> str:
    return os.environ.get("LEAD_DELIVERY_PROVIDER", "disabled").strip().lower()


def build_crm_client(http_client: httpx.AsyncClient) -> CrmClient:
    provider = get_delivery_provider()

    if provider in ("disabled", "fake"):
        return FakeCrmClient()
    if provider == "webhook":
        url = os.getenv("LEAD_WEBHOOK_URL", "").strip()
        if not url:
            raise RuntimeError("LEAD_WEBHOOK_URL required for provider=webhook")
        return WebhookLeadDeliveryClient(http_client=http_client, url=url)
    if provider == "amocrm":
        base_url = os.getenv("AMOCRM_BASE_URL", "").strip()
        token = os.getenv("AMOCRM_ACCESS_TOKEN", "").strip()
        if not base_url or not token:
            raise RuntimeError("AMOCRM_BASE_URL and AMOCRM_ACCESS_TOKEN required")
        return AmoCrmLeadDeliveryClient(
            http_client=http_client, base_url=base_url, access_token=token
        )
    raise RuntimeError(f"Unsupported LEAD_DELIVERY_PROVIDER: {provider}")


async def build_queue_client() -> tuple[QueueClient, Any]:
    """Возвращает (queue_client, redis_conn_or_None).
    redis_conn закрывает вызвавший."""

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return FakeQueueClient(), None

    import redis.asyncio as aioredis

    from app.client.queue_client import RedisQueueClient

    redis_conn = aioredis.from_url(redis_url)
    return RedisQueueClient(redis_conn), redis_conn
