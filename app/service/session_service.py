from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.dialog_session_repository import DialogSessionRepository
from app.repository.message_repository import MessageRepository
from app.schemas.agent_schema import Channel, DialogState
from app.schemas.session_schema import (
    MessageRole,
    SessionResponse,
    StoredMessageResponse,
)


class SessionNotFoundError(Exception):
    """Ошибка, если сессия диалога не найдена"""

    pass


class SessionService:
    def __init__(self, db_session: AsyncSession) -> None:
        self._dialog_sessions = DialogSessionRepository(db_session)
        self._messages = MessageRepository(db_session)

    async def get_session(self, session_id: UUID) -> SessionResponse:
        dialog_session = await self._dialog_sessions.get_by_id_with_user(session_id)

        if dialog_session is None:
            raise SessionNotFoundError

        return SessionResponse(
            id=dialog_session.id,
            user_id=dialog_session.user_id,
            state=DialogState(dialog_session.state),
            channel=Channel(dialog_session.user.channel),
            created_at=dialog_session.created_at,
            updated_at=dialog_session.updated_at,
        )

    async def get_session_messages(
        self,
        session_id: UUID,
    ) -> list[StoredMessageResponse]:
        dialog_session = await self._dialog_sessions.get_by_id(session_id)

        if dialog_session is None:
            raise SessionNotFoundError

        messages = await self._messages.list_messages_by_session_id(session_id)

        return [
            StoredMessageResponse(
                id=message.id,
                session_id=message.session_id,
                role=MessageRole(message.role),
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ]
