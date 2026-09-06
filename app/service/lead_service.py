from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_model import Lead
from app.repository.lead_repository import LeadRepository


class LeadNotFoundError(Exception):
    """Лид не найден."""


class LeadService:
    def __init__(self, db_session: AsyncSession) -> None:
        self._leads = LeadRepository(db_session)

    async def list_leads(self, status: str | None = None) -> list[Lead]:
        return await self._leads.list_all(status=status)

    async def get_lead(self, lead_id: UUID) -> Lead:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError
        return lead
