"""Optional Langfuse tracing; application payloads are never captured implicitly."""

import asyncio
import json
import logging
import os
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Literal, ParamSpec, TypeVar

from langfuse import Langfuse
from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanPatch,
)

from app.privacy import PiiSanitizer

_client: Langfuse | None = None
_logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")


def mask_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult:
    pii = PiiSanitizer()
    patches = {}
    for identifier, span in params.spans.items():
        attributes = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                try:
                    decoded = json.loads(value)
                except ValueError:
                    value = pii.sanitize_text(value).text
                else:
                    value = json.dumps(pii.sanitize_value(decoded), ensure_ascii=False)
            elif isinstance(value, (list, tuple)):
                value = pii.sanitize_value(value)
            attributes[key] = value
        # Fail closed: SDK drops the batch if analysis or this check fails.
        PiiSanitizer.ensure_safe(attributes)
        patches[identifier] = OtelSpanPatch(set_attributes=attributes)
    return MaskOtelSpansResult(span_patches=patches)


def init_tracing() -> Langfuse | None:
    global _client
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() in {"false", "0"}:
        return None
    settings = [
        os.getenv(key, "").strip()
        for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    ]
    if not all(settings):
        if any(settings):
            _logger.warning(
                "Langfuse disabled: public key, secret key and base URL required"
            )
        return None
    _client = Langfuse(mask_otel_spans=mask_spans)
    # Official OpenAI integration also instruments AG2's underlying SDK calls.
    from langfuse.openai import openai  # noqa: F401

    return _client


async def close_tracing() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await asyncio.to_thread(client.shutdown)


def update_observation(**attributes: Any) -> None:
    if _client is not None:
        _client.update_current_span(**attributes)


def traced(
    name: str,
    *,
    as_type: Literal["span", "agent", "retriever", "tool"] = "span",
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]:
    def decorate(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            if _client is None:
                return await func(*args, **kwargs)
            error = None
            with _client.start_as_current_observation(
                name=name, as_type=as_type
            ) as span:
                try:
                    return await func(*args, **kwargs)
                except BaseException as exc:
                    # OTel exception events bypass attribute masking; record only the type.
                    span.update(level="ERROR", status_message=type(exc).__name__)
                    error = exc
            raise error

        return wrapped

    return decorate
