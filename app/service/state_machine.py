from app.schemas.agent_schema import DialogState
from app.client.ag2_agent_client import AgentDecision


# Обязательные поля квалификации
_REQUIRED_QUAL: tuple[str, ...] = ("service", "deadline", "budget")


# Допустимые переходы
_ALLOWED_TRANSITIONS: dict[DialogState, set[DialogState]] = {
    DialogState.GREETING: {
        DialogState.FAQ,
        DialogState.QUALIFICATION,
        DialogState.CONTACT_CAPTURE,
    },
    DialogState.FAQ: {
        DialogState.FAQ,
        DialogState.QUALIFICATION,
        DialogState.CONTACT_CAPTURE,
    },
    DialogState.QUALIFICATION: {
        DialogState.QUALIFICATION,
        DialogState.CONTACT_CAPTURE,
        DialogState.CLOSED,
    },
    DialogState.CONTACT_CAPTURE: {
        DialogState.CONTACT_CAPTURE,
        DialogState.LEAD_READY,
        DialogState.CLOSED,
    },
    DialogState.LEAD_READY: {DialogState.CLOSED},
    DialogState.CLOSED: set(),
}


def merge_qualification_data(
        existing: dict[str, str | None],
        extracted: dict[str, str | None],
) -> dict[str, str]:
    """Слить старые и новые данные.
    None из LLM не затирает реальные значения."""
    merged = {k: v for k, v in existing.items() if v is not None}
    for key, value in extracted.items():
        if value is not None:
            merged[key] = value
    return merged


def merge_contact(
        existing: dict[str, str | None] | None,
        extracted: dict[str, str | None] | None,
) -> dict[str, str]:
    """Слить контакт. Та же логика: None не затирает значение."""
    merged = {k: v for k, v in (existing or {}).items() if v is not None}
    for key, value in (extracted or {}).items():
        if value is not None:
            merged[key] = value
    return merged

def is_contact_valid(contact: dict | None) -> bool:
    """
    Валиден, если есть хотя бы одно непустое строковое значение.

    Свободный fallback намеренно разрешён: строгая регекс-валидация
    не должна блокировать реальный лид
    """
    if not contact:
        return False
    return any(isinstance(v, str) and v.strip() for v in contact.values())


def compute_missing_fields(
        qualification_data: dict[str, str | None],
        contact: dict[str, str | None],
) -> list[str]:
    """Backend сам считает, чего не хватает. LLM не доверяем."""
    missing = [f for f in _REQUIRED_QUAL if not qualification_data.get(f)]
    if not is_contact_valid(contact):
        missing.append("contact")
    return missing


def is_lead_ready(qualification_data: dict, contact: dict | None) -> bool:
    """Лид готов, когда backend не видит ни одного missing field."""
    return not compute_missing_fields(qualification_data, contact)


def resolve_next_state(
        current: DialogState,
        decision: AgentDecision,
        merged_qualification: dict,
        merged_contact: dict,
) -> DialogState:
    """Детерминированно определяет следующее состояние.

    Рекомендация LLM учитывается, но код проверяет допустимость перехода.
    LEAD_READY разрешается ТОЛЬКО если backend подтвердил готовность
    по merged data. decision.lead_ready как источник истины не используется.
    """

    suggested = decision.next_state

    if suggested == DialogState.LEAD_READY and not is_lead_ready(
        merged_qualification, merged_contact
    ):
        qual_missing = [f for f in _REQUIRED_QUAL if not merged_qualification.get(f)]
        suggested = DialogState.QUALIFICATION if qual_missing else DialogState.CONTACT_CAPTURE

    # Если переход допустим — принимаем
    if suggested in _ALLOWED_TRANSITIONS.get(current, set()):
        return suggested

    # Если нет — остаёмся на месте (не падаем)
    return current

_MAX_CONTACT_ATTEMPTS = 2

def should_close_after_contact_attempts(
        current: DialogState,
        merged_contact: dict | None,
        contact_attempts:int,
) -> bool:
    """True, если в CONTACT_CAPTURE контакт не получен за лимит попыток → закрываем."""
    return (
        current == DialogState.CONTACT_CAPTURE
        and not is_contact_valid(merged_contact)
        and contact_attempts >= _MAX_CONTACT_ATTEMPTS
    )
