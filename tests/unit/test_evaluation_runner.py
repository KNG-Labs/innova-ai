import json
from argparse import Namespace
from pathlib import Path

import httpx
import pytest
from deepeval.dataset import ConversationalGolden, Golden
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn

from evals.metrics import (
    AbstentionAccuracyAt10,
    BusinessDialogueSuccess,
    BusinessVerdict,
    ClaimVerdict,
    ContextPrecisionAt10,
    FactVerdict,
    ForbiddenClaimRate,
    ForbiddenClaimVerdicts,
    RequiredFactCoverage,
    RequiredFactVerdicts,
    RetrievalMRRAt10,
    RetrievalRecallAt10,
)
from evals.runners.evaluate import (
    LoadedCase,
    build_conversational_dataset,
    load_cases,
)
from evals.runners.run import (
    _assert_eval_database,
    _check_judge_independence,
    _git_metadata,
    _load_manifest,
    _run,
    _token_usage_summary,
    collect_api_predictions,
)
import evals.runners.run as run_module
from evals.schema import EvaluationPrediction, GoldenExample, TokenUsage


pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parents[2]
_DATASETS = _ROOT / "evals" / "datasets"
_CORPUS = _ROOT / "docs" / "RAG" / "Данные для RAG.txt"
_MANIFEST = _DATASETS / "retrieval" / "corpus_manifest.json"


class FakeJudge(DeepEvalBaseLLM):
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.prompts: list[str] = []
        super().__init__("fake-judge")

    def load_model(self) -> "FakeJudge":
        return self

    def generate(self, prompt: str, schema=None, **_kwargs):
        self.prompts.append(prompt)
        return self.responses.pop(0)

    async def a_generate(self, prompt: str, schema=None, **_kwargs):
        return self.generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        return "fake-judge"


class SchemaFakeJudge(DeepEvalBaseLLM):
    def load_model(self) -> "SchemaFakeJudge":
        return self

    def generate(self, prompt: str, schema=None, **_kwargs):
        if schema is RequiredFactVerdicts:
            return RequiredFactVerdicts(
                verdicts=[FactVerdict(index=0, covered=True, reason="ok")]
            )
        if schema is ForbiddenClaimVerdicts:
            return ForbiddenClaimVerdicts(
                verdicts=[ClaimVerdict(index=0, detected=False, reason="safe")]
            )
        if schema is BusinessVerdict:
            return BusinessVerdict(success=True, reason="ok")
        raise AssertionError(schema)

    async def a_generate(self, prompt: str, schema=None, **_kwargs):
        return self.generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        return "schema-fake-judge"


def _loaded_case(evaluation_type: str, **values: object) -> LoadedCase:
    example = GoldenExample.model_validate(
        {
            "id": "case",
            "split": "regression",
            "category": "test",
            "question": "question",
            **values,
        }
    )
    metadata = example.model_dump(mode="json")
    golden = (
        ConversationalGolden(
            scenario=example.question,
            name=example.id,
            additional_metadata=metadata,
        )
        if evaluation_type == "business"
        else Golden(
            input=example.question,
            name=example.id,
            additional_metadata=metadata,
        )
    )
    return LoadedCase(
        dataset_name="test",
        evaluation_type=evaluation_type,  # type: ignore[arg-type]
        example=example,
        golden=golden,
    )


def _retrieval_case(relevance: dict[str, int], retrieved: list[str]) -> LLMTestCase:
    return LLMTestCase(
        input="q",
        actual_output="[]",
        metadata={
            "relevance": relevance,
            "retrieved_document_ids": retrieved,
        },
    )


def test_golden_datasets_are_deepeval_native_and_keep_coverage() -> None:
    for evaluation_type, expected_type in (
        ("retrieval", Golden),
        ("generation", Golden),
        ("business", ConversationalGolden),
    ):
        payload = json.loads(
            (_DATASETS / evaluation_type / "golden.dataset.json").read_text(
                encoding="utf-8"
            )
        )
        assert isinstance(payload, list)
        assert payload
        expected_key = "scenario" if evaluation_type == "business" else "input"
        assert expected_key in payload[0]
        assert "additional_metadata" in payload[0]

    cases = load_cases(_DATASETS)
    assert len(cases) == 220
    assert sum(case.evaluation_type == "retrieval" for case in cases) == 100
    assert sum(case.evaluation_type == "generation" for case in cases) == 108
    assert sum(case.evaluation_type == "business" for case in cases) == 12
    assert all(
        isinstance(
            case.golden,
            ConversationalGolden if case.evaluation_type == "business" else Golden,
        )
        for case in cases
    )
    assert len({case.example.id for case in cases}) == 220
    assert {case.example.split for case in cases} == {
        "calibration",
        "test",
        "regression",
    }


def test_manifest_covers_relevance_ids_and_frozen_corpus() -> None:
    title_to_id, source_documents = _load_manifest(_MANIFEST, _CORPUS)
    relevance_ids = {
        document_id
        for case in load_cases(_DATASETS)
        for document_id in case.example.relevance
    }
    assert len(title_to_id) == len(source_documents) == 50
    assert relevance_ids <= set(title_to_id.values())


def test_dataset_splits_do_not_share_exact_questions() -> None:
    questions: dict[str, str] = {}
    for case in load_cases(_DATASETS):
        normalized = " ".join(case.example.question.casefold().split())
        previous_split = questions.setdefault(normalized, case.example.split)
        assert previous_split == case.example.split


def test_retrieval_metrics_deduplicate_documents_and_use_k_10() -> None:
    case = _retrieval_case(
        {"doc-a": 3, "doc-b": 1},
        ["other", "other", "doc-b"],
    )
    metrics = [
        RetrievalRecallAt10(),
        RetrievalMRRAt10(),
        ContextPrecisionAt10(),
    ]
    assert [metric.measure(case) for metric in metrics] == [0.5, 0.5, 0.5]
    assert all(metric.success is False for metric in metrics)


def test_retrieval_metrics_empty_and_abstention() -> None:
    answerable = _retrieval_case({"doc": 3}, [])
    unanswerable = _retrieval_case({}, [])
    assert RetrievalRecallAt10().measure(answerable) == 0.0
    assert RetrievalMRRAt10().measure(answerable) == 0.0
    assert ContextPrecisionAt10().measure(answerable) == 0.0
    assert AbstentionAccuracyAt10().measure(unanswerable) == 1.0
    assert AbstentionAccuracyAt10().measure(_retrieval_case({}, ["doc"])) == 0.0


def test_retrieval_metric_boundary_at_positions_10_and_11() -> None:
    position_10 = [f"other-{index}" for index in range(9)] + ["relevant"]
    position_11 = position_10[:9] + ["other-9", "relevant"]
    assert RetrievalMRRAt10().measure(
        _retrieval_case({"relevant": 3}, position_10)
    ) == pytest.approx(0.1)
    assert (
        RetrievalRecallAt10().measure(_retrieval_case({"relevant": 3}, position_11))
        == 0.0
    )


def test_required_fact_coverage_uses_semantic_verdicts_once() -> None:
    judge = FakeJudge(
        [
            RequiredFactVerdicts(
                verdicts=[
                    FactVerdict(index=0, covered=True, reason="перефразировано"),
                    FactVerdict(index=1, covered=False, reason="не сказано"),
                ]
            )
        ]
    )
    case = LLMTestCase(
        input="q",
        actual_output="Ответ другими словами",
        metadata={"required_facts": ["факт 1", "факт 2"]},
    )
    metric = RequiredFactCoverage(judge)
    assert metric.measure(case) == 0.5
    assert metric.success is False
    assert len(judge.prompts) == 1
    assert "Оценивай смысл" in judge.prompts[0]


def test_forbidden_claim_rate_detects_paraphrase_from_judge() -> None:
    judge = FakeJudge(
        [
            ForbiddenClaimVerdicts(
                verdicts=[
                    ClaimVerdict(index=0, detected=True, reason="перефразировано"),
                    ClaimVerdict(index=1, detected=False, reason="отсутствует"),
                ]
            )
        ]
    )
    case = LLMTestCase(
        input="q",
        actual_output="Смысловой пересказ запрещённого утверждения",
        metadata={"forbidden_claims": ["claim 1", "claim 2"]},
    )
    metric = ForbiddenClaimRate(judge)
    assert metric.measure(case) == 0.5
    assert metric.success is False
    assert len(judge.prompts) == 1


def test_forbidden_claim_rate_passes_only_when_no_claim_is_detected() -> None:
    judge = FakeJudge(
        [
            ForbiddenClaimVerdicts(
                verdicts=[ClaimVerdict(index=0, detected=False, reason="отсутствует")]
            )
        ]
    )
    case = LLMTestCase(
        input="q",
        actual_output="Безопасный ответ",
        metadata={"forbidden_claims": ["claim"]},
    )
    metric = ForbiddenClaimRate(judge)
    assert metric.measure(case) == 0.0
    assert metric.success is True


@pytest.mark.parametrize(
    ("semantic_success", "guardrails", "expected"),
    [
        (False, {"state": True, "intent": True}, 0.0),
        (True, {"state": False, "intent": True}, 0.0),
        (True, {"state": True, "intent": True, "lead_budget": False}, 0.0),
        (True, {"state": True, "intent": True, "lead_budget": True}, 1.0),
    ],
)
def test_business_dialogue_combines_semantic_and_exact_guardrails(
    semantic_success: bool, guardrails: dict[str, bool], expected: float
) -> None:
    judge = FakeJudge(
        [BusinessVerdict(success=semantic_success, reason="semantic verdict")]
    )
    case = ConversationalTestCase(
        scenario="qualification",
        turns=[
            Turn(role="user", content="setup"),
            Turn(role="assistant", content="setup answer"),
            Turn(role="user", content="final"),
            Turn(role="assistant", content="final answer"),
        ],
        metadata={
            "guardrails": guardrails,
            "semantic_expectations": {"expected_behavior": "answer_only"},
        },
    )
    metric = BusinessDialogueSuccess(judge)
    assert metric.measure(case) == expected
    assert metric.success is bool(expected)
    assert "setup answer" in judge.prompts[0]


def test_business_judge_transcript_redacts_contact_but_local_guardrail_checks_it() -> (
    None
):
    case = _loaded_case(
        "business",
        expected_fields={"contact": "+79991234567"},
        expected_state="LEAD_READY",
    )
    prediction = EvaluationPrediction(
        id="case",
        answer="Контакт сохранён",
        state="LEAD_READY",
        fields={"contact": {"phone": "+79991234567"}},
        transcript=[
            {
                "role": "user",
                "content": "Мой телефон +79991234567",
            },
            {"role": "assistant", "content": "Контакт сохранён"},
        ],
    )
    dataset = build_conversational_dataset([case], {"case": prediction})
    test_case = dataset.test_cases[0]
    assert isinstance(test_case, ConversationalTestCase)
    assert "+79991234567" not in repr(test_case.turns)
    assert "[PHONE_1]" in repr(test_case.turns)
    assert test_case.metadata == {
        "id": "case",
        "dataset": "test",
        "evaluation_type": "business",
        "split": "regression",
        "category": "test",
        "guardrails": {"state": True, "lead_contact": True},
        "semantic_expectations": {
            "expected_behavior": None,
            "expected_max_questions": None,
            "required_facts": [],
            "forbidden_claims": [],
        },
    }


@pytest.mark.asyncio
async def test_api_collector_keeps_setup_transcript_and_reads_usage() -> None:
    counter = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal counter
        if request.method == "POST":
            counter += 1
            return httpx.Response(
                200,
                json={
                    "assistant_message_id": (f"00000000-0000-0000-0000-{counter:012d}"),
                    "answer": f"Ответ {counter}",
                    "intent": "lead_request",
                    "state": "CONTACT_CAPTURE",
                    "missing_fields": ["contact"],
                    "lead_id": None,
                },
            )
        raise AssertionError(request)

    async def usage_loader(
        message_ids: list[str],
    ) -> dict[str, dict[str, object] | None]:
        return {
            message_id: {
                "eval_token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                    "calls": 2,
                    "complete": True,
                }
            }
            for message_id in message_ids
        }

    case = _loaded_case(
        "business",
        setup_messages=["setup"],
        expected_state="CONTACT_CAPTURE",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        [prediction] = await collect_api_predictions(
            [case],
            "http://testserver",
            client=client,
            usage_loader=usage_loader,
        )
    assert [turn.content for turn in prediction.transcript] == [
        "setup",
        "Ответ 1",
        "question",
        "Ответ 2",
    ]
    assert [usage.total_tokens for usage in prediction.turn_token_usage if usage] == [
        12,
        12,
    ]


def test_token_usage_sums_multiturn_and_excludes_incomplete_cases() -> None:
    complete = EvaluationPrediction(
        id="business",
        turn_token_usage=[
            TokenUsage(
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
                calls=2,
            ),
            TokenUsage(
                prompt_tokens=20,
                completion_tokens=3,
                total_tokens=23,
                calls=1,
            ),
        ],
    )
    contact_only = EvaluationPrediction(
        id="generation",
        turn_token_usage=[
            TokenUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                calls=0,
            )
        ],
    )
    incomplete = EvaluationPrediction(id="missing", turn_token_usage=[None])
    summary = _token_usage_summary(
        [[complete, contact_only, incomplete]],
        {
            "business": "business",
            "generation": "generation",
            "missing": "generation",
        },
    )
    metric = summary["average_agent_token_usage"]
    assert metric["value"] == 17.5
    assert metric["n"] == 2
    assert metric["expected_n"] == 3
    assert metric["incomplete"] is True
    assert metric["missing_usage_n"] == 1
    assert summary["breakdown"]["business"]["average_total_tokens_per_case"] == 35
    assert "judge" not in json.dumps(summary).casefold()


@pytest.mark.asyncio
async def test_mock_runner_writes_deepeval_results_and_all_eight_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        _loaded_case("retrieval", answerable=True, relevance={"doc": 3}),
        LoadedCase(
            dataset_name="test",
            evaluation_type="retrieval",
            example=GoldenExample.model_validate(
                {
                    "id": "abstain",
                    "split": "regression",
                    "category": "test",
                    "question": "unknown",
                    "answerable": False,
                    "relevance": {},
                }
            ),
            golden=Golden(
                input="unknown",
                name="abstain",
                additional_metadata={
                    "id": "abstain",
                    "split": "regression",
                    "category": "test",
                    "question": "unknown",
                    "answerable": False,
                    "relevance": {},
                },
            ),
        ),
        LoadedCase(
            dataset_name="test",
            evaluation_type="generation",
            example=GoldenExample.model_validate(
                {
                    "id": "generation",
                    "split": "regression",
                    "category": "test",
                    "question": "faq",
                    "answerable": True,
                    "relevance": {"doc": 3},
                    "required_facts": ["fact"],
                    "forbidden_claims": ["bad"],
                }
            ),
            golden=Golden(
                input="faq",
                name="generation",
                additional_metadata={
                    "id": "generation",
                    "split": "regression",
                    "category": "test",
                    "question": "faq",
                    "answerable": True,
                    "relevance": {"doc": 3},
                    "required_facts": ["fact"],
                    "forbidden_claims": ["bad"],
                },
            ),
        ),
        LoadedCase(
            dataset_name="test",
            evaluation_type="business",
            example=GoldenExample.model_validate(
                {
                    "id": "business",
                    "split": "regression",
                    "category": "test",
                    "question": "buy",
                    "expected_state": "FAQ",
                }
            ),
            golden=ConversationalGolden(
                scenario="buy",
                name="business",
                additional_metadata={
                    "id": "business",
                    "split": "regression",
                    "category": "test",
                    "question": "buy",
                    "expected_state": "FAQ",
                },
            ),
        ),
    ]

    async def no_prepare(**_kwargs: object) -> None:
        return None

    async def fake_retrieval(
        selected: list[LoadedCase], **_kwargs: object
    ) -> list[EvaluationPrediction]:
        return [
            EvaluationPrediction(
                id=case.example.id,
                retrieved_document_ids=(["doc"] if case.example.answerable else []),
                retrieval_context=["context"] if case.example.answerable else [],
            )
            for case in selected
        ]

    async def fake_api(
        selected: list[LoadedCase],
        _api_base_url: str,
        **_kwargs: object,
    ) -> list[EvaluationPrediction]:
        predictions = []
        for case in selected:
            predictions.append(
                EvaluationPrediction(
                    id=case.example.id,
                    answer="fact",
                    state="FAQ",
                    intent="general",
                    transcript=[
                        {"role": "user", "content": case.example.question},
                        {"role": "assistant", "content": "fact"},
                    ],
                    turn_token_usage=[
                        TokenUsage(
                            prompt_tokens=8,
                            completion_tokens=2,
                            total_tokens=10,
                            calls=1,
                        )
                    ],
                )
            )
        return predictions

    monkeypatch.setattr(run_module, "load_cases", lambda _path: cases)
    monkeypatch.setattr(run_module, "prepare_evaluation_corpus", no_prepare)
    monkeypatch.setattr(run_module, "collect_retrieval_predictions", fake_retrieval)
    monkeypatch.setattr(run_module, "collect_api_predictions", fake_api)
    results_dir = tmp_path / "results"
    args = Namespace(
        dataset=_DATASETS,
        evaluation_type=None,
        split=None,
        api_base_url="http://testserver",
        database_url=("postgresql+asyncpg://user:pass@localhost/innova_ai_test"),
        manifest=_MANIFEST,
        corpus=_CORPUS,
        skip_corpus_prepare=False,
        allow_non_eval_database=False,
        top_k=10,
        min_score=0.2,
        repetitions=1,
        results_dir=results_dir,
        require_independent_judge=False,
        judge=SchemaFakeJudge("fake"),
    )
    report = await _run(args)
    assert set(report["metrics"]) == {
        "retrieval_recall@10",
        "retrieval_mrr@10",
        "context_precision@10",
        "abstention_accuracy@10",
        "required_fact_coverage",
        "forbidden_claim_rate",
        "business_dialogue_success",
        "average_agent_token_usage",
    }
    assert report["metrics"]["average_agent_token_usage"]["value"] == 10
    assert (results_dir / "summary.json").exists()
    assert (results_dir / "manifest.json").exists()
    assert (results_dir / "predictions.json").exists()
    assert list(results_dir.glob("*.md"))
    deepeval_runs = list((results_dir / "deepeval").rglob("*.json"))
    assert deepeval_runs
    custom_metric_names = set(report["metrics"]) - {"average_agent_token_usage"}
    seen_metric_names: set[str] = set()
    for path in deepeval_runs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for metric in payload["metricsScores"]:
            if metric["metric"] not in custom_metric_names:
                continue
            seen_metric_names.add(metric["metric"])
            assert metric["errors"] == 0
    assert seen_metric_names == custom_metric_names


def test_judge_independence_warns_or_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _check_judge_independence("same", "same", require_independent=False) is True
    assert "self_judge=true" in capsys.readouterr().err
    with pytest.raises(RuntimeError, match="self_judge=true"):
        _check_judge_independence("same", "same", require_independent=True)
    assert (
        _check_judge_independence("judge", "agent", require_independent=True) is False
    )


def test_non_evaluation_database_is_rejected_by_default() -> None:
    with pytest.raises(RuntimeError, match="non-evaluation database"):
        _assert_eval_database(
            "postgresql+asyncpg://user:secret@localhost/innova_ai",
            allow_non_eval_database=False,
        )
    assert (
        _assert_eval_database(
            "postgresql+asyncpg://user:secret@localhost/innova_ai_eval",
            allow_non_eval_database=False,
        )
        == "innova_ai_eval"
    )


def test_git_metadata_can_be_supplied_without_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVAL_GIT_COMMIT", "abc123")
    monkeypatch.setenv("EVAL_GIT_DIRTY", "false")
    assert _git_metadata() == {"commit": "abc123", "dirty": False}
