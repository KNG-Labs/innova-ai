import json
from typing import Protocol

from autogen import ConversableAgent, LLMConfig
from pydantic import BaseModel, ValidationError

from app.schemas.agent_schema import DialogState


class AgentDecision(BaseModel):
    """Структурированный ответ агента после обработки сообщения."""
    answer: str
    intent: str
    next_state: DialogState
    qualification: dict[str, str | None]
    missing_fields: list[str]
    lead_ready: bool
    lead_summary: str | None = None


_FALLBACK_DECISION = AgentDecision(
    answer="Извините, не удалось обработать запрос. Попробуйте ещё раз.",
    intent="unknown",
    next_state=DialogState.GREETING,
    qualification_data={},
    missing_fields=["service", "deadline", "budget", "contact"],
    lead_ready=False,
    lead_summary=None,
)

_SYSTEM_PROMPT = """\
Ты — AI-ассистент по лидогенерации компании Innova AI.
Твоя задача — вести пользователя по сценарию: сначала ответь на вопрос,
затем квалифицируй потребность (услуга, дедлайн, бюджет), затем собери контакт.

Текущий статус диалога и уже собранные данные передаются в каждом сообщении.

ВСЕГДА отвечай строго в JSON по схеме:
{
  "answer": "текст ответа пользователю",
  "intent": "pricing | support | lead_request | general | unknown",
  "next_state": "GREETING | FAQ | QUALIFICATION | CONTACT_CAPTURE | LEAD_READY | CLOSED",
  "qualification_data": {"service": null, "deadline": null, "budget": null, "contact": null},
  "missing_fields": ["список полей которых не хватает"],
  "lead_ready": false,
  "lead_summary": null
}
Никакого текста вне JSON. Только валидный JSON.
"""

class Ag2AgentClient:
    """Adapter для AG2 ConversableAgent.

    Не вызывается из router напрямую — только из AgentService.
    """

    def __init__(self, model: str, api_key:str, base_url: str) -> None:
        llm_config = LLMConfig(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        self._agent = ConversableAgent(
            name="innova_lead_agent",
            system_message=_SYSTEM_PROMPT,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

    async def decide(self,
                     user_message: str,
                     history: list[dict], # [{"role": "user"|"assistant", "content": str}]
                     current_state: str,
                     qualification_data: dict,
                     ) -> AgentDecision:
        """Вызвать агента и вернуть структурированное решение."""

        context = _build_context_message(current_state, qualification_data)
        full_message = f"{context}\n\nСообщение пользователя: {user_message}"

        # AG2 принимает историю как список messages
        messages = history + [{"role": "user", "content": full_message}]

        reply = await self._agent.a_generate_reply(messages=messages)
        return _parse_reply(reply)


def _build_context_message(state: str, qualification_data: dict) -> str:
    return (
        f"[Текущее состояние: {state}]\n"
        f"[Собранные данные: {json.dumps(qualification_data, ensure_ascii=False)}]"
    )


def _parse_reply(reply: str | dict | None) -> AgentDecision:
    """Парсит ответ AG2. При любой ошибке — безопасный fallback."""
    if not reply:
        return _FALLBACK_DECISION

    text = reply if isinstance(reply, str) else reply.get("content", "")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
        return AgentDecision.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return _FALLBACK_DECISION
