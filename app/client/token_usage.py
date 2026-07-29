from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentTokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    complete: bool = True

    def __add__(self, other: AgentTokenUsage) -> AgentTokenUsage:
        return AgentTokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            calls=self.calls + other.calls,
            complete=self.complete and other.complete,
        )

    def as_metadata(self) -> dict[str, int | bool]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "complete": self.complete,
        }


def capture_token_usage_enabled() -> bool:
    return os.getenv("EVAL_CAPTURE_TOKEN_USAGE") == "1"


def normalize_actual_usage(value: object) -> AgentTokenUsage | None:
    """Normalize AG2's cumulative, per-model usage summary."""

    if isinstance(value, AgentTokenUsage):
        return value
    if not isinstance(value, dict):
        return None
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    found = False

    def visit(item: object) -> None:
        nonlocal prompt_tokens, completion_tokens, total_tokens, found
        if not isinstance(item, dict):
            return
        prompt = _non_negative_int(item.get("prompt_tokens"))
        completion = _non_negative_int(item.get("completion_tokens"))
        total = _non_negative_int(item.get("total_tokens"))
        if prompt is not None or completion is not None or total is not None:
            found = True
            prompt_tokens += prompt or 0
            completion_tokens += completion or 0
            total_tokens += (
                total if total is not None else (prompt or 0) + (completion or 0)
            )
        for nested in item.values():
            if isinstance(nested, dict):
                visit(nested)

    visit(value)
    if not found:
        return None
    return AgentTokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def usage_delta(before: object, after: object) -> AgentTokenUsage | None:
    normalized_after = normalize_actual_usage(after)
    if normalized_after is None:
        return None
    normalized_before = normalize_actual_usage(before) or AgentTokenUsage()
    return AgentTokenUsage(
        prompt_tokens=max(
            0, normalized_after.prompt_tokens - normalized_before.prompt_tokens
        ),
        completion_tokens=max(
            0,
            normalized_after.completion_tokens - normalized_before.completion_tokens,
        ),
        total_tokens=max(
            0, normalized_after.total_tokens - normalized_before.total_tokens
        ),
        calls=1,
    )


def consume_token_usage(client: Any) -> AgentTokenUsage | None:
    consume = getattr(client, "consume_last_token_usage", None)
    if not callable(consume):
        return None
    value = consume()
    return value if isinstance(value, AgentTokenUsage) else None


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, value)
