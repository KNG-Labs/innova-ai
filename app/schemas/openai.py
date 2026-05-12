from typing import Any, Literal, List

from pydantic import BaseModel, Field, field_validator


class ReasoningConfig(BaseModel):
    """Конфигурация reasoning для OpenRouter. {"enabled": true}"""
    enabled: bool


class ChatMessage(BaseModel):
    """
    Один элемент истории диалога.
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None

    # Поле для сохранения контекста "размышлений" модели.
    # API возвращает и ожидает список.
    reasoning_details: List[dict[str, Any]] | None = Field(default=None)

    @field_validator('reasoning_details', mode='before')
    @classmethod
    def reasoning_details_not_empty(cls, v) -> List[dict[str, Any]] | None:
        """Если клиент вместо списка/null присылает пустой или некорректный объект,
        считаем, что деталей нет (None)"""
        if isinstance(v, dict):
            return None
        return v


class ChatCompletionRequest(BaseModel):
    """
    Входной payload для /v1/chat/completions.
    """

    model: str = Field(default="openai/gpt-oss-120b:free")
    messages: list[ChatMessage]
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=500, ge=1)
    stream: bool = False
    reasoning: ReasoningConfig | None = None


# --- Схемы для ответа ---

class ChatChoiceMessage(BaseModel):
    """Сообщение ассистента в ответе."""

    role: Literal["assistant"]
    content: str | None = None
    # API возвращает список деталей "размышлений"
    reasoning_details: List[dict[str, Any]] | None = None


class ChatChoice(BaseModel):
    """Один вариант ответа."""

    index: int
    message: ChatChoiceMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None


class ChatUsage(BaseModel):
    """Статистика токенов."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Стандартный ответ OpenAI-совместимого API."""

    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage | None = None
