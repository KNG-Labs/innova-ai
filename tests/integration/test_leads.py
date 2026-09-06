import pytest
from uuid import uuid4

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.schemas.agent_schema import DialogState
from main import app
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


async def test_get_leads_lists_lead_and_detail_shows_qualification(client) -> None:
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Расскажите подробнее.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
                missing_fields=["budget", "purchase_type", "contact"],
            ),
        ]
    )

    msg = await client.post(
        "/message",
        json={
            "anonymous_id": "lead-read-user",
            "channel": "website",
            "content": "Хочу купить Toyota Camry",
        },
    )
    assert msg.status_code == 200
    lead_id = msg.json()["lead_id"]
    assert lead_id is not None

    listing = await client.get("/leads")
    assert listing.status_code == 200
    rows = listing.json()
    assert any(row["id"] == lead_id for row in rows)
    # лёгкая схema: qualification в список НЕ попадает
    assert "qualification" not in rows[0]

    detail = await client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == lead_id
    assert data["status"] == "draft"
    assert data["qualification"]["car_model"] == "Toyota Camry"


async def test_get_lead_unknown_id_returns_404(client) -> None:
    response = await client.get(f"/leads/{uuid4()}")
    assert response.status_code == 404


async def test_get_leads_filter_by_status(client) -> None:
    response = await client.get("/leads?status=ready")
    assert response.status_code == 200
    assert all(row["status"] == "ready" for row in response.json())
