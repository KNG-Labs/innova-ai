import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from app.client.retrieval_planner_client import (
    FakeRetrievalPlannerClient,
    RetrievalMode,
    RetrievalPlan,
)
from app.schemas.agent_schema import DialogState
from app.schemas.agent_schema import LeadIntentStatus
from main import app
from uuid import UUID, uuid4
from app.models.dialog_session_model import DialogSession
from app.models.lead_model import Lead
from app.models.message_model import Message
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("alias", "alias_id"),
    [("trade-in", "latin"), ("трейд-ин", "hyphen"), ("трейдин", "phonetic")],
)
async def test_trade_in_aliases_retrieve_same_source(
    client,
    alias: str,
    alias_id: str,
) -> None:
    captured_contexts: list[str] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": (
                    "Trade-in, также называемый «трейд-ин» или «трейдин», — "
                    "это зачёт старого автомобиля при покупке нового."
                ),
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Trade-in — зачёт старого автомобиля.",
            )
        ]
    )

    response = await client.post(
        "/message",
        json={"anonymous_id": f"alias-{alias_id}", "content": alias},
    )

    assert response.status_code == 200
    assert "[Источник: Программа Trade-in]" in captured_contexts[0]


async def test_post_message_creates_anonymous_user_session_and_messages(client) -> None:
    """/message: успешный путь со сценарным AG2-стабом.

    Сценарий: на вопрос о цене агент отвечает и двигает диалог GREETING -> FAQ.
    """

    # Подменяем стаб ДО запроса: фикстура client уже подняла app.state через
    # init_app_state, а get_agent_service читает llm_client из app.state в момент запроса.
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Toyota Camry — от 2 500 000 ₽. Что ещё подсказать?",
                intent="pricing",
            ),
        ]
    )

    payload = {
        "anonymous_id": "test-user-1",
        "channel": "website",
        "content": " Сколько   стоит Camry? ",
    }

    response = await client.post("/message", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"]
    assert data["session_id"]
    assert data["user_message_id"]
    assert data["assistant_message_id"]
    assert data["answer"] == "Toyota Camry — от 2 500 000 ₽. Что ещё подсказать?"
    assert data["intent"] == "pricing"
    # GREETING -> FAQ — допустимый переход в state_machine,
    # next_step в новом контракте — это имя следующего состояния.
    assert data["state"] == "FAQ"
    assert data["next_step"] == "FAQ"

    messages_response = await client.get(f"/sessions/{data['session_id']}/messages")

    assert messages_response.status_code == 200
    messages = messages_response.json()

    assert len(messages) == 2

    assert messages[0]["role"] == "user"
    # content нормализуется: лишние пробелы схлопываются.
    assert messages[0]["content"] == "Сколько стоит Camry?"

    assert messages[1]["role"] == "assistant"
    assert (
        messages[1]["content"] == "Toyota Camry — от 2 500 000 ₽. Что ещё подсказать?"
    )


async def test_post_message_continues_existing_dialog_session(client) -> None:
    """session_id сохраняется между сообщениями.

    Сценарий из двух ходов: явный lead intent (GREETING -> QUALIFICATION),
    затем явный запрос заявки (QUALIFICATION -> CONTACT_CAPTURE).
    """

    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Здравствуйте! Какая модель вас интересует?",
                next_state=DialogState.QUALIFICATION,
            ),
            agent_decision(
                answer="Отлично! Оставьте контакт, и мы свяжемся.",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_patch={"car_model": "Toyota Camry"},
                missing_fields=["budget", "purchase_type", "contact"],
            ),
        ]
    )

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-2",
            "channel": "website",
            "content": "Хочу купить автомобиль",
        },
    )

    assert first_response.status_code == 200
    first_data = first_response.json()
    assert first_data["state"] == "QUALIFICATION"

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-2",
            "channel": "website",
            "session_id": first_data["session_id"],
            "content": "Хочу оставить заявку",
        },
    )

    assert second_response.status_code == 200
    second_data = second_response.json()

    assert second_data["user_id"] == first_data["user_id"]
    assert second_data["session_id"] == first_data["session_id"]
    assert second_data["intent"] == "lead_request"
    # QUALIFICATION -> CONTACT_CAPTURE — допустимый переход.
    assert second_data["state"] == "CONTACT_CAPTURE"
    assert second_data["next_step"] == "CONTACT_CAPTURE"

    messages_response = await client.get(
        f"/sessions/{first_data['session_id']}/messages"
    )

    assert messages_response.status_code == 200
    messages = messages_response.json()

    assert len(messages) == 4
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    assert messages[0]["content"] == "Хочу купить автомобиль"
    assert messages[2]["content"] == "Хочу оставить заявку"


async def test_post_message_rejects_missing_anonymous_id(client) -> None:
    """
    Тест: ошибка при отсутствии поля anonymous_id

    """

    response = await client.post(
        "/message",
        json={
            "channel": "website",
            "content": "Привет",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


async def test_post_message_rejects_invalid_anonymous_id(client) -> None:
    """
    Тест: валидация поля anonymous_id

    """

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "bad anonymous id with spaces",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]


async def test_post_message_continues_active_session_without_session_id(client) -> None:
    """
    Тест: DialogSessionRepository.get_or_create_active_session() должен уметь
    найти открытую сессию пользователя даже без session_id в запросе.

    """

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "active-user-1",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert first_response.status_code == 200
    first_data = first_response.json()

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "active-user-1",
            "channel": "website",
            "content": "Сколько стоит?",
        },
    )

    assert second_response.status_code == 200
    second_data = second_response.json()

    assert second_data["user_id"] == first_data["user_id"]
    assert second_data["session_id"] == first_data["session_id"]

    messages_response = await client.get(
        f"/sessions/{first_data['session_id']}/messages"
    )

    assert messages_response.status_code == 200
    assert len(messages_response.json()) == 4


async def test_different_anonymous_users_get_different_sessions(client) -> None:
    """
    Тест: разные anonymous users получают разные сессии.
    Память разных пользователей не смешивается.

    """

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-a",
            "channel": "website",
            "content": "Привет",
        },
    )

    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-b",
            "channel": "website",
            "content": "Привет",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_data = first_response.json()
    second_data = second_response.json()

    assert first_data["user_id"] != second_data["user_id"]
    assert first_data["session_id"] != second_data["session_id"]


async def test_same_anonymous_id_in_different_channels_creates_different_users(
    client,
) -> None:
    """
    Тест: разные каналы с одинаковым anonymous_id — это разные пользователи.

    """
    website_response = await client.post(
        "/message",
        json={
            "anonymous_id": "same-user-id",
            "channel": "website",
            "content": "Привет с сайта",
        },
    )

    telegram_response = await client.post(
        "/message",
        json={
            "anonymous_id": "same-user-id",
            "channel": "telegram",
            "content": "Привет из Telegram",
        },
    )

    assert website_response.status_code == 200
    assert telegram_response.status_code == 200

    website_data = website_response.json()
    telegram_data = telegram_response.json()

    assert website_data["user_id"] != telegram_data["user_id"]
    assert website_data["session_id"] != telegram_data["session_id"]


async def test_post_message_rejects_blank_content(client) -> None:
    """
    Тест: невалидный content

    """
    response = await client.post(
        "/message",
        json={
            "anonymous_id": "blank-content-user",
            "channel": "website",
            "content": "   ",
        },
    )

    assert response.status_code == 422


async def test_post_message_rejects_unknown_channel(client) -> None:
    """
    Тест: невалидный channel

    """

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-1",
            "channel": "unknown",
            "content": "Привет",
        },
    )

    assert response.status_code == 422


async def test_post_message_rejects_session_belonging_to_other_user(
    client,
) -> None:
    """
    Тест: чужой session_id должен быть отклонён с 403.
    IDOR-проверка: пользователь не может писать в чужую сессию.
    """
    # 1. Владелец создаёт свою сессию
    owner_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-owner",
            "channel": "website",
            "content": "Привет, я владелец этой сессии",
        },
    )
    assert owner_response.status_code == 200
    owner_data = owner_response.json()
    owner_session_id = owner_data["session_id"]

    # 2. Злоумышленник создаёт свою отдельную сессию
    attacker_first = await client.post(
        "/message",
        json={
            "anonymous_id": "user-attacker",
            "channel": "website",
            "content": "Я другой пользователь",
        },
    )
    assert attacker_first.status_code == 200

    # 3. Злоумышленник пытается писать в чужую сессию
    attack_response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-attacker",
            "channel": "website",
            "session_id": owner_session_id,
            "content": "Хочу подмешать сообщение в чужую историю",
        },
    )

    assert attack_response.status_code == 403
    assert "does not belong" in attack_response.json()["detail"].lower()

    # 4. Проверяем, что история владельца не изменилась —
    #    сообщение злоумышленника НЕ попало в чужую сессию
    messages_response = await client.get(f"/sessions/{owner_session_id}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()

    # Было ровно 2 сообщения: user + assistant от владельца
    assert len(messages) == 2
    assert messages[0]["content"] == "Привет, я владелец этой сессии"
    assert all("подмешать" not in m["content"] for m in messages), (
        "Чужое сообщение не должно попасть в историю"
    )


async def test_post_message_rejects_nonexistent_session_id(client) -> None:
    """
    Тест: если передан несуществующий session_id,
    система не падает, а создаёт новую сессию (graceful fallback).
    """

    fake_session_id = str(uuid4())

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "user-with-fake-session",
            "channel": "website",
            "session_id": fake_session_id,
            "content": "Привет",
        },
    )

    assert response.status_code == 200
    data = response.json()
    # Создаётся новая сессия, а не используется фейковая
    assert data["session_id"] != fake_session_id


async def test_closed_session_sets_closed_at_and_next_message_starts_new_session(
    client,
) -> None:
    """CLOSED проставляет closed_at; закрытая сессия не переиспользуется."""

    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Расскажите, что нужно?",
                next_state=DialogState.QUALIFICATION,
            ),
            agent_decision(
                answer="Хорошо, закрываю обращение.",
                next_state=DialogState.CLOSED,
            ),
        ]
    )

    # Ход 1: подтверждённый lead intent, GREETING -> QUALIFICATION
    first = await client.post(
        "/message",
        json={
            "anonymous_id": "close-user-1",
            "channel": "website",
            "content": "Хочу купить автомобиль",
        },
    )
    assert first.status_code == 200
    first_data = first.json()
    session_id = first_data["session_id"]

    # Ход 2: QUALIFICATION -> CLOSED (тот же session_id)
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "close-user-1",
            "channel": "website",
            "session_id": session_id,
            "content": "Больше не нужно",
        },
    )
    assert second.status_code == 200
    assert second.json()["state"] == "CLOSED"

    # closed_at проставлен в БД
    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(session_id))
        assert row is not None
        assert row.closed_at is not None

    # Ход 3: клиент повторно прислал сохранённый ID закрытой сессии.
    # Backend должен проигнорировать его и создать новую.
    third = await client.post(
        "/message",
        json={
            "anonymous_id": "close-user-1",
            "channel": "website",
            "session_id": session_id,
            "content": "Здравствуйте снова",
        },
    )
    assert third.status_code == 200
    third_data = third.json()
    assert third_data["user_id"] == first_data["user_id"]
    assert third_data["session_id"] != session_id


async def test_two_explicit_contact_refusals_opt_out_without_closing_session(
    client,
) -> None:
    captured_opt_out: list[bool] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, contact_opt_out=False, **kwargs):
            captured_opt_out.append(contact_opt_out)
            return await super().decide(
                *args,
                contact_opt_out=contact_opt_out,
                **kwargs,
            )

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Оставьте контакт для связи.",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                qualification_patch={
                    "car_model": "Toyota Camry",
                    "budget": "3000000",
                    "purchase_type": "кредит",
                },
                missing_fields=["contact"],
            ),
            agent_decision(
                answer="Понимаю.",
                next_state=DialogState.CLOSED,
                missing_fields=["contact"],
                contact_preference="refusal",
            ),
            agent_decision(
                answer="Работаем ежедневно с 9:00 до 21:00.",
                missing_fields=["contact"],
            ),
            agent_decision(
                answer="Могу продолжить подбор. Оставьте контакт.",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                missing_fields=["contact"],
            ),
            agent_decision(
                answer="Хорошо, больше не буду просить контакт.",
                next_state=DialogState.CLOSED,
                missing_fields=["contact"],
                contact_preference="refusal",
            ),
            agent_decision(
                answer="Camry стоит от 2 800 000 рублей.",
                intent="pricing",
                missing_fields=["contact"],
            ),
            agent_decision(
                answer="Хорошо, вернёмся к заявке. Оставьте контакт.",
                intent="lead_request",
                next_state=DialogState.CONTACT_CAPTURE,
                missing_fields=["contact"],
                contact_preference="resume",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "channel": "website",
            "content": "Хочу купить Camry в кредит до 3 миллионов",
        },
    )
    session_id = first.json()["session_id"]
    assert first.json()["state"] == "CONTACT_CAPTURE"

    first_refusal = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "Не хочу оставлять контакт",
        },
    )
    assert first_refusal.json()["state"] == "CONTACT_CAPTURE"

    faq = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "А какие часы работы?",
        },
    )
    assert faq.json()["state"] == "FAQ"

    resume = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "Продолжим подбор",
        },
    )
    assert resume.json()["state"] == "CONTACT_CAPTURE"

    second_refusal = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "Я не буду давать телефон",
        },
    )
    assert second_refusal.json()["state"] == "FAQ"

    after_opt_out = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "Сколько стоит Camry?",
        },
    )
    assert after_opt_out.json()["session_id"] == session_id
    assert after_opt_out.json()["state"] == "FAQ"

    opt_in = await client.post(
        "/message",
        json={
            "anonymous_id": "contact-opt-out-user",
            "session_id": session_id,
            "content": "Хочу всё-таки оставить заявку",
        },
    )
    assert opt_in.json()["state"] == "CONTACT_CAPTURE"

    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(session_id))
        assert row is not None
        assert row.closed_at is None
        assert row.contact_refusals == 0
        assert row.contact_opt_out is False

    assert captured_opt_out == [False, False, False, False, False, True, True]


async def test_post_message_threads_page_title_to_llm(client) -> None:
    """page_title из запроса доходит до llm_client.decide нормализованным."""

    captured: dict = {}

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, page_title=None, **kwargs):
            captured["page_title"] = page_title
            return await super().decide(*args, page_title=page_title, **kwargs)

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Подскажу по Camry.",
                next_state=DialogState.QUALIFICATION,
            ),
        ]
    )

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-pt",
            "channel": "website",
            "content": "расскажите про эту модель",
            "page_title": "  Toyota   Camry 2024  ",
        },
    )

    assert response.status_code == 200
    assert captured["page_title"] == "Toyota Camry 2024"


async def test_post_message_threads_missing_fields_to_llm(client) -> None:
    captured: list[list[str] | None] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            missing_fields=None,
            **kwargs,
        ):
            captured.append(missing_fields)
            return await super().decide(
                *args,
                missing_fields=missing_fields,
                **kwargs,
            )

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Уточню условия покупки.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
                extracted_contact={"phone": "+79991234567"},
                missing_fields=["budget", "purchase_type"],
            ),
            agent_decision(
                answer="Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                missing_fields=["budget", "purchase_type"],
            ),
        ]
    )

    first_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-context",
            "channel": "website",
            "content": "Хочу Camry, мой телефон +79991234567",
        },
    )

    assert first_response.status_code == 200
    second_response = await client.post(
        "/message",
        json={
            "anonymous_id": "test-user-context",
            "channel": "website",
            "session_id": first_response.json()["session_id"],
            "content": "Что ещё нужно уточнить?",
        },
    )

    assert second_response.status_code == 200
    assert captured[0] == ["car_model", "budget", "purchase_type"]
    assert captured[1] == ["budget", "purchase_type"]


async def test_mixed_contact_is_sanitized_for_llm_history_and_embeddings(
    client,
) -> None:
    llm_calls: list[dict] = []

    class _CapturingEmbedding:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def embed(self, texts):
            self.calls.append(texts)
            return [[0.0] * 1536 for _ in texts]

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, **kwargs):
            llm_calls.append(kwargs)
            return await super().decide(*args, **kwargs)

    embedding = _CapturingEmbedding()
    app.state.embedding_client = embedding
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
                extracted_contact={"phone": "+70000000000"},
                missing_fields=["budget", "purchase_type"],
                lead_summary=("Позвонить +79991234567 или написать user@example.com"),
            ),
            agent_decision(
                answer="Уточните бюджет.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                missing_fields=["budget", "purchase_type"],
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "pii-mixed-user",
            "content": (
                "Хочу купить Camry, телефон +7 (999) 123-45-67, email User@Example.COM"
            ),
        },
    )
    assert first.status_code == 200

    second = await client.post(
        "/message",
        json={
            "anonymous_id": "pii-mixed-user",
            "session_id": first.json()["session_id"],
            "content": "Что ещё нужно уточнить?",
        },
    )
    assert second.status_code == 200

    outbound = repr({"llm": llm_calls, "embedding": embedding.calls})
    assert "+79991234567" not in outbound
    assert "999) 123-45-67" not in outbound
    assert "user@example.com" not in outbound.casefold()
    assert "[PHONE_1]" in outbound
    assert "[EMAIL_1]" in outbound
    assert "[PHONE_1]" in repr(llm_calls[1]["history"])
    assert "[EMAIL_1]" in repr(llm_calls[1]["history"])

    async with app.state.db_session_maker() as db:
        lead = await db.get(Lead, UUID(first.json()["lead_id"]))
        assert lead is not None
        assert lead.contact == {
            "phone": "+79991234567",
            "email": "user@example.com",
        }
        assert lead.summary is not None
        assert "+79991234567" not in lead.summary
        assert "user@example.com" not in lead.summary


async def test_contact_only_message_skips_all_external_ai_calls(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_CAPTURE_TOKEN_USAGE", "1")

    class _CapturingEmbedding:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def embed(self, texts):
            self.calls.append(texts)
            return [[0.0] * 1536 for _ in texts]

    class _CapturingClient(FakeAg2AgentClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[dict] = []

        async def decide(self, *args, **kwargs):
            self.calls.append(kwargs)
            return await super().decide(*args, **kwargs)

    embedding = _CapturingEmbedding()
    llm = _CapturingClient()
    planner = FakeRetrievalPlannerClient()
    app.state.embedding_client = embedding
    app.state.llm_client = llm
    app.state.retrieval_planner_client = planner

    response = await client.post(
        "/message",
        json={
            "anonymous_id": "pii-contact-only-user",
            "content": (
                "Мой телефон +79991234567, email user@example.com, Telegram @ivan_auto"
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("Спасибо, контакт сохранён.")
    assert llm.calls == []
    assert planner.calls == []
    assert embedding.calls == []

    async with app.state.db_session_maker() as db:
        assistant_message = await db.get(
            Message, UUID(response.json()["assistant_message_id"])
        )
        assert assistant_message is not None
        assert assistant_message.message_metadata == {
            "eval_token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 0,
                "complete": True,
                "components": {
                    "retrieval_planner": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "calls": 0,
                        "complete": True,
                    },
                    "agent": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "calls": 0,
                        "complete": True,
                    },
                },
            }
        }
        lead = await db.get(Lead, UUID(response.json()["lead_id"]))
        assert lead is not None
        assert lead.contact == {
            "phone": "+79991234567",
            "email": "user@example.com",
            "telegram": "@ivan_auto",
        }


async def test_qualification_patch_null_removes_saved_field(client) -> None:
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
                missing_fields=["budget", "purchase_type", "contact"],
            ),
            agent_decision(
                answer="Хорошо, убрал Camry из параметров подбора.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": None},
                missing_fields=["car_model", "budget", "purchase_type", "contact"],
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "qualification-patch-user",
            "content": "Хочу купить Toyota Camry",
        },
    )
    assert first.status_code == 200
    assert "car_model" not in first.json()["missing_fields"]

    second = await client.post(
        "/message",
        json={
            "anonymous_id": "qualification-patch-user",
            "session_id": first.json()["session_id"],
            "content": "Camry больше не хочу, другую пока не выбрал",
        },
    )

    assert second.status_code == 200
    assert "car_model" in second.json()["missing_fields"]

    lead = await client.get(f"/leads/{second.json()['lead_id']}")
    assert lead.status_code == 200
    assert "car_model" not in lead.json()["qualification"]


async def test_faq_during_qualification_preserves_data_and_can_resume(client) -> None:
    captured_states: list[str] = []
    captured_qualification: list[dict] = []
    captured_contexts: list[str] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            current_state,
            qualification_data,
            retrieved_context="",
            **kwargs,
        ):
            captured_states.append(current_state)
            captured_qualification.append(dict(qualification_data))
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                current_state=current_state,
                qualification_data=qualification_data,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": (
                    "Оценка автомобиля по программе trade-in бесплатна "
                    "и занимает 30–40 минут."
                ),
            }
        ],
    )
    assert knowledge.status_code == 201

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Toyota Camry"},
                missing_fields=["budget", "purchase_type", "contact"],
            ),
            agent_decision(
                answer="Оценка по trade-in бесплатна и занимает 30–40 минут.",
                missing_fields=["budget", "purchase_type", "contact"],
            ),
            agent_decision(
                answer="Хорошо. Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                missing_fields=["budget", "purchase_type", "contact"],
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "qualification-faq-user",
            "content": "Хочу купить Toyota Camry",
        },
    )
    session_id = first.json()["session_id"]

    faq = await client.post(
        "/message",
        json={
            "anonymous_id": "qualification-faq-user",
            "session_id": session_id,
            "content": "А какие условия trade-in?",
        },
    )

    resumed = await client.post(
        "/message",
        json={
            "anonymous_id": "qualification-faq-user",
            "session_id": session_id,
            "content": "Продолжим подбор",
        },
    )

    assert faq.json()["state"] == "QUALIFICATION"
    assert faq.json()["answer"].startswith("Оценка по trade-in")
    assert resumed.json()["state"] == "QUALIFICATION"
    assert captured_states == ["GREETING", "QUALIFICATION", "QUALIFICATION"]
    assert captured_qualification[1] == {"car_model": "Toyota Camry"}
    assert captured_qualification[2] == {"car_model": "Toyota Camry"}
    assert "[Источник: Программа Trade-in]" in captured_contexts[1]

    lead = await client.get(f"/leads/{faq.json()['lead_id']}")
    assert lead.status_code == 200
    assert lead.json()["qualification"] == {"car_model": "Toyota Camry"}

    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(session_id))
        assert row is not None
        assert row.expected_qualification_field == "budget"
        assert row.last_rag_source_title == "Программа Trade-in"


async def test_trade_in_follow_up_does_not_send_credit_context_to_llm(client) -> None:
    captured_contexts: list[str] = []

    class _TradeInEmbedding:
        async def embed(self, texts):
            embeddings = []
            for text in texts:
                normalized = text.casefold()
                if "trade" in normalized or "трей" in normalized:
                    vector = [1.0, 0.0]
                elif "кредит" in normalized:
                    vector = [0.0, 1.0]
                else:
                    vector = [0.6, 0.8]
                embeddings.append(vector + [0.0] * 1534)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _TradeInEmbedding()
    app.state.retrieval_planner_client = FakeRetrievalPlannerClient(
        [
            RetrievalPlan(
                mode=RetrievalMode.LAST_SOURCE,
                query="Условия программы Trade-in",
            ),
            RetrievalPlan(
                mode=RetrievalMode.LAST_SOURCE,
                query="Условия программы Trade-in",
            ),
            RetrievalPlan(
                mode=RetrievalMode.LAST_SOURCE,
                query="Подробности программы Trade-in",
            ),
        ]
    )
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": (
                    "Оценка автомобиля по программе trade-in бесплатна. "
                    "Для оценки нужны ПТС, СТС и паспорт собственника."
                ),
            },
            {
                "title": "Кредитование и финансирование",
                "content": (
                    "Автокредит оформляется через банки-партнёры. "
                    "Первоначальный взнос — от 10%."
                ),
            },
        ],
    )
    assert knowledge.status_code == 201

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Trade-in позволяет сдать автомобиль в зачёт нового.",
            ),
            agent_decision(
                answer="Оценка бесплатна; нужны ПТС, СТС и паспорт собственника.",
            ),
            agent_decision(
                answer="Оценка бесплатна и занимает 30–40 минут.",
            ),
            agent_decision(
                answer="Для оценки нужны ПТС или ЭПТС, СТС и паспорт.",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "trade-in-follow-up-user",
            "content": "Расскажи про треййдин",
        },
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "trade-in-follow-up-user",
            "session_id": first.json()["session_id"],
            "content": "А условия",
        },
    )
    third = await client.post(
        "/message",
        json={
            "anonymous_id": "trade-in-follow-up-user",
            "session_id": first.json()["session_id"],
            "content": "Условия",
        },
    )
    fourth = await client.post(
        "/message",
        json={
            "anonymous_id": "trade-in-follow-up-user",
            "session_id": first.json()["session_id"],
            "content": "Подробнее",
        },
    )

    assert second.status_code == 200
    assert "кредит" not in second.json()["answer"].casefold()
    assert third.json()["answer"].startswith("Оценка бесплатна")
    assert fourth.json()["answer"].startswith("Для оценки нужны")
    for context in captured_contexts[1:]:
        assert "[Источник: Программа Trade-in]" in context
        assert "Кредитование и финансирование" not in context


async def test_explicit_credit_topic_replaces_saved_trade_in_source(client) -> None:
    embedding_calls: list[list[str]] = []
    captured_contexts: list[str] = []

    class _TopicEmbedding:
        async def embed(self, texts):
            embedding_calls.append(list(texts))
            embeddings = []
            for text in texts:
                normalized = text.casefold()
                if "trade" in normalized or "трей" in normalized:
                    vector = [1.0, 0.0]
                elif "кредит" in normalized:
                    vector = [0.0, 1.0]
                else:
                    vector = [0.0, 0.0]
                embeddings.append(vector + [0.0] * 1534)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _TopicEmbedding()
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": "Trade-in включает бесплатную оценку автомобиля.",
            },
            {
                "title": "Кредитование и финансирование",
                "content": "Автокредит доступен через банки-партнёры.",
            },
        ],
    )
    assert knowledge.status_code == 201

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Trade-in — зачёт старого автомобиля.",
            ),
            agent_decision(
                answer="Кредит оформляется через банки-партнёры.",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={"anonymous_id": "topic-switch-user", "content": "Trade-in"},
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "topic-switch-user",
            "session_id": first.json()["session_id"],
            "content": "Кредит",
        },
    )

    assert second.status_code == 200
    assert embedding_calls[-1] == ["Кредит"]
    assert "[Источник: Кредитование и финансирование]" in captured_contexts[1]
    assert "Программа Trade-in" not in captured_contexts[1]

    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(first.json()["session_id"]))
        assert row is not None
        assert row.last_rag_source_title == "Кредитование и финансирование"


async def test_low_relevance_keeps_previous_confirmed_source(client) -> None:
    captured_contexts: list[str] = []

    class _Embedding:
        async def embed(self, texts):
            embeddings = []
            for text in texts:
                normalized = text.casefold()
                if "trade" in normalized:
                    vector = [1.0, 0.0, 0.0]
                else:
                    vector = [0.0, 0.0, 1.0]
                embeddings.append(vector + [0.0] * 1533)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _Embedding()
    app.state.retrieval_planner_client = FakeRetrievalPlannerClient(
        [RetrievalPlan.none()]
    )
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": "Trade-in включает бесплатную оценку автомобиля.",
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Оценка бесплатна.",
            ),
            agent_decision(
                answer="Точной информации нет.",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={"anonymous_id": "low-score-source-user", "content": "Trade-in"},
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "low-score-source-user",
            "session_id": first.json()["session_id"],
            "content": "Как приготовить борщ?",
        },
    )

    assert second.status_code == 200
    assert captured_contexts[1] == ""
    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(first.json()["session_id"]))
        assert row is not None
        assert row.last_rag_source_title == "Программа Trade-in"


async def test_rag_source_is_not_shared_between_users_or_channels(client) -> None:
    captured_contexts: list[str] = []

    class _Embedding:
        async def embed(self, texts):
            embeddings = []
            for text in texts:
                vector = [1.0, 0.0] if "trade" in text.casefold() else [0.0, 1.0]
                embeddings.append(vector + [0.0] * 1534)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _Embedding()
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Программа Trade-in",
                "content": "Trade-in включает бесплатную оценку автомобиля.",
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Оценка бесплатна.",
            ),
            agent_decision(
                answer="Нужно уточнить тему.",
            ),
            agent_decision(
                answer="Нужно уточнить тему.",
            ),
        ]
    )

    await client.post(
        "/message",
        json={
            "anonymous_id": "isolated-source",
            "channel": "website",
            "content": "Trade-in",
        },
    )
    await client.post(
        "/message",
        json={
            "anonymous_id": "another-user",
            "channel": "website",
            "content": "А условия какие?",
        },
    )
    await client.post(
        "/message",
        json={
            "anonymous_id": "isolated-source",
            "channel": "telegram",
            "content": "А условия какие?",
        },
    )

    assert "[Источник: Программа Trade-in]" in captured_contexts[0]
    assert captured_contexts[1:] == ["", ""]


async def test_credit_offer_confirmation_retrieves_credit_and_keeps_original_yes(
    client,
) -> None:
    captured_user_messages: list[str] = []
    captured_contexts: list[str] = []

    class _CreditEmbedding:
        async def embed(self, texts):
            embeddings = []
            for text in texts:
                vector = [0.0] * 1536
                vector[0 if "кредит" in text.casefold() else 1] = 1.0
                embeddings.append(vector)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            user_message,
            retrieved_context="",
            **kwargs,
        ):
            captured_user_messages.append(user_message)
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                user_message=user_message,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _CreditEmbedding()
    app.state.retrieval_planner_client = FakeRetrievalPlannerClient(
        [
            RetrievalPlan(
                mode=RetrievalMode.LAST_SOURCE,
                query="Условия автокредитования",
            )
        ]
    )
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Кредитование и финансирование",
                "content": (
                    "Автокредит оформляется через банки-партнёры на срок "
                    "от 1 до 7 лет с первоначальным взносом от 10%."
                ),
            }
        ],
    )
    assert knowledge.status_code == 201

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer=(
                    "Автокредит — это банковское финансирование покупки. "
                    "Могу рассказать подробнее об условиях автокредита."
                ),
            ),
            agent_decision(
                answer="Срок — от 1 до 7 лет, первоначальный взнос — от 10%.",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={
            "anonymous_id": "credit-confirmation-user",
            "content": "Кредит что такое?",
        },
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "credit-confirmation-user",
            "session_id": first.json()["session_id"],
            "content": "Да",
        },
    )

    assert second.status_code == 200
    assert captured_user_messages == ["Кредит что такое?", "Да"]
    assert "[Источник: Кредитование и финансирование]" in captured_contexts[1]
    assert "бюджет" not in second.json()["answer"].casefold()
    assert second.json()["state"] == "FAQ"

    session_maker = app.state.db_session_maker
    async with session_maker() as db:
        row = await db.get(DialogSession, UUID(first.json()["session_id"]))
        assert row is not None
        assert row.last_rag_source_title == "Кредитование и финансирование"


async def test_credit_word_cannot_start_qualification_from_faq(client) -> None:
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Кредитование и финансирование",
                "content": "Автокредит оформляется через банки-партнёры.",
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.llm_client = FakeAg2AgentClient(
        responses=[
            agent_decision(
                answer="Чем могу помочь?",
            ),
            agent_decision(
                answer="Автокредит оформляется через банки-партнёры.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"purchase_type": "кредит"},
                missing_fields=["car_model", "budget", "contact"],
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={"anonymous_id": "credit-word-guard", "content": "Здравствуйте"},
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "credit-word-guard",
            "session_id": first.json()["session_id"],
            "content": "Кредит",
        },
    )

    assert second.status_code == 200
    assert second.json()["state"] == "FAQ"
    lead = await client.get(f"/leads/{second.json()['lead_id']}")
    assert lead.status_code == 200
    assert lead.json()["qualification"] == {}


async def test_ambiguous_model_and_service_requests_set_confirmation_pending(
    client,
) -> None:
    captured_contexts: list[str] = []

    class _TopicEmbedding:
        async def embed(self, texts):
            embeddings = []
            for text in texts:
                normalized = text.casefold()
                vector = [0.0, 1.0] if "кредит" in normalized else [1.0, 0.0]
                embeddings.append(vector + [0.0] * 1534)
            return embeddings

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(self, *args, retrieved_context="", **kwargs):
            captured_contexts.append(retrieved_context)
            return await super().decide(
                *args,
                retrieved_context=retrieved_context,
                **kwargs,
            )

    app.state.embedding_client = _TopicEmbedding()
    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Автомобили Skoda",
                "content": "Skoda Kodiaq — семейный кроссовер с полным приводом.",
            },
            {
                "title": "Кредитование",
                "content": "Автокредит оформляется через банки-партнёры.",
            },
        ],
    )
    assert knowledge.status_code == 201
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer=(
                    "Skoda Kodiaq — семейный кроссовер с полным приводом. "
                    "Хотите, чтобы я помог подобрать Skoda для покупки?"
                ),
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
            agent_decision(
                answer=(
                    "Skoda Kodiaq — семейный кроссовер с полным приводом. "
                    "Хотите, чтобы я помог подобрать Skoda для покупки?"
                ),
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
            agent_decision(
                answer=(
                    "Кредит доступен через банки-партнёры. "
                    "Хотите, чтобы я помог оформить покупку в кредит?"
                ),
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
        ]
    )

    for index, message in enumerate(("Skoda", "хочу Skoda", "нужен кредит")):
        response = await client.post(
            "/message",
            json={
                "anonymous_id": f"ambiguous-intent-{index}",
                "content": message,
            },
        )

        assert response.status_code == 200
        assert response.json()["state"] == "FAQ"
        assert response.json()["answer"].count("?") == 1
        lead = await client.get(f"/leads/{response.json()['lead_id']}")
        assert lead.json()["qualification"] == {}
        async with app.state.db_session_maker() as db:
            row = await db.get(DialogSession, UUID(response.json()["session_id"]))
            assert row is not None
            assert row.lead_intent_confirmation_pending is True

    assert all("[Источник:" in context for context in captured_contexts)


async def test_yes_after_purchase_confirmation_starts_qualification_and_restores_topic(
    client,
) -> None:
    captured_pending: list[bool] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            lead_intent_confirmation_pending=False,
            **kwargs,
        ):
            captured_pending.append(lead_intent_confirmation_pending)
            return await super().decide(
                *args,
                lead_intent_confirmation_pending=(lead_intent_confirmation_pending),
                **kwargs,
            )

    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Автомобили Skoda",
                "content": "Skoda Kodiaq — семейный кроссовер.",
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.retrieval_planner_client = FakeRetrievalPlannerClient(
        [RetrievalPlan.none()]
    )
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer=(
                    "Skoda Kodiaq — семейный кроссовер. "
                    "Хотите, чтобы я помог подобрать Skoda для покупки?"
                ),
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
            agent_decision(
                answer="Отлично. Какой бюджет вы рассматриваете?",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Skoda"},
                missing_fields=["budget", "purchase_type", "contact"],
                lead_intent_status=LeadIntentStatus.CONFIRMED,
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={"anonymous_id": "pending-confirmation-user", "content": "Skoda"},
    )
    second = await client.post(
        "/message",
        json={
            "anonymous_id": "pending-confirmation-user",
            "session_id": first.json()["session_id"],
            "content": "Да",
        },
    )

    assert first.json()["state"] == "FAQ"
    assert second.json()["state"] == "QUALIFICATION"
    assert captured_pending == [False, True]
    lead = await client.get(f"/leads/{second.json()['lead_id']}")
    assert lead.json()["qualification"] == {"car_model": "Skoda"}
    async with app.state.db_session_maker() as db:
        row = await db.get(DialogSession, UUID(first.json()["session_id"]))
        assert row is not None
        assert row.lead_intent_confirmation_pending is False


@pytest.mark.parametrize(
    ("non_confirmation", "status"),
    [
        ("Нет, просто смотрю", LeadIntentStatus.DECLINED),
        ("А какие часы работы?", LeadIntentStatus.ABSENT),
    ],
)
async def test_nonconfirming_turn_clears_pending_and_later_yes_stays_faq(
    client,
    non_confirmation: str,
    status: LeadIntentStatus,
) -> None:
    captured_pending: list[bool] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            lead_intent_confirmation_pending=False,
            **kwargs,
        ):
            captured_pending.append(lead_intent_confirmation_pending)
            return await super().decide(
                *args,
                lead_intent_confirmation_pending=(lead_intent_confirmation_pending),
                **kwargs,
            )

    knowledge = await client.post(
        "/knowledge/documents",
        json=[
            {
                "title": "Автомобили Skoda",
                "content": "Skoda Kodiaq — семейный кроссовер.",
            }
        ],
    )
    assert knowledge.status_code == 201
    app.state.retrieval_planner_client = FakeRetrievalPlannerClient(
        [RetrievalPlan.none(), RetrievalPlan.none()]
    )
    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Хотите, чтобы я помог подобрать Skoda для покупки?",
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
            agent_decision(
                answer="Хорошо, обращайтесь, если появятся вопросы.",
                lead_intent_status=status,
            ),
            agent_decision(
                answer="Что именно вас интересует?",
            ),
        ]
    )

    first = await client.post(
        "/message",
        json={"anonymous_id": "declined-intent-user", "content": "Skoda"},
    )
    await client.post(
        "/message",
        json={
            "anonymous_id": "declined-intent-user",
            "session_id": first.json()["session_id"],
            "content": non_confirmation,
        },
    )
    late_yes = await client.post(
        "/message",
        json={
            "anonymous_id": "declined-intent-user",
            "session_id": first.json()["session_id"],
            "content": "Да",
        },
    )

    assert late_yes.json()["state"] == "FAQ"
    assert captured_pending == [False, True, False]
    lead = await client.get(f"/leads/{late_yes.json()['lead_id']}")
    assert lead.json()["qualification"] == {}


async def test_rejected_qualification_start_gets_one_corrective_retry(client) -> None:
    correction_flags: list[bool] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            force_lead_intent_confirmation=False,
            **kwargs,
        ):
            correction_flags.append(force_lead_intent_confirmation)
            return await super().decide(
                *args,
                force_lead_intent_confirmation=force_lead_intent_confirmation,
                **kwargs,
            )

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Начнём подбор.",
                intent="lead_request",
                next_state=DialogState.QUALIFICATION,
                qualification_patch={"car_model": "Skoda"},
            ),
            agent_decision(
                answer="Хотите, чтобы я помог подобрать Skoda для покупки?",
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
        ]
    )

    response = await client.post(
        "/message",
        json={"anonymous_id": "corrected-intent-user", "content": "Skoda"},
    )

    assert response.json()["state"] == "FAQ"
    assert correction_flags == [False, True]
    lead = await client.get(f"/leads/{response.json()['lead_id']}")
    assert lead.json()["qualification"] == {}


async def test_repeated_bad_qualification_uses_safe_fallback(client) -> None:
    invalid = agent_decision(
        answer="Начнём подбор.",
        intent="lead_request",
        next_state=DialogState.QUALIFICATION,
        qualification_patch={"car_model": "Skoda"},
    )
    app.state.llm_client = FakeAg2AgentClient(responses=[invalid, invalid])

    response = await client.post(
        "/message",
        json={"anonymous_id": "fallback-intent-user", "content": "Skoda"},
    )

    assert response.json()["state"] == "FAQ"
    assert response.json()["answer"] == (
        "Уточните, пожалуйста: хотите, чтобы я помог подобрать автомобиль для покупки?"
    )
    lead = await client.get(f"/leads/{response.json()['lead_id']}")
    assert lead.json()["qualification"] == {}


async def test_intent_confirmation_pending_is_isolated_by_user_and_channel(
    client,
) -> None:
    captured_pending: list[bool] = []

    class _CapturingClient(FakeAg2AgentClient):
        async def decide(
            self,
            *args,
            lead_intent_confirmation_pending=False,
            **kwargs,
        ):
            captured_pending.append(lead_intent_confirmation_pending)
            return await super().decide(
                *args,
                lead_intent_confirmation_pending=(lead_intent_confirmation_pending),
                **kwargs,
            )

    app.state.llm_client = _CapturingClient(
        responses=[
            agent_decision(
                answer="Хотите, чтобы я помог подобрать Skoda для покупки?",
                lead_intent_status=LeadIntentStatus.NEEDS_CONFIRMATION,
            ),
            agent_decision(
                answer="Что именно вас интересует?",
            ),
            agent_decision(
                answer="Что именно вас интересует?",
            ),
        ]
    )

    owner = await client.post(
        "/message",
        json={
            "anonymous_id": "pending-owner",
            "channel": "website",
            "content": "Skoda",
        },
    )
    another_user = await client.post(
        "/message",
        json={
            "anonymous_id": "pending-other",
            "channel": "website",
            "content": "Да",
        },
    )
    another_channel = await client.post(
        "/message",
        json={
            "anonymous_id": "pending-owner",
            "channel": "telegram",
            "content": "Да",
        },
    )

    assert captured_pending == [False, False, False]
    assert another_user.json()["state"] == "FAQ"
    assert another_channel.json()["state"] == "FAQ"
    async with app.state.db_session_maker() as db:
        owner_row = await db.get(DialogSession, UUID(owner.json()["session_id"]))
        other_user_row = await db.get(
            DialogSession,
            UUID(another_user.json()["session_id"]),
        )
        other_channel_row = await db.get(
            DialogSession,
            UUID(another_channel.json()["session_id"]),
        )
        assert owner_row is not None
        assert other_user_row is not None
        assert other_channel_row is not None
        assert owner_row.lead_intent_confirmation_pending is True
        assert other_user_row.lead_intent_confirmation_pending is False
        assert other_channel_row.lead_intent_confirmation_pending is False
