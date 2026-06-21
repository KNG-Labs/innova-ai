import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv

from app.client.delivery_factory import build_crm_client, build_queue_client
from app.db.session import create_engine, create_session_maker
from app.service.lead_delivery_service import (
    LeadDeliveryService,
    LeadNotDeliverableError,
    LeadNotFoundError,
)

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("app.worker.lead_delivery")


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
    finally:
        await http_client.aclose()
        if redis_conn is not None:
            await redis_conn.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
