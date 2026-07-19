from uuid import UUID

import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.schemas.agent_schema import AgentDecision, DialogState
from app.models import DialogSession, Lead
from main import app

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_full_lead_flow_reaches_lead_ready(client) -> None:
    """E2E: три хода fake client доводят диалог до LEAD_READY.

    Ход 1: GREETING → QUALIFICATION (модель названа)
    Ход 2: QUALIFICATION → CONTACT_CAPTURE (бюджет и способ покупки собраны)
    Ход 3: CONTACT_CAPTURE → LEAD_READY (контакт получен)

    После хода 3:
    - state == LEAD_READY
    - lead в БД имеет status="ready"
    - lead.qualification содержит car_model, budget, purchase_type
    - lead.contact содержит phone
    """
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            # Ход 1: GREETING → QUALIFICATION
            AgentDecision(
                answer="Подскажите, какая модель вас интересует?",
                intent="general",
                next_state=DialogState.QUALIFICATION,
                qualification_data={"car_model": "Toyota Camry"},
                missing_fields=["budget", "purchase_type", "contact"],
                lead_ready=False,
                extracted_contact=None,
            ),
            # Ход 2: QUALIFICATION → CONTACT_CAPTURE
            AgentDecision(
                answer="Отлично! Как с вами связаться?",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_data={"budget": "2500000", "purchase_type": "кредит"},
                missing_fields=["contact"],
                lead_ready=False,
                extracted_contact=None,
            ),
            # Ход 3: CONTACT_CAPTURE → LEAD_READY
            AgentDecision(
                answer="Спасибо! Заявка принята, мы свяжемся.",
                intent="lead_request",
                next_state=DialogState.LEAD_READY,
                qualification_data={},
                missing_fields=[],
                lead_ready=True,
                extracted_contact={"phone": "+79991234567", "name": "Иван"},
                lead_summary="Клиент хочет Toyota Camry в кредит, бюджет 2.5 млн.",
            ),
        ]
    )

    anon_id = "e2e-lead-flow-user"

    # Ход 1
    r1 = await client.post(
        "/message",
        json={"anonymous_id": anon_id, "channel": "website", "content": "Здравствуйте"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["state"] == "QUALIFICATION"
    session_id = d1["session_id"]
    assert d1["lead_id"] is not None
    assert "missing_fields" in d1

    # Ход 2
    r2 = await client.post(
        "/message",
        json={
            "anonymous_id": anon_id,
            "channel": "website",
            "session_id": session_id,
            "content": "Toyota Camry, бюджет 2.5 млн, в кредит",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["state"] == "CONTACT_CAPTURE"

    # Ход 3
    r3 = await client.post(
        "/message",
        json={
            "anonymous_id": anon_id,
            "channel": "website",
            "session_id": session_id,
            "content": "Телефон +79991234567, меня зовут Иван",
        },
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["state"] == "LEAD_READY"
    assert d3["missing_fields"] == []

    # История полная: 3 user + 3 assistant
    msgs = await client.get(f"/sessions/{session_id}/messages")
    assert msgs.status_code == 200
    assert len(msgs.json()) == 6

    # Lead в БД: ready + накопленная qualification + contact
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(d3["lead_id"]))
        assert lead.status == "ready"
        assert lead.qualification["car_model"] == "Toyota Camry"
        assert lead.qualification["budget"] == "2500000"
        assert lead.qualification["purchase_type"] == "кредит"
        assert lead.contact["phone"] == "+79991234567"
        session = await db.get(DialogSession, UUID(session_id))
        assert session is not None
        assert session.closed_at is not None

    # Даже если виджет повторно прислал старый session_id,
    # backend должен начать новый диалог.
    r4 = await client.post(
        "/message",
        json={
            "anonymous_id": anon_id,
            "channel": "website",
            "session_id": session_id,
            "content": "Хочу подобрать ещё один автомобиль",
        },
    )

    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["session_id"] != session_id
    assert d4["lead_id"] != d3["lead_id"]
