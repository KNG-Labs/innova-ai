from __future__ import annotations

from typing import Any, Annotated, cast

from openai.types.chat.chat_completion import ChatCompletion as SDKChatCompletion
from openai.types.chat.chat_completion import Choice as SDKChatChoice
from openai.types.chat.chat_completion_message import (
    ChatCompletionMessage as SDKChatChoiceMessage,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import (
    CompletionCreateParamsNonStreaming,
)
from openai.types.completion_usage import CompletionUsage as SDKChatUsage
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Literal


ChatChoice = SDKChatChoice
ChatChoiceMessage = SDKChatChoiceMessage
ChatUsage = SDKChatUsage
ChatCompletionResponse = SDKChatCompletion


class UserMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user"] = "user"
    content: str

    def to_sdk_message_param(self) -> ChatCompletionUserMessageParam:
        return {
            "role": "user",
            "content": self.content,
        }


class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant"] = "assistant"
    content: str | None = None
    reasoning_details: list[dict[str, Any]] | None = Field(default=None)

    @field_validator("reasoning_details", mode="before")
    @classmethod
    def reasoning_details_not_empty(cls, value: Any) -> list[dict[str, Any]] | None:
        if isinstance(value, dict):
            return None
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> "AssistantMessage":
        if self.content is None and self.reasoning_details is None:
            raise ValueError("assistant message requires content or reasoning_details")
        return self

    def to_sdk_message_param(self) -> ChatCompletionMessageParam:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
        }
        if self.content is not None:
            assistant_message["content"] = self.content
        if self.reasoning_details is not None:
            # OpenRouter expects this field in the assistant history message,
            # even though it is outside the standard OpenAI schema.
            assistant_message["reasoning_details"] = self.reasoning_details
        return cast(ChatCompletionMessageParam, cast(object, assistant_message))


ChatMessage = Annotated[UserMessage | AssistantMessage, Field(discriminator="role")]


class ChatCompletionRequest(BaseModel):
    """Минимальный payload для OpenRouter через OpenAI SDK."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(default="openai/gpt-oss-120b:free")
    messages: list[ChatMessage]
    reasoning: bool = False

    def to_sdk_completion_params(self) -> CompletionCreateParamsNonStreaming:
        sdk_messages: list[ChatCompletionMessageParam] = [
            message.to_sdk_message_param() for message in self.messages
        ]
        return {
            "model": self.model,
            "messages": sdk_messages,
        }

    def to_openrouter_extra_body(self) -> dict[str, Any] | None:
        if not self.reasoning:
            return None

        return {"reasoning": {"enabled": True}}
