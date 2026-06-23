import hashlib
import math
import os
import re
from typing import Protocol, runtime_checkable

from app.domain import EMBEDDING_DIM


@runtime_checkable
class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingClient(EmbeddingClient):
    """Детерминированные embeddings без внешнего API."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for tok in re.findall(r"\w+", text.lower()):
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self._dim
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v] if norm else v


class OpenRouterEmbeddingClient(EmbeddingClient):
    """Real embeddings через OpenRouter (OpenAI-совместимый эндпоинт).
    Тот же ключ, что у AG2. Модель должна давать dim == EMBEDDING_DIM."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


def build_embedding_client() -> EmbeddingClient:
    provider = os.getenv("EMBEDDING_PROVIDER", "fake").strip().lower()
    if provider == "fake":
        return FakeEmbeddingClient()
    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY required for EMBEDDING_PROVIDER=openrouter"
            )
        base_url = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).strip()
        model = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small").strip()
        return OpenRouterEmbeddingClient(
            api_key=api_key, base_url=base_url, model=model
        )
    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
