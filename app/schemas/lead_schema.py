from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeadListItem(BaseModel):
    """Строка списка GET /leads. Лёгкая: без тяжёлых JSONB-полей."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    user_id: UUID
    status: str
    summary: str | None
    created_at: datetime


class LeadResponse(BaseModel):
    """Карточка лида GET /leads/{lead_id}. Полная."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    user_id: UUID
    status: str
    qualification: dict | None
    contact: dict | None
    summary: str | None
    created_at: datetime
    updated_at: datetime