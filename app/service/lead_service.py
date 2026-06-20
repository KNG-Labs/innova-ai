from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.lead_repository import LeadRepository
from app.schemas.lead_schema import LeadListItem, LeadResponse


class LeadNotFoundError(Exception):
    """Лид не найден."""


class LeadService:
    def __init__(self, db_session: AsyncSession) -> None:
        self._leads = LeadRepository(db_session)

    async def list_leads(self, status: str | None = None) -> list[LeadListItem]:
        rows = await self._leads.list_all(status=status)
        return [
            LeadListItem(
                id=row.id,
                session_id=row.session_id,
                user_id=row.user_id,
                status=row.status,
                summary=row.summary,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_lead(self, lead_id: UUID) -> LeadResponse:
        lead = await self._leads.get_by_id(lead_id)
        if lead is None:
            raise LeadNotFoundError

        return LeadResponse(
            id=lead.id,
            session_id=lead.session_id,
            user_id=lead.user_id,
            status=lead.status,
            qualification=lead.qualification,
            contact=lead.contact,
            summary=lead.summary,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
