from typing import Protocol
from uuid import UUID
from collections import deque

from app.schemas.lead_delivery_schema import LeadDeliveryJob


class QueueClient(Protocol):
    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None: ...

    async def dequeue_lead_delivery(self) -> LeadDeliveryJob | None: ...

    async def ack(self, job: LeadDeliveryJob) -> None: ...

    async def fail(self, job: LeadDeliveryJob) -> None: ...


class FakeQueueClient:
    """
    Заглушка для тестов без Redis
    """

    def __init__(self) -> None:
        self._queue: deque[LeadDeliveryJob] = deque()
        self.enqueued: list[LeadDeliveryJob] = []
        self.acked: list[LeadDeliveryJob] = []
        self.failed: list[LeadDeliveryJob] = []

    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None:
        job = LeadDeliveryJob(lead_id=lead_id, destination=destination)
        self._queue.append(job)
        self.enqueued.append(job)

    async def dequeue_lead_delivery(self) -> LeadDeliveryJob | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    async def ack(self, job: LeadDeliveryJob) -> None:
        self.acked.append(job)

    async def fail(self, job: LeadDeliveryJob) -> None:
        self.failed.append(job)
