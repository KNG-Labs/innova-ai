import pytest
from uuid import uuid4

from app.client.crm_client import FakeCrmClient
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
    lead = await LeadRepository(db).create(
        user_id=user.id,
        session_id=session.id,
        status=status,
        qualification={
            "car_model": "Kia",
            "budget": "2 млн",
            "purchase_type": "наличные",
        },
        contact={"name": "Пётр", "phone": "+79990000000"},
        summary="тест",
    )
    await db.commit()
    return lead


async def _db():
    """Достаём request-less сессию из того же maker, что и приложение."""
    maker = app.state.db_session_maker
    return maker()


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_draft_lead_rejected(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="draft")

    crm = FakeCrmClient()
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotDeliverableError):
            await svc.deliver(lead.id)

    assert crm.delivered == []  # draft не доставлялся


@pytest.mark.asyncio
async def test_crm_failure_marks_delivery_failed(client) -> None:
    async with await _db() as db:
        lead = await _make_lead(db, status="ready")

    crm = FakeCrmClient(fail=True)
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        result = await svc.deliver(lead.id)

    assert result.status == "delivery_failed"
    assert result.last_delivery_error  # текст ошибки сохранён


@pytest.mark.asyncio
async def test_unknown_lead_raises(client) -> None:
    crm = FakeCrmClient()
    async with await _db() as db:
        svc = LeadDeliveryService(db_session=db, crm_client=crm)
        with pytest.raises(LeadNotFoundError):
            await svc.deliver(uuid4())
