from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.di import close_app_state, init_app_state
from app.models.lead_model import Lead
from app.models.message_model import Message
from app.schemas.agent_schema import DialogState
from main import create_app
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


async def test_demo_preserves_dialog_and_lead_without_delivery(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    app = create_app()
    await init_app_state(app)
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Какой бюджет?",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
            ),
            agent_decision(
                answer="Оставьте контакт.",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_patch={"budget": "3000000", "purchase_type": "наличные"},
            ),
            agent_decision(
                answer="Заявка подготовлена.",
                next_state=DialogState.LEAD_READY,
                lead_ready=True,
            ),
        ]
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as demo:
            session_id = None
            for content in (
                "Хочу купить Toyota Camry",
                "Бюджет 3000000, за наличные",
                "+7 999 123-45-67",
            ):
                payload = {"anonymous_id": "public-demo-test", "content": content}
                if session_id:
                    payload["session_id"] = session_id
                response = await demo.post("/message", json=payload)
                assert response.status_code == 200, response.text
                data = response.json()
                if session_id:
                    assert data["session_id"] == session_id
                session_id = data["session_id"]
            assert data["state"] == "LEAD_READY"
            assert data["lead_id"] is not None
            assert app.state.queue_client.enqueued == []
            async with app.state.db_session_maker() as db:
                lead = await db.get(Lead, UUID(data["lead_id"]))
                assert lead.qualification["budget"] == "3000000"
                assert lead.contact["phone"]
                messages = list(
                    await db.scalars(
                        select(Message).where(Message.session_id == UUID(session_id))
                    )
                )
                assert len(messages) == 6
    finally:
        await close_app_state(app)
