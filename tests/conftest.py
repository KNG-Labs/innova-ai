import os
from collections.abc import AsyncGenerator
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.di import close_app_state, init_app_state
from main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test",
)


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection:Base.metadata.drop_all)
        await connection.run_sync(lambda sync_connection:Base.metadata.create_all)

    await engine.dispose()

    transport = httpx.ASGITransport(app=app)

    await init_app_state(app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            yield test_client
    finally:
        await close_app_state(app)
        app.dependency_overrides.clear()
