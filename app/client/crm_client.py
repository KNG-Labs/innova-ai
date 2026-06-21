from typing import Any, Protocol
from uuid import UUID


class CrmPayload:
    def __init__(
        self,
        lead_id: UUID,
        source: str,
        contact_name: str | None,
        contact_phone: str | None,
        contact_email: str | None,
        car_model: str | None,
        budget: str | None,
        purchase_type: str | None,
        summary: str | None,
        session_id: UUID,
    ) -> None:
        self.lead_id = lead_id
        self.source = source
        self.contact_name = contact_name
        self.contact_phone = contact_phone
        self.contact_email = contact_email
        self.car_model = car_model
        self.budget = budget
        self.purchase_type = purchase_type
        self.summary = summary
        self.session_id = session_id


def build_crm_payload(
    *,
    lead_id: UUID,
    session_id: UUID,
    qualification: dict[str, Any] | None,
    contact: dict[str, Any] | None,
    summary: str | None,
) -> CrmPayload:
    """Маппинг Innova-домена -> CRM payload. Единственная точка маппинга.

    Домен: car_model / budget / purchase_type (см. app/domain.py).
    Внешние данные недоверенные -> .get с None по умолчанию.
    """
    qual = qualification or {}
    cont = contact or {}
    return CrmPayload(
        lead_id=lead_id,
        session_id=session_id,
        source=qual.get("source_channel") or "website",
        contact_name=cont.get("name"),
        contact_phone=cont.get("phone"),
        contact_email=cont.get("email"),
        car_model=qual.get("car_model"),
        budget=qual.get("budget"),
        purchase_type=qual.get("purchase_type"),
        summary=summary,
    )


class CrmClient(Protocol):
    async def deliver_lead(self, payload: CrmPayload) -> None: ...


class FakeCrmClient:
    """Заглушка для тестов без реальных CRM токенов."""

    def __init__(self, *, fail: bool = False) -> None:
        self.delivered: list[CrmPayload] = []
        self._fail = fail

    async def deliver_lead(self, payload: CrmPayload) -> None:
        if self._fail:
            raise RuntimeError("fake CRM rejected the lead")
        self.delivered.append(payload)
