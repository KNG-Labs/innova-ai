import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.di import get_db_session
from main import app


pytestmark = pytest.mark.integration


async def test_health_returns_ok_when_database_is_available(client) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_returns_503_without_exposing_error(client) -> None:
    class FailingSession:
        async def execute(self, statement) -> None:
            raise SQLAlchemyError("credentials must not be exposed")

    async def failing_session():
        yield FailingSession()

    app.dependency_overrides[get_db_session] = failing_session

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "credentials" not in response.text
