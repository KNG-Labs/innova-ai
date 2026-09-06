from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dialog_session_model import DialogSession
from app.models.message_model import Message
from app.repository.dialog_session_repository import DialogSessionRepository
from app.repository.message_repository import MessageRepository


class SessionNotFoundError(Exception):
    """Ошибка, если сессия диалога не найдена"""

    pass


class SessionService:
    def __init__(self, db_session: AsyncSession) -> None:
        self._dialog_sessions = DialogSessionRepository(db_session)
        self._messages = MessageRepository(db_session)

    async def get_session(self, session_id: UUID) -> DialogSession:
        dialog_session = await self._dialog_sessions.get_by_id_with_user(session_id)

        if dialog_session is None:
            raise SessionNotFoundError

        return dialog_session

    async def get_session_messages(
        self,
        session_id: UUID,
    ) -> list[Message]:
        dialog_session = await self._dialog_sessions.get_by_id(session_id)

        if dialog_session is None:
            raise SessionNotFoundError

        return await self._messages.list_messages_by_session_id(session_id)
