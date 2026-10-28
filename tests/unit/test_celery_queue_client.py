from unittest.mock import Mock
from uuid import uuid4

import pytest
from celery import Celery

from app.client.queue_client import CeleryQueueClient

pytestmark = pytest.mark.unit


async def test_publishes_lead_id_as_single_task_argument() -> None:
    celery_app = Mock(spec=Celery)
    client = CeleryQueueClient(celery_app)
    lead_id = uuid4()

    await client.enqueue_lead_delivery(lead_id, destination="fake")

    celery_app.send_task.assert_called_once_with(
        "app.worker.lead_delivery.deliver_lead",
        args=[str(lead_id)],
    )
