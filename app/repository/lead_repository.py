from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.lead_delivery_attempt_model import LeadDeliveryAttemptModel
from app.models.lead_model import Lead


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        stmt = select(Lead).where(Lead.id == lead_id)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_delivery_attempt(
        self, lead_id: UUID
    ) -> LeadDeliveryAttemptModel | None:
        return await self._session.get(LeadDeliveryAttemptModel, lead_id)

    async def start_delivery_attempt(self, lead_id: UUID) -> None:
        bind = self._session.bind
        if not isinstance(bind, AsyncEngine):
            raise RuntimeError("Delivery attempts require an engine-bound session")

        # An independent connection avoids exhausting the pool while holding a lead lock.
        journal_engine = create_async_engine(bind.url, poolclass=NullPool)
        try:
            async with journal_engine.begin() as connection:
                await connection.execute(
                    insert(LeadDeliveryAttemptModel).values(lead_id=lead_id)
                )
        finally:
            await journal_engine.dispose()

    async def clear_delivery_attempt(self, lead_id: UUID) -> None:
        await self._session.execute(
            delete(LeadDeliveryAttemptModel).where(
                LeadDeliveryAttemptModel.lead_id == lead_id
            )
        )

    async def get_by_session_id(self, session_id: UUID) -> Lead | None:
        stmt = select(Lead).where(Lead.session_id == session_id)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def list_all(self, status: str | None = None) -> list[Lead]:
        stmt = select(Lead)
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        stmt = stmt.order_by(Lead.created_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_draft(
        self,
        user_id: UUID,
        session_id: UUID,
        qualification: dict,
        contact: dict | None,
        summary: str | None,
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
                lead.contact = {
                    k: v for k, v in merged_contact.items() if v is not None
                }
            if summary:
                lead.summary = summary

        return lead
