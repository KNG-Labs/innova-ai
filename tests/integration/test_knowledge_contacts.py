import re
from uuid import UUID

import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.models.dialog_session_model import DialogSession
from app.models.lead_model import Lead
from app.privacy import PiiSanitizer
from app.schemas.agent_schema import DialogState, LeadIntentStatus
from main import app
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


class _ConstantEmbedding:
    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(texts)
        PiiSanitizer.ensure_safe(texts)
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.mark.parametrize(
    ("kind", "public", "private", "updated"),
    [
        ("phone", "+7 (999) 777-88-01", "+79991234567", "+79991234568"),
        ("email", "sales@example.com", "client@example.com", "newclient@example.com"),
        ("telegram", "@dealer_auto", "@client_user", "@newclient_user"),
    ],
)
@pytest.mark.parametrize("with_client_contact", [False, True])
async def test_knowledge_contacts_are_visible_but_never_become_client_contacts(
    client, kind, public, private, updated, with_client_contact
):
    captured = []

    class _Client(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            return agent_decision(
                answer="Контакт салона: [KB_CONTACT_1]. [PHONE_1] [KB_CONTACT_99]",
                extracted_contact={
                    kind: f"[{kind.upper()}_1]" if with_client_contact else public
                },
            )

    embedding = _ConstantEmbedding()
    app.state.embedding_client = embedding
    app.state.llm_client = _Client()
    response = await client.post(
        "/knowledge/documents",
        json=[
            {"title": "Контакты салона", "content": f"Контакт отдела продаж: {public}"}
        ],
    )
    assert response.status_code == 201
    message = "Как связаться с отделом продаж?"
    if with_client_contact:
        message += f" Мой контакт: {private}"
    response = await client.post(
        "/message", json={"anonymous_id": "knowledge-contact", "content": message}
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert public in answer
    assert private not in answer
    assert "[PHONE_1]" in answer
    assert "[KB_CONTACT_99]" in answer
    assert public not in repr(captured)
    assert private not in repr(captured)
    assert "[KB_CONTACT_1]" in captured[0]["retrieved_context"]
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(response.json()["lead_id"]))
        assert lead.contact == ({kind: private} if with_client_contact else None)
    assert ("contact" in response.json()["missing_fields"]) is not with_client_contact

    class _QuotedClient(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            return agent_decision(answer="Да, это контакт отдела продаж.")

    app.state.llm_client = _QuotedClient()
    quoted = await client.post(
        "/message",
        json={
            "anonymous_id": "knowledge-contact",
            "session_id": response.json()["session_id"],
            "content": f"Это контакт отдела продаж {public}?",
        },
    )
    assert quoted.status_code == 200
    assert quoted.json()["state"] == "FAQ"
    assert quoted.json()["lead_id"] == response.json()["lead_id"]
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(quoted.json()["lead_id"]))
        assert lead.contact == ({kind: private} if with_client_contact else None)

    class _UpdatedClient(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            token = re.search(rf"\[{kind.upper()}_\d+\]", kwargs["user_message"])[0]
            return agent_decision(
                answer="Контакт обновлён.", extracted_contact={kind: token}
            )

    app.state.llm_client = _UpdatedClient()
    changed = await client.post(
        "/message",
        json={
            "anonymous_id": "knowledge-contact",
            "session_id": response.json()["session_id"],
            "content": f"Теперь мой контакт для связи: {updated}",
        },
    )
    assert changed.status_code == 200
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(changed.json()["lead_id"]))
        assert lead.contact == {kind: updated}
    outbound = repr({"llm": captured, "embedding": embedding.calls})
    for contact in (public, private, updated):
        assert contact not in outbound


async def test_third_party_contact_does_not_confirm_lead_intent(client):
    calls = []

    class _Client(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            calls.append(kwargs)
            return await super().decide(**kwargs)

    app.state.llm_client = _Client(
        responses=[
            agent_decision(next_state=DialogState.QUALIFICATION),
            agent_decision(
                answer="Хотите оформить заявку?",
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
        ]
    )
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "third-party-contact",
            "content": "Это телефон коллеги +79991234567?",
        },
    )
    assert response.status_code == 200
    assert response.json()["state"] == "FAQ"
    assert len(calls) == 2
    assert calls[1]["force_lead_intent_confirmation"] is True
    lead = (await client.get(f"/leads/{response.json()['lead_id']}")).json()
    assert not lead["contact"]


@pytest.mark.parametrize("contact_opt_out", [False, True])
async def test_contact_question_does_not_fill_contact_or_resume_collection(
    client, contact_opt_out
):
    initial = await client.post(
        "/message", json={"anonymous_id": "contact-question", "content": "Привет"}
    )
    data = initial.json()
    async with app.state.db_session_maker() as db:
        session = await db.get(DialogSession, UUID(data["session_id"]))
        session.state = DialogState.CONTACT_CAPTURE.value
        session.contact_opt_out = contact_opt_out
        session.contact_refusals = 2 if contact_opt_out else 0
        lead = await db.get(Lead, UUID(data["lead_id"]))
        lead.qualification = {
            "car_model": "Camry",
            "budget": "3000000",
            "purchase_type": "наличные",
        }
        await db.commit()
    app.state.llm_client = FakeAg2AgentClient(
        responses=[agent_decision(answer="Уточните, о чьём телефоне идёт речь.")]
    )
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-question",
            "session_id": data["session_id"],
            "content": "Это телефон +79991234567?",
        },
    )
    assert response.status_code == 200
    lead = (await client.get(f"/leads/{data['lead_id']}")).json()
    assert not lead["contact"]
    async with app.state.db_session_maker() as db:
        session = await db.get(DialogSession, UUID(data["session_id"]))
        assert session.contact_opt_out is contact_opt_out
        assert session.contact_refusals == (2 if contact_opt_out else 0)
