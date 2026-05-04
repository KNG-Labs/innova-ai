from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MessageRequest(BaseModel):
    """Входной объект для эндпоинта /message"""

    text: Annotated[str, Field(min_length=1, max_length=1000)]
    session_id: UUID

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Сообщение не должно быть пустым!")
        return v


class MessageResponse(BaseModel):
    """Ответ для эндпоинта /message"""

    text: str
    intent: Literal["greeting", "faq", "lead_ready", "unknown"]
