from fastapi import APIRouter, Depends

from app.di import get_message_service
from app.schemas.openai_message import ChatCompletionResponse, ChatCompletionRequest
from app.service.message_service import MessageService


router = APIRouter()


@router.post("/message", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    message_service: MessageService = Depends(get_message_service),
) -> ChatCompletionResponse:
    return await message_service.handle_chat_completion(request)
