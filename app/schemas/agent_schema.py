from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, BaseModel, ConfigDict, field_validator

_PAGE_TITLE_MAX = 200

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
    """Состояние backend-машины диалога."""

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
    page_title: str | None = Field(
        default=None,
        description=(
            "Заголовок страницы сайта, с которой пишет пользователь. "
            "Необязательный context-сигнал для агента."
        ),
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Сообщение не должно быть пустым")
        return normalized

    @field_validator("page_title")
    @classmethod
    def _normalize_page_title(cls, value: str | None) -> str | None:
        """Внешний (браузерный) ввод -> нормализуем на границе.

        " ".join(split()) схлопывает пробелы И вырезает переводы строк —
        чтобы заголовок не разорвал строку [Страница сайта: ...] в промпте
        (минимальная защита от инъекции в контекст).
        Пустой после нормализации -> None. Длину РЕЖЕМ, а не отвергаем:
        опциональный context не должен ронять сообщение через 422.
        """
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        return normalized[:_PAGE_TITLE_MAX]


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
