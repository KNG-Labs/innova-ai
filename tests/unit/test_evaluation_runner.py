import json
from types import SimpleNamespace

import pytest
from deepeval.models import DeepEvalBaseSystemOneModel
from deepeval.models.system_one.schema import (
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SystemOneAnswers,
)
from deepeval.test_case import LLMTestCase

from app.privacy import PiiAnalysisError, PiiSanitizer
from evals.run import (
    ReportedTypeSafeModel,
    load_goldens,
    require_eval_database,
    safe_case,
    score_cases,
)

pytestmark = pytest.mark.unit


class FakeJev(DeepEvalBaseSystemOneModel):
    def __init__(self, fail_on_call=None):
        self.states = []
        self.fail_on_call = fail_on_call
        self.response_models = set()
        super().__init__("fake-jev")

    def load_model(self):
        return self

    def get_model_name(self):
        return "fake-jev"

    def decide(self, state, questions):
        self.states.append(state)
        passing = len(self.states) != self.fail_on_call
        answers = SystemOneAnswers()
        for key, question in questions.items():
            if isinstance(question, NoulQuestion):
                answers.nouls[key] = NoulAnswer(probability=1.0 if passing else 0.0)
            elif isinstance(question, ScoreQuestion):
                top = len(question.levels) - 1 if passing else 0
                answers.scores[key] = ScoreAnswer(
                    score=top, probabilities={top: 1.0}, confidence=1.0
                )
            else:
                raise AssertionError(question)
        self.response_models.add("jev-test-version")
        return answers, 0.0

    async def a_decide(self, state, questions):
        return self.decide(state, questions)


def test_load_goldens_filters_split_answerability_and_limit(tmp_path):
    path = tmp_path / "goldens.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": name,
                    "input": "Question",
                    "additional_metadata": {"split": split, "answerable": answerable},
                }
                for name, split, answerable in (
                    ("cal", "calibration", True),
                    ("negative", "test", False),
                    ("test-1", "test", True),
                    ("test-2", "test", True),
                )
            ]
        )
    )
    assert [golden.name for golden in load_goldens(path, "test", 1)] == ["test-1"]


@pytest.mark.parametrize("database", ["production", "innova", "innova_eval_backup"])
def test_working_databases_are_rejected(database):
    with pytest.raises(ValueError, match="temporary PostgreSQL"):
        require_eval_database(f"postgresql+asyncpg://localhost/{database}")


def test_case_redaction_preserves_contact_identity():
    case = safe_case(
        LLMTestCase(
            name="contacts",
            input="Телефон?",
            expected_output="Звоните +7 (999) 777-88-01",
            actual_output="Звоните +79997778801",
            retrieval_context=["Телефон +7 (999) 777-88-01, другой +1 415 555 2671"],
        )
    )
    assert case.actual_output == "Звоните [PHONE_1]"
    assert case.expected_output == "Звоните [PHONE_1]"
    assert case.retrieval_context == ["Телефон [PHONE_1], другой [PHONE_2]"]


def test_analysis_failure_blocks_judge(monkeypatch, tmp_path):
    def fail(*args):
        raise PiiAnalysisError("synthetic failure")

    monkeypatch.setattr(PiiSanitizer, "find_entities", fail)
    with pytest.raises(PiiAnalysisError):
        score_cases(
            [LLMTestCase(name="blocked", input="q", actual_output="a")], tmp_path
        )


@pytest.mark.parametrize("with_context", [True, False])
def test_native_metrics_use_jev_without_llm(monkeypatch, tmp_path, with_context):
    jev = FakeJev()
    monkeypatch.setattr("evals.run.ReportedTypeSafeModel", lambda **kwargs: jev)
    case = LLMTestCase(
        name="hours",
        input="До скольких работает салон?",
        expected_output="Салон открыт до 21:00. Телефон +79997778801.",
        actual_output="До 21:00. Телефон +79997778801.",
        retrieval_context=["Салон открыт до 21:00, телефон +79997778801"]
        if with_context
        else [],
    )
    assert score_cases([case], tmp_path) is with_context
    results = json.loads((tmp_path / "results.json").read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["judge"]["response_models"] == ["jev-test-version"]
    assert manifest["judge"]["requested_model"] == "jev-latest"
    assert manifest["judge"]["deepeval_version"]
    assert manifest["judge"]["typesafe_sdk_version"]
    assert results["answer_relevancy"]["test_results"][0]["success"] is True
    if with_context:
        for name in (
            "faithfulness",
            "contextual_relevancy",
            "contextual_precision",
            "contextual_recall",
        ):
            metric = results[name]["test_results"][0]["metrics_data"][0]
            assert metric["score"] == 1.0
            assert results[name]["test_results"][0]["success"] is True
            assert (tmp_path / name).is_dir()
        assert "expected_output" in jev.states[3]["test_case"]
        assert "expected_output" in jev.states[4]["test_case"]
    else:
        assert results["faithfulness_skipped_no_context"] == ["hours"]
        assert results["retrieval_metrics_skipped_no_context"] == ["hours"]
        assert "faithfulness" not in results
        assert not any(name.startswith("contextual_") for name in results)
    assert len(jev.states) == (5 if with_context else 1)
    assert "+79997778801" not in repr(jev.states)


def test_jev_error_does_not_fall_back_to_llm(monkeypatch, tmp_path):
    jev = FakeJev()

    def fail(*args, **kwargs):
        raise RuntimeError("Jev unavailable")

    monkeypatch.setattr(jev, "decide", fail)
    monkeypatch.setattr("evals.run.ReportedTypeSafeModel", lambda **kwargs: jev)
    with pytest.raises(RuntimeError, match="Jev unavailable"):
        score_cases(
            [
                LLMTestCase(
                    name="error", input="q", actual_output="a", expected_output="a"
                )
            ],
            tmp_path,
        )
    judge = json.loads((tmp_path / "manifest.json").read_text())["judge"]
    assert judge["provider"] == "typesafe"
    assert judge["response_models"] == []


@pytest.mark.parametrize("expected_output", [None, "", "   "])
def test_missing_reference_is_rejected_before_judge(
    monkeypatch, tmp_path, expected_output
):
    monkeypatch.setattr(
        "evals.run.ReportedTypeSafeModel",
        lambda **kwargs: pytest.fail("Judge must not be initialized"),
    )
    with pytest.raises(ValueError, match="require expected_output.*hours"):
        score_cases(
            [
                LLMTestCase(
                    name="hours",
                    input="q",
                    actual_output="a",
                    expected_output=expected_output,
                    retrieval_context=["context"],
                )
            ],
            tmp_path,
        )


@pytest.mark.parametrize(
    "metric_name,call_number",
    [
        ("contextual_relevancy", 3),
        ("contextual_precision", 4),
        ("contextual_recall", 5),
    ],
)
def test_failed_retrieval_metric_fails_the_run(
    monkeypatch, tmp_path, metric_name, call_number
):
    jev = FakeJev(fail_on_call=call_number)
    monkeypatch.setattr("evals.run.ReportedTypeSafeModel", lambda **kwargs: jev)
    assert (
        score_cases(
            [
                LLMTestCase(
                    name="hours",
                    input="q",
                    actual_output="a",
                    expected_output="a",
                    retrieval_context=["context"],
                )
            ],
            tmp_path,
        )
        is False
    )
    results = json.loads((tmp_path / "results.json").read_text())
    assert results[metric_name]["test_results"][0]["success"] is False


@pytest.mark.parametrize("returned_model", ["jev-1.14.0", "jev-latest"])
def test_records_api_model_without_changing_native_conversion(returned_model):
    model = ReportedTypeSafeModel(model="jev-latest", api_key="test-key")
    response = SimpleNamespace(
        model=returned_model,
        nouls={"relevant": SimpleNamespace(noul=0.8)},
        choices={},
        scores={},
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
    )
    answers, _cost = model._from_sdk_response(response)
    assert model.response_models == {returned_model}
    assert answers.nouls["relevant"].probability == 0.8
