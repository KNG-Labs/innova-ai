from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("error", "expected_attempts"),
    [
        (httpx.ConnectError("connection failed"), 4),
        (httpx.ConnectTimeout("connect timed out"), 4),
        (httpx.PoolTimeout("pool exhausted"), 4),
        (httpx.ReadTimeout("response timed out"), 1),
        (RuntimeError("unconfirmed CRM response"), 1),
    ],
)
def test_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_attempts: int,
) -> None:
    monkeypatch.setenv("REDIS_URL", "memory://")
    from app.worker import lead_delivery

    delivery = AsyncMock(side_effect=error)
    monkeypatch.setattr(lead_delivery, "_deliver_lead", delivery)

    result = lead_delivery.deliver_lead.apply(args=[str(uuid4())])

    assert result.failed()
    assert delivery.await_count == expected_attempts
