import os
from collections.abc import AsyncGenerator

import httpx
from fastapi import FastAPI, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.ag2_agent_client import LLMClient
from app.client.delivery_factory import (
    get_delivery_provider,
    build_queue_client,
    build_crm_client,
)
from app.db.session import create_engine as create_db_engine
from app.db.session import create_session_maker
from app.service.agent_service import AgentService
from app.service.business_service import MessageNormalizer
from app.service.lead_delivery_service import LeadDeliveryService
from app.service.session_service import SessionService
from app.service.lead_service import LeadService


async def init_app_state(app: FastAPI) -> None:
    # fail fast: ag2 без ключа смысла не имеет (Phase 6)
    if (
        os.getenv("LLM_PROVIDER", "stub").strip().lower() == "ag2"
        and not os.getenv("OPENROUTER_API_KEY", "").strip()
    ):
        raise RuntimeError("LLM_PROVIDER=ag2 требует OPENROUTER_API_KEY")
    
    http_client = httpx.AsyncClient(timeout=30.0)

    app.state.http_client = http_client

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        await http_client.aclose()
        raise RuntimeError("DATABASE_URL is required")

    db_engine = create_db_engine(database_url)
    db_session_maker = create_session_maker(db_engine)

    app.state.db_engine = db_engine
    app.state.db_session_maker = db_session_maker

    normalizer = MessageNormalizer()

    app.state.normalizer = normalizer

    llm_provider = os.getenv("LLM_PROVIDER", "stub").strip().lower()
    llm_client: LLMClient

    if llm_provider == "ag2":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        base_url = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).strip()
        model = os.getenv("AG2_MODEL", "openai/gpt-oss-120b:free").strip()
        from app.client.ag2_agent_client import Ag2AgentClient

        llm_client = Ag2AgentClient(model=model, api_key=api_key, base_url=base_url)

    elif llm_provider == "stub":
        from app.client.ag2_agent_client import FakeAg2AgentClient

        llm_client = FakeAg2AgentClient()
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {llm_provider}")

    app.state.llm_client = llm_client

    app.state.delivery_provider = get_delivery_provider()
    app.state.crm_client = build_crm_client(http_client)

    queue_client, redis_conn = await build_queue_client()
    app.state.queue_client = queue_client
    app.state.redis_conn = redis_conn


async def close_app_state(app: FastAPI) -> None:
    http_client = getattr(app.state, "http_client", None)
    if http_client is not None:
        await http_client.aclose()

    redis_conn = getattr(app.state, "redis_conn", None)
    if redis_conn is not None:
        await redis_conn.aclose()

    db_engine = getattr(app.state, "db_engine", None)
    if db_engine is not None:
        await db_engine.dispose()


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_maker = request.app.state.db_session_maker

    async with session_maker() as session:
        yield session


async def get_agent_service(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentService:
    return AgentService(
        db_session=db_session,
        llm_client=request.app.state.llm_client,
        normalizer=request.app.state.normalizer,
        queue_client=request.app.state.queue_client,
        delivery_provider=request.app.state.delivery_provider,
    )


async def get_session_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(db_session=db_session)


async def get_lead_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> LeadService:
    return LeadService(db_session=db_session)


async def get_lead_delivery_service(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> LeadDeliveryService:
    return LeadDeliveryService(
        db_session=db_session,
        crm_client=request.app.state.crm_client,
    )
