from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import EmbeddingClient
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentListItem,
)

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 120


def chunk_text(
    text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP
) -> list[str]:
    """Нарезка на куски ~size симв. с overlap. Пустые отбрасываются."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = size - overlap
    chunks = [text[i : i + size].strip() for i in range(0, len(text), step)]
    return [c for c in chunks if c]


class KnowledgeIngestionService:
    def __init__(
        self, db_session: AsyncSession, embedding_client: EmbeddingClient
    ) -> None:
        self._db = db_session
        self._repo = KnowledgeRepository(db_session)
        self._embedding = embedding_client

    async def ingest(self, payload: KnowledgeDocumentCreate) -> UUID:
        doc = await self._repo.create_document(
            title=payload.title, source=payload.source, content=payload.content
        )
        await self._index_document(doc.id, payload.content)
        await self._db.commit()
        return doc.id

    async def ingest_many(self, payloads: list[KnowledgeDocumentCreate]) -> list[UUID]:
        ids: list[UUID] = []
        for payload in payloads:
            doc = await self._repo.create_document(
                title=payload.title, source=payload.source, content=payload.content
            )
            await self._index_document(doc.id, payload.content)
            ids.append(doc.id)
        await self._db.commit()
        return ids

    async def list_documents(self) -> list[KnowledgeDocumentListItem]:
        rows = await self._repo.list_documents()
        return [
            KnowledgeDocumentListItem(
                id=r.id, title=r.title, source=r.source, created_at=r.created_at
            )
            for r in rows
        ]

    async def reindex(self) -> int:
        docs = await self._repo.list_documents()
        for doc in docs:
            await self._repo.delete_chunks_for_document(doc.id)
            await self._index_document(doc.id, doc.content)
        await self._db.commit()
        return len(docs)

    async def _index_document(self, document_id: UUID, content: str) -> None:
        chunks = chunk_text(content)
        if not chunks:
            return
        embeddings = await self._embedding.embed(chunks)
        await self._repo.add_chunks(
            document_id=document_id, chunks=chunks, embeddings=embeddings
        )
