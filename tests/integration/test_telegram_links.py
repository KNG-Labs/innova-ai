from uuid import UUID

import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.models.lead_model import Lead
from app.privacy import PiiSanitizer
from main import app
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


class _CapturingEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(texts)
        PiiSanitizer.ensure_safe(texts)
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.mark.parametrize("prefix", ["", "Telegram: "])
async def test_private_telegram_link_is_saved_and_masked_in_ai_payloads(
    client, prefix
) -> None:
    captured = []

    class _Client(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            return agent_decision(
                extracted_contact={"telegram": "[TELEGRAM_1]"},
            )

    embedding = _CapturingEmbedding()
    app.state.embedding_client = embedding
    app.state.llm_client = _Client()
    raw = "https://t.me/Ivan_Auto"
    first = await client.post(
        "/message",
        json={
            "anonymous_id": "telegram-link",
            "content": f"Расскажите об услугах. Мой контакт: {prefix}{raw}",
        },
    )
    assert first.status_code == 200
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "telegram-link",
            "session_id": first.json()["session_id"],
            "content": "Какие часы работы?",
        },
    )
    assert second.status_code == 200

    outbound = repr({"llm": captured, "embeddings": embedding.calls})
    assert raw not in outbound
    assert "ivan_auto" not in outbound.casefold()
    assert "t.me/" not in outbound.casefold()
    assert "[TELEGRAM_1]" in captured[0]["user_message"]
    assert "[TELEGRAM_1]" in repr(captured[1]["history"])
    assert "[TELEGRAM_1]" in repr(embedding.calls)
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(first.json()["lead_id"]))
        assert lead is not None
        assert lead.contact == {"telegram": "@ivan_auto"}


async def test_public_telegram_link_is_restored_whole_without_becoming_client_contact(
    client,
) -> None:
    captured = []

    class _Client(FakeAg2AgentClient):
        async def decide(self, **kwargs):
            captured.append(kwargs)
            PiiSanitizer.ensure_safe(kwargs)
            return agent_decision(
                answer="Пишите: [KB_CONTACT_1].",
                extracted_contact={"telegram": "[KB_CONTACT_1]"},
            )

    embedding = _CapturingEmbedding()
    app.state.embedding_client = embedding
    app.state.llm_client = _Client()
    public = "https://t.me/Company_Support"
    knowledge = await client.post(
        "/knowledge/documents",
        json=[{"title": "Контакты", "content": f"Telegram: {public}"}],
    )
    assert knowledge.status_code == 201
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "public-telegram-link",
            "content": "Как с вами связаться?",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == f"Пишите: {public}."
    assert "[KB_CONTACT_1]" in captured[0]["retrieved_context"]
    assert public not in repr(captured)
    assert public not in repr(embedding.calls)
    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(response.json()["lead_id"]))
        assert lead is not None
        assert lead.contact is None
