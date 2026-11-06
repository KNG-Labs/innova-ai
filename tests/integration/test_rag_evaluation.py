import os
import json

import pytest
from deepeval.dataset import Golden

from app.client.ag2_agent_client import FakeAg2AgentClient
from evals import run
from tests.factories import agent_decision

pytestmark = pytest.mark.integration


async def test_collects_actual_context_and_final_answer(client, monkeypatch, tmp_path):
    original_init = run.init_app_state
    original_retrieve = run.RecordingRetrieval.retrieve
    queries = []

    async def initialize(app):
        await original_init(app)
        app.state.llm_client = FakeAg2AgentClient(
            responses=[
                agent_decision(answer="Салон открыт до 21:00. Телефон [KB_CONTACT_1].")
            ]
        )

    async def retrieve(self, query):
        queries.append(query)
        return await original_retrieve(self, query)

    monkeypatch.setattr(run, "init_app_state", initialize)
    monkeypatch.setattr(run.RecordingRetrieval, "retrieve", retrieve)
    monkeypatch.setenv("RAG_MIN_SCORE", "0")
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "title": "Время работы",
                    "content": "Салон открыт до 21:00. Телефон +79997778801.",
                }
            ]
        )
    )
    cases = await run.collect_cases(
        [Golden(name="hours", input="До скольких работает салон?")],
        os.environ["TEST_DATABASE_URL"],
        corpus,
    )
    [case] = cases
    assert queries == ["До скольких работает салон?"]
    assert case.actual_output == "Салон открыт до 21:00. Телефон [PHONE_1]."
    assert case.retrieval_context == [
        "[Источник: Время работы]\nСалон открыт до 21:00. Телефон [PHONE_1]."
    ]
