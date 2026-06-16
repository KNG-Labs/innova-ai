from app.schemas.agent_schema import DialogState
from app.client.ag2_agent_client import AgentDecision

# Допустимые переходы
_ALLOWED_TRANSITIONS: dict[DialogState, set[DialogState]] = {
    DialogState.GREETING: {DialogState.FAQ, DialogState.QUALIFICATION, DialogState.CONTACT_CAPTURE},
    DialogState.FAQ: {DialogState.FAQ, DialogState.QUALIFICATION, DialogState.CONTACT_CAPTURE},
    DialogState.QUALIFICATION: {DialogState.QUALIFICATION, DialogState.CONTACT_CAPTURE, DialogState.CLOSED},
    DialogState.CONTACT_CAPTURE: {DialogState.LEAD_READY},
    DialogState.LEAD_READY: {DialogState.CLOSED},
    DialogState.CLOSED: set(),
}

_REQUIRED_FIELDS = {"service", "deadline", "budget", "contact"}

def resolve_next_state(
        current: DialogState,
        decision: AgentDecision,
) -> DialogState:
    """Детерминированно определяет следующее состояние.

    Рекомендация LLM учитывается, но код проверяет допустимость перехода.
    """

    suggested = decision.next_state

    # Если LLM хочет перейти в LEAD_READY, проверяем, что контакт реально есть
    if suggested == DialogState.LEAD_READY:
        if not decision.lead_ready or not decision.qualification_data.get("contact"):
            suggested = DialogState.CONTACT_CAPTURE

    # Если переход допустим — принимаем
    if suggested in _ALLOWED_TRANSITIONS.get(current, set()):
        return suggested

    # Если нет — остаёмся на месте (не падаем)
    return current


def is_lead_ready(qualification_data: dict) -> bool:
    """Все обязательные поля собраны."""
    return all(
        qualification_data.get(field)
        for field in _REQUIRED_FIELDS
    )