from app.client.llm_client import LLMClient
from app.schemas.openai import ChatCompletionRequest, ChatCompletionResponse


class MessageService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def handle_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        return await self._llm_client.create_chat_completion(request)
