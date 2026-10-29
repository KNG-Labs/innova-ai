import asyncio
import os
import signal
import sys
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from uuid import uuid4

from app.client.crm_client import FakeCrmClient
from app.db.session import create_session_maker
from app.models.lead_delivery_attempt_model import LeadDeliveryAttemptModel
from app.repository.lead_repository import LeadRepository
from app.service.lead_delivery_service import (
    LeadDeliveryService,
    LeadNotDeliverableError,
    LeadNotFoundError,
)
from main import app

pytestmark = [pytest.mark.integration, pytest.mark.integration_crm_fake]


async def _make_lead(db, *, status: str):
    """Лиду нужен user+session (FK RESTRICT). Создаём через /message-стаб? нет — напрямую."""
    from app.repository.user_repository import UserRepository
    from app.repository.dialog_session_repository import DialogSessionRepository

    user = await UserRepository(db).get_or_create_anonymous_user(
        channel="website", anonymous_id=f"deliver-{uuid4()}"
    )
    session = await DialogSessionRepository(db).get_or_create_active_session(
        user_id=user.id, session_id=None
    )
    repository = LeadRepository(db)
    lead = await repository.upsert_draft(
        user_id=user.id,
        session_id=session.id,
        qualification={
            "car_model": "Kia",
            "budget": "2 млн",
            "purchase_type": "наличные",
        },
        contact={"name": "Пётр", "phone": "+79990000000"},
        summary="тест",
    )
    if status != "draft":
        await repository.update(lead, status=status)
    await db.commit()
    return lead


async def _db():
    """Достаём request-less сессию из того же maker, что и приложение."""
    maker = app.state.db_session_maker
    return maker()


async def test_ready_lead_delivered(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")

    crm = FakeCrmClient()
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await svc.deliver(lead.id)

    assert result.status == "delivered"
    assert result.last_delivery_error is None
    assert len(crm.delivered) == 1
    assert crm.delivered[0].car_model == "Kia"
    async with await _db() as db:
        assert await LeadRepository(db).get_delivery_attempt(lead.id) is None


async def test_draft_lead_rejected(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="draft")

    crm = FakeCrmClient()
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotDeliverableError):
            await svc.deliver(lead.id)

    assert crm.delivered == []  # draft не доставлялся


async def test_crm_failure_marks_delivery_failed(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")

    crm = FakeCrmClient(fail=True)
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await svc.deliver(lead.id)

    assert result.status == "delivery_failed"
    assert result.last_delivery_error  # текст ошибки сохранён
    async with await _db() as db:
        assert await LeadRepository(db).get_delivery_attempt(lead.id) is None


async def test_unknown_lead_raises(client) -> None:
    crm = FakeCrmClient()
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotFoundError):
            await svc.deliver(uuid4())


async def test_delivered_lead_is_not_sent_twice(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")

    crm = FakeCrmClient()

    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        await service.deliver(lead.id)

    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await service.deliver(
            lead.id,
            raise_on_delivery_error=True,
        )

    assert result.id == lead.id
    assert result.status == "delivered"
    assert result.last_delivery_error is None
    assert len(crm.delivered) == 1


async def test_concurrent_delivery_calls_crm_once(client, monkeypatch) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    both_read_ready = asyncio.Barrier(2)
    original_get = LeadRepository.get_by_id

    async def synchronized_get(repository, requested_id):
        result = await original_get(repository, requested_id)
        assert result is not None
        assert result.status == "ready"
        # Both sessions must read ready before either can attempt delivery.
        await both_read_ready.wait()
        return result

    monkeypatch.setattr(LeadRepository, "get_by_id", synchronized_get)
    crm = FakeCrmClient()

    async def deliver() -> str:
        async with await _db() as db:
            service = LeadDeliveryService(db_session=db, crm_client=crm)
            result = await service.deliver(lead_id, raise_on_delivery_error=True)
            return result.status

    statuses = await asyncio.wait_for(asyncio.gather(deliver(), deliver()), timeout=10)

    assert statuses == ["delivered", "delivered"]
    assert len(crm.delivered) == 1
    assert crm.delivered[0].lead_id == lead_id

    async with await _db() as db:
        stored = await original_get(LeadRepository(db), lead_id)
        assert stored is not None
        assert stored.status == "delivered"
        assert stored.last_delivery_error is None


async def test_delivery_attempt_is_saved_and_unique_per_lead(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is None
        db.add(LeadDeliveryAttemptModel(lead_id=lead_id))
        await db.commit()

    async with await _db() as db:
        stored = await LeadRepository(db).get_delivery_attempt(lead_id)
        assert stored is not None
        assert stored.started_at.utcoffset() is not None
        started_at = stored.started_at

    async with await _db() as db:
        # Different timestamps must not permit a second attempt for the same lead.
        db.add(
            LeadDeliveryAttemptModel(
                lead_id=lead_id, started_at=started_at + timedelta(seconds=1)
            )
        )
        with pytest.raises(IntegrityError) as caught:
            await db.commit()
        assert caught.value.orig.sqlstate == "23505"
        await db.rollback()

        stored = await LeadRepository(db).get_delivery_attempt(lead_id)
        assert stored is not None
        assert stored.started_at == started_at


async def test_delivery_attempt_requires_existing_lead(client) -> None:
    async with await _db() as db:
        db.add(LeadDeliveryAttemptModel(lead_id=uuid4()))
        with pytest.raises(IntegrityError) as caught:
            await db.commit()
        assert caught.value.orig.sqlstate == "23503"
        await db.rollback()


async def test_unresolved_delivery_attempt_prevents_lead_deletion(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id
        db.add(LeadDeliveryAttemptModel(lead_id=lead_id))
        await db.commit()

    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead is not None
        await db.delete(lead)
        with pytest.raises(IntegrityError) as caught:
            await db.commit()
        assert caught.value.orig.sqlstate == "23503"
        await db.rollback()

        assert await LeadRepository(db).get_by_id(lead_id) is not None
        assert await db.get(LeadDeliveryAttemptModel, lead_id) is not None


@pytest.mark.parametrize("raise_on_delivery_error", [False, True])
async def test_read_timeout_requires_review_and_blocks_redelivery(
    client, monkeypatch, raise_on_delivery_error
) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    crm = FakeCrmClient()
    original_delivery = crm.deliver_lead
    error = httpx.ReadTimeout("CRM response was lost after creating the lead")

    async def deliver_then_timeout(payload) -> None:
        await original_delivery(payload)
        raise error

    monkeypatch.setattr(crm, "deliver_lead", deliver_then_timeout)

    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        if raise_on_delivery_error:
            with pytest.raises(httpx.ReadTimeout) as caught:
                await service.deliver(lead_id, raise_on_delivery_error=True)
            assert caught.value is error
        else:
            result = await service.deliver(lead_id)
            assert result.status == "needs_review"

    async with await _db() as db:
        stored = await LeadRepository(db).get_by_id(lead_id)
        assert stored is not None
        assert stored.status == "needs_review"
        assert stored.last_delivery_error == repr(error)
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is not None

        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotDeliverableError):
            await service.deliver(lead_id, raise_on_delivery_error=True)

    assert len(crm.delivered) == 1
    assert crm.delivered[0].lead_id == lead_id


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadError("response lost"),
        httpx.WriteTimeout("write timed out"),
        httpx.WriteError("write interrupted"),
        httpx.RemoteProtocolError("invalid response"),
        httpx.DecodingError("invalid encoding"),
        RuntimeError("CRM returned 500"),
    ],
)
async def test_unconfirmed_error_preserves_attempt(client, error) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    crm = AsyncMock()
    crm.deliver_lead.side_effect = error
    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(type(error)):
            await service.deliver(lead_id, raise_on_delivery_error=True)

    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead.status == "needs_review"
        assert lead.last_delivery_error == repr(error)
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is not None

    response = await client.post(f"/leads/{lead_id}/deliver")
    assert response.status_code == 409
    assert "needs_review" in response.json()["detail"]
    assert crm.deliver_lead.await_count == 1


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("connection refused"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.PoolTimeout("pool exhausted"),
    ],
)
async def test_safe_failure_allows_later_delivery(client, error) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    crm = AsyncMock()
    crm.deliver_lead.side_effect = [error, None]
    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(type(error)):
            await service.deliver(lead_id, raise_on_delivery_error=True)

    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead.status == "delivery_failed"
        assert lead.last_delivery_error == repr(error)
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is None
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await service.deliver(lead_id, raise_on_delivery_error=True)
        assert result.status == "delivered"
        assert result.last_delivery_error is None
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is None
    assert crm.deliver_lead.await_count == 2


async def test_crm_is_not_called_when_journal_cannot_be_saved(
    client, monkeypatch
) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    monkeypatch.setattr(
        LeadRepository,
        "start_delivery_attempt",
        AsyncMock(side_effect=RuntimeError("DB unavailable")),
    )
    crm = AsyncMock()
    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(RuntimeError, match="DB unavailable"):
            await service.deliver(lead_id)
    crm.deliver_lead.assert_not_awaited()


async def test_failed_result_commit_leaves_attempt_for_review(
    client, monkeypatch
) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    crm = FakeCrmClient()
    async with await _db() as db:
        monkeypatch.setattr(
            db, "commit", AsyncMock(side_effect=RuntimeError("commit failed"))
        )
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(RuntimeError, match="commit failed"):
            await service.deliver(lead_id)

    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead.status == "ready"
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is not None
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await service.deliver(lead_id)
        assert result.status == "needs_review"
    assert len(crm.delivered) == 1


async def test_killed_worker_leaves_attempt_and_blocks_duplicate(
    client, tmp_path
) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    created = tmp_path / "crm-created.txt"
    worker_code = """
import asyncio
import sys
from pathlib import Path
from uuid import UUID
from app.worker import lead_delivery

class Crm:
    async def deliver_lead(self, payload):
        Path(sys.argv[2]).write_text(str(payload.lead_id))
        print("CRM_CREATED", flush=True)
        await asyncio.Future()

lead_delivery.build_crm_client = lambda http: Crm()
asyncio.run(lead_delivery._deliver_lead(UUID(sys.argv[1])))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-B",
        "-c",
        worker_code,
        str(lead_id),
        str(created),
        env={**os.environ, "PYTHON_DOTENV_DISABLED": "1", "REDIS_URL": "memory://"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        line = await asyncio.wait_for(process.stdout.readline(), timeout=20)
        assert line == b"CRM_CREATED\n"
    finally:
        if process.returncode is None:
            process.kill()
        await asyncio.wait_for(process.communicate(), timeout=10)

    assert process.returncode == -signal.SIGKILL
    assert created.read_text() == str(lead_id)
    crm = FakeCrmClient()
    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead.status == "ready"
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is not None
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotDeliverableError, match="unconfirmed"):
            await service.deliver(lead_id, raise_on_delivery_error=True)

    async with await _db() as db:
        lead = await LeadRepository(db).get_by_id(lead_id)
        assert lead.status == "needs_review"
        assert "unconfirmed" in lead.last_delivery_error
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is not None
    assert crm.delivered == []


async def test_journal_can_be_saved_with_a_single_connection_pool(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")
        lead_id = lead.id

    engine = create_async_engine(
        app.state.db_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.2
    )
    try:
        maker = create_session_maker(engine)
        crm = FakeCrmClient()
        async with maker() as db:
            service = LeadDeliveryService(db_session=db, crm_client=crm)
            result = await service.deliver(lead_id, raise_on_delivery_error=True)
            assert result.status == "delivered"
            assert await LeadRepository(db).get_delivery_attempt(lead_id) is None
        assert len(crm.delivered) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize("resolved_status", ["delivered", "ready"])
@pytest.mark.parametrize("has_attempt", [False, True])
async def test_manual_review_resolves_attempt_atomically(
    client, resolved_status, has_attempt
) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="needs_review")
        lead_id = lead.id
        if has_attempt:
            db.add(LeadDeliveryAttemptModel(lead_id=lead_id))
        await db.commit()

    async with await _db() as db:
        await db.execute(
            text("SELECT id FROM leads WHERE id=:lead_id FOR NO KEY UPDATE"),
            {"lead_id": lead_id},
        )
        resolved_id = await db.scalar(
            text("""
                WITH resolved AS (
                    UPDATE leads SET status=:status, last_delivery_error=NULL
                    WHERE id=:lead_id AND status='needs_review' RETURNING id
                ), cleared AS (
                    DELETE FROM lead_delivery_attempts USING resolved
                    WHERE lead_delivery_attempts.lead_id=resolved.id
                    RETURNING lead_delivery_attempts.lead_id
                )
                SELECT id FROM resolved
            """),
            {"lead_id": lead_id, "status": resolved_status},
        )
        assert resolved_id == lead_id
        await db.commit()

    crm = FakeCrmClient()
    async with await _db() as db:
        service = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await service.deliver(lead_id, raise_on_delivery_error=True)
        assert result.status == "delivered"
        assert await LeadRepository(db).get_delivery_attempt(lead_id) is None
    assert len(crm.delivered) == (1 if resolved_status == "ready" else 0)
