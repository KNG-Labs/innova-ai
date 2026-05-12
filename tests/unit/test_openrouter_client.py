from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from app.client.openrouter_client import OpenRouterClient
from app.schemas.openai import ChatCompletionRequest, UserMessage

pytestmark = pytest.mark.unit


def build_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="test-model",
        messages=[UserMessage(content="hi")],
    )


def build_response(model: str) -> dict:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


class FakeSDKResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_openrouter_client_sends_request_and_parses_response() -> None:
    sdk_create = AsyncMock(return_value=FakeSDKResponse(build_response("test-model")))

    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1/",
            api_key="test-key",
        )
        client._client.chat.completions.create = sdk_create
        response = await client.create_chat_completion(build_request())

    sdk_create.assert_awaited_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert response.model == "test-model"
    assert response.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_openrouter_client_passes_reasoning_in_extra_body() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[UserMessage(content="hi")],
        reasoning=True,
    )
    sdk_create = AsyncMock(return_value=FakeSDKResponse(build_response("test-model")))

    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        client._client.chat.completions.create = sdk_create
        await client.create_chat_completion(request)

    sdk_create.assert_awaited_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        extra_body={"reasoning": {"enabled": True}},
    )


@pytest.mark.asyncio
async def test_openrouter_client_http_error() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(401, json={"error": "unauthorized"}, request=request)
    sdk_create = AsyncMock(
        side_effect=APIStatusError(
            "unauthorized",
            response=response,
            body={"error": "unauthorized"},
        )
    )

    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        client._client.chat.completions.create = sdk_create
        with pytest.raises(RuntimeError, match="status 401: unauthorized"):
            await client.create_chat_completion(build_request())


@pytest.mark.asyncio
async def test_openrouter_client_timeout_error() -> None:
    sdk_create = AsyncMock(
        side_effect=APITimeoutError(
            request=httpx.Request(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
            )
        )
    )

    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        client._client.chat.completions.create = sdk_create
        with pytest.raises(RuntimeError, match="timed out"):
            await client.create_chat_completion(build_request())


@pytest.mark.asyncio
async def test_openrouter_client_invalid_schema() -> None:
    async with httpx.AsyncClient() as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        client._client.chat.completions.create = AsyncMock(
            return_value=FakeSDKResponse({"id": "cmpl-1"})
        )

        with pytest.raises(RuntimeError, match="invalid response schema"):
            await client.create_chat_completion(build_request())
