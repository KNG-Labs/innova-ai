import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with TestClient(app) as test_client:
        yield test_client
