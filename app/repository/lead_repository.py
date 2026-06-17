from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_model import Lead


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        stmt = select(Lead).where(Lead.id == lead_id)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session_id(self, session_id: UUID) -> Lead | None:
        stmt = select(Lead).where(Lead.session_id == session_id)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        status: str = "draft",
        contact: dict | None = None,
        qualification: dict | None = None,
        summary: str | None = None,
    ) -> Lead:
        lead = Lead(
            user_id=user_id,
            session_id=session_id,
            status=status,
            contact=contact,
            qualification=qualification,
            summary=summary,
        )

        self._session.add(lead)
        await self._session.flush()

        return lead

    async def get_or_create_by_session_id(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> Lead:
        lead = await self.get_by_session_id(session_id)

        if lead is not None:
            return lead

        return await self.create(
            user_id=user_id,
            session_id=session_id,
        )

    async def update(
        self,
        lead: Lead,
        *,
        status: str | None = None,
        contact: dict | None = None,
        qualification: dict | None = None,
        summary: str | None = None,
    ) -> Lead:

        if status is not None:
            lead.status = status

        if contact is not None:
            lead.contact = contact

        if qualification is not None:
            lead.qualification = qualification

        if summary is not None:
            lead.summary = summary

        await self._session.flush()

        return lead

    async def list_by_user_id(self, user_id: UUID) -> list[Lead]:
        stmt = (
            select(Lead).where(Lead.user_id == user_id).order_by(Lead.created_at.desc())
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


    async def upsert_draft(
        self,
        user_id: UUID,
        session_id: UUID,
        qualification: dict,
        contact: dict | None,
        summary: str | None
    ) -> Lead:
        lead = await self.get_by_session_id(session_id)
        if lead is None:
            lead = Lead(
                user_id=user_id,
                session_id=session_id,
                status="draft",
                qualification=qualification,
                contact=contact,
                summary=summary,
            )
            self._session.add(lead)
        else:
            lead.qualification = qualification
            if contact:  # непустой dict
                merged_contact = {**(lead.contact or {}), **contact}
                # убрать None-значения
                lead.contact = {k: v for k, v in merged_contact.items() if v is not None}
            if summary:
                lead.summary = summary

        return Lead