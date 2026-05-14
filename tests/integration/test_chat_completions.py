import pytest

from app.di import get_message_service
from app.main import app
from app.schemas.message import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionResponse,
    ChatUsage,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_chat_completions_returns_business_metadata(client) -> None:
    payload = {
        "model": "test-model",
        "messages": [
            {"role": "user", "content": "  Сколько   стоит внедрение?  "},
        ],
    }

    response = await client.post("/message", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["object"] == "chat.completion"
    assert data["model"] == payload["model"]
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"]
    assert data["innova_ai"] == {
        "normalized_message": "Сколько стоит внедрение?",
        "intent": "pricing",
        "next_step": "send_pricing_summary",
    }


@pytest.mark.asyncio
async def test_chat_completions_validation_error(client) -> None:
    response = await client.post("/message", json={"model": "test-model"})

    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_completions_can_override_service_dependency(client) -> None:
    class FakeMessageService:
        async def handle_chat_completion(self, request) -> ChatCompletionResponse:
            return ChatCompletionResponse(
                id="override-1",
                object="chat.completion",
                created=1,
                model=request.model,
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatChoiceMessage(
                            role="assistant",
                            content="Ответ из подмененного сервиса",
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=ChatUsage(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                ),
            )

    async def override_message_service() -> FakeMessageService:
        return FakeMessageService()

    app.dependency_overrides[get_message_service] = override_message_service
    try:
        response = await client.post(
            "/message",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == (
        "Ответ из подмененного сервиса"
    )
