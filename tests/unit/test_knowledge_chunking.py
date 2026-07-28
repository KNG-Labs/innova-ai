from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.service.knowledge_ingestion_service import (
    KnowledgeIngestionService,
    chunk_text,
)


def test_short_text_single_chunk():
    assert chunk_text("короткий текст") == ["короткий текст"]


def test_blank_text_no_chunks():
    assert chunk_text("   ") == []


def test_long_text_chunks_with_overlap():
    chunks = chunk_text("a" * 2000, size=800, overlap=120)
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)


@pytest.mark.asyncio
async def test_document_title_is_included_in_embedding_but_not_stored_content():
    class _Embedding:
        def __init__(self):
            self.texts = []

        async def embed(self, texts):
            self.texts = texts
            return [[0.0] * 1536 for _ in texts]

    class _Repository:
        def __init__(self):
            self.saved = None

        async def add_chunks(self, **kwargs):
            self.saved = kwargs

    embedding = _Embedding()
    repository = _Repository()
    service = KnowledgeIngestionService(
        SimpleNamespace(),  # type: ignore[arg-type]
        embedding,
    )
    service._repo = repository
    document_id = uuid4()

    await service._index_document(
        document_id,
        "Программа Trade-in",
        "Оценка автомобиля бесплатна.",
    )

    assert embedding.texts == ["Программа Trade-in\nОценка автомобиля бесплатна."]
    assert repository.saved["chunks"] == ["Оценка автомобиля бесплатна."]
