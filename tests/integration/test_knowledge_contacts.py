from uuid import UUID

import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.models.lead_model import Lead
from app.privacy import PiiSanitizer
from main import app
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


class _ConstantEmbedding:
    async def embed(self, texts):
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.mark.parametrize(
    ("kind", "public", "private"),
    [
        ("phone", "+7 (999) 777-88-01", "+79991234567"),
        ("email", "sales@example.com", "client@example.com"),
        ("telegram", "@dealer_auto", "@client_user"),
    ],
)
@pytest.mark.parametrize("with_client_contact", [False, True])
async def test_knowledge_contacts_are_visible_but_never_become_client_contacts(
    client, kind, public, private, with_client_contact
):
    captured = []

    class _Client(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            return agent_decision(
                answer="Контакт салона: [KB_CONTACT_1]. [PHONE_1] [KB_CONTACT_99]",
                extracted_contact={kind: public},
            )

    app.state.embedding_client = _ConstantEmbedding()
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
