from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import EmbeddingClient
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import RetrievedChunk

_DEFAULT_TOP_K = 3
_DEFAULT_MIN_SCORE = 0.2


class KnowledgeRetrievalService:
    def __init__(
        self,
        db_session: AsyncSession,
        embedding_client: EmbeddingClient,
        *,
        top_k: int = _DEFAULT_TOP_K,
        min_score: float = _DEFAULT_MIN_SCORE,
    ) -> None:
        self._repo = KnowledgeRepository(db_session)
        self._embedding = embedding_client
        self._top_k = top_k
        self._min_score = min_score

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        [query_emb] = await self._embedding.embed([query])
        rows = await self._repo.search_chunks(query_emb, self._top_k)
        return [
            RetrievedChunk(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                score=score,
                content=chunk.content,
            )
            for chunk, score in rows
            if score >= self._min_score
        ]


def format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Блок для AG2. Пусто -> ''."""
    if not chunks:
        return ""
    return "\n\n".join(f"[score={c.score:.2f}] {c.content}" for c in chunks)
