"""Replay fixed conversations and score the resulting transcripts with Jev."""

import json
import os
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig
from deepeval.metrics import (
    ConversationalJevEval,
    KnowledgeRetentionMetric,
    TurnFaithfulnessMetric,
    TurnRelevancyMetric,
)
from deepeval.metrics.jev_eval.questions import Noul
from deepeval.test_case import ConversationalTestCase, MultiTurnParams, Turn
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.client.queue_client import FakeQueueClient
from app.privacy import PiiSanitizer
from app.repository.lead_repository import LeadRepository
from app.schemas.agent_schema import AgentMessageRequest, DialogState
from app.service.agent_service import AgentService
from app.service.knowledge_retrieval_service import format_chunks_for_prompt
from evals.run import (
    THRESHOLD,
    RecordingRetrieval,
    ReportedTypeSafeModel,
    eval_app,
    write_judge_manifest,
)

DATASET = Path("evals/datasets/conversations.json")
FACTUAL_CATEGORIES = {"rag_follow_up", "topic_switch", "unanswerable_detail"}
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ScenarioTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: NonBlank = Field(max_length=4000)
    expected_output: NonBlank | None = None
    expected_state: DialogState | None = None
    expected_missing_fields: list[NonBlank] | None = None
    expected_lead_status: Literal["draft", "ready"] | None = None
    expect_retrieval: bool | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]+$")]
    split: Literal["calibration", "test", "regression"]
    category: NonBlank
    expected_outcome: NonBlank
    turns: list[ScenarioTurn] = Field(min_length=2)
    expected_queue_jobs: int | None = Field(default=None, ge=0)


def load_scenarios(path: Path, split: str, limit: int) -> list[Scenario]:
    scenarios = TypeAdapter(list[Scenario]).validate_json(path.read_bytes())
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError("Conversation scenario names must be unique")
    selected = [scenario for scenario in scenarios if scenario.split == split]
    if not selected:
        raise ValueError(f"No conversation scenarios match split {split}")
    return selected[:limit]


def safe_conversation(case: ConversationalTestCase) -> ConversationalTestCase:
    payload = PiiSanitizer().sanitize_value(case.model_dump(mode="json"))
    PiiSanitizer.ensure_safe(payload)
    return ConversationalTestCase.model_validate(payload)


def load_conversations(path: Path) -> list[ConversationalTestCase]:
    return [
        safe_conversation(case)
        for case in TypeAdapter(list[ConversationalTestCase]).validate_json(
            path.read_bytes()
        )
    ]


async def collect_conversations(
    scenarios: list[Scenario], database_url: str, corpus: Path
) -> list[ConversationalTestCase]:
    cases = []
    async with eval_app(database_url, corpus) as app:
        for scenario in scenarios:
            anonymous_id = f"eval-{uuid4().hex}"
            session_id = None
            queue = FakeQueueClient()
            turns = []
            for index, turn in enumerate(scenario.turns, start=1):
                request = AgentMessageRequest(
                    anonymous_id=anonymous_id, session_id=session_id, content=turn.input
                )
                async with app.state.db_session_maker() as db:
                    retrieval = RecordingRetrieval(
                        db,
                        app.state.embedding_client,
                        top_k=int(os.getenv("RAG_TOP_K", "5")),
                        min_score=float(os.getenv("RAG_MIN_SCORE", "0.2")),
                    )
                    service = AgentService(
                        db_session=db,
                        llm_client=app.state.llm_client,
                        queue_client=queue,
                        delivery_provider="fake",
                        retrieval=retrieval,
                    )
                    try:
                        response = await service.handle_message(request)
                    except Exception as exc:
                        exc.add_note(f"Conversation {scenario.name}, turn {index}")
                        raise
                    lead = await LeadRepository(db).get_by_session_id(
                        response.session_id
                    )
                    lead_status = lead.status if lead is not None else None
                turns.extend(
                    [
                        Turn(role="user", content=request.content),
                        Turn(
                            role="assistant",
                            content=response.answer,
                            retrieval_context=[
                                format_chunks_for_prompt((chunk,))
                                for chunk in retrieval.chunks
                            ],
                            metadata={
                                **turn.model_dump(
                                    mode="json", exclude={"input"}, exclude_none=True
                                ),
                                "state": response.state.value,
                                "missing_fields": response.missing_fields,
                                "lead_status": lead_status,
                                "session_continued": (
                                    session_id is None
                                    or response.session_id == session_id
                                ),
                            },
                        ),
                    ]
                )
                session_id = response.session_id
            case = safe_conversation(
                ConversationalTestCase(
                    name=scenario.name,
                    turns=turns,
                    expected_outcome=scenario.expected_outcome,
                    metadata={
                        "category": scenario.category,
                        "split": scenario.split,
                        "expected_queue_jobs": scenario.expected_queue_jobs,
                        "queue_jobs": len(queue.enqueued),
                    },
                )
            )
            cases.append(case)
            print(f"Collected {case.name}: {len(scenario.turns)} user turns")
    return cases


def write_checks(cases: list[ConversationalTestCase], output: Path) -> bool:
    results = {}
    for case in cases:
        failures = []
        metadata = case.metadata or {}
        expected_jobs = metadata.get("expected_queue_jobs")
        actual_jobs = metadata.get("queue_jobs")
        if expected_jobs is not None and actual_jobs != expected_jobs:
            failures.append(
                {
                    "field": "queue_jobs",
                    "expected": expected_jobs,
                    "actual": actual_jobs,
                }
            )
        for index, turn in enumerate(case.turns[1::2], start=1):
            metadata = turn.metadata or {}
            for field, expected, actual in (
                ("session_continued", True, metadata.get("session_continued", True)),
                ("state", metadata.get("expected_state"), metadata.get("state")),
                (
                    "lead_status",
                    metadata.get("expected_lead_status"),
                    metadata.get("lead_status"),
                ),
                (
                    "missing_fields",
                    metadata.get("expected_missing_fields"),
                    metadata.get("missing_fields"),
                ),
                (
                    "retrieval",
                    metadata.get("expect_retrieval"),
                    bool(turn.retrieval_context),
                ),
            ):
                if (
                    field == "missing_fields"
                    and expected is not None
                    and actual is not None
                ):
                    expected, actual = sorted(expected), sorted(actual)
                if expected is not None and actual != expected:
                    failures.append(
                        {
                            "turn": index,
                            "field": field,
                            "expected": expected,
                            "actual": actual,
                        }
                    )
        results[case.name] = {"success": not failures, "failures": failures}
    (output / "checks.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    )
    failed = [name for name, result in results.items() if not result["success"]]
    if failed:
        print(f"Conversation checks failed: {', '.join(failed)}")
    return not failed


def score_conversations(cases: list[ConversationalTestCase], output: Path) -> bool:
    cases = [safe_conversation(case) for case in cases]
    if (
        not cases
        or any(not case.name for case in cases)
        or len({case.name for case in cases}) != len(cases)
    ):
        raise ValueError("Conversation cases must be non-empty and have unique names")
    for case in cases:
        if not (case.expected_outcome or "").strip():
            raise ValueError(f"Conversation {case.name} requires expected_outcome")
        roles = [turn.role for turn in case.turns]
        if len(roles) < 4 or roles != ["user", "assistant"] * (len(roles) // 2):
            raise ValueError(
                f"Conversation {case.name} requires alternating user/assistant turns"
            )
        if case.multimodal or case.voice:
            raise ValueError(f"Conversation {case.name} must contain text turns")

    passed = write_checks(cases, output)
    requested_model = os.getenv("EVAL_JEV_MODEL", "jev-latest")
    model = ReportedTypeSafeModel(model=requested_model)
    results = {
        "turn_faithfulness_skipped_no_context": [],
        "turn_faithfulness_skipped_not_applicable": [],
    }
    grounded = []
    for case in cases:
        category = (case.metadata or {}).get("category")
        if category is not None and category not in FACTUAL_CATEGORIES:
            results["turn_faithfulness_skipped_not_applicable"].append(case.name)
        elif any(turn.retrieval_context for turn in case.turns[1::2]):
            grounded.append(case)
        else:
            results["turn_faithfulness_skipped_no_context"].append(case.name)
    options = {"threshold": THRESHOLD, "system_one_model": model, "async_mode": False}
    try:
        for name, metric, selected in (
            (
                "turn_relevancy",
                TurnRelevancyMetric(eval_mode="system_one", **options),
                cases,
            ),
            (
                "knowledge_retention",
                KnowledgeRetentionMetric(eval_mode="system_one", **options),
                cases,
            ),
            (
                "expected_outcome",
                ConversationalJevEval(
                    name="Expected Outcome",
                    evaluation_params=[MultiTurnParams.EXPECTED_OUTCOME],
                    questions=[
                        Noul(
                            "The assistant's behavior across the conversation meets the expected outcome."
                        )
                    ],
                    **options,
                ),
                cases,
            ),
            (
                "turn_faithfulness",
                TurnFaithfulnessMetric(eval_mode="system_one", **options),
                grounded,
            ),
        ):
            if not selected:
                continue
            result = evaluate(
                test_cases=selected,
                metrics=[metric],
                async_config=AsyncConfig(run_async=False),
                cache_config=CacheConfig(write_cache=False, use_cache=False),
                display_config=DisplayConfig(
                    results_folder=str(output),
                    results_subfolder=name,
                    inspect_after_run=False,
                ),
            )
            results[name] = result.model_dump(mode="json")
            passed = passed and all(item.success for item in result.test_results)
    finally:
        write_judge_manifest(output, requested_model, model)
        (output / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n"
        )
    return passed


if __name__ == "__main__":
    from evals.run import main

    main(conversational=True)
