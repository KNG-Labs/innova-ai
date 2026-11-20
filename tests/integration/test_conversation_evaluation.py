import json
import os

import pytest

from app.client.ag2_agent_client import FakeAg2AgentClient
from evals import conversations

pytestmark = pytest.mark.integration


async def test_followup_uses_history_and_its_own_retrieval(
    client, monkeypatch, tmp_path
):
    histories = []
    original_decide = FakeAg2AgentClient.decide

    async def record(self, **kwargs):
        histories.append(kwargs["history"].copy())
        return await original_decide(self, **kwargs)

    monkeypatch.setattr(FakeAg2AgentClient, "decide", record)
    monkeypatch.setenv("RAG_MIN_SCORE", "0")
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "hours",
                    "split": "test",
                    "category": "followup",
                    "expected_outcome": "Клиент получает часы работы и сообщает контакт.",
                    "expected_queue_jobs": 0,
                    "turns": [
                        {
                            "input": "До скольких работает салон?",
                            "expected_output": "До 21:00.",
                        },
                        {"input": "+79997778801", "expected_output": "Контакт принят."},
                    ],
                }
            ]
        )
    )
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps([{"title": "Салон", "content": "Открыт до 21:00."}]))
    scenarios = conversations.load_scenarios(path, "test", 1)
    [case] = await conversations.collect_conversations(
        scenarios, os.environ["TEST_DATABASE_URL"], corpus
    )
    assert [turn.role for turn in case.turns] == ["user", "assistant"] * 2
    assert any("скольких" in str(message) for message in histories[-1])
    assert case.turns[1].retrieval_context
    assert not case.turns[3].retrieval_context
    assert "+79997778801" not in case.model_dump_json()
