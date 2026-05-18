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
