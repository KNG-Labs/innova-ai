import re

from app.schemas.agent_schema import AgentDecision, DialogState, LeadIntentStatus
from app.domain import REQUIRED_QUAL


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
        DialogState.FAQ,
        DialogState.CONTACT_CAPTURE,
        DialogState.LEAD_READY,
        DialogState.CLOSED,
    },
    DialogState.LEAD_READY: {DialogState.CLOSED},
    DialogState.CLOSED: set(),
}


def apply_qualification_patch(
    existing: dict[str, str | None],
    patch: dict[str, str | None],
) -> dict[str, str]:
    """Применить patch: null удаляет, значение устанавливает."""
    result = {k: v for k, v in existing.items() if v is not None}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


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


_CONTACT_FIELDS = ("phone", "email", "telegram")


def is_contact_valid(contact: dict | None) -> bool:
    """Контакт валиден, если указан хотя бы один поддерживаемый способ связи."""
    if not contact:
        return False

    return any(
        isinstance(contact.get(field), str) and bool(contact[field].strip())
        for field in _CONTACT_FIELDS
    )


def compute_missing_fields(
    qualification_data: dict[str, str],
    contact: dict[str, str] | None,
) -> list[str]:
    """Backend сам считает, чего не хватает. LLM не доверяем."""
    missing = [f for f in REQUIRED_QUAL if not qualification_data.get(f)]
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
    merged_contact: dict | None,
    *,
    lead_intent_confirmed: bool = False,
) -> DialogState:
    """Детерминированно определяет следующее состояние.

    Рекомендация LLM учитывается, но код проверяет допустимость перехода.
    LEAD_READY разрешается ТОЛЬКО если backend подтвердил готовность
    по merged data. decision.lead_ready как источник истины не используется.
    """

    suggested = decision.next_state

    if (
        current in {DialogState.GREETING, DialogState.FAQ}
        and suggested == DialogState.QUALIFICATION
        and not lead_intent_confirmed
    ):
        suggested = DialogState.FAQ

    if suggested == DialogState.LEAD_READY and not is_lead_ready(
        merged_qualification, merged_contact
    ):
        qual_missing = [f for f in REQUIRED_QUAL if not merged_qualification.get(f)]
        suggested = (
            DialogState.QUALIFICATION if qual_missing else DialogState.CONTACT_CAPTURE
        )

    # Если переход допустим — принимаем
    if suggested in _ALLOWED_TRANSITIONS.get(current, set()):
        return suggested

    # Если нет — остаёмся на месте (не падаем)
    return current


_EXPLICIT_LEAD_PATTERNS = (
    re.compile(
        r"\b(?:хочу|желаю|планирую)\s+"
        r"(?:купить|подобрать|заказать|оформить|приобрести|записаться)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:помоги(?:те)?|нужно)\s+"
        r"(?:купить|подобрать|заказать|оформить|выбрать)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:оставить|оформить)\s+заявк", re.IGNORECASE),
    re.compile(r"\b(?:можно|хочу)\s+записаться\b", re.IGNORECASE),
    re.compile(r"\bперезвоните\b", re.IGNORECASE),
)

_QUESTION_PREFIXES = (
    "а ",
    "где ",
    "зачем ",
    "как ",
    "какие ",
    "какой ",
    "когда ",
    "можно ли ",
    "почему ",
    "расскажи ",
    "расскажите ",
    "сколько ",
    "что ",
)

_INFORMATION_REQUEST_PATTERN = re.compile(
    r"\b(?:напомни(?:те)?|расскажи(?:те)?|подскажи(?:те)?|объясни(?:те)?)\b",
    re.IGNORECASE,
)

_UNKNOWN_ANSWER_PATTERNS = (
    re.compile(r"\b(?:пока\s+)?не\s+знаю\b", re.IGNORECASE),
    re.compile(r"\bне\s+определил(?:ся|ась)?\b", re.IGNORECASE),
    re.compile(r"\bне\s+решил(?:а)?\b", re.IGNORECASE),
    re.compile(r"\bбез\s+понятия\b", re.IGNORECASE),
    re.compile(r"\bзатрудняюсь\s+ответить\b", re.IGNORECASE),
)


def has_explicit_lead_request(message: str) -> bool:
    """Домен-нейтральные действия покупки/заявки, а не название услуги."""

    return any(pattern.search(message) for pattern in _EXPLICIT_LEAD_PATTERNS)


def is_information_question(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return (
        "?" in message
        or normalized.startswith(_QUESTION_PREFIXES)
        or _INFORMATION_REQUEST_PATTERN.search(normalized) is not None
    )


def is_unknown_qualification_answer(message: str) -> bool:
    """Пользователь явно не может назвать значение ожидаемого поля."""

    return any(pattern.search(message) for pattern in _UNKNOWN_ANSWER_PATTERNS)


def has_confirmed_lead_intent(
    *,
    current_state: DialogState,
    user_message: str,
    decision: AgentDecision,
    expected_qualification_field: str | None,
    lead_intent_confirmation_pending: bool = False,
) -> bool:
    """Проверяем фактические сигналы; одного next_state от LLM недостаточно."""

    if has_explicit_lead_request(user_message):
        return True
    if is_contact_valid(decision.extracted_contact):
        return True
    if (
        current_state in {DialogState.GREETING, DialogState.FAQ}
        and lead_intent_confirmation_pending
        and decision.lead_intent_status == LeadIntentStatus.CONFIRMED
    ):
        return True

    patch_keys = {
        key for key, value in decision.qualification_patch.items() if value is not None
    }
    if (
        current_state == DialogState.QUALIFICATION
        and expected_qualification_field in patch_keys
    ):
        return True

    return False


def next_expected_qualification_field(
    state: DialogState,
    qualification_data: dict[str, str],
) -> str | None:
    if state != DialogState.QUALIFICATION:
        return None
    return next(
        (field for field in REQUIRED_QUAL if not qualification_data.get(field)),
        None,
    )


_MAX_CONTACT_REFUSALS = 2


def should_opt_out_after_contact_refusals(contact_refusals: int) -> bool:
    """После двух явных отказов сбор контакта прекращается."""
    return contact_refusals >= _MAX_CONTACT_REFUSALS
