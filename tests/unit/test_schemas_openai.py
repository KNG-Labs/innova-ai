import pytest
from pydantic import ValidationError

from app.schemas.openai import (
    AssistantMessage,
    ChatCompletionRequest,
    UserMessage,
)

pytestmark = pytest.mark.unit


def test_reasoning_details_dict_coerced_to_none() -> None:
    message = AssistantMessage(
        content="ok",
        reasoning_details={"step": "ignored"},
    )

    assert message.reasoning_details is None


def test_reasoning_details_list_kept() -> None:
    details = [{"step": 1}]

    message = AssistantMessage(
        content="ok",
        reasoning_details=details,
    )

    assert message.reasoning_details == details


def test_chat_completion_request_defaults() -> None:
    request = ChatCompletionRequest(
        messages=[UserMessage(content="hi")],
    )

    assert request.model == "openai/gpt-oss-120b:free"
    assert request.reasoning is False


def test_chat_completion_request_converts_to_sdk_params() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[
            AssistantMessage(
                content="ok",
                reasoning_details=[{"step": 1}],
            ),
            UserMessage(content="hi"),
        ],
    )

    params = request.to_sdk_completion_params()

    assert params["model"] == "test-model"
    assert params["messages"][0]["role"] == "assistant"
    assert params["messages"][0]["reasoning_details"] == [{"step": 1}]
    assert params["messages"][1] == {
        "role": "user",
        "content": "hi",
    }


def test_chat_completion_request_builds_openrouter_extra_body() -> None:
    request = ChatCompletionRequest(
        messages=[UserMessage(content="hi")],
        reasoning=True,
    )

    assert request.to_openrouter_extra_body() == {"reasoning": {"enabled": True}}


def test_chat_completion_request_without_reasoning_has_no_extra_body() -> None:
    request = ChatCompletionRequest(
        messages=[UserMessage(content="hi")],
    )

    assert request.to_openrouter_extra_body() is None


def test_assistant_message_requires_content_or_reasoning_details() -> None:
    with pytest.raises(
        ValidationError, match="assistant message requires content or reasoning_details"
    ):
        AssistantMessage()


def test_user_message_with_reasoning_details_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ChatCompletionRequest.model_validate(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "hi",
                        "reasoning_details": [{"step": 1}],
                    }
                ]
            }
        )
