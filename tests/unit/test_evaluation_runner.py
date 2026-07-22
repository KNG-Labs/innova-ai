import json
from argparse import Namespace
from pathlib import Path

import httpx
import pytest

import evals.runners.run as run_module
from evals.runners.evaluate import (
    LoadedCase,
    evaluate,
    load_cases,
    load_predictions,
    score_case,
)
from evals.runners.run import (
    _assert_eval_database,
    _git_metadata,
    _load_manifest,
    _merge_reports,
    collect_api_predictions,
)
from evals.schema import (
    EvaluationPrediction,
    GoldenDataset,
    GoldenExample,
)


pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parents[2]
_DATASETS = _ROOT / "evals" / "datasets"
_CORPUS = _ROOT / "docs" / "RAG" / "Данные для RAG.txt"
_MANIFEST = _DATASETS / "retrieval" / "corpus_manifest.json"


def _case(evaluation_type: str, **values: object) -> LoadedCase:
    return LoadedCase(
        dataset_name="test",
        evaluation_type=evaluation_type,  # type: ignore[arg-type]
        example=GoldenExample.model_validate(
            {
                "id": "case",
                "split": "regression",
                "category": "test",
                "question": "question",
                **values,
            }
        ),
    )


def test_golden_datasets_have_expected_coverage() -> None:
    cases = load_cases(_DATASETS)

    assert len(cases) == 160
    assert sum(case.evaluation_type == "retrieval" for case in cases) == 100
    assert sum(case.evaluation_type == "generation" for case in cases) == 48
    assert sum(case.evaluation_type == "business" for case in cases) == 12
    assert {case.example.split for case in cases} == {
        "calibration",
        "test",
        "regression",
    }


def test_manifest_covers_and_hashes_the_entire_corpus() -> None:
    title_to_id, source_documents = _load_manifest(_MANIFEST, _CORPUS)
    cases = load_cases(_DATASETS)
    relevance_ids = {
        document_id for case in cases for document_id in case.example.relevance
    }

    assert len(title_to_id) == len(source_documents) == 50
    assert len(set(title_to_id.values())) == 50
    assert title_to_id["Автомобили в наличии"] == "vehicle_inventory"
    assert relevance_ids <= set(title_to_id.values())


def test_dataset_splits_do_not_share_exact_questions() -> None:
    questions: dict[str, str] = {}
    for case in load_cases(_DATASETS):
        normalized = " ".join(case.example.question.casefold().split())
        previous_split = questions.setdefault(normalized, case.example.split)
        assert previous_split == case.example.split


def test_retrieval_scores_only_selected_metrics() -> None:
    case = _case(
        "retrieval",
        answerable=True,
        relevance={"doc-a": 3, "doc-b": 1},
    )
    prediction = EvaluationPrediction(
        id="case",
        retrieved_document_ids=["other", "doc-b"],
    )

    assert score_case(case, prediction, top_k=3) == {
        "retrieval_recall@3": 0.5,
        "context_precision@3": 0.5,
        "retrieval_mrr@3": 0.5,
    }


def test_unanswerable_retrieval_scores_abstention() -> None:
    case = _case("retrieval", answerable=False, relevance={})

    assert score_case(case, EvaluationPrediction(id="case"), top_k=3) == {
        "abstention_accuracy@3": 1.0
    }


def test_generation_scores_required_and_forbidden_facts() -> None:
    case = _case(
        "generation",
        answerable=True,
        relevance={"hours": 3},
        required_facts=["21:00 || девяти вечера"],
        forbidden_claims=["закрыты в воскресенье", "работаем до 20:00"],
    )
    prediction = EvaluationPrediction(
        id="case",
        answer="Работаем до 21:00, но закрыты в воскресенье.",
    )

    assert score_case(case, prediction) == {
        "required_fact_coverage": 1.0,
        "forbidden_claim_rate": 0.5,
    }


def test_business_collapses_internal_checks_into_one_metric() -> None:
    case = _case(
        "business",
        required_facts=["от 10%"],
        expected_behavior="answer_before_qualification",
        expected_state="CONTACT_CAPTURE",
        expected_fields={"budget": "до 3 миллионов"},
    )
    good = EvaluationPrediction.model_validate(
        {
            "id": "case",
            "answer": "Первоначальный взнос от 10%. Какую модель ищете?",
            "state": "contact_capture",
            "fields": {"budget": "3000000"},
        }
    )
    bad = good.model_copy(
        update={"answer": "Какую модель ищете? Первоначальный взнос от 10%."}
    )

    assert score_case(case, good) == {"business_dialogue_success": 1.0}
    assert score_case(case, bad) == {"business_dialogue_success": 0.0}


@pytest.mark.asyncio
async def test_api_collector_runs_setup_and_reads_persisted_lead() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "answer": "Ответ",
                    "intent": "lead_request",
                    "state": "LEAD_READY",
                    "missing_fields": [],
                    "lead_id": "00000000-0000-0000-0000-000000000001",
                },
            )
        return httpx.Response(
            200,
            json={
                "qualification": {
                    "car_model": "Toyota Camry",
                    "budget": "3 миллиона",
                    "purchase_type": "кредит",
                },
                "contact": {"phone": "+79991234567"},
            },
        )

    case = _case(
        "business",
        question="Мой номер +79991234567",
        setup_messages=["Ищу Camry до 3 миллионов в кредит"],
        expected_state="LEAD_READY",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    ) as client:
        [prediction] = await collect_api_predictions(
            [case], "http://testserver", client=client
        )

    assert requests == [
        ("POST", "/message"),
        ("POST", "/message"),
        ("GET", "/leads/00000000-0000-0000-0000-000000000001"),
    ]
    assert prediction.fields is not None
    assert prediction.fields.contact == {"phone": "+79991234567"}
    assert prediction.latency_ms is not None


def test_missing_prediction_is_penalized() -> None:
    generation = _case(
        "generation",
        answerable=False,
        relevance={},
        forbidden_claims=["wrong"],
    )

    report = evaluate([generation], {})

    assert report["missing_prediction_count"] == 1
    assert report["cases"][0]["metrics"] == {
        "forbidden_claim_rate": 1.0,
    }


def test_report_keeps_denominators_and_types_separate() -> None:
    retrieval = _case("retrieval", answerable=True, relevance={"doc": 3})
    generation = LoadedCase(
        dataset_name="test",
        evaluation_type="generation",
        example=GoldenExample.model_validate(
            {
                "id": "generation",
                "split": "test",
                "category": "test",
                "question": "question",
                "answerable": False,
                "relevance": {},
                "forbidden_claims": ["wrong"],
            }
        ),
    )

    report = evaluate(
        [retrieval, generation],
        {
            "case": EvaluationPrediction(id="case", retrieved_document_ids=["doc"]),
            "generation": EvaluationPrediction(
                id="generation",
                answer="safe",
            ),
        },
    )

    assert report["metrics_by_type"]["retrieval"]["retrieval_recall@3"] == {
        "value": 1.0,
        "n": 1,
    }
    assert "retrieval_recall@3" not in report["metrics_by_type"]["generation"]


def test_report_contains_only_selected_quality_metrics() -> None:
    cases = load_cases(_DATASETS)
    predictions = {
        case.example.id: EvaluationPrediction(id=case.example.id) for case in cases
    }

    metric_names = set(evaluate(cases, predictions)["metrics"])

    assert metric_names == {
        "retrieval_recall@3",
        "retrieval_mrr@3",
        "context_precision@3",
        "abstention_accuracy@3",
        "required_fact_coverage",
        "forbidden_claim_rate",
        "business_dialogue_success",
    }


def test_dataset_schema_requires_explicit_answerability() -> None:
    with pytest.raises(ValueError, match="answerable is required"):
        GoldenDataset.model_validate(
            {
                "schema_version": "2.0",
                "name": "retrieval",
                "evaluation_type": "retrieval",
                "cases": [
                    {
                        "id": "case",
                        "split": "test",
                        "category": "test",
                        "question": "question",
                    }
                ],
            }
        )


def test_duplicate_ids_across_dataset_files_are_rejected(tmp_path: Path) -> None:
    case = {
        "id": "same_id",
        "split": "test",
        "category": "faq",
        "question": "question",
        "expected_state": "FAQ",
    }
    for name in ("one", "two"):
        payload = {
            "schema_version": "2.0",
            "name": name,
            "evaluation_type": "business",
            "cases": [case],
        }
        (tmp_path / f"{name}.dataset.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    with pytest.raises(ValueError, match="Duplicate case ID"):
        load_cases(tmp_path)


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


def test_multi_run_predictions_require_explicit_repetition(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(
        json.dumps(
            {
                "runs": [
                    {"repetition": 1, "predictions": [{"id": "one"}]},
                    {"repetition": 2, "predictions": [{"id": "two"}]},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="select --repetition"):
        load_predictions(path)
    assert list(load_predictions(path, repetition=2)) == ["two"]


def test_multi_run_report_keeps_mean_and_spread() -> None:
    case = _case("retrieval", answerable=True, relevance={"doc": 3})
    success = evaluate(
        [case],
        {"case": EvaluationPrediction(id="case", retrieved_document_ids=["doc"])},
    )
    failure = evaluate(
        [case],
        {"case": EvaluationPrediction(id="case", retrieved_document_ids=[])},
    )

    report = _merge_reports([success, failure], {"test": True})

    assert report["prediction_count"] == 1
    assert report["prediction_observation_count"] == 2
    assert report["missing_prediction_count"] == 0
    assert report["missing_prediction_observation_count"] == 0
    assert report["metrics"]["retrieval_recall@3"] == {
        "value": 0.5,
        "n": 1,
        "observation_n": 2,
        "runs": 2,
        "run_stddev": 0.5,
    }
    assert report["cases"][0]["metrics"]["retrieval_recall@3"] == {
        "value": 0.5,
        "n": 1,
        "observation_n": 2,
        "runs": 2,
        "run_stddev": 0.5,
    }


@pytest.mark.asyncio
async def test_repetitions_prepare_corpus_and_retrieve_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = tmp_path / "retrieval.dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "name": "retrieval",
                "evaluation_type": "retrieval",
                "cases": [
                    {
                        "id": "case",
                        "split": "test",
                        "category": "test",
                        "question": "question",
                        "answerable": True,
                        "relevance": {"doc": 3},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = {"prepare": 0, "retrieve": 0}

    async def fake_prepare(**_kwargs: object) -> None:
        calls["prepare"] += 1

    async def fake_retrieve(
        _cases: list[LoadedCase], **_kwargs: object
    ) -> list[EvaluationPrediction]:
        calls["retrieve"] += 1
        return [EvaluationPrediction(id="case", retrieved_document_ids=["doc"])]

    monkeypatch.setattr(run_module, "prepare_evaluation_corpus", fake_prepare)
    monkeypatch.setattr(run_module, "collect_retrieval_predictions", fake_retrieve)
    args = Namespace(
        dataset=dataset,
        evaluation_type=["retrieval"],
        split=["test"],
        database_url="postgresql+asyncpg://user:pass@localhost/innova_ai_eval",
        manifest=_MANIFEST,
        corpus=_CORPUS,
        skip_corpus_prepare=False,
        allow_non_eval_database=False,
        top_k=3,
        min_score=0.2,
        repetitions=3,
        api_base_url="http://localhost:8001",
        output=tmp_path / "report.json",
        predictions_output=None,
    )

    report = await run_module._run(args)

    assert calls == {"prepare": 1, "retrieve": 1}
    assert report["run_count"] == 3
    assert report["metrics"]["retrieval_recall@3"] == {
        "value": 1.0,
        "n": 1,
        "observation_n": 1,
        "runs": 1,
        "run_stddev": 0.0,
    }
