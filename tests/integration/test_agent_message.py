
import pytest


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_post_message_creates_anonymous_user_session_and_messages(client) -> None:
    """
    Тест: /message успешный путь.

    """

    payload = {
        "anonymous_id": "test-user-1",
        "channel": "website",
        "content": " Сколько   стоит внедрение? ",
    }

    response = await client.post("/message", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"]
    assert data["session_id"]
    assert data["user_message_id"]
    assert data["assistant_message_id"]
    assert data["answer"] == "Здравствуйте! Чем могу помочь?"
    assert data["state"] == "GREETING"
    assert data["intent"] == "pricing"
    assert data["next_step"] == "send_pricing_summary"

    messages_response = await client.get(f"/sessions/{data['session_id']}/messages")

    assert messages_response.status_code == 200
    messages = messages_response.json()

    assert len(messages) == 2

    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Сколько стоит внедрение?"

    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Здравствуйте! Чем могу помочь?"


@pytest.mark.asyncio
async def test_post_message_continues_existing_dialog_session(client) -> None:
    """
    Тест: session_id сохраняется со следующими сообщениями.

    """

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-2",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert first_response.status_code == 200
    first_data = first_response.json()

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-2",
            "channel": "website",
            "session_id": first_data["session_id"],
            "content": "Хочу оставить заявку",
        },
    )

    assert second_response.status_code == 200
    second_data = second_response.json()

    assert second_data["user_id"] == first_data["user_id"]
    assert second_data["session_id"] == first_data["session_id"]
    assert second_data["intent"] == "lead_request"
    assert second_data["next_step"] == "collect_contact"

    messages_response = await client.get(
        f"/sessions/{first_data['session_id']}/messages"
    )

    assert messages_response.status_code == 200
    messages = messages_response.json()

    assert len(messages) == 4
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    assert messages[0]["content"] == "Привет"
    assert messages[2]["content"] == "Хочу оставить заявку"


@pytest.mark.asyncio
async def test_post_message_rejects_missing_anonymous_id(client) -> None:
    """
    Тест: ошибка при отсутствии поля anonymous_id

    """

    response = await client.post(
        "/message",
        json={
            "channel": "website",
            "content": "Привет",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_post_message_rejects_invalid_anonymous_id(client) -> None:
    """
    Тест: валидация поля anonymous_id

    """

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "bad anonymous id with spaces",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_post_message_continues_active_session_without_session_id(client) -> None:
    """
    Тест: DialogSessionRepository.get_or_create_active_session() должен уметь
    найти открытую сессию пользователя даже без session_id в запросе.

    """

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "active-user-1",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert first_response.status_code == 200
    first_data = first_response.json()

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "active-user-1",
            "channel": "website",
            "content": "Сколько стоит?",
        },
    )

    assert second_response.status_code == 200
    second_data = second_response.json()

    assert second_data["user_id"] == first_data["user_id"]
    assert second_data["session_id"] == first_data["session_id"]

    messages_response = await client.get(
        f"/sessions/{first_data['session_id']}/messages"
    )

    assert messages_response.status_code == 200
    assert len(messages_response.json()) == 4


@pytest.mark.asyncio
async def test_different_anonymous_users_get_different_sessions(client) -> None:
    """
    Тест: разные anonymous users получают разные сессии.
    Память разных пользователей не смешивается.

    """

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-a",
            "channel": "website",
            "content": "Привет",
        },
    )

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-b",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_data = first_response.json()
    second_data = second_response.json()

    assert first_data["user_id"] != second_data["user_id"]
    assert first_data["session_id"] != second_data["session_id"]


@pytest.mark.asyncio
async def test_same_anonymous_id_in_different_channels_creates_different_users(
    client,
) -> None:
    """
    Тест: разные каналы с одинаковым anonymous_id — это разные пользователи.

    """
    website_response = await client.post(
        "/message",
        json={
            "anonymous_id": "same-user-id",
            "channel": "website",
            "content": "Привет с сайта",
        },
    )

    telegram_response = await client.post(
        "/message",
        json={
            "anonymous_id": "same-user-id",
            "channel": "telegram",
            "content": "Привет из Telegram",
        },
    )

    assert website_response.status_code == 200
    assert telegram_response.status_code == 200

    website_data = website_response.json()
    telegram_data = telegram_response.json()

    assert website_data["user_id"] != telegram_data["user_id"]
    assert website_data["session_id"] != telegram_data["session_id"]


@pytest.mark.asyncio
async def test_post_message_rejects_blank_content(client) -> None:
    """
    Тест: невалидный content

    """
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "blank-content-user",
            "channel": "website",
            "content": "   ",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_message_rejects_unknown_channel(client) -> None:
    """
    Тест: невалидный channel

    """

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-1",
            "channel": "unknown",
            "content": "Привет",
        },
    )

    assert response.status_code == 422



@pytest.mark.asyncio
async def test_post_message_rejects_session_belonging_to_other_user(
    client,
) -> None:
    """
    Тест: чужой session_id должен быть отклонён с 403.
    IDOR-проверка: пользователь не может писать в чужую сессию.
    """
    # 1. Владелец создаёт свою сессию
    owner_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-owner",
            "channel": "website",
            "content": "Привет, я владелец этой сессии",
        },
    )
    assert owner_response.status_code == 200
    owner_data = owner_response.json()
    owner_session_id = owner_data["session_id"]

    # 2. Злоумышленник создаёт свою отдельную сессию
    attacker_first = await client.post(
        "/message",
        json={
            "anonymous_id": "user-attacker",
            "channel": "website",
            "content": "Я другой пользователь",
        },
    )
    assert attacker_first.status_code == 200

    # 3. Злоумышленник пытается писать в чужую сессию
    attack_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-attacker",
            "channel": "website",
            "session_id": owner_session_id,
            "content": "Хочу подмешать сообщение в чужую историю",
        },
    )

    assert attack_response.status_code == 403
    assert (
        "does not belong" in attack_response.json()["detail"].lower()
    )

    # 4. Проверяем, что история владельца не изменилась —
    #    сообщение злоумышленника НЕ попало в чужую сессию
    messages_response = await client.get(
        f"/sessions/{owner_session_id}/messages"
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()

    # Было ровно 2 сообщения: user + assistant от владельца
    assert len(messages) == 2
    assert messages[0]["content"] == "Привет, я владелец этой сессии"
    assert all(
        "подмешать" not in m["content"] for m in messages
    ), "Чужое сообщение не должно попасть в историю"


@pytest.mark.asyncio
async def test_post_message_rejects_nonexistent_session_id(client) -> None:
    """
    Тест: если передан несуществующий session_id,
    система не падает, а создаёт новую сессию (graceful fallback).
    """
    from uuid import uuid4

    fake_session_id = str(uuid4())

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-with-fake-session",
            "channel": "website",
            "session_id": fake_session_id,
            "content": "Привет",
        },
    )

    assert response.status_code == 200
    data = response.json()
    # Создаётся новая сессия, а не используется фейковая
    assert data["session_id"] != fake_session_id