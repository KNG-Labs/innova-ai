from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DialogSession


class DialogSessionRepository:
    """
    если client передал session_id → пробуем найти эту сессию,
    если не передал → ищем активную сессию пользователя,
    если активной нет → создаём новую
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, session_id: UUID) -> DialogSession | None:
        stmt = select(DialogSession).where(DialogSession.id == session_id)

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_user(self, session_id: UUID) -> DialogSession | None:
        stmt = (
            select(DialogSession)
            .options(selectinload(DialogSession.user))
            .where(DialogSession.id == session_id)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_user_id(self, user_id: UUID) -> DialogSession | None:
        stmt = (
            select(DialogSession)
            .where(
                DialogSession.user_id == user_id,
                DialogSession.closed_at.is_(None),
            )
            .order_by(DialogSession.created_at.desc())
            .limit(1)
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, user_id: UUID, state: str = "GREETING") -> DialogSession:
        dialog_session = DialogSession(
            user_id=user_id,
            state=state,
        )

        self._session.add(dialog_session)
        await self._session.flush()

        return dialog_session

    async def get_or_create_active_session(
        self, *, user_id: UUID, session_id: UUID | None
    ) -> DialogSession:
        if session_id is not None:
            existing_session = await self.get_by_id(session_id)

            if existing_session is not None:
                return existing_session

        active_session = await self.get_active_by_user_id(user_id)

        if active_session is not None:
            return active_session

        return await self.create(user_id=user_id)
