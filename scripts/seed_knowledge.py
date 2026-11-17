"""Seed an empty demo database without exposing an administrative HTTP route."""

import argparse
import asyncio
import os
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy.engine import make_url

from app.client.embedding_client import build_embedding_client
from app.db.session import create_engine, create_session_maker
from app.repository.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import KnowledgeDocumentCreate
from app.service.knowledge_ingestion_service import KnowledgeIngestionService


async def seed_knowledge(corpus: Path) -> int:
    database_url = os.environ["DATABASE_URL"]
    database = make_url(database_url).database or ""
    if database != "innova" and not database.endswith(("_test", "_eval")):
        raise RuntimeError("Knowledge seed requires innova or a temporary test DB")
    documents = TypeAdapter(list[KnowledgeDocumentCreate]).validate_json(
        corpus.read_text(encoding="utf-8")
    )
    if not documents:
        raise ValueError("Knowledge corpus must not be empty")

    engine = create_engine(database_url)
    try:
        async with create_session_maker(engine)() as session:
            if await KnowledgeRepository(session).list_documents():
                return 0
            ids = await KnowledgeIngestionService(
                session, build_embedding_client()
            ).ingest_many(documents)
            return len(ids)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    print(f"Seeded {asyncio.run(seed_knowledge(args.corpus))} knowledge documents")
