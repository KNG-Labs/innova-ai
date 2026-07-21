import pytest

from app.client.ag2_agent_client import AgentDecision, FakeAg2AgentClient
from app.client.queue_client import FakeQueueClient
from app.schemas import DialogState
from main import app

pytestmark = [pytest.mark.integration, pytest.mark.integration_crm_fake]


@pytest.mark.asyncio
async def test_ready_lead_enqueues_once(client) -> None:
    fake_queue = FakeQueueClient()
    app.state.queue_client = fake_queue
    app.state.delivery_provider = "fake"
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            AgentDecision(
                answer="Готово!",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_patch={
                    "car_model": "Toyota Camry",
                    "budget": "3 млн",
                    "purchase_type": "кредит",
                },
                extracted_contact={"name": "Иван", "phone": "+79991234567"},
                missing_fields=[],
                lead_ready=True,
            ),
            AgentDecision(
                answer="Готово!",
                intent="lead_request",
                next_state=DialogState.LEAD_READY,
                qualification_patch={
                    "car_model": "Toyota Camry",
                    "budget": "3 млн",
                    "purchase_type": "кредит",
                },
                extracted_contact={"name": "Иван", "phone": "+79991234567"},
                missing_fields=[],
                lead_ready=True,
            ),
        ]
    )

    await client.post(
        "/message",
        json={
            "anonymous_id": "enqueue-user",
            "channel": "website",
            "content": "Хочу Camry, 3 млн, кредит, Иван +79991234567",
        },
    )
    resp = await client.post(
        "/message",
        json={
            "anonymous_id": "enqueue-user",
            "channel": "website",
            "content": "Хочу Camry, 3 млн, кредит, Иван +79991234567",
        },
    )
    assert resp.status_code == 200
    assert len(fake_queue.enqueued) == 1
    assert fake_queue.enqueued[0].destination == "fake"
