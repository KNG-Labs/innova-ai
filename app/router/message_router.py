from fastapi import APIRouter, Depends

from app.di import get_agent_service
from app.schemas import AgentMessageResponse, AgentMessageRequest
from app.service.agent_service import AgentService


router = APIRouter()


@router.post("/message", response_model=AgentMessageResponse)
async def handle_agent_message(
    request: AgentMessageRequest,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentMessageResponse:
    return await agent_service.handle_message(request)
