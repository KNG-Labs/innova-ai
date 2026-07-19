from app.service.knowledge_ingestion_service import chunk_text


def test_short_text_single_chunk():
    assert chunk_text("короткий текст") == ["короткий текст"]


def test_blank_text_no_chunks():
    assert chunk_text("   ") == []


def test_long_text_chunks_with_overlap():
    chunks = chunk_text("a" * 2000, size=800, overlap=120)
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)
