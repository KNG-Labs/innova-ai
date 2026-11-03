import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import tracing
from app.client.ag2_agent_client import Ag2AgentClient
from app.client.queue_client import CeleryQueueClient
from app.privacy import PiiAnalysisError, PiiSanitizer

pytestmark = pytest.mark.unit


@pytest.fixture
def capture(monkeypatch):
    from langfuse import openai as integration

    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    client = Langfuse(
        public_key=f"pk-lf-offline-{uuid4()}",
        secret_key="sk-lf-offline-test",
        tracing_enabled=True,
        tracer_provider=provider,
        span_exporter=exporter,
        mask_otel_spans=tracing.mask_spans,
        environment="test",
    )
    monkeypatch.setattr(tracing, "_client", client)
    monkeypatch.setattr(integration, "get_client", lambda **kwargs: client)

    def spans():
        client.flush()
        return exporter.get_finished_spans()

    yield spans
    client.shutdown()
    provider.shutdown()


@pytest.mark.parametrize("enabled", ["false", "0", "true"])
def test_unconfigured_tracing_has_no_client(monkeypatch, enabled):
    constructor = Mock()
    monkeypatch.setattr(tracing, "Langfuse", constructor)
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", enabled)
    assert tracing.init_tracing() is None
    constructor.assert_not_called()


async def test_exports_masked_payloads_without_implicit_capture(capture):
    @tracing.traced("privacy-check")
    async def run(secret):
        tracing.update_observation(
            input="Camry +79991234567 user@example.com @example_user",
            output={"answer": "Пишите user@example.com"},
            metadata={"nested": ["+7 (999) 123-45-67"]},
        )
        return secret

    assert await run("secret-argument") == "secret-argument"
    [span] = capture()
    payload = json.dumps(dict(span.attributes))
    for raw in ("+79991234567", "user@example.com", "@example_user", "secret-argument"):
        assert raw not in payload
    assert "[PHONE_1]" in payload
    assert "[EMAIL_1]" in payload
    assert "[TELEGRAM_1]" in payload


async def test_analysis_failure_drops_telemetry_and_preserves_result(
    capture, monkeypatch
):
    @tracing.traced("blocked-export")
    async def run():
        tracing.update_observation(input="user@example.com")
        return "ok"

    def fail(self, text):
        raise PiiAnalysisError("synthetic failure")

    monkeypatch.setattr(PiiSanitizer, "find_entities", fail)
    assert await run() == "ok"
    assert capture() == ()


async def test_error_text_does_not_leak_through_otel_events(capture):
    @tracing.traced("failing-operation")
    async def run():
        raise ValueError("user@example.com and private credentials")

    with pytest.raises(ValueError, match="user@example.com"):
        await run()
    [span] = capture()
    assert not span.events
    assert span.attributes["langfuse.observation.level"] == "ERROR"
    assert span.attributes["langfuse.observation.status_message"] == "ValueError"
    assert "private credentials" not in str(span.attributes)


async def test_concurrent_ag2_generations_keep_parents_and_per_call_usage(
    capture, monkeypatch
):
    def send(self, request, **kwargs):
        payload = json.loads(request.content)
        first = "first" in payload["messages"][-1]["content"]
        tokens = 11 if first else 22
        decision = {
            "answer": "Пишите user@example.com",
            "intent": "general",
            "next_state": "FAQ",
            "qualification_patch": {},
            "missing_fields": [],
            "lead_ready": False,
        }
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(decision),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": tokens,
                    "completion_tokens": 3,
                    "total_tokens": tokens + 3,
                },
            },
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    agent = Ag2AgentClient(
        model="test-model", api_key="test-key", base_url="https://provider.invalid/v1"
    )

    @tracing.traced("test-turn", as_type="agent")
    async def turn(message):
        tracing.update_observation(input=message)
        return await agent.decide(
            user_message=message, history=[], current_state="FAQ", qualification_data={}
        )

    decisions = await asyncio.gather(turn("first"), turn("second"))
    assert all(d.next_state.value == "FAQ" for d in decisions)
    spans = capture()
    roots = {s.context.trace_id: s for s in spans if s.name == "test-turn"}
    generations = [
        s
        for s in spans
        if s.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(roots) == len(generations) == 2
    for generation in generations:
        root = roots[generation.context.trace_id]
        [parent] = [s for s in spans if s.context.span_id == generation.parent.span_id]
        assert parent.name == "decide-lead"
        assert parent.parent.span_id == root.context.span_id
        usage = json.loads(generation.attributes["langfuse.observation.usage_details"])
        assert usage["prompt_tokens"] == (
            11 if root.attributes["langfuse.observation.input"] == "first" else 22
        )
        assert generation.attributes["langfuse.observation.model.name"] == "test-model"
        assert (
            "user@example.com"
            not in generation.attributes["langfuse.observation.output"]
        )


@pytest.mark.parametrize("reply", [None, "not-json"])
async def test_parse_fallback_is_visible(capture, reply):
    class Agent:
        def generate_reply(self, **kwargs):
            return reply

    client = object.__new__(Ag2AgentClient)
    client._agent = Agent()
    decision = await client.decide(
        user_message="Camry", history=[], current_state="FAQ", qualification_data={}
    )
    assert decision.intent == "unknown"
    [span] = capture()
    assert span.attributes["langfuse.observation.level"] == "WARNING"
    assert json.loads(span.attributes["langfuse.observation.metadata.fallback"]) is True


@pytest.fixture
def worker_delivery(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "memory://")
    from app.worker import lead_delivery

    engine = Mock(dispose=AsyncMock())
    monkeypatch.setattr(lead_delivery, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        lead_delivery,
        "create_session_maker",
        lambda engine: Mock(return_value=AsyncMock()),
    )
    service = Mock(
        deliver=AsyncMock(
            return_value=SimpleNamespace(
                user_id=uuid4(),
                session_id=uuid4(),
                status="delivered",
            )
        )
    )
    monkeypatch.setattr(
        lead_delivery, "LeadDeliveryService", Mock(return_value=service)
    )
    return lead_delivery, service


async def test_worker_continues_enqueue_trace(capture, worker_delivery):
    worker, service = worker_delivery
    app = Mock()
    lead_id = uuid4()
    await CeleryQueueClient(app).enqueue_lead_delivery(lead_id, "fake")
    headers = app.send_task.call_args.kwargs["headers"]
    assert set(headers) == {"traceparent"}

    result = await asyncio.to_thread(
        worker.deliver_lead.apply, args=[str(lead_id)], headers=headers
    )
    assert result.successful()
    service.deliver.assert_awaited_once_with(lead_id, raise_on_delivery_error=True)
    spans = capture()
    [enqueue] = [s for s in spans if s.name == "enqueue-lead"]
    [delivery] = [s for s in spans if s.name == "process-lead-delivery"]
    assert delivery.context.trace_id == enqueue.context.trace_id
    assert delivery.parent.span_id == enqueue.context.span_id
    assert json.loads(delivery.attributes["langfuse.observation.output"]) == {
        "status": "delivered"
    }
    assert (
        json.loads(delivery.attributes["langfuse.observation.metadata.task_id"])
        == result.id
    )


@pytest.mark.parametrize(
    "headers", [{}, {"traceparent": "invalid"}, {"traceparent": 123}]
)
async def test_worker_accepts_untraced_and_invalid_headers(
    capture, worker_delivery, headers
):
    worker, service = worker_delivery
    result = await asyncio.to_thread(
        worker.deliver_lead.apply, args=[str(uuid4())], headers=headers
    )
    assert result.successful()
    [span] = capture()
    assert span.name == "process-lead-delivery"
    assert span.parent is None


async def test_worker_retries_keep_trace_and_redact_errors(capture, worker_delivery):
    worker, service = worker_delivery
    service.deliver.side_effect = httpx.ConnectError("private user@example.com")
    app = Mock()
    lead_id = uuid4()
    await CeleryQueueClient(app).enqueue_lead_delivery(lead_id, "fake")
    result = await asyncio.to_thread(
        worker.deliver_lead.apply,
        args=[str(lead_id)],
        headers=app.send_task.call_args.kwargs["headers"],
    )
    assert result.failed()
    spans = capture()
    [enqueue] = [s for s in spans if s.name == "enqueue-lead"]
    attempts = [s for s in spans if s.name == "process-lead-delivery"]
    assert len(attempts) == 4
    assert {
        json.loads(s.attributes["langfuse.observation.metadata.retry"])
        for s in attempts
    } == {0, 1, 2, 3}
    for attempt in attempts:
        assert attempt.context.trace_id == enqueue.context.trace_id
        assert attempt.parent.span_id == enqueue.context.span_id
        assert attempt.attributes["langfuse.observation.level"] == "ERROR"
        assert not attempt.events
        assert "user@example.com" not in str(attempt.attributes)


def test_flush_failure_does_not_fail_task(monkeypatch):
    monkeypatch.setattr(tracing, "_client", Mock(flush=Mock(side_effect=RuntimeError)))
    tracing.flush_tracing()
