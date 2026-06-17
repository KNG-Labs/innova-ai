from typing import Protocol
from uuid import UUID


class QueueClient(Protocol):
    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None: ...


class FakeQueueClient:
    """
    Заглушка для тестов без Redis
    """

    def __init__(self) -> None:
        self.enqueued: list[tuple[UUID, str]] = []

    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None:
        self.enqueued.append((lead_id, destination))
