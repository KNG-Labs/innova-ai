from typing import Protocol

from app.schemas.message import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatUsage,
)


class LLMClient(Protocol):
    async def create_chat_completion(
        self,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse: ...


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


# Заглушка
class StubLLMClient:
    @staticmethod
    async def create_chat_completion(
            request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="1",
            object="chat.completion",
            created=0,
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatChoiceMessage(
                        role="assistant", content="Здравствуйте! Чем могу помочь?"
                    ),
                    finish_reason="stop",
                )
            ],
            usage=ChatUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ),
        )
