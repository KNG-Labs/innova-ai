from types import SimpleNamespace

import pytest

from app.client.ag2_agent_client import Ag2AgentClient
from app.client.embedding_client import OpenRouterEmbeddingClient
from app.client.retrieval_planner_client import (
    Ag2RetrievalPlannerClient,
    RetrievalPlan,
)
from app.privacy import PiiAnalysisError, PiiDetectedError, PiiSanitizer
from evals.judge import OpenRouterJudge

pytestmark = pytest.mark.unit


class _CapturingAgent:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[dict]] = []

    async def a_generate_reply(self, *, messages):
        self.calls.append(messages)
        return self.reply


class _CapturingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0])])


class _CapturingJudgeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
        )


class _CapturingAsyncJudgeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
        )


@pytest.mark.asyncio
async def test_llm_guard_blocks_raw_pii_before_agent_call() -> None:
    agent = _CapturingAgent("{}")
    client = object.__new__(Ag2AgentClient)
    client._agent = agent

    decision = await client.decide(
        user_message="Мой телефон +79991234567",
        history=[],
        current_state="GREETING",
        qualification_data={},
    )

    assert agent.calls == []
    assert decision.intent == "unknown"


@pytest.mark.asyncio
async def test_llm_captured_payload_contains_tokens_not_original_values() -> None:
    raw = "Хочу Camry, телефон +79991234567, email user@example.com"
    safe = PiiSanitizer().sanitize_text(raw).text
    agent = _CapturingAgent(
        '{"answer":"Хорошо","intent":"general","next_state":"FAQ",'
        '"qualification_patch":{},"missing_fields":[],"lead_ready":false}'
    )
    client = object.__new__(Ag2AgentClient)
    client._agent = agent

    await client.decide(
        user_message=safe,
        history=[{"role": "user", "content": safe}],
        current_state="GREETING",
        qualification_data={},
    )

    payload = str(agent.calls)
    assert "+79991234567" not in payload
    assert "user@example.com" not in payload
    assert "[PHONE_1]" in payload
    assert "[EMAIL_1]" in payload


@pytest.mark.asyncio
async def test_planner_guard_blocks_raw_pii_before_agent_call() -> None:
    agent = _CapturingAgent('{"mode":"none","query":""}')
    client = object.__new__(Ag2RetrievalPlannerClient)
    client._agent = agent

    result = await client.plan(
        current_message="Условия кредита, телефон +79991234567",
        last_source_title="Кредит",
        history=[],
    )

    assert agent.calls == []
    assert result == RetrievalPlan.none()


@pytest.mark.asyncio
async def test_planner_captured_payload_contains_tokens_not_original_values() -> None:
    raw = "Кредит, телефон +79991234567, email user@example.com"
    safe = PiiSanitizer().sanitize_text(raw).text
    agent = _CapturingAgent('{"mode":"current","query":"Условия кредита"}')
    client = object.__new__(Ag2RetrievalPlannerClient)
    client._agent = agent

    await client.plan(
        current_message=safe,
        last_source_title="Кредит",
        history=[{"role": "user", "content": safe}],
    )

    payload = repr(agent.calls)
    assert "+79991234567" not in payload
    assert "user@example.com" not in payload
    assert "[PHONE_1]" in payload
    assert "[EMAIL_1]" in payload


@pytest.mark.asyncio
async def test_embedding_guard_blocks_raw_pii_before_http_call() -> None:
    embeddings = _CapturingEmbeddings()
    client = object.__new__(OpenRouterEmbeddingClient)
    client._client = SimpleNamespace(embeddings=embeddings)
    client._model = "test-model"

    with pytest.raises(PiiDetectedError):
        await client.embed(["Телефон +79991234567"])

    assert embeddings.calls == []


@pytest.mark.asyncio
async def test_embedding_captured_payload_contains_token_not_phone() -> None:
    embeddings = _CapturingEmbeddings()
    client = object.__new__(OpenRouterEmbeddingClient)
    client._client = SimpleNamespace(embeddings=embeddings)
    client._model = "test-model"
    safe = PiiSanitizer().sanitize_text("Camry +79991234567").text

    await client.embed([safe])

    assert embeddings.calls == [{"model": "test-model", "input": ["Camry [PHONE_1]"]}]


@pytest.mark.asyncio
async def test_embedding_analyzer_failure_is_fail_closed(monkeypatch) -> None:
    embeddings = _CapturingEmbeddings()
    client = object.__new__(OpenRouterEmbeddingClient)
    client._client = SimpleNamespace(embeddings=embeddings)
    client._model = "test-model"

    def _fail_analysis(self, text):
        raise PiiAnalysisError("synthetic analyzer failure")

    monkeypatch.setattr(PiiSanitizer, "find_entities", _fail_analysis)

    with pytest.raises(PiiAnalysisError):
        await client.embed(["Безопасный на вид текст"])

    assert embeddings.calls == []


def test_eval_judge_pseudonymizes_pii_and_preserves_value_identity() -> None:
    completions = _CapturingJudgeCompletions()
    judge = OpenRouterJudge(model="test-judge", api_key="test-key")
    judge._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    judge.generate(
        "Ответ: +7 (999) 777-88-01; ожидается +79997778801; "
        "другой номер +1 415 555 2671"
    )

    payload = repr(completions.calls)
    assert "+7 (999) 777-88-01" not in payload
    assert "+79997778801" not in payload
    assert "+1 415 555 2671" not in payload
    assert payload.count("[PHONE_1]") == 2
    assert payload.count("[PHONE_2]") == 1


@pytest.mark.asyncio
async def test_eval_judge_async_pseudonymizes_pii() -> None:
    completions = _CapturingAsyncJudgeCompletions()
    judge = OpenRouterJudge(model="test-judge", api_key="test-key")
    judge._async_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    await judge.a_generate("Телефон дилера: +7 (999) 777-88-01")

    payload = repr(completions.calls)
    assert "+7 (999) 777-88-01" not in payload
    assert "[PHONE_1]" in payload
