from __future__ import annotations

import re
from pydantic import BaseModel, ConfigDict

from app.schemas.openai_schema import ChatCompletionRequest, UserMessage
from app.service.intent_detector.base_intent_detector import BaseIntentDetector, Intent


class MessageAnalysis(BaseModel):
    """Класс для анализа сообщения пользователя"""

    model_config = ConfigDict(frozen=True)

    original_content: str
    normalized_content: str
    intent: Intent
    next_step: str


class MessageNormalizer:
    """Класс для нормализации контента"""

    @staticmethod
    def normalize(content: str) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()
        if not normalized:
            raise ValueError("user message must not be empty")
        return normalized


class DialogBusinessService:
    def __init__(
        self,
        normalizer: MessageNormalizer,
        intent_detector: BaseIntentDetector,
    ) -> None:
        self._normalizer = normalizer
        self._intent_detector = intent_detector

    async def prepare_request(
        self,
        request: ChatCompletionRequest,
    ) -> tuple[ChatCompletionRequest, MessageAnalysis]:
        """Подготовка запроса"""

        user_message_index = self._find_last_user_message_index(request)
        original = request.messages[
            user_message_index
        ]  # последнее сообщение юзера в истории диалога

        if not isinstance(original, UserMessage):
            raise ValueError("last user message must be a user message")

        normalized_content = self._normalizer.normalize(
            original.content
        )  # нормализация
        intent = await self._intent_detector.detect(normalized_content)
        normalized_messages = list(request.messages)  # копия списка сообщений
        normalized_messages[user_message_index] = UserMessage(
            content=normalized_content
        )
        # замена последнего сообщения на очищенную версию
        # другие сообщения нужны как контекст для LLM, но intent обычно надо определять по последней реплике.

        normalized_request = request.model_copy(
            update={"messages": normalized_messages},
            deep=True,
        )
        analysis = MessageAnalysis(
            original_content=original.content,
            normalized_content=normalized_content,
            intent=intent,
            next_step=self._next_step_for(intent),
        )
        return normalized_request, analysis

    @staticmethod
    def _find_last_user_message_index(request: ChatCompletionRequest) -> int:
        for index in range(len(request.messages) - 1, -1, -1):
            if isinstance(request.messages[index], UserMessage):
                return index
        raise ValueError("request must contain at least one user message")

    @staticmethod
    def _next_step_for(intent: Intent) -> str:
        if intent == "lead_request":
            return "collect_contact"
        if intent == "pricing":
            return "send_pricing_summary"
        if intent == "support":
            return "ask_support_details"
        return "continue_dialog"
