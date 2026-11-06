import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from deepeval.dataset import ConversationalGolden, Golden
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
    DATASET,
    ReportedTypeSafeModel,
    load_goldens,
    require_eval_database,
    safe_case,
    score_cases,
)

pytestmark = pytest.mark.unit


class FakeJev(DeepEvalBaseSystemOneModel):
    def __init__(self):
        self.states = []
        self.response_models = set()
        super().__init__("fake-jev")

    def load_model(self):
        return self

    def get_model_name(self):
        return "fake-jev"

    def decide(self, state, questions):
        self.states.append(state)
        answers = SystemOneAnswers()
        for key, question in questions.items():
            if isinstance(question, NoulQuestion):
                answers.nouls[key] = NoulAnswer(probability=1.0)
            elif isinstance(question, ScoreQuestion):
                top = len(question.levels) - 1
                answers.scores[key] = ScoreAnswer(
                    score=top, probabilities={top: 1.0}, confidence=1.0
                )
            else:
                raise AssertionError(question)
        self.response_models.add("jev-test-version")
        return answers, 0.0

    async def a_decide(self, state, questions):
        return self.decide(state, questions)


def test_preserved_datasets_and_corpus_are_consistent():
    ids = set()
    splits_by_question = {}
    manifest = json.loads(
        Path("evals/datasets/retrieval/corpus_manifest.json").read_text()
    )
    corpus_path = Path("docs/RAG/Данные для RAG.txt")
    corpus = {row["title"]: row for row in json.loads(corpus_path.read_text())}
    assert (
        manifest["source_sha256"]
        == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    )
    assert len(manifest["documents"]) == len(corpus) == 50
    for document in manifest["documents"]:
        assert (
            document["content_sha256"]
            == hashlib.sha256(corpus[document["title"]]["content"].encode()).hexdigest()
        )
    document_ids = {row["id"] for row in manifest["documents"]}
    for kind, count in (("retrieval", 100), ("generation", 108), ("business", 12)):
        rows = json.loads(
            Path(f"evals/datasets/{kind}/golden.dataset.json").read_text()
        )
        assert len(rows) == count
        for row in rows:
            golden = (
                ConversationalGolden if kind == "business" else Golden
            ).model_validate(row)
            meta = golden.additional_metadata
            assert golden.name == meta["id"] and golden.name not in ids
            ids.add(golden.name)
            question = row["scenario" if kind == "business" else "input"]
            assert question == meta["question"]
            assert meta["split"] in {"calibration", "test", "regression"}
            key = " ".join(question.casefold().split())
            assert splits_by_question.setdefault(key, meta["split"]) == meta["split"]
            if kind != "business":
                assert set(meta["relevance"]) <= document_ids
                assert meta["answerable"] == bool(meta["relevance"])
    assert len(ids) == 220
    assert len(load_goldens(DATASET, "test", 100)) == 24


@pytest.mark.parametrize("database", ["production", "innova", "innova_eval_backup"])
def test_working_databases_are_rejected(database):
    with pytest.raises(ValueError, match="temporary PostgreSQL"):
        require_eval_database(f"postgresql+asyncpg://localhost/{database}")


def test_case_redaction_preserves_contact_identity():
    case = safe_case(
        LLMTestCase(
            name="contacts",
            input="Телефон?",
            actual_output="Звоните +79997778801",
            retrieval_context=["Телефон +7 (999) 777-88-01, другой +1 415 555 2671"],
        )
    )
    assert case.actual_output == "Звоните [PHONE_1]"
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
        metric = results["faithfulness"]["test_results"][0]["metrics_data"][0]
        assert metric["name"] == "Faithfulness"
        assert metric["score"] == 1.0
    else:
        assert results["faithfulness_skipped_no_context"] == ["hours"]
        assert "faithfulness" not in results
    assert len(jev.states) == (2 if with_context else 1)
    assert "+79997778801" not in repr(jev.states)


def test_jev_error_does_not_fall_back_to_llm(monkeypatch, tmp_path):
    jev = FakeJev()

    def fail(*args, **kwargs):
        raise RuntimeError("Jev unavailable")

    monkeypatch.setattr(jev, "decide", fail)
    monkeypatch.setattr("evals.run.ReportedTypeSafeModel", lambda **kwargs: jev)
    with pytest.raises(RuntimeError, match="Jev unavailable"):
        score_cases([LLMTestCase(name="error", input="q", actual_output="a")], tmp_path)
    judge = json.loads((tmp_path / "manifest.json").read_text())["judge"]
    assert judge["provider"] == "typesafe"
    assert judge["response_models"] == []


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
