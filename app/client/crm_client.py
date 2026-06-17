from typing import Protocol
from uuid import UUID


class CrmPayload:
    def __init__(
        self,
        lead_id: UUID,
        source: str,
        contact_name: str | None,
        contact_phone: str | None,
        contact_email: str | None,
        service: str | None,
        deadline: str | None,
        budget: str | None,
        summary: str | None,
        session_id: UUID,
    ) -> None:
        self.lead_id = lead_id
        self.source = source
        self.contact_name = contact_name
        self.contact_phone = contact_phone
        self.contact_email = contact_email
        self.service = service
        self.deadline = deadline
        self.budget = budget
        self.summary = summary
        self.session_id = session_id


class CrmClient(Protocol):
    async def deliver_lead(self, payload: CrmPayload) -> None: ...


class FakeCrmClient:
    """
    Заглушка для тестов без реальных CRM токенов
    """

    def __init__(self) -> None:
        self.delivered: list[CrmPayload] = []

    async def deliver_lead(self, payload: CrmPayload) -> None:
        self.delivered.append(payload)
