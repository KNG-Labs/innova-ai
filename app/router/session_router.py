from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.di import get_session_service
from app.models.dialog_session_model import DialogSession
from app.models.message_model import Message
from app.schemas.session_schema import SessionResponse, StoredMessageResponse
from app.service.session_service import SessionService, SessionNotFoundError

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    session_service: SessionService = Depends(get_session_service),
) -> DialogSession:
    try:
        return await session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )


@router.get(
    "/{session_id}/messages",
    response_model=list[StoredMessageResponse],
)
async def get_session_messages(
    session_id: UUID,
    session_service: SessionService = Depends(get_session_service),
) -> list[Message]:
    try:
        return await session_service.get_session_messages(session_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
