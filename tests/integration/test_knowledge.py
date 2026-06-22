import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.client.embedding_client import FakeEmbeddingClient
from app.db.base import Base
from app.schemas.knowledge_schema import KnowledgeDocumentCreate
from app.service.knowledge_ingestion_service import KnowledgeIngestionService
from app.service.knowledge_retrieval_service import KnowledgeRetrievalService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(lambda c: Base.metadata.drop_all(c))
        await conn.run_sync(lambda c: Base.metadata.create_all(c))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session):
    ingest = KnowledgeIngestionService(session, FakeEmbeddingClient())
    for doc in (
        (
            "Цены",
            "Базовый пилот Innova AI стоит от 150000 рублей за внедрение ассистента.",
        ),
        ("Сроки", "Внедрение ассистента занимает от двух до четырёх недель."),
        (
            "Поддержка",
            "Поддержка плюс обновление базы знаний — часть стоимости пилота.",
        ),
    ):
        await ingest.ingest(KnowledgeDocumentCreate(title=doc[0], content=doc[1]))


async def test_relevant_faq_is_retrieved(session):
    await _seed(session)
    retrieval = KnowledgeRetrievalService(session, FakeEmbeddingClient(), min_score=0.2)
    chunks = await retrieval.retrieve("сколько стоит внедрение пилота")
    assert chunks
    assert any("150000" in c.content for c in chunks)


async def test_unknown_question_returns_nothing(session):
    await _seed(session)
    retrieval = KnowledgeRetrievalService(session, FakeEmbeddingClient(), min_score=0.2)
    assert await retrieval.retrieve("как приготовить домашний борщ") == []


async def test_ingest_and_list_via_api(client):
    r = await client.post(
        "/knowledge/documents",
        json=[
            {"title": "Camry", "content": "Toyota Camry — седан бизнес-класса."},
            {"title": "RAV4", "content": "Toyota RAV4 — компактный кроссовер."},
        ],
    )
    assert r.status_code == 201
    assert len(r.json()["document_ids"]) == 2
    listed = await client.get("/knowledge/documents")
    titles = [d["title"] for d in listed.json()]
    assert {"Camry", "RAV4"} <= set(titles)
