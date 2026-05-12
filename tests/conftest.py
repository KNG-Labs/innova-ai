import httpx
import pytest
import pytest_asyncio

from app.di import close_app_state, init_app_state
from app.main import app


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> httpx.AsyncClient:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

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
