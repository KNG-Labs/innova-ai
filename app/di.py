import os

from fastapi import FastAPI, Request
import httpx

from app.client.llm_client import LLMClient, StubLLMClient
from app.client.openrouter_client import OpenRouterClient
from app.service.business_service import DialogBusinessService, MessageNormalizer
from app.service.intent_detector import KeywordIntentDetector
from app.service.message_service import MessageService


async def init_app_state(app: FastAPI) -> None:

    provider = os.getenv("LLM_PROVIDER", "openrouter")

    http_client = httpx.AsyncClient()
    app.state.http_client = http_client

    llm_client: LLMClient

    if provider == "stub":
        llm_client = StubLLMClient()
    elif provider == "openrouter":
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        if not api_key:
            await http_client.aclose()
            raise RuntimeError("OPENROUTER_API_KEY is required")

        llm_client = OpenRouterClient(
            http=http_client,
            base_url=base_url,
            api_key=api_key,
        )
    else:
        await http_client.aclose()
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

    message_normalizer = MessageNormalizer()
    intent_detector = KeywordIntentDetector()
    business_processor = DialogBusinessService(
        normalizer=message_normalizer,
        intent_detector=intent_detector,
    )
    message_service = MessageService(llm_client, business_processor)
    app.state.llm_client = llm_client
    app.state.message_normalizer = message_normalizer
    app.state.intent_detector = intent_detector
    app.state.business_processor = business_processor
    app.state.message_service = message_service


async def close_app_state(app: FastAPI) -> None:
    http_client = getattr(app.state, "http_client", None)
    if http_client is not None:
        await http_client.aclose()


async def get_message_service(request: Request) -> MessageService:
    return request.app.state.message_service


async def get_message_normalizer(request: Request) -> MessageNormalizer:
    return request.app.state.message_normalizer
