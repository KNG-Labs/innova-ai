import asyncio

from celery import Celery
from typing import Protocol
from uuid import UUID
from collections import deque

from app.schemas.lead_delivery_schema import LeadDeliveryJob
from app.tracing import trace_headers, traced, update_observation


class QueueClient(Protocol):
    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None: ...


class FakeQueueClient:
    """
    Заглушка для тестов без Redis
    """

    def __init__(self) -> None:
        self._queue: deque[LeadDeliveryJob] = deque()
        self.enqueued: list[LeadDeliveryJob] = []
        self.acked: list[LeadDeliveryJob] = []
        self.failed: list[LeadDeliveryJob] = []

    @traced("enqueue-lead", as_type="tool")
    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None:
        update_observation(input={"lead_id": str(lead_id), "destination": destination})
        job = LeadDeliveryJob(lead_id=lead_id, destination=destination)
        self._queue.append(job)
        self.enqueued.append(job)
        update_observation(output={"enqueued": True})

    async def dequeue_lead_delivery(self) -> LeadDeliveryJob | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    async def ack(self, job: LeadDeliveryJob) -> None:
        self.acked.append(job)

    async def fail(self, job: LeadDeliveryJob) -> None:
        self.failed.append(job)


class CeleryQueueClient:
    def __init__(self, celery_app: Celery) -> None:
        self._celery_app = celery_app

    @traced("enqueue-lead", as_type="tool")
    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None:
        update_observation(input={"lead_id": str(lead_id), "destination": destination})
        await asyncio.to_thread(
            self._celery_app.send_task,
            "app.worker.lead_delivery.deliver_lead",
            args=[str(lead_id)],
            headers=trace_headers(),
        )
        update_observation(output={"enqueued": True})
