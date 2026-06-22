from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=512)
    source: str = Field(default="manual", max_length=128)
    content: str = Field(min_length=1)


class KnowledgeDocumentListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    source: str
    created_at: datetime


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    chunk_id: UUID
    score: float
    content: str
