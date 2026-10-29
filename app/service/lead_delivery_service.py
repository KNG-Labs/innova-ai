from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.crm_client import CrmClient, CrmDeliveryRejectedError, build_crm_payload
from app.models.lead_model import Lead
from app.repository.lead_repository import LeadRepository
from app.service.lead_service import LeadNotFoundError

_DELIVERABLE_STATUSES = {"ready", "delivery_failed"}
_ERROR_MAX_LEN = 1000
_SAFE_DELIVERY_FAILURES = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    CrmDeliveryRejectedError,
)


class LeadNotDeliverableError(Exception):
    """Доставка запрещена текущим состоянием лида."""


class LeadDeliveryService:
    def __init__(self, *, db_session: AsyncSession, crm_client: CrmClient) -> None:
        self._db_session = db_session
        self._leads = LeadRepository(db_session)
        self._crm = crm_client

    async def deliver(
        self,
        lead_id: UUID,
        *,
        raise_on_delivery_error: bool = False,
    ) -> Lead:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError

        # FOR NO KEY UPDATE permits the independently committed journal foreign key.
        await self._db_session.refresh(lead, with_for_update={"key_share": True})

        if lead.status == "delivered":
            return lead

        # Draft leads do not contain a complete, backend-validated payload.
        if lead.status not in _DELIVERABLE_STATUSES:
            raise LeadNotDeliverableError(
                f"Lead status '{lead.status}' does not allow delivery"
            )

        if await self._leads.get_delivery_attempt(lead_id) is not None:
            message = (
                "Previous delivery attempt is unconfirmed; review CRM before resending"
            )
            lead.status = "needs_review"
            lead.last_delivery_error = message
            await self._db_session.commit()
            await self._db_session.refresh(lead)
            if raise_on_delivery_error:
                raise LeadNotDeliverableError(message)
            return lead

        payload = build_crm_payload(
            lead_id=lead.id,
            session_id=lead.session_id,
            qualification=lead.qualification,
            contact=lead.contact,
            summary=lead.summary,
        )

        delivery_error: Exception | None = None
        await self._leads.start_delivery_attempt(lead_id)

        try:
            await self._crm.deliver_lead(payload)
            lead.status = "delivered"
            lead.last_delivery_error = None
        except Exception as exc:  # noqa: BLE001 - ошибка доставки = бизнес-исход, не 500
            if isinstance(exc, _SAFE_DELIVERY_FAILURES):
                lead.status = "delivery_failed"
            else:
                lead.status = "needs_review"
            lead.last_delivery_error = repr(exc)[:_ERROR_MAX_LEN]
            delivery_error = exc

        if lead.status in {"delivered", "delivery_failed"}:
            await self._leads.clear_delivery_attempt(lead_id)
        await self._db_session.commit()
        await self._db_session.refresh(lead)

        if raise_on_delivery_error and delivery_error is not None:
            raise delivery_error

        return lead
