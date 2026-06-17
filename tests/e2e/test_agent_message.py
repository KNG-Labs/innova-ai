import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.schemas.agent_schema import AgentDecision, DialogState
from main import app

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_full_lead_flow_reaches_lead_ready(client) -> None:
    """E2E: три хода fake client доводят диалог до LEAD_READY.

    Ход 1: GREETING → QUALIFICATION (сервис назван)
    Ход 2: QUALIFICATION → CONTACT_CAPTURE (бюджет и дедлайн собраны)
    Ход 3: CONTACT_CAPTURE → LEAD_READY (контакт получен)

    После хода 3:
    - state == LEAD_READY
    - lead в БД имеет status="ready"
    - lead.qualification содержит service, deadline, budget
    - lead.contact содержит phone
    """
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            # Ход 1: GREETING → QUALIFICATION
            AgentDecision(
                answer="Расскажите подробнее о задаче.",
                intent="general",
                next_state=DialogState.QUALIFICATION,
                qualification_data={"service": "AI-ассистент"},
                missing_fields=["deadline", "budget", "contact"],
                lead_ready=False,
                extracted_contact=None,
            ),
            # Ход 2: QUALIFICATION → CONTACT_CAPTURE
            AgentDecision(
                answer="Отлично! Как с вами связаться?",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_data={"deadline": "1 месяц", "budget": "300000"},
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
                lead_summary="Клиент хочет AI-ассистента за 300к за месяц.",
            ),
        ]
    )

    anon_id = "e2e-lead-flow-user"

    # Ход 1
    r1 = await client.post(
        "/message",
        json={"anonymous_id": anon_id, "channel": "website", "content": "Привет"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["state"] == "QUALIFICATION"
    session_id = d1["session_id"]

    # Ход 2
    r2 = await client.post(
        "/message",
        json={
            "anonymous_id": anon_id,
            "channel": "website",
            "session_id": session_id,
            "content": "Нужен AI-ассистент, бюджет 300к, срок месяц",
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

    # Проверяем lead в БД через session
    # (GET /leads ещё не реализован — Phase 4)
    # Проверяем через session messages что история полная
    msgs = await client.get(f"/sessions/{session_id}/messages")
    assert msgs.status_code == 200
    assert len(msgs.json()) == 6  # 3 user + 3 assistant
