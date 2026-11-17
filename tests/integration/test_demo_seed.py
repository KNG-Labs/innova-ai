import json

import pytest
from sqlalchemy import select, func

from app.db.session import create_engine, create_session_maker
from app.models.knowledge_model import KnowledgeDocument
from scripts.seed_knowledge import seed_knowledge
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.integration


async def test_seed_only_populates_an_empty_database(client, tmp_path):
    corpus = tmp_path / "knowledge.json"
    corpus.write_text(
        json.dumps([{"title": "Демо", "content": "Информация компании."}])
    )
    assert await seed_knowledge(corpus) == 1
    assert await seed_knowledge(corpus) == 0
    engine = create_engine(TEST_DATABASE_URL)
    try:
        async with create_session_maker(engine)() as db:
            assert (
                await db.scalar(select(func.count()).select_from(KnowledgeDocument))
                == 1
            )
    finally:
        await engine.dispose()


async def test_seed_rejects_unrelated_database_before_connecting(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/production")
    with pytest.raises(RuntimeError, match="temporary test DB"):
        await seed_knowledge(tmp_path / "not-read.json")
