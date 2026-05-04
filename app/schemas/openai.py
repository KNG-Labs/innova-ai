from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator


class ReasoningConfig(BaseModel):
    """Конфигурация reasoning для OpenRouter."""

    enabled: bool = False


class ChatMessage(BaseModel):
    """
    Один элемент истории диалога (роль + текст).

    Совместим с OpenAI API и OpenRouter расширениями.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = Field(default=None, description="Имя участника диалога (опционально)")
    reasoning_details: dict[str, Any] | None = Field(
        default=None,
        exclude=True,  # Не сериализуется по умолчанию
        description="[OpenRouter] Reasoning детали из предыдущего ответа. НЕ заполняйте вручную!"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Содержимое сообщения не может быть пустым")
        return v.strip()


class ChatChoiceMessage(BaseModel):
    """Сообщение ассистента внутри варианта ответа (choices)."""

    role: Literal["assistant"]
    content: str | None = None
    reasoning_details: dict[str, Any] | None = Field(
        default=None,
        description="[OpenRouter] Детали reasoning процесса модели"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None) -> str | None:
        if v is not None and isinstance(v, str) and len(v.strip()) == 0:
            raise ValueError("Content cannot be empty string")
        return v

class ChatChoice(BaseModel):
    """Один вариант ответа, включая причину завершения генерации."""

    index: int
    message: ChatChoiceMessage
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] | None


class ChatUsage(BaseModel):
    """Статистика токенов по запросу и ответу."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionRequest(BaseModel):
    """
    Входной payload для /v1/chat/completions.

    Совместим с OpenAI API и OpenRouter расширениями.
    """

    model: str = Field(
        default="google/gemma-4-26b-a4b-it:free",
        min_length=1,
        description="ID модели для использования"
    )
    messages: list[ChatMessage] = Field(
        min_length=1,
        description="Массив сообщений в формате chat completion"
    )
    temperature: float | None = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Температура сэмплирования (0.0-2.0)"
    )
    max_tokens: int | None = Field(
        default=500,
        ge=1,
        description="Максимальное количество токенов в ответе"
    )
    stream: bool = Field(
        default=False,
        description="Включить потоковый режим"
    )
    top_p: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling параметр"
    )
    frequency_penalty: float | None = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Штраф за частоту использования токенов"
    )
    presence_penalty: float | None = Field(
        default=None,
        ge=-2.0,
        le=2.0,
        description="Штраф за присутствие токенов"
    )
    reasoning: ReasoningConfig | None = Field(
        default=None,
        description='[OpenRouter] Включить reasoning: {"enabled": true}'
    )

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Не указана модель!")
        return v

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("Список сообщений не может быть пустым")
        return v


class ChatCompletionResponse(BaseModel):
    """Стандартный ответ OpenAI-совместимого API."""

    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatChoice]
    usage: ChatUsage | None = None
