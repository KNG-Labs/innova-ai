import os
from collections.abc import AsyncGenerator

import httpx
from fastapi import FastAPI, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.llm_client import LLMClient, StubLLMClient
from app.client.openrouter_client import OpenRouterClient
from app.db.session import create_engine as create_db_engine
from app.db.session import create_session_maker
from app.service.agent_service import AgentService
from app.service.business_service import DialogBusinessService, MessageNormalizer
from app.service.intent_detector import KeywordIntentDetector
from app.service.intent_detector.base_intent_detector import BaseIntentDetector
from app.service.message_service import MessageService
from app.service.session_service import SessionService


async def init_app_state(app: FastAPI) -> None:
    http_client = httpx.AsyncClient()

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
    intent_detector = KeywordIntentDetector()

    app.state.normalizer = normalizer
    app.state.intent_detector = intent_detector

    llm_provider = os.getenv("LLM_PROVIDER", "stub").strip().lower()

    if llm_provider == "stub":
        llm_client: LLMClient = StubLLMClient()
    elif llm_provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            await http_client.aclose()
            await db_engine.dispose()
            raise RuntimeError("OPENROUTER_API_KEY is required")

        base_url = os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ).strip()

        llm_client = OpenRouterClient(
            http=http_client,
            base_url=base_url,
            api_key=api_key,
        )
    else:
        await http_client.aclose()
        await db_engine.dispose()
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {llm_provider}")

    app.state.llm_client = llm_client

    # Оставляем временно
    business_processor = DialogBusinessService(
        normalizer=normalizer,
        intent_detector=intent_detector,
    )
    app.state.message_service = MessageService(
        llm_client=llm_client,
        business_processor=business_processor,
    )


async def close_app_state(app: FastAPI) -> None:
    http_client = getattr(app.state, "http_client", None)
    if http_client is not None:
        await http_client.aclose()

    db_engine = getattr(app.state, "db_engine", None)
    if db_engine is not None:
        await db_engine.dispose()


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_maker = request.app.state.db_session_maker

    async with session_maker() as session:
        yield session


async def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


async def get_normalizer(request: Request) -> MessageNormalizer:
    return request.app.state.normalizer


async def get_intent_detector(request: Request) -> BaseIntentDetector:
    return request.app.state.intent_detector


async def get_agent_service(
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentService:
    return AgentService(
        db_session=db_session,
        llm_client=request.app.state.llm_client,
        normalizer=request.app.state.normalizer,
        intent_detector=request.app.state.intent_detector,
    )


async def get_session_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(db_session=db_session)


async def get_message_service(request: Request) -> MessageService:
    """
    Можно удалить позже, когда уберем старый MessageService.
    """

    return request.app.state.message_service
