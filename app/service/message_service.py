from app.core.schemas import MessageRequest, MessageResponse
from app.gateway.llm_client import LLMClient


class MessageService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def handle_message(self, request: MessageRequest) -> MessageResponse:
        reply = await self._llm_client.generate_reply(request.text)
        return MessageResponse(text=reply.text, intent=reply.intent)
