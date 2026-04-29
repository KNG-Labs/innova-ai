from fastapi import APIRouter, Depends

from app.core.di import get_message_service
from app.core.schemas import MessageRequest, MessageResponse
from app.service.message_service import MessageService

router = APIRouter()


@router.post("/message", response_model=MessageResponse)
async def handle_message(
    request: MessageRequest,
    service: MessageService = Depends(get_message_service),
) -> MessageResponse:
    return await service.handle_message(request)
