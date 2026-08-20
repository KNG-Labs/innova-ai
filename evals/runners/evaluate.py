from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from deepeval.dataset import ConversationalGolden, EvaluationDataset, Golden
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn
from pydantic import TypeAdapter

from app.privacy import PiiSanitizer
from evals.schema import (
    EvaluationPrediction,
    EvaluationType,
    GoldenDataset,
    GoldenExample,
    TranscriptTurn,
)


_PREDICTION_LIST = TypeAdapter(list[EvaluationPrediction])


@dataclass(frozen=True)
class LoadedCase:
    dataset_name: str
    evaluation_type: EvaluationType
    example: GoldenExample
    golden: Golden | ConversationalGolden


def _dataset_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.dataset.json"))


def load_cases(path: Path) -> list[LoadedCase]:
    """Load DeepEval-native Golden arrays and validate Innova metadata."""

    files = _dataset_files(path)
    if not files:
        raise ValueError(f"No *.dataset.json files found in {path}")

    loaded: list[LoadedCase] = []
    seen_ids: dict[str, Path] = {}
    for dataset_path in files:
        evaluation_type = _type_from_parent(dataset_path)
        dataset = EvaluationDataset()
        dataset.add_goldens_from_json_file(str(dataset_path.resolve()))
        goldens = cast(list[Golden | ConversationalGolden], list(dataset.goldens))
        if not goldens:
            raise ValueError(f"Dataset is empty: {dataset_path}")

        examples = [
            GoldenExample.model_validate(golden.additional_metadata or {})
            for golden in goldens
        ]
        GoldenDataset.model_validate(
            {
                "schema_version": "2.0",
                "name": dataset_path.parent.name,
                "evaluation_type": evaluation_type,
                "cases": [example.model_dump(mode="json") for example in examples],
            }
        )
        for golden, example in zip(goldens, examples, strict=True):
            if previous := seen_ids.get(example.id):
                raise ValueError(
                    f"Duplicate case ID {example.id!r} in {previous} and {dataset_path}"
                )
            if golden.name != example.id:
                raise ValueError(f"{dataset_path}: Golden name must equal metadata id")
            if evaluation_type == "business" and not isinstance(
                golden, ConversationalGolden
            ):
                raise ValueError(f"{example.id}: expected ConversationalGolden")
            if evaluation_type != "business" and not isinstance(golden, Golden):
                raise ValueError(f"{example.id}: expected Golden")
            seen_ids[example.id] = dataset_path
            loaded.append(
                LoadedCase(
                    dataset_name=dataset_path.parent.name,
                    evaluation_type=evaluation_type,
                    example=example,
                    golden=golden,
                )
            )
    return loaded


def _type_from_parent(path: Path) -> EvaluationType:
    value = path.parent.name
    if value not in {"retrieval", "generation", "business"}:
        raise ValueError(
            "Datasets must be placed in retrieval, generation, or business"
        )
    return value  # type: ignore[return-value]


def load_predictions(
    path: Path, *, repetition: int | None = None
) -> dict[str, EvaluationPrediction]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "runs" in payload:
            runs = payload["runs"]
            if repetition is None and len(runs) != 1:
                raise ValueError(
                    "Predictions contain multiple runs; select --repetition"
                )
            selected_repetition = repetition or 1
            selected = next(
                (run for run in runs if run.get("repetition") == selected_repetition),
                None,
            )
            if selected is None:
                raise ValueError(
                    f"Prediction repetition {selected_repetition} not found"
                )
            payload = selected.get("predictions", [])
        else:
            payload = payload.get("predictions", [])
    predictions = _PREDICTION_LIST.validate_python(payload)
    by_id: dict[str, EvaluationPrediction] = {}
    for prediction in predictions:
        if prediction.id in by_id:
            raise ValueError(f"Duplicate prediction ID: {prediction.id}")
        by_id[prediction.id] = prediction
    return by_id


def build_single_turn_dataset(
    cases: list[LoadedCase],
    predictions: dict[str, EvaluationPrediction],
) -> EvaluationDataset:
    goldens = [case.golden for case in cases]
    if any(not isinstance(golden, Golden) for golden in goldens):
        raise TypeError("Single-turn dataset contains a ConversationalGolden")
    dataset = EvaluationDataset(goldens=goldens)  # type: ignore[arg-type]
    for case in cases:
        prediction = predictions.get(
            case.example.id, EvaluationPrediction(id=case.example.id)
        )
        metadata = {
            **case.example.model_dump(mode="json"),
            "dataset": case.dataset_name,
            "evaluation_type": case.evaluation_type,
        }
        if case.evaluation_type == "retrieval":
            metadata["retrieved_document_ids"] = prediction.retrieved_document_ids
            actual_output = json.dumps(
                prediction.retrieved_document_ids, ensure_ascii=False
            )
        else:
            actual_output = prediction.answer or ""
        dataset.add_test_case(
            LLMTestCase(
                name=case.example.id,
                input=case.example.question,
                actual_output=actual_output,
                expected_output=(
                    case.golden.expected_output
                    if isinstance(case.golden, Golden)
                    else None
                ),
                retrieval_context=cast(Any, prediction.retrieval_context or None),
                metadata=metadata,
                completion_time=(
                    prediction.latency_ms / 1000
                    if prediction.latency_ms is not None
                    else None
                ),
                tags=[case.example.split, case.example.category],
            )
        )
    return dataset


def build_conversational_dataset(
    cases: list[LoadedCase],
    predictions: dict[str, EvaluationPrediction],
) -> EvaluationDataset:
    goldens = [case.golden for case in cases]
    if any(not isinstance(golden, ConversationalGolden) for golden in goldens):
        raise TypeError("Conversational dataset contains a Golden")
    dataset = EvaluationDataset(goldens=goldens)  # type: ignore[arg-type]
    for case in cases:
        prediction = predictions.get(
            case.example.id, EvaluationPrediction(id=case.example.id)
        )
        turns = _sanitized_turns(case, prediction)
        metadata = {
            "id": case.example.id,
            "dataset": case.dataset_name,
            "evaluation_type": case.evaluation_type,
            "split": case.example.split,
            "category": case.example.category,
            "guardrails": business_guardrails(case.example, prediction),
            "semantic_expectations": {
                "expected_behavior": case.example.expected_behavior,
                "expected_max_questions": case.example.expected_max_questions,
                "required_facts": case.example.required_facts,
                "forbidden_claims": case.example.forbidden_claims,
            },
        }
        dataset.add_test_case(
            ConversationalTestCase(
                name=case.example.id,
                scenario=case.example.question,
                expected_outcome=(
                    case.golden.expected_outcome
                    if isinstance(case.golden, ConversationalGolden)
                    else None
                ),
                turns=turns,
                metadata=metadata,
                tags=[case.example.split, case.example.category],
            )
        )
    return dataset


def _sanitized_turns(case: LoadedCase, prediction: EvaluationPrediction) -> list[Turn]:
    raw_turns = list(prediction.transcript)
    if not raw_turns:
        raw_turns = [
            *[
                TranscriptTurn(role="user", content=content)
                for content in case.example.setup_messages
            ],
            TranscriptTurn(role="user", content=case.example.question),
            TranscriptTurn(role="assistant", content=prediction.answer or ""),
        ]
    sanitizer = PiiSanitizer()
    turns: list[Turn] = []
    for raw in raw_turns:
        turns.append(
            Turn(
                role=raw.role,
                content=sanitizer.sanitize_text(raw.content).text,
            )
        )
    return turns


def business_guardrails(
    example: GoldenExample, prediction: EvaluationPrediction
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if example.expected_intent is not None:
        checks["intent"] = _normalize(example.expected_intent) == _normalize(
            prediction.intent
        )
    if example.expected_state is not None:
        checks["state"] = _normalize(example.expected_state) == _normalize(
            prediction.state
        )
    if example.expected_missing_fields is not None:
        checks["missing_fields"] = set(example.expected_missing_fields) == set(
            prediction.missing_fields or []
        )
    if example.expected_fields is not None:
        actual = prediction.fields
        for field_name in example.expected_fields.model_fields_set:
            expected_value = getattr(example.expected_fields, field_name)
            actual_value = getattr(actual, field_name) if actual is not None else None
            checks[f"lead_{field_name}"] = _field_matches(
                field_name, expected_value, actual_value
            )
    return checks


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.casefold().split()) or None


def _tokens(value: str | None) -> list[str]:
    return re.findall(r"\w+", _normalize(value) or "", re.UNICODE)


def _normalize_budget(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    numbers = re.findall(r"\d+(?:[.,]\d+)?", normalized.replace(" ", ""))
    if len(numbers) != 1:
        return " ".join(_tokens(normalized))
    amount = float(numbers[0].replace(",", "."))
    if re.search(r"\b(млн|миллион\w*)\b", normalized):
        amount *= 1_000_000
    elif re.search(r"\b(тыс|тысяч\w*)\b", normalized):
        amount *= 1_000
    return str(round(amount))


def _normalize_purchase_type(value: str | None) -> str | None:
    normalized = " ".join(_tokens(value))
    if not normalized:
        return None
    if "кредит" in normalized:
        return "credit"
    if "trade in" in normalized or "трейд ин" in normalized:
        return "trade_in"
    if normalized in {"наличные", "наличными", "cash"}:
        return "cash"
    return normalized


def _normalize_contact(value: str | None) -> str | None:
    normalized = _normalize(value)
    if normalized is None:
        return None
    digits = re.sub(r"\D", "", normalized)
    return digits[-10:] if len(digits) >= 10 else normalized.lstrip("@")


def _contact_matches(expected: str | None, actual: object) -> bool:
    if isinstance(actual, dict):
        actual_values = [_normalize_contact(value) for value in actual.values()]
        if expected is None:
            return not any(actual_values)
        return _normalize_contact(expected) in actual_values
    return _normalize_contact(expected) == _normalize_contact(
        actual if isinstance(actual, str) else None
    )


def _field_matches(field_name: str, expected: str | None, actual: object) -> bool:
    if field_name == "contact":
        return _contact_matches(expected, actual)
    actual_string = actual if isinstance(actual, str) else None
    if field_name == "budget":
        return _normalize_budget(expected) == _normalize_budget(actual_string)
    if field_name == "purchase_type":
        return _normalize_purchase_type(expected) == _normalize_purchase_type(
            actual_string
        )
    return " ".join(_tokens(expected)) == " ".join(_tokens(actual_string))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Innova DeepEval datasets")
    parser.add_argument("--dataset", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    cases = load_cases(_parse_args().dataset)
    by_type: dict[str, int] = defaultdict(int)
    by_split: dict[str, int] = defaultdict(int)
    for case in cases:
        by_type[case.evaluation_type] += 1
        by_split[case.example.split] += 1
    print(
        json.dumps(
            {
                "valid": True,
                "case_count": len(cases),
                "case_count_by_type": dict(sorted(by_type.items())),
                "case_count_by_split": dict(sorted(by_split.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
