import json

import httpx
import pytest

from app.client.openrouter_client import OpenRouterClient
from app.schemas.openai import ChatCompletionRequest, ChatMessage

pytestmark = pytest.mark.unit


def build_request() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
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


@pytest.mark.asyncio
async def test_openrouter_client_sends_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["json"] = json.loads(request.content.decode("utf-8"))
        response_body = build_response(model=captured["json"]["model"])
        return httpx.Response(200, json=response_body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1/",
            api_key="test-key",
        )
        response = await client.create_chat_completion(build_request())

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    headers = captured["headers"]
    assert headers is not None
    assert headers["Authorization"] == "Bearer test-key"

    payload = captured["json"]
    assert payload is not None
    assert payload["model"] == "test-model"
    assert "reasoning" not in payload

    assert response.model == "test-model"
    assert response.choices[0].message.content == "ok"


@pytest.mark.asyncio
async def test_openrouter_client_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        with pytest.raises(RuntimeError, match="status 401: unauthorized"):
            await client.create_chat_completion(build_request())


@pytest.mark.asyncio
async def test_openrouter_client_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        with pytest.raises(RuntimeError, match="timed out"):
            await client.create_chat_completion(build_request())


@pytest.mark.asyncio
async def test_openrouter_client_invalid_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "cmpl-1"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenRouterClient(
            http=http,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        )
        with pytest.raises(RuntimeError, match="invalid response schema"):
            await client.create_chat_completion(build_request())
