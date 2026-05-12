import pytest

from app.schemas.openai import ChatCompletionRequest, ChatMessage, ReasoningConfig

pytestmark = pytest.mark.unit


def test_reasoning_details_dict_coerced_to_none() -> None:
    message = ChatMessage(
        role="assistant",
        content="ok",
        reasoning_details={"step": "ignored"},
    )

    assert message.reasoning_details is None


def test_reasoning_details_list_kept() -> None:
    details = [{"step": 1}]

    message = ChatMessage(
        role="assistant",
        content="ok",
        reasoning_details=details,
    )

    assert message.reasoning_details == details


def test_chat_completion_request_defaults() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
    )

    assert request.stream is False
    assert request.temperature == 0.7
    assert request.max_tokens == 500


def test_chat_completion_request_reasoning_config() -> None:
    request = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
        reasoning=ReasoningConfig(enabled=True),
    )

    assert request.reasoning is not None
    assert request.reasoning.enabled is True
