from __future__ import annotations

import os
from typing import Any

from deepeval.models import DeepEvalBaseLLM
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from app.privacy import PiiSanitizer


class OpenRouterJudge(DeepEvalBaseLLM):
    """Schema-aware DeepEval judge backed by OpenRouter."""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model_name = (model or os.getenv("EVAL_JUDGE_MODEL", "") or "").strip()
        if not self._model_name:
            raise RuntimeError("EVAL_JUDGE_MODEL is required for judge metrics")
        resolved_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not resolved_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for judge metrics")
        resolved_url = base_url or os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self._client = OpenAI(api_key=resolved_key, base_url=resolved_url)
        self._async_client = AsyncOpenAI(api_key=resolved_key, base_url=resolved_url)
        super().__init__(model=self._model_name)

    def load_model(self, *_args: Any, **_kwargs: Any) -> OpenRouterJudge:
        return self

    def generate(  # type: ignore[override]
        self, prompt: str, schema: type[BaseModel] | None = None, **_kwargs: Any
    ) -> str | BaseModel:
        safe_prompt = _sanitize_prompt(prompt)
        request: Any = {
            "model": self._model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": safe_prompt}],
            "response_format": _response_format(schema),
        }
        response = self._client.chat.completions.create(**request)
        content = response.choices[0].message.content or ""
        return schema.model_validate_json(content) if schema is not None else content

    async def a_generate(  # type: ignore[override]
        self, prompt: str, schema: type[BaseModel] | None = None, **_kwargs: Any
    ) -> str | BaseModel:
        safe_prompt = _sanitize_prompt(prompt)
        request: Any = {
            "model": self._model_name,
            "temperature": 0,
            "messages": [{"role": "user", "content": safe_prompt}],
            "response_format": _response_format(schema),
        }
        response = await self._async_client.chat.completions.create(**request)
        content = response.choices[0].message.content or ""
        return schema.model_validate_json(content) if schema is not None else content

    def get_model_name(self, *_args: Any, **_kwargs: Any) -> str:
        return self._model_name

    def supports_temperature(self) -> bool:
        return True

    def supports_structured_outputs(self) -> bool:
        return True


def _sanitize_prompt(prompt: str) -> str:
    safe_prompt = PiiSanitizer().sanitize_text(prompt).text
    PiiSanitizer.ensure_safe([{"role": "user", "content": safe_prompt}])
    return safe_prompt


def _response_format(schema: type[BaseModel] | None) -> dict[str, Any]:
    if schema is None:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "strict": True,
            "schema": schema.model_json_schema(),
        },
    }
