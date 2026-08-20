import json

import httpx
import pytest

from app.channel.telegram_bot import handle_update


def telegram_update(
    *,
    text: str = "Ищу Toyota Camry",
    chat_type: str = "private",
) -> dict:
    return {
        "update_id": 101,
        "message": {
            "chat": {"id": 500, "type": chat_type},
            "from": {"id": 700},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_text_is_forwarded_to_innova_and_answer_is_sent() -> None:
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append((request.url.host, payload))

        if request.url.host == "innova.test":
            return httpx.Response(
                200,
                json={
                    "answer": "Какой у вас бюджет?",
                    "state": "CONTACT_CAPTURE",
                    "missing_fields": ["contact"],
                },
            )

        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        await handle_update(
            client,
            "https://telegram.test/bot-token",
            "https://innova.test",
            telegram_update(),
        )

    innova_payload = calls[0][1]
    assert innova_payload == {
        "anonymous_id": "tg:700",
        "channel": "telegram",
        "content": "Ищу Toyota Camry",
    }

    telegram_payload = calls[1][1]
    assert telegram_payload["chat_id"] == 500
    assert telegram_payload["text"] == "Какой у вас бюджет?"
    assert telegram_payload["reply_markup"]["keyboard"][0][0] == {
        "text": "Поделиться телефоном",
        "request_contact": True,
    }


@pytest.mark.asyncio
async def test_start_does_not_call_innova_api() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        await handle_update(
            client,
            "https://telegram.test/bot-token",
            "https://innova.test",
            telegram_update(text="/start"),
        )

    assert hosts == ["telegram.test"]


@pytest.mark.asyncio
async def test_group_message_is_ignored() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected request: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        await handle_update(
            client,
            "https://telegram.test/bot-token",
            "https://innova.test",
            telegram_update(chat_type="group"),
        )
