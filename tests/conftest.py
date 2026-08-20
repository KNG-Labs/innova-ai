# ruff: noqa: E402

import os
from collections.abc import AsyncGenerator

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test",
)

TEST_ENV = {
    "DATABASE_URL": TEST_DATABASE_URL,
    "LLM_PROVIDER": "stub",
    "EMBEDDING_PROVIDER": "fake",
    "LEAD_DELIVERY_PROVIDER": "disabled",
    "OPENROUTER_API_KEY": "",
    "AMOCRM_BASE_URL": "",
    "AMOCRM_ACCESS_TOKEN": "",
    "LEAD_WEBHOOK_URL": "",
    "TELEGRAM_BOT_TOKEN": "",
    "REDIS_URL": "",
    "DEEPEVAL_DISABLE_DOTENV": "1",
    "DEEPEVAL_TELEMETRY_OPT_OUT": "YES",
    "DEEPEVAL_CACHE_FOLDER": "/tmp/innova-deepeval-test-cache",
    "CONFIDENT_API_KEY": "",
}

# Keep test imports hermetic: main.py loads .env at import time.
os.environ.update(TEST_ENV)

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from app.db.base import Base
from app.di import close_app_state, init_app_state
from main import app


@pytest_asyncio.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    for name, value in TEST_ENV.items():
        monkeypatch.setenv(name, value)

    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(lambda c: Base.metadata.drop_all(c))
        await connection.run_sync(lambda c: Base.metadata.create_all(c))

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
