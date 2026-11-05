from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.privacy import PiiAnalysisError, PiiSanitizer
from app.schemas.knowledge_schema import RetrievedChunk
from app.service.knowledge_retrieval_service import (
    KnowledgeRetrievalService,
    format_chunks_for_prompt,
)

pytestmark = pytest.mark.unit


class _Embedding:
    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(texts)
        return [[1.0] for _ in texts]


class _Repository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def search_chunks(self, embedding, top_k):
        self.calls.append((embedding, top_k))
        return self.rows[:top_k]


def _row(title, score):
    return (
        SimpleNamespace(document_id=uuid4(), id=uuid4(), content=title + " facts"),
        title,
        score,
    )


def _retrieval(rows):
    embedding = _Embedding()
    service = KnowledgeRetrievalService(None, embedding, top_k=3, min_score=0.2)
    repository = _Repository(rows)
    service._repo = repository
    return service, embedding, repository


async def test_direct_search_keeps_multiple_documents_and_applies_score_threshold():
    service, embedding, repository = _retrieval(
        [
            _row("Camry", 0.9),
            _row("Creta", 0.8),
            _row("Unrelated", 0.19),
            _row("Extra", 0.5),
        ]
    )

    result = await service.retrieve("  Сравни   Camry и Creta  ")

    assert [chunk.title for chunk in result] == ["Camry", "Creta"]
    assert embedding.calls == [["Сравни Camry и Creta"]]
    assert repository.calls == [([1.0], 3)]


async def test_current_message_is_not_rewritten_or_restricted_to_previous_source():
    service, embedding, _ = _retrieval([_row("Trade-in", 0.8)])
    await service.retrieve("Trade-in")
    await service.retrieve("Кредит")
    assert embedding.calls == [["Trade-in"], ["Кредит"]]


async def test_query_contacts_are_masked_before_embedding():
    service, embedding, _ = _retrieval([])
    await service.retrieve("Телефон +79991234567, условия кредита")
    assert embedding.calls == [["Телефон [PHONE_1], условия кредита"]]


async def test_empty_query_does_not_call_embedding_or_database():
    service, embedding, repository = _retrieval([])
    assert await service.retrieve("  ") == ()
    assert embedding.calls == repository.calls == []


async def test_analyzer_failure_blocks_embedding_and_database(monkeypatch):
    def fail(self, text):
        raise PiiAnalysisError("synthetic failure")

    monkeypatch.setattr(PiiSanitizer, "find_entities", fail)
    service, embedding, repository = _retrieval([])
    assert await service.retrieve("Кредит") == ()
    assert embedding.calls == repository.calls == []


def test_prompt_keeps_source_labels():
    chunk = RetrievedChunk(
        document_id=uuid4(),
        chunk_id=uuid4(),
        title="Trade-in",
        content="Оценка бесплатна.",
        score=0.9,
    )
    assert (
        format_chunks_for_prompt((chunk,)) == "[Источник: Trade-in]\nОценка бесплатна."
    )
    assert format_chunks_for_prompt(()) == ""
