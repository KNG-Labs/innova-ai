from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message


class MessageRepository:
    """
    создать сообщение
    получить историю сообщений сессии
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        session_id: UUID,
        role: str,
        content: str,
        message_metadata: dict | None = None,
    ) -> Message:

        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )

        self._session.add(message)
        await self._session.flush()

        return message

    async def list_messages_by_session_id(self, session_id: UUID) -> list[Message]:
        """Вернуть всю историю сообщений сессии в хронологическом порядке.

        Используется read-route:
        GET /sessions/{session_id}/messages
        """

        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_messages(
        self,
        session_id: UUID,
        *,
        limit: int,
    ) -> list[Message]:
        """Вернуть последние сообщения сессии (для LLM-контекста).

        В БД выбираем последние N сообщений через DESC,
        потом разворачиваем список обратно в хронологический порядок,
        чтобы LLM получила историю от старых сообщений к новым.
        """

        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())

        return list(reversed(messages))
