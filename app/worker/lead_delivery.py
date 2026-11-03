import asyncio
import os

import httpx
from uuid import UUID

from celery.signals import worker_process_shutdown, worker_shutdown
from langfuse import propagate_attributes
from opentelemetry import context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.worker.celery_app import celery_app
from app.client.delivery_factory import build_crm_client, get_delivery_provider
from app.db.session import create_engine, create_session_maker
from app.service.lead_delivery_service import LeadDeliveryService
from app.tracing import (
    close_tracing,
    flush_tracing,
    init_tracing,
    traced,
    update_observation,
)

from app.models.dialog_session_model import DialogSession  # noqa: F401
from app.models.knowledge_model import KnowledgeDocument  # noqa: F401
from app.models.message_model import Message  # noqa: F401
from app.models.user_model import User  # noqa: F401
from app.models.lead_delivery_attempt_model import LeadDeliveryAttemptModel  # noqa: F401


@worker_process_shutdown.connect
@worker_shutdown.connect
def close_worker_tracing(**kwargs: object) -> None:
    asyncio.run(close_tracing())


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
    # Initialize lazily in the executing process, never before prefork.
    init_tracing()
    parent = (deliver_lead.request.headers or {}).get("traceparent")
    carrier = {"traceparent": parent} if isinstance(parent, str) else {}
    token = context.attach(
        TraceContextTextMapPropagator().extract(carrier, context=context.Context())
    )
    try:
        asyncio.run(_deliver_lead(UUID(lead_id)))
    finally:
        context.detach(token)
        flush_tracing()


@traced("process-lead-delivery")
async def _deliver_lead(lead_id: UUID) -> None:
    update_observation(
        input={"lead_id": str(lead_id), "provider": get_delivery_provider()},
        metadata={
            "task_id": deliver_lead.request.id,
            "retry": deliver_lead.request.retries,
        },
    )
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        session_maker = create_session_maker(engine)
        async with httpx.AsyncClient() as http_client, session_maker() as db:
            service = LeadDeliveryService(
                db_session=db,
                crm_client=build_crm_client(http_client),
            )
            lead = await service.deliver(lead_id, raise_on_delivery_error=True)
            with propagate_attributes(
                user_id=str(lead.user_id),
                session_id=str(lead.session_id),
                tags=["celery", "lead-delivery"],
            ):
                update_observation(output={"status": lead.status})
    finally:
        await engine.dispose()
