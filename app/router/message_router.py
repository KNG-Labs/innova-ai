from fastapi import APIRouter, Depends, HTTPException, status

from app.di import get_agent_service
from app.exceptions import SessionOwnershipError
from app.schemas import AgentMessageRequest, AgentMessageResponse
from app.service.agent_service import AgentService

router = APIRouter()


@router.post("/message", response_model=AgentMessageResponse)
async def handle_agent_message(
    request: AgentMessageRequest,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentMessageResponse:
    try:
        return await agent_service.handle_message(request)
    except SessionOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to the current user",
        )