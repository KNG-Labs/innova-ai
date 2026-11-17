import pytest
from uuid import UUID

from app.client.ag2_agent_client import (
    Ag2AgentClient,
    FakeAg2AgentClient,
    _FALLBACK_DECISION,
)
from app.client.queue_client import FakeQueueClient
from app.models.dialog_session_model import DialogSession
from app.models.lead_model import Lead
from app.schemas.agent_schema import ContactPreference, DialogState
from main import app
from tests.factories import agent_decision

pytestmark = [pytest.mark.integration, pytest.mark.integration_crm_fake]


async def test_ready_lead_enqueues_once(client) -> None:
    fake_queue = FakeQueueClient()
    app.state.queue_client = fake_queue
    app.state.delivery_provider = "fake"
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
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
            agent_decision(
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


@pytest.fixture
async def contact_capture(client):
    app.state.queue_client = FakeQueueClient()
    app.state.delivery_provider = "fake"
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Как с вами связаться?",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_patch={
                    "car_model": "Toyota Camry",
                    "budget": "2500000",
                    "purchase_type": "наличные",
                },
                missing_fields=["contact"],
            )
        ]
    )
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "content": "Хочу купить Toyota Camry за 2500000, наличные",
        },
    )
    assert response.status_code == 200
    assert response.json()["state"] == "CONTACT_CAPTURE"
    return response.json()


@pytest.mark.parametrize("failure", ["timeout", "empty", "invalid"])
async def test_last_contact_completes_lead_when_llm_reply_fails(
    client, contact_capture, failure
) -> None:
    class _FailingAgent:
        def generate_reply(self, **kwargs):
            if failure == "timeout":
                raise TimeoutError
            return None if failure == "empty" else "invalid JSON"

    llm = object.__new__(Ag2AgentClient)
    llm._agent = _FailingAgent()
    app.state.llm_client = llm

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": contact_capture["session_id"],
            "content": "+79991234567",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "LEAD_READY"
    assert data["missing_fields"] == []
    assert "Заявка принята" in data["answer"]
    assert "Попробуйте ещё раз" not in data["answer"]
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(data["lead_id"]))
        assert lead is not None
        assert lead.status == "ready"
        assert lead.contact == {"phone": "+79991234567"}
        session = await db.get(DialogSession, UUID(data["session_id"]))
        assert session is not None
        assert session.state == "LEAD_READY"
        assert session.closed_at is not None
    assert len(app.state.queue_client.enqueued) == 1
    assert app.state.queue_client.enqueued[0].lead_id == UUID(data["lead_id"])

    # A repeated submission against the closed session cannot enqueue its lead again.
    retry = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": data["session_id"],
            "content": "+79991234567",
        },
    )
    assert retry.status_code == 200
    assert retry.json()["session_id"] != data["session_id"]
    assert retry.json()["state"] != "LEAD_READY"
    assert retry.json()["answer"] == _FALLBACK_DECISION.answer
    assert len(app.state.queue_client.enqueued) == 1


@pytest.mark.parametrize("state", [DialogState.FAQ, DialogState.CONTACT_CAPTURE])
async def test_llm_failure_does_not_complete_unconfirmed_or_incomplete_lead(
    client, contact_capture, state
) -> None:
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(contact_capture["lead_id"]))
        session = await db.get(DialogSession, UUID(contact_capture["session_id"]))
        assert lead is not None
        assert session is not None
        session.state = state.value
        if state == DialogState.CONTACT_CAPTURE:
            lead.qualification = {"car_model": "Toyota Camry"}
        await db.commit()
    app.state.llm_client = FakeAg2AgentClient(responses=[_FALLBACK_DECISION])

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": contact_capture["session_id"],
            "content": "+79991234567",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == state.value
    assert response.json()["answer"] == _FALLBACK_DECISION.answer
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(contact_capture["lead_id"]))
        assert lead is not None
        assert lead.status == "draft"
    assert not app.state.queue_client.enqueued


@pytest.mark.parametrize("existing_contact", [False, True])
@pytest.mark.parametrize(
    "overrides",
    [
        {"next_state": DialogState.CLOSED},
        {"contact_preference": "refusal"},
        {"lead_intent_status": "declined"},
    ],
)
async def test_complete_lead_is_not_enqueued_after_refusal_or_cancellation(
    client, contact_capture, existing_contact, overrides
) -> None:
    if existing_contact:
        async with app.state.db_session_maker() as db:
            lead = await db.get(Lead, UUID(contact_capture["lead_id"]))
            assert lead is not None
            lead.contact = {"phone": "+79991234567"}
            await db.commit()
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                **{
                    "next_state": DialogState.LEAD_READY,
                    "lead_ready": True,
                    **overrides,
                }
            )
        ]
    )

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": contact_capture["session_id"],
            "content": (
                "Отмените заявку"
                if existing_contact
                else "Не оформляйте заявку, +79991234567"
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] != "LEAD_READY"
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(contact_capture["lead_id"]))
        assert lead is not None
        assert lead.status == "draft"
    assert not app.state.queue_client.enqueued


class _CapturingClient(FakeAg2AgentClient):
    def __init__(self, responses):
        super().__init__(responses=responses)
        self.calls: list[dict] = []

    async def decide(self, **kwargs):
        self.calls.append(kwargs)
        return await super().decide(**kwargs)


@pytest.mark.parametrize(
    ("suggested_state", "lead_ready"),
    [
        (DialogState.LEAD_READY, True),
        (DialogState.LEAD_READY, False),
        (DialogState.CONTACT_CAPTURE, True),
    ],
)
async def test_rejected_contact_gets_one_correction_then_can_complete_lead(
    client, contact_capture, monkeypatch, suggested_state, lead_ready
) -> None:
    corrected_answer = (
        "Не удалось распознать контакт. Проверьте телефон "
        "или укажите email либо Telegram."
    )
    llm = _CapturingClient(
        responses=[
            agent_decision(
                answer="Телефон записан, заявка готова, передаю специалисту.",
                next_state=suggested_state,
                lead_ready=lead_ready,
                qualification_patch={"budget": "3000000"},
                extracted_contact={"phone": "+79991234567"},
                missing_fields=[],
            ),
            agent_decision(
                answer=corrected_answer,
                next_state=DialogState.CONTACT_CAPTURE,
                missing_fields=["contact"],
            ),
            agent_decision(
                answer="Спасибо, заявка готова.",
                next_state=DialogState.LEAD_READY,
                lead_ready=True,
                missing_fields=[],
            ),
        ]
    )
    app.state.llm_client = llm
    observations: list[dict] = []
    monkeypatch.setattr(
        "app.service.agent_service.update_observation",
        lambda **attributes: observations.append(attributes),
    )
    payload = {
        "anonymous_id": "contact-correction-user",
        "session_id": contact_capture["session_id"],
        "content": "+70000000000",
    }

    response = await client.post("/message", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == corrected_answer
    assert data["state"] == data["next_step"] == "CONTACT_CAPTURE"
    assert data["missing_fields"] == ["contact"]
    assert data["lead_id"] == contact_capture["lead_id"]
    assert len(llm.calls) == 2
    assert not llm.calls[0].get("force_contact_correction", False)
    assert llm.calls[1]["force_contact_correction"] is True
    assert llm.calls[1]["current_state"] == "CONTACT_CAPTURE"
    assert llm.calls[1]["missing_fields"] == ["contact"]
    assert llm.calls[1]["qualification_data"]["budget"] == "3000000"
    for key in ("user_message", "history", "retrieved_context", "page_title"):
        assert llm.calls[1][key] == llm.calls[0][key]
    assert observations[-1]["output"] == corrected_answer
    assert observations[-1]["metadata"]["contact_confirmation_rejected"] is True
    session = await client.get(f"/sessions/{data['session_id']}")
    assert session.json()["state"] == "CONTACT_CAPTURE"
    lead = await client.get(f"/leads/{data['lead_id']}")
    assert lead.json()["status"] == "draft"
    assert not lead.json()["contact"]
    assert lead.json()["qualification"]["budget"] == "3000000"
    history = await client.get(f"/sessions/{data['session_id']}/messages")
    assert len(history.json()) == 4
    assert history.json()[-1]["id"] == data["assistant_message_id"]
    assert history.json()[-1]["content"] == corrected_answer
    assert all("передаю специалисту" not in row["content"] for row in history.json())
    assert app.state.queue_client.enqueued == []

    accepted = await client.post(
        "/message", json={**payload, "content": "+79991234567"}
    )

    assert accepted.status_code == 200
    assert accepted.json()["session_id"] == data["session_id"]
    assert accepted.json()["lead_id"] == data["lead_id"]
    assert accepted.json()["state"] == "LEAD_READY"
    assert accepted.json()["missing_fields"] == []
    assert len(llm.calls) == 3
    assert not llm.calls[2].get("force_contact_correction", False)
    assert llm.calls[2]["user_message"] == "[PHONE_1]"
    lead = await client.get(f"/leads/{data['lead_id']}")
    assert lead.json()["status"] == "ready"
    assert lead.json()["contact"] == {"phone": "+79991234567"}
    [job] = app.state.queue_client.enqueued
    assert job.lead_id == UUID(data["lead_id"])
    assert job.destination == "fake"


@pytest.mark.parametrize(
    "correction",
    [
        agent_decision(next_state=DialogState.LEAD_READY, missing_fields=["contact"]),
        agent_decision(
            next_state=DialogState.CONTACT_CAPTURE,
            lead_ready=True,
            missing_fields=["contact"],
        ),
        agent_decision(next_state=DialogState.CONTACT_CAPTURE, missing_fields=[]),
        agent_decision(
            next_state=DialogState.CONTACT_CAPTURE,
            missing_fields=["contact"],
            qualification_patch={"budget": "1"},
        ),
        agent_decision(
            answer=" ",
            next_state=DialogState.CONTACT_CAPTURE,
            missing_fields=["contact"],
        ),
        _FALLBACK_DECISION,
    ],
    ids=["ready-state", "ready-flag", "missing-contact", "patch", "empty", "fallback"],
)
async def test_failed_contact_correction_rolls_back_current_turn(
    client, contact_capture, correction
) -> None:
    session_url = f"/sessions/{contact_capture['session_id']}"
    lead_url = f"/leads/{contact_capture['lead_id']}"
    before_session = (await client.get(session_url)).json()
    before_lead = (await client.get(lead_url)).json()
    before_history = (await client.get(f"{session_url}/messages")).json()
    llm = _CapturingClient(
        responses=[
            agent_decision(
                answer="Заявка готова.",
                next_state=DialogState.LEAD_READY,
                lead_ready=True,
                qualification_patch={"budget": "3000000"},
            ),
            correction,
        ]
    )
    app.state.llm_client = llm

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": contact_capture["session_id"],
            "content": "+70000000000",
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Agent response unavailable"}
    assert len(llm.calls) == 2
    assert (await client.get(session_url)).json() == before_session
    assert (await client.get(lead_url)).json() == before_lead
    assert (await client.get(f"{session_url}/messages")).json() == before_history
    assert app.state.queue_client.enqueued == []


@pytest.mark.parametrize(
    ("content", "next_state", "preference"),
    [
        ("Когда работаете?", DialogState.FAQ, ContactPreference.NONE),
        ("Не оставлю контакт", DialogState.CONTACT_CAPTURE, ContactPreference.REFUSAL),
    ],
)
async def test_contact_capture_preserves_faq_and_refusal_without_correction(
    client, contact_capture, content, next_state, preference
) -> None:
    llm = _CapturingClient(
        responses=[
            agent_decision(
                answer="Ответ по текущему запросу.",
                next_state=next_state,
                missing_fields=["contact"],
                contact_preference=preference,
            )
        ]
    )
    app.state.llm_client = llm

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-correction-user",
            "session_id": contact_capture["session_id"],
            "content": content,
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Ответ по текущему запросу."
    assert response.json()["state"] == next_state.value
    assert len(llm.calls) == 1
    assert app.state.queue_client.enqueued == []


async def test_existing_contact_allows_readiness_without_correction(
    client, contact_capture
) -> None:
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(contact_capture["lead_id"]))
        assert lead is not None
        lead.contact = {"phone": "+79991234567"}
        await db.commit()
    llm = _CapturingClient(
        responses=[
            agent_decision(
                answer="Заявка готова.",
                next_state=DialogState.LEAD_READY,
                lead_ready=True,
                missing_fields=[],
            ),
        ]
    )
    app.state.llm_client = llm
    payload = {
        "anonymous_id": "contact-correction-user",
        "session_id": contact_capture["session_id"],
        "content": "+70000000000",
    }
    ready = await client.post("/message", json=payload)

    assert ready.status_code == 200
    assert ready.json()["answer"] == "Заявка готова."
    assert ready.json()["state"] == "LEAD_READY"
    assert ready.json()["missing_fields"] == []
    assert len(llm.calls) == 1
    assert all(not call.get("force_contact_correction", False) for call in llm.calls)
    lead = await client.get(f"/leads/{contact_capture['lead_id']}")
    assert lead.json()["contact"] == {"phone": "+79991234567"}
    assert len(app.state.queue_client.enqueued) == 1
