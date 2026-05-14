from unittest.mock import AsyncMock

import pytest

from app.schemas.message import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatUsage,
    UserMessage,
)
from app.client.llm_client import LLMProviderError
from app.service.business_service import (
    DialogBusinessService,
    MessageNormalizer,
)
from app.service.intent_detector.keyword_intent_detector import KeywordIntentDetector
from app.service.message_service import MessageService

pytestmark = pytest.mark.unit


def build_response(model: str) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cmpl-1",
        object="chat.completion",
        created=1,
        model=model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(role="assistant", content="ok"),
                finish_reason="stop",
            )
        ],
        usage=ChatUsage(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        ),
    )


def build_business_processor() -> DialogBusinessService:
    return DialogBusinessService(
        normalizer=MessageNormalizer(),
        intent_detector=KeywordIntentDetector(),
    )


@pytest.mark.asyncio
async def test_handle_chat_completion_normalizes_and_detects_intent() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[UserMessage(content="  Сколько   стоит консультация?  ")],
    )
    expected = build_response(model=request.model)

    llm_client = AsyncMock()
    llm_client.create_chat_completion.return_value = expected

    service = MessageService(llm_client, build_business_processor())
    result = await service.handle_chat_completion(request)

    normalized_request = llm_client.create_chat_completion.await_args.args[0]
    assert normalized_request.messages[0].content == "Сколько стоит консультация?"
    assert result == expected
    assert result.innova_ai == {
        "normalized_message": "Сколько стоит консультация?",
        "intent": "pricing",
        "next_step": "send_pricing_summary",
    }


@pytest.mark.asyncio
async def test_handle_chat_completion_returns_fallback_on_provider_error() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[UserMessage(content="Нужна консультация")],
    )
    llm_client = AsyncMock()
    llm_client.create_chat_completion.side_effect = LLMProviderError(
        "LLM provider request timed out",
        retryable=True,
    )

    service = MessageService(llm_client, build_business_processor())
    result = await service.handle_chat_completion(request)

    assert result.model == "test-model"
    assert result.choices[0].message.content
    assert result.innova_ai == {
        "normalized_message": "Нужна консультация",
        "intent": "lead_request",
        "next_step": "collect_contact",
    }
    assert result.innova_ai_error == {
        "provider_error": "LLM provider request timed out",
        "retryable": True,
        "fallback": True,
    }
