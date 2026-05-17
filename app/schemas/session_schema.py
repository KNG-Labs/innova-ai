from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas import Channel, DialogState


class SessionResponse(BaseModel):
    """Response для GET /session/{session_id}"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    state: DialogState
    channel: Channel
    created_at: datetime
    updated_at: datetime


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class StoredMessageResponse(BaseModel):
    """Response для GET /session/{session_id}/messages"""

    model_config = ConfigDict(extra="forbid")
    
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime