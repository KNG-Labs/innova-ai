import asyncio
import logging
import os

import httpx
from uuid import UUID
from dotenv import load_dotenv

from app.worker.celery_app import celery_app
from app.client.delivery_factory import build_crm_client, build_queue_client
from app.db.session import create_engine, create_session_maker
from app.service.lead_delivery_service import (
    LeadDeliveryService,
    LeadNotDeliverableError,
    LeadNotFoundError,
)

from app.models.dialog_session_model import DialogSession  # noqa: F401
from app.models.knowledge_model import KnowledgeDocument  # noqa: F401
from app.models.message_model import Message  # noqa: F401
from app.models.user_model import User  # noqa: F401

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("app.worker.lead_delivery")


@celery_app.task
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
            await service.deliver(lead_id)
    finally:
        await engine.dispose()


async def main() -> None:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(database_url)
    session_maker = create_session_maker(engine)
    http_client = httpx.AsyncClient()
    queue_client, redis_conn = await build_queue_client()
    crm_client = build_crm_client(http_client)

    _logger.info("lead delivery worker started")
    try:
        while True:
            job = await queue_client.dequeue_lead_delivery()
            if job is None:
                continue  # таймаут BRPOP — снова ждём
            async with session_maker() as db:
                svc = LeadDeliveryService(db_session=db, crm_client=crm_client)
                try:
                    lead = await svc.deliver(job.lead_id)
                    _logger.info("lead %s -> %s", job.lead_id, lead.status)
                    await queue_client.ack(job)
                except (LeadNotFoundError, LeadNotDeliverableError):
                    # ретрай бессмысленен — снимаем job
                    _logger.warning("skip lead %s: not deliverable", job.lead_id)
                    await queue_client.ack(job)
    except KeyboardInterrupt:
        pass
    finally:
        await http_client.aclose()
        if redis_conn is not None:
            await redis_conn.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
