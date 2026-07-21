import asyncio
import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_logger = logging.getLogger(__name__)


def required_env(name: str) -> str:
    """Проверка зависимостей"""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def telegram_call(
    client: httpx.AsyncClient,
    bot_api_url: str,
    method: str,
    payload: dict[str, Any],
) -> Any:
    """Клиент для Телеграмм"""
    response = await client.post(
        f"{bot_api_url}/{method}",
        json=payload,
    )
    response.raise_for_status()

    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram method {method} failed")

    return body.get("result")


async def send_message(
    client: httpx.AsyncClient,
    bot_api_url: str,
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    """Адаптер для работы Телеграм API и контракта Innova

    принимает только личные чаты;
    отвечает на /start и /help без обращения к LLM;
    превращает переданный Telegram-контакт в текст Мой телефон: ...;
    показывает кнопку передачи телефона в состоянии CONTACT_CAPTURE;
    разбивает ответы длиннее 4000 символов.
    """

    # У Telegram ограничение 4096 символов на одно сообщение.
    chunks = [text[index : index + 4000] for index in range(0, len(text), 4000)]

    for index, chunk in enumerate(chunks):
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
        }

        if reply_markup is not None and index == len(chunks) - 1:
            payload["reply_markup"] = reply_markup

        await telegram_call(
            client,
            bot_api_url,
            "sendMessage",
            payload,
        )


async def handle_update(
    client: httpx.AsyncClient,
    bot_api_url: str,
    innova_api_url: str,
    update: dict[str, Any],
) -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return

    # Текущая модель диалога рассчитана на личный разговор.
    if chat.get("type") != "private":
        return

    chat_id = chat.get("id")
    sender_id = sender.get("id")
    if not isinstance(chat_id, int) or not isinstance(sender_id, int):
        return

    text = message.get("text")
    contact = message.get("contact")

    if isinstance(text, str):
        command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]

        if command in {"/start", "/help"}:
            await send_message(
                client,
                bot_api_url,
                chat_id,
                "Здравствуйте! Чем могу помочь?",
            )
            return

        content = text

    elif isinstance(contact, dict) and contact.get("phone_number"):
        content = f"Мой телефон: {contact['phone_number']}"

    else:
        await send_message(
            client,
            bot_api_url,
            chat_id,
            "Пока я умею обрабатывать текстовые сообщения и телефонные контакты.",
        )
        return

    try:
        response = await client.post(
            f"{innova_api_url}/message",
            json={
                "anonymous_id": f"tg:{sender_id}",
                "channel": "telegram",
                "content": content,
            },
        )
        response.raise_for_status()
        result = response.json()
        answer = result["answer"]

    except (httpx.HTTPError, KeyError, ValueError):
        _logger.warning(
            "Innova API request failed for Telegram update %s",
            update.get("update_id"),
        )
        await send_message(
            client,
            bot_api_url,
            chat_id,
            "Сервис временно недоступен. Попробуйте отправить сообщение ещё раз.",
        )
        return

    reply_markup: dict[str, Any]

    if result.get("state") == "CONTACT_CAPTURE" and "contact" in result.get(
        "missing_fields", []
    ):
        reply_markup = {
            "keyboard": [
                [
                    {
                        "text": "Поделиться телефоном",
                        "request_contact": True,
                    }
                ]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
    else:
        reply_markup = {"remove_keyboard": True}

    await send_message(
        client,
        bot_api_url,
        chat_id,
        answer,
        reply_markup=reply_markup,
    )


async def main() -> None:
    token = required_env("TELEGRAM_BOT_TOKEN")
    innova_api_url = required_env("INNOVA_API_URL").rstrip("/")
    bot_api_url = f"https://api.telegram.org/bot{token}"

    timeout = httpx.Timeout(
        connect=10.0,
        read=65.0,
        write=10.0,
        pool=10.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Long polling нельзя использовать одновременно с webhook.
        await telegram_call(
            client,
            bot_api_url,
            "deleteWebhook",
            {"drop_pending_updates": False},
        )

        offset: int | None = None
        _logger.info("Telegram bot polling started")

        while True:
            try:
                updates = await telegram_call(
                    client,
                    bot_api_url,
                    "getUpdates",
                    {
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                )

                for update in updates:
                    update_id = update.get("update_id")
                    if not isinstance(update_id, int):
                        continue

                    try:
                        await handle_update(
                            client,
                            bot_api_url,
                            innova_api_url,
                            update,
                        )
                    except Exception:
                        # Не выводим exception: URL Telegram содержит токен.
                        _logger.error(
                            "Unexpected failure for Telegram update %s",
                            update_id,
                        )

                    offset = update_id + 1

            except Exception as exc:
                _logger.warning(
                    "Telegram polling failed: %s",
                    type(exc).__name__,
                )
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
