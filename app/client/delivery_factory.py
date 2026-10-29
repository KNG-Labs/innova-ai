import os

import httpx

from app.client.crm_client import (
    AmoCrmLeadDeliveryClient,
    CrmClient,
    FakeCrmClient,
    WebhookLeadDeliveryClient,
)
from app.client.queue_client import (
    FakeQueueClient,
    QueueClient,
    CeleryQueueClient,
)


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


def build_queue_client() -> QueueClient:
    if get_delivery_provider() == "disabled":
        return FakeQueueClient()

    if not os.getenv("REDIS_URL", "").strip():
        raise RuntimeError("REDIS_URL is required when lead delivery is enabled")

    from app.worker.celery_app import celery_app

    return CeleryQueueClient(celery_app=celery_app)
