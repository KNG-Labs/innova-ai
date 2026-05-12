from unittest.mock import AsyncMock

import pytest

from app.schemas.openai import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatUsage,
    UserMessage,
)
from app.service.message import MessageService

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


@pytest.mark.asyncio
async def test_handle_chat_completion_delegates() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[UserMessage(content="hi")],
    )
    expected = build_response(model=request.model)

    llm_client = AsyncMock()
    llm_client.create_chat_completion.return_value = expected

    service = MessageService(llm_client)
    result = await service.handle_chat_completion(request)

    llm_client.create_chat_completion.assert_awaited_once_with(request)
    assert result == expected
