from typing import Protocol
from uuid import UUID
from collections import deque
import redis.asyncio as aioredis
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.schemas.lead_delivery_schema import LeadDeliveryJob


_QUEUE_KEY = "innova:lead_delivery"


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


class RedisQueueClient:
    """LPUSH/BRPOP, FIFO. Без DLQ/reliability-листа - MVP"""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def enqueue_lead_delivery(self, lead_id: UUID, destination: str) -> None:
        job = LeadDeliveryJob(lead_id=lead_id, destination=destination)
        await self._client.lpush(_QUEUE_KEY, job.model_dump_json())

    async def dequeue_lead_delivery(self) -> LeadDeliveryJob | None:
        # блокирующий pop с таймаутом - worker не крутит busy-loop
        try:
            item = await self._client.brpop(_QUEUE_KEY, timeout=5)
        except RedisTimeoutError:
            return None  # пустая очередь
        if item is None:
            return None
        _key, raw = item
        return LeadDeliveryJob.model_validate_json(raw)

    async def ack(self, job: LeadDeliveryJob) -> None:
        return None  # no-op: lead.status - источник истины

    async def fail(self, job: LeadDeliveryJob) -> None:
        return None
