from typing import Protocol


class VectorSearchResult:
    def __init__(self, content: str, score: float) -> int:
        self.content = content
        self.score = score


class VectorClient(Protocol):
    async def search(self, query: str, top_k: int = 3) -> list[VectorSearchResult]: ...


class FakeVectorClient:
    """
    Заглушка для тестов без Qdrant/pgvector
    """

    def __init__(self, results: list[VectorSearchResult] | None = None):
        self._results = results or []

    async def search(self, query: str, top_k: int = 3) -> list[VectorSearchResult]:
        return self._results[:top_k]
