from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_session_returns_session_details(client) -> None:
    """
    Тест: тест эндпоинта /sessions/{session_id}

    """
    message_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-3",
            "channel": "website",
            "content": "Нужна консультация",
        },
    )

    assert message_response.status_code == 200
    message_data = message_response.json()

    session_response = await client.get(f"/sessions/{message_data['session_id']}")

    assert session_response.status_code == 200
    session_data = session_response.json()

    assert session_data["id"] == message_data["session_id"]
    assert session_data["user_id"] == message_data["user_id"]
    assert session_data["state"] == "GREETING"
    assert session_data["channel"] == "website"
    assert session_data["created_at"]
    assert session_data["updated_at"]


@pytest.mark.asyncio
async def test_get_unknown_session_returns_404(client) -> None:
    """
    Тест: сессия не найдена

    """

    unknown_session_id = uuid4()

    response = await client.get(f"/sessions/{unknown_session_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


@pytest.mark.asyncio
async def test_list_messages_by_session_id(client) -> None:
    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "long-history-user",
            "channel": "website",
            "content": "Сообщение 1",
        },
    )

    assert first_response.status_code == 200
    session_id = first_response.json()["session_id"]

    for index in range(2, 12):
        response = await client.post(
            "/message",
            json={
                "anonymous_id": "long-history-user",
                "channel": "website",
                "session_id": session_id,
                "content": f"Сообщение {index}",
            },
        )

        assert response.status_code == 200

    messages_response = await client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200

    messages = messages_response.json()
    assert len(messages) == 22
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Сообщение 1"
    assert messages[-2]["role"] == "user"
    assert messages[-2]["content"] == "Сообщение 11"
    assert messages[-1]["role"] == "assistant"
