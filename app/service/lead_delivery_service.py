from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.crm_client import CrmClient, build_crm_payload
from app.models.lead_model import Lead
from app.repository.lead_repository import LeadRepository

_DELIVERABLE_STATUSES = {"ready", "delivery_failed"}
_ERROR_MAX_LEN = 1000


class LeadNotFoundError(Exception):
    """Лид не найден."""


class LeadNotDeliverableError(Exception):
    """Лид в статусе, из которого доставка запрещена (например draft)."""


class LeadDeliveryService:
    def __init__(self, *, db_session: AsyncSession, crm_client: CrmClient) -> None:
        self._db_session = db_session
        self._leads = LeadRepository(db_session)
        self._crm = crm_client

    async def deliver(self, lead_id: UUID) -> Lead:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError

        # draft не доставляется (acceptance Phase 5)
        if lead.status not in _DELIVERABLE_STATUSES:
            raise LeadNotDeliverableError

        payload = build_crm_payload(
            lead_id=lead.id,
            session_id=lead.session_id,
            qualification=lead.qualification,
            contact=lead.contact,
            summary=lead.summary,
        )

        try:
            await self._crm.deliver_lead(payload)
            lead.status = "delivered"
            lead.last_delivery_error = None
        except Exception as exc:  # noqa: BLE001 - ошибка доставки = бизнес-исход, не 500
            lead.status = "delivery_failed"
            lead.last_delivery_error = str(exc)[:_ERROR_MAX_LEN]

        await self._db_session.flush()
        await self._db_session.commit()
        return lead
