from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_model import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self, *, title: str, source: str, content: str
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(title=title, source=source, content=content)
        self._session.add(doc)
        await self._session.flush()
        return doc

    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None:
        return await self._session.get(KnowledgeDocument, document_id)

    async def list_documents(self) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_chunks(
        self,
        *,
        document_id: UUID,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        for i, (content, emb) in enumerate(zip(chunks, embeddings, strict=True)):
            self._session.add(
                KnowledgeChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=content,
                    embedding=emb,
                )
            )
        await self._session.flush()

    async def delete_chunks_for_document(self, document_id: UUID) -> None:
        await self._session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        await self._session.flush()

    async def search_chunks(
        self, query_embedding: list[float], top_k: int
    ) -> list[tuple[KnowledgeChunk, float]]:
        """top_k ближайших по cosine. score = 1 - cosine_distance."""
        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(KnowledgeChunk, distance.label("distance"))
            .order_by(distance)
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return [(row[0], 1.0 - float(row[1])) for row in result.all()]
