import json
import logging
import asyncio

from autogen import ConversableAgent, LLMConfig
from pydantic import ValidationError
from typing import Protocol, runtime_checkable

from app.schemas.agent_schema import DialogState, AgentDecision
from app.domain import QUALIFICATION_FIELDS, MISSING_ALL

logger = logging.getLogger(__name__)

_AG2_TIMEOUT_S = 60  # free-модели OpenRouter медленные; жёсткий потолок

_FALLBACK_DECISION = AgentDecision(
    answer="Извините, не удалось обработать запрос. Попробуйте ещё раз.",
    intent="unknown",
    next_state=DialogState.GREETING,
    qualification_data={},
    missing_fields=MISSING_ALL,
    lead_ready=False,
    lead_summary=None,
)

_fields_desc = "\n".join(f"- {k}: {v}" for k, v in QUALIFICATION_FIELDS.items())
_qual_json = ", ".join(f'"{k}": null' for k in QUALIFICATION_FIELDS)

_SYSTEM_PROMPT = f"""\
Ты — AI-ассистент по лидогенерации.
Сначала ответь на вопрос, затем квалифицируй потребность по полям:
{_fields_desc}
затем собери контакт.

Текущий статус и собранные данные передаются в каждом сообщении.

ВСЕГДА отвечай строго в JSON по схеме:
{{
  "answer": "текст ответа пользователю",
  "intent": "pricing | support | lead_request | general | unknown",
  "next_state": "GREETING | FAQ | QUALIFICATION | CONTACT_CAPTURE | LEAD_READY | CLOSED",
  "qualification_data": {{{_qual_json}}},
  "extracted_contact": {{"phone": null, "email": null, "telegram": null, "name": null}},
  "missing_fields": [],
  "lead_ready": false,
  "lead_summary": null
}}

В qualification_data клади извлечённые значения полей или null, если поля ещё нет.
В missing_fields перечисли поля, которых не хватает.
Контакт (телефон/email/telegram/имя) клади ТОЛЬКО в extracted_contact.
Не благодари и не обещай, что менеджер свяжется, пока контакт не собран.
Отвечай на вопросы о ценах, услугах и условиях ТОЛЬКО на основе блока [База знаний].
Но не сваливай сразу всю информацию на человека, делай это постепенно, с предложением рассказать 
о чём нибудь ещё в конце сообщения.
Если он пуст или ответа там нет — честно скажи, что не знаешь точно, и предложи оставить контакт менеджеру.
Не выдумывай цены, суммы и сроки.
Если в контексте есть строка [Страница сайта: ...], считай её подсказкой о том, какая модель или тема интересует пользователя. Но не записывай модель в qualification_data, пока пользователь сам её не подтвердит.
Никакого текста вне JSON. Только валидный JSON.
Никакого текста вне JSON. Только валидный JSON.
"""


@runtime_checkable
class LLMClient(Protocol):
    async def decide(
        self,
        user_message: str,
        history: list[dict],
        current_state: str,
        qualification_data: dict,
        retrieved_context: str = "",
        page_title: str | None = None,
    ) -> AgentDecision: ...


class Ag2AgentClient(LLMClient):
    """Adapter для AG2 ConversableAgent.

    Не вызывается из router напрямую — только из AgentService.
    """

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        llm_config = LLMConfig(
            {
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
                "price": [0, 0],
            }
        )
        self._agent = ConversableAgent(
            name="innova_lead_agent",
            system_message=_SYSTEM_PROMPT,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

    async def decide(
        self,
        user_message: str,
        history: list[dict],
        current_state: str,
        qualification_data: dict,
        retrieved_context: str = "",
        page_title: str | None = None,
    ) -> AgentDecision:
        """Вызвать агента и вернуть структурированное решение.

        Любой сбой провайдера (timeout/exception) -> безопасный fallback.
        Состояние при этом НЕ теряется: _FALLBACK_DECISION.next_state=GREETING
        не пройдёт проверку переходов и state machine оставит текущее состояние.
        """
        context = _build_context_message(
            current_state,
            qualification_data,
            retrieved_context,
            page_title,
        )
        full_message = f"{context}\n\nСообщение пользователя: {user_message}"
        messages = history + [{"role": "user", "content": full_message}]

        try:
            reply = await asyncio.wait_for(
                self._agent.a_generate_reply(messages=messages),
                timeout=_AG2_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 — любой сбой провайдера = fallback, не 500
            logger.warning("AG2 call failed (%s): %r", type(exc).__name__, exc)
            return _FALLBACK_DECISION

        return _parse_reply(reply)


def _build_context_message(
    state: str,
    qualification_data: dict,
    retrieved_context: str,
    page_title: str | None = None,
) -> str:
    kb = retrieved_context.strip() or "ничего релевантного не найдено"
    lines = [
        f"[Текущее состояние: {state}]",
        f"[Собранные данные: {json.dumps(qualification_data, ensure_ascii=False)}]",
    ]
    if page_title:
        lines.append(f"[Страница сайта: {page_title}]")
    lines.append(f"[База знаний:\n{kb}\n]")
    return "\n".join(lines)


def _parse_reply(reply: str | dict | None) -> AgentDecision:
    """Парсит ответ AG2. При любой ошибке — безопасный fallback."""
    if not reply:
        return _FALLBACK_DECISION

    text = reply if isinstance(reply, str) else reply.get("content", "")
    raw = text  # сохранить сырое для лога

    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
        return AgentDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("AG2 parse failed: %s | raw=%r", e, raw)
        return _FALLBACK_DECISION


class FakeAg2AgentClient(LLMClient):
    """Заглушка для тестов без LLM key."""

    def __init__(self, responses: list[AgentDecision] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0

    async def decide(
        self,
        user_message: str,
        history: list[dict],
        current_state: str,
        qualification_data: dict,
        retrieved_context: str = "",
        page_title: str | None = None,
    ) -> AgentDecision:
        if self._responses and self._call_count < len(self._responses):
            result = self._responses[self._call_count]
        else:
            result = AgentDecision(
                answer="Расскажите подробнее о задаче.",
                intent="general",
                next_state=DialogState.QUALIFICATION,
                qualification_data={},
                missing_fields=MISSING_ALL,
                lead_ready=False,
            )
        self._call_count += 1
        return result
