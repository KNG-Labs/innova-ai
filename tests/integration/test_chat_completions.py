import pytest

pytestmark = pytest.mark.integration


def test_chat_completions_returns_stub_response(client) -> None:
    payload = {
        "model": "test-model",
        "messages": [
            {"role": "user", "content": "hi"},
        ],
    }

    response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["object"] == "chat.completion"
    assert data["model"] == payload["model"]
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"]


def test_chat_completions_validation_error(client) -> None:
    response = client.post("/v1/chat/completions", json={"model": "test-model"})

    assert response.status_code == 422
    assert response.json()["detail"]
