from dataclasses import dataclass
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import EmbeddingClient
from app.client.retrieval_planner_client import (
    RetrievalMode,
    RetrievalPlan,
    RetrievalPlannerClient,
)
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import RetrievedChunk
from app.service.retrieval_selector import RetrievalCandidate, select_source

_DEFAULT_TOP_K = 5
_DEFAULT_MIN_SCORE = 0.2


@dataclass(frozen=True)
class RetrievalResult:
    chunks: tuple[RetrievedChunk, ...] = ()
    source_id: UUID | None = None
    source_title: str | None = None


class KnowledgeRetrievalService:
    def __init__(
        self,
        db_session: AsyncSession,
        embedding_client: EmbeddingClient,
        retrieval_planner: RetrievalPlannerClient,
        *,
        top_k: int = _DEFAULT_TOP_K,
        min_score: float = _DEFAULT_MIN_SCORE,
    ) -> None:
        self._repo = KnowledgeRepository(db_session)
        self._embedding = embedding_client
        self._planner = retrieval_planner
        self._top_k = top_k
        self._min_score = min_score

    async def retrieve(
        self,
        query: str,
        *,
        last_source_id: UUID | None = None,
        last_source_title: str | None = None,
        history: list[dict] | None = None,
    ) -> RetrievalResult:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            return RetrievalResult()

        plan = RetrievalPlan(mode=RetrievalMode.CURRENT, query=normalized_query)
        normalized_title = (last_source_title or "").strip()
        if last_source_id is not None and normalized_title:
            try:
                plan = await self._planner.plan(
                    current_message=normalized_query,
                    last_source_title=normalized_title,
                    history=(history or [])[-6:],
                )
            except Exception as exc:  # noqa: BLE001 - retrieval must abstain safely
                logging.getLogger(__name__).warning(
                    "Retrieval planner failed (%s): %r",
                    type(exc).__name__,
                    exc,
                )
                plan = RetrievalPlan.none()

        if plan.mode == RetrievalMode.NONE:
            return RetrievalResult()

        [query_embedding] = await self._embedding.embed([plan.query])
        required_source_id = (
            last_source_id if plan.mode == RetrievalMode.LAST_SOURCE else None
        )
        rows = await self._repo.search_chunks(
            query_embedding,
            self._top_k,
            document_id=required_source_id,
        )
        candidates = [
            RetrievalCandidate(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                title=title,
                score=score,
                content=chunk.content,
            )
            for chunk, title, score in rows
            if score >= self._min_score
        ]

        selection = select_source(
            candidates=candidates,
            required_source_id=required_source_id,
        )
        if selection is None:
            return RetrievalResult()

        chunks = tuple(
            RetrievedChunk(
                document_id=candidate.document_id,
                chunk_id=candidate.chunk_id,
                title=candidate.title,
                score=candidate.score,
                content=candidate.content,
            )
            for candidate in selection.candidates
        )
        return RetrievalResult(
            chunks=chunks,
            source_id=selection.source_id,
            source_title=selection.source_title,
        )


def format_chunks_for_prompt(chunks: tuple[RetrievedChunk, ...]) -> str:
    """Блок для AG2. Пусто -> ''."""
    if not chunks:
        return ""
    return "\n\n".join(f"[Источник: {c.title}]\n{c.content}" for c in chunks)
