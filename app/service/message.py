from time import time

from app.client.llm_client import LLMClient, LLMProviderError
from app.schemas.message import (
    ChatChoice,
    ChatChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatUsage,
)
from app.service.business import DialogBusinessProcessor, MessageAnalysis


class MessageService:
    def __init__(
        self,
        llm_client: LLMClient,
        business_processor: DialogBusinessProcessor,
    ) -> None:

        self._llm_client = llm_client
        self._business_processor = business_processor

    async def handle_chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:

        normalized_request, analysis = self._business_processor.prepare_request(request)

        try:
            response = await self._llm_client.create_chat_completion(normalized_request)
        except LLMProviderError as exc:
            response = self._build_fallback_response(
                normalized_request,
                error=str(exc),
                retryable=exc.retryable,
            )

        setattr(response, "innova_ai", self._build_business_metadata(analysis))
        return response


    @staticmethod
    def _build_business_metadata(analysis: MessageAnalysis) -> dict[str, object]:
        return {
            "normalized_message": analysis.normalized_content,
            "intent": analysis.intent,
            "next_step": analysis.next_step,
        }


    @staticmethod
    def _build_fallback_response(
            request: ChatCompletionRequest,
        *,
        error: str,
        retryable: bool,
    ) -> ChatCompletionResponse:
        response = ChatCompletionResponse(
            id=f"fallback-{int(time())}",
            object="chat.completion",
            created=int(time()),
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatChoiceMessage(
                        role="assistant",
                        content=(
                            "Сейчас не получается получить ответ от AI-провайдера. "
                            "Я зафиксировал обращение и вернусь с ответом позже."
                        ),
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
        setattr(
            response,
            "innova_ai_error",
            {
                "provider_error": error,
                "retryable": retryable,
                "fallback": True,
            },
        )
        return response
