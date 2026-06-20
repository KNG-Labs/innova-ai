from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, BaseModel, ConfigDict, field_validator

AnonymousId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=128,
        pattern=r"^[a-zA-Z0-9._:-]+$",
        description=(
            "Анонимный идентификатор юзера.Генерирует клиентская часть.Хранится в куки"
        ),
    ),
]


class Channel(StrEnum):
    """Канал, из которого пришло сообщение пользователя."""

    WEBSITE = "website"
    TELEGRAM = "telegram"
    AVITO = "avito"


class DialogState(StrEnum):
    """Состояние диалога.

    Заготовка под будущий state machine.
    """

    GREETING = "GREETING"
    FAQ = "FAQ"
    QUALIFICATION = "QUALIFICATION"
    CONTACT_CAPTURE = "CONTACT_CAPTURE"
    LEAD_READY = "LEAD_READY"
    CLOSED = "CLOSED"


class AgentMessageRequest(BaseModel):
    """Публичный request для POST /message.

    Это именно сообщение от пользователя агенту.
    """

    model_config = ConfigDict(extra="forbid")

    anonymous_id: AnonymousId
    session_id: UUID | None = Field(
        default=None,
        description=(
            "ID текущей сессии, "
            "Если упущено, бэкэнд должен создать или найти активную сессию."
        ),
    )
    channel: Channel = Field(default=Channel.WEBSITE)
    content: str = Field(
        min_length=1,
        max_length=4000,
        description="User message text.",
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Сообщение не должно быть пустым")
        return normalized


class AgentMessageResponse(BaseModel):
    """Публичный response от агента Innova AI."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID

    answer: str

    state: DialogState
    intent: str
    next_step: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    lead_id: UUID | None = None


class AgentDecision(BaseModel):
    """Структурированный ответ агента после обработки сообщения."""

    answer: str
    intent: str
    next_state: DialogState
    qualification_data: dict[str, str | None]
    missing_fields: list[str]
    lead_ready: bool
    extracted_contact: dict[str, str | None] | None = None
    lead_summary: str | None = None

    @field_validator("qualification_data", "extracted_contact", mode="before")
    @classmethod
    def _stringify_values(cls, v: object) -> object:
        """LLM иногда шлёт числа (budget: 500000, phone: 7999...).
        Приводим значения dict к строке до проверки типа."""
        if isinstance(v, dict):
            return {k: (None if val is None else str(val)) for k, val in v.items()}
        return v
