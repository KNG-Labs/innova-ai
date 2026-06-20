import pytest
from uuid import uuid4

from app.client.ag2_agent_client import FakeAg2AgentClient, AgentDecision
from app.schemas import DialogState
from main import app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_leads_lists_lead_and_detail_shows_qualification(client) -> None:
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            AgentDecision(
                answer="Расскажите подробнее.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_data={"service": "SEO"},
                missing_fields=["deadline", "budget", "contact"],
                lead_ready=False,
            ),
        ]
    )

    msg = await client.post(
        "/message",
        json={"anonymous_id": "lead-read-user", "channel": "website", "content": "Нужно SEO"},
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
    assert data["qualification"]["service"] == "SEO"


@pytest.mark.asyncio
async def test_get_lead_unknown_id_returns_404(client) -> None:
    response = await client.get(f"/leads/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_leads_filter_by_status(client) -> None:
    response = await client.get("/leads?status=ready")
    assert response.status_code == 200
    assert all(row["status"] == "ready" for row in response.json())