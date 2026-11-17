import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import EmbeddingClient
from app.privacy import PrivacyBoundaryError, PiiSanitizer
from app.tracing import traced, update_observation
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import RetrievedChunk

_DEFAULT_TOP_K = 5
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

    @traced("retrieve-context", as_type="retriever")
    async def retrieve(self, query: str) -> tuple[RetrievedChunk, ...]:
        update_observation(output={"chunks": []})
        try:
            query = " ".join(PiiSanitizer().sanitize_text(query).text.split())
            if not query:
                return ()
            update_observation(
                input=query,
                metadata={"top_k": self._top_k, "min_score": self._min_score},
            )
            [query_embedding] = await self._embedding.embed([query])
        except PrivacyBoundaryError:
            update_observation(level="WARNING", status_message="privacy_blocked")
            logging.getLogger(__name__).warning("Retrieval blocked by privacy boundary")
            return ()

        rows = await self._repo.search_chunks(query_embedding, self._top_k)
        chunks = tuple(
            RetrievedChunk(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                title=title,
                score=score,
                content=chunk.content,
            )
            for chunk, title, score in rows
            if score >= self._min_score
        )
        update_observation(
            output={"chunks": [chunk.model_dump(mode="json") for chunk in chunks]}
        )
        return chunks


def format_chunks_for_prompt(chunks: tuple[RetrievedChunk, ...]) -> str:
    return "\n\n".join(f"[Источник: {c.title}]\n{c.content}" for c in chunks)
