import asyncio
import os

import httpx
from uuid import UUID

from app.worker.celery_app import celery_app
from app.client.delivery_factory import build_crm_client
from app.db.session import create_engine, create_session_maker
from app.service.lead_delivery_service import LeadDeliveryService

from app.models.dialog_session_model import DialogSession  # noqa: F401
from app.models.knowledge_model import KnowledgeDocument  # noqa: F401
from app.models.message_model import Message  # noqa: F401
from app.models.user_model import User  # noqa: F401
from app.models.lead_delivery_attempt_model import LeadDeliveryAttemptModel  # noqa: F401


@celery_app.task(
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
    ),
    retry_kwargs={"max_retries": 3},
    retry_backoff=2,
    retry_jitter=True,
)
def deliver_lead(lead_id: str) -> None:
    asyncio.run(_deliver_lead(UUID(lead_id)))


async def _deliver_lead(lead_id: UUID) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        session_maker = create_session_maker(engine)
        async with httpx.AsyncClient() as http_client, session_maker() as db:
            service = LeadDeliveryService(
                db_session=db,
                crm_client=build_crm_client(http_client),
            )
            await service.deliver(lead_id, raise_on_delivery_error=True)
    finally:
        await engine.dispose()
