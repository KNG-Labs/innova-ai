from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping

from pydantic import TypeAdapter

from evals.schema import (
    EvaluationPrediction,
    EvaluationType,
    GoldenDataset,
    GoldenExample,
)


_PREDICTION_LIST = TypeAdapter(list[EvaluationPrediction])
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_FACT_ALTERNATIVE_SEPARATOR = "||"


@dataclass(frozen=True)
class LoadedCase:
    dataset_name: str
    evaluation_type: EvaluationType
    example: GoldenExample


def _dataset_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.dataset.json")) + sorted(path.rglob("*.dataset.jsonl"))


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Expected a JSON array in {path}")


def load_cases(path: Path) -> list[LoadedCase]:
    files = _dataset_files(path)
    if not files:
        raise ValueError(f"No *.dataset.json or *.dataset.jsonl files found in {path}")

    loaded: list[LoadedCase] = []
    seen_ids: dict[str, Path] = {}
    for dataset_path in files:
        if dataset_path.name.endswith(".dataset.jsonl"):
            records = _read_json_records(dataset_path)
            dataset = GoldenDataset.model_validate(
                {
                    "schema_version": "2.0",
                    "name": dataset_path.stem.removesuffix(".dataset"),
                    "evaluation_type": _type_from_parent(dataset_path),
                    "cases": records,
                }
            )
        else:
            dataset = GoldenDataset.model_validate_json(
                dataset_path.read_text(encoding="utf-8")
            )

        for example in dataset.cases:
            if previous := seen_ids.get(example.id):
                raise ValueError(
                    f"Duplicate case ID {example.id!r} in {previous} and {dataset_path}"
                )
            seen_ids[example.id] = dataset_path
            loaded.append(
                LoadedCase(
                    dataset_name=dataset.name,
                    evaluation_type=dataset.evaluation_type,
                    example=example,
                )
            )
    return loaded


def _type_from_parent(path: Path) -> EvaluationType:
    value = path.parent.name
    if value not in {"retrieval", "generation", "business"}:
        raise ValueError(
            "JSONL datasets must be placed in retrieval, generation, or business"
        )
    return value  # type: ignore[return-value]


def load_predictions(
    path: Path, *, repetition: int | None = None
) -> dict[str, EvaluationPrediction]:
    if path.suffix == ".jsonl":
        predictions = _PREDICTION_LIST.validate_python(_read_json_records(path))
    else:
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
                    (
                        run
                        for run in runs
                        if run.get("repetition") == selected_repetition
                    ),
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


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.casefold().split()) or None


def _tokens(value: str | None) -> list[str]:
    return _TOKEN_RE.findall(_normalize(value) or "")


def _fact_matches(label: str, answer: str | None) -> bool:
    answer_tokens = " ".join(_tokens(answer))
    if not answer_tokens:
        return False
    alternatives = label.split(_FACT_ALTERNATIVE_SEPARATOR)
    return any(
        " ".join(_tokens(alternative)) in answer_tokens for alternative in alternatives
    )


def _rank_metrics(
    relevance: dict[str, int], retrieved: list[str], *, top_k: int
) -> dict[str, float]:
    retrieved_at_k = retrieved[:top_k]
    suffix = f"@{top_k}"
    if not relevance:
        return {f"abstention_accuracy{suffix}": float(not retrieved_at_k)}

    relevant_ids = set(relevance)
    hit_count = sum(item in relevant_ids for item in retrieved_at_k)
    first_rank = next(
        (
            index
            for index, item in enumerate(retrieved_at_k, start=1)
            if item in relevant_ids
        ),
        None,
    )
    return {
        f"retrieval_recall{suffix}": len(relevant_ids.intersection(retrieved_at_k))
        / len(relevant_ids),
        f"context_precision{suffix}": hit_count / len(retrieved_at_k)
        if retrieved_at_k
        else 0.0,
        f"retrieval_mrr{suffix}": 0.0 if first_rank is None else 1.0 / first_rank,
    }


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
    if len(digits) >= 10:
        return digits[-10:]
    return normalized.lstrip("@")


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
    actual_string = actual if isinstance(actual, str) else None
    if field_name == "contact":
        return _contact_matches(expected, actual)
    if field_name == "budget":
        return _normalize_budget(expected) == _normalize_budget(actual_string)
    if field_name == "purchase_type":
        return _normalize_purchase_type(expected) == _normalize_purchase_type(
            actual_string
        )
    return " ".join(_tokens(expected)) == " ".join(_tokens(actual_string))


def _field_metrics(
    case: GoldenExample, prediction: EvaluationPrediction
) -> dict[str, float]:
    if case.expected_fields is None:
        return {}
    actual = prediction.fields
    metrics: dict[str, float] = {}
    for field_name in case.expected_fields.model_fields_set:
        expected_value = getattr(case.expected_fields, field_name)
        actual_value = getattr(actual, field_name) if actual is not None else None
        metrics[f"field_{field_name}_match"] = float(
            _field_matches(field_name, expected_value, actual_value)
        )
    return metrics


def _behavior_checks(case: GoldenExample, answer: str | None) -> list[bool]:
    if case.expected_behavior is None and case.expected_max_questions is None:
        return []
    answer_text = answer or ""
    question_count = answer_text.count("?")
    default_limits = {
        "answer_only": 0,
        "answer_before_qualification": 1,
        "abstain": 0,
    }
    max_questions = case.expected_max_questions
    if max_questions is None and case.expected_behavior is not None:
        max_questions = default_limits[case.expected_behavior]

    checks: list[bool] = []
    if max_questions is not None:
        checks.append(question_count <= max_questions)

    if case.expected_behavior == "answer_before_qualification" and case.required_facts:
        answer_part = answer_text.split("?", maxsplit=1)[0]
        checks.append(
            all(_fact_matches(fact, answer_part) for fact in case.required_facts)
        )
    return checks


def score_case(
    case: LoadedCase, prediction: EvaluationPrediction, *, top_k: int = 3
) -> dict[str, float]:
    example = case.example
    metrics: dict[str, float] = {}

    if case.evaluation_type == "retrieval":
        metrics.update(
            _rank_metrics(
                example.relevance,
                prediction.retrieved_document_ids,
                top_k=top_k,
            )
        )

    if case.evaluation_type == "generation":
        if example.required_facts:
            matched = sum(
                _fact_matches(fact, prediction.answer)
                for fact in example.required_facts
            )
            metrics["required_fact_coverage"] = matched / len(example.required_facts)
        if example.forbidden_claims:
            matched = sum(
                _fact_matches(claim, prediction.answer)
                for claim in example.forbidden_claims
            )
            metrics["forbidden_claim_rate"] = matched / len(example.forbidden_claims)

    if case.evaluation_type == "business":
        checks = [bool(prediction.answer and prediction.answer.strip())]
        checks.extend(_behavior_checks(example, prediction.answer))
        checks.extend(
            _fact_matches(fact, prediction.answer) for fact in example.required_facts
        )
        checks.extend(
            not _fact_matches(claim, prediction.answer)
            for claim in example.forbidden_claims
        )
        if example.expected_intent is not None:
            checks.append(
                _normalize(example.expected_intent) == _normalize(prediction.intent)
            )
        if example.expected_state is not None:
            checks.append(
                _normalize(example.expected_state) == _normalize(prediction.state)
            )
        if example.expected_missing_fields is not None:
            checks.append(
                set(example.expected_missing_fields)
                == set(prediction.missing_fields or [])
            )
        checks.extend(
            value == 1.0 for value in _field_metrics(example, prediction).values()
        )
        metrics["business_dialogue_success"] = float(all(checks))
    return metrics


def _aggregate_metrics(
    rows: Iterable[dict[str, float]],
) -> dict[str, dict[str, float | int]]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for name, value in row.items():
            values[name].append(value)
    return {
        name: {"value": round(fmean(metric_values), 4), "n": len(metric_values)}
        for name, metric_values in sorted(values.items())
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _operational_metrics(
    cases: list[LoadedCase], predictions: Mapping[str, EvaluationPrediction]
) -> dict[str, Any]:
    selected = [
        predictions[case.example.id] for case in cases if case.example.id in predictions
    ]
    latency = [item.latency_ms for item in selected if item.latency_ms is not None]
    result: dict[str, Any] = {}
    if latency:
        result["latency_ms"] = {
            "mean": round(fmean(latency), 2),
            "p50": round(_percentile(latency, 0.5), 2),
            "p95": round(_percentile(latency, 0.95), 2),
            "n": len(latency),
        }
    return result


def _missing_metrics(case: LoadedCase, *, top_k: int) -> dict[str, float]:
    expected = score_case(case, EvaluationPrediction(id=case.example.id), top_k=top_k)
    return {name: 1.0 if name == "forbidden_claim_rate" else 0.0 for name in expected}


def evaluate(
    cases: list[LoadedCase],
    predictions: Mapping[str, EvaluationPrediction],
    *,
    top_k: int = 3,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    known_ids = {case.example.id for case in cases}
    for case in cases:
        prediction = predictions.get(case.example.id)
        if prediction is None:
            metrics = _missing_metrics(case, top_k=top_k)
        else:
            metrics = score_case(case, prediction, top_k=top_k)
        results.append(
            {
                "id": case.example.id,
                "dataset": case.dataset_name,
                "evaluation_type": case.evaluation_type,
                "split": case.example.split,
                "category": case.example.category,
                "metrics": metrics,
            }
        )

    by_type: dict[str, list[dict[str, float]]] = defaultdict(list)
    by_split: dict[str, list[dict[str, float]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, float]]] = defaultdict(list)
    for result in results:
        by_type[result["evaluation_type"]].append(result["metrics"])
        by_split[result["split"]].append(result["metrics"])
        key = f"{result['evaluation_type']}:{result['category']}"
        by_category[key].append(result["metrics"])

    missing_count = sum(case.example.id not in predictions for case in cases)
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "metadata": metadata or {},
        "case_count": len(cases),
        "prediction_count": sum(case.example.id in predictions for case in cases),
        "missing_prediction_count": missing_count,
        "unexpected_prediction_ids": sorted(set(predictions) - known_ids),
        "operational": _operational_metrics(cases, predictions),
        "metrics": _aggregate_metrics(result["metrics"] for result in results),
        "metrics_by_type": {
            name: _aggregate_metrics(rows) for name, rows in sorted(by_type.items())
        },
        "splits": {
            name: _aggregate_metrics(rows) for name, rows in sorted(by_split.items())
        },
        "categories": {
            name: _aggregate_metrics(rows) for name, rows in sorted(by_category.items())
        },
        "cases": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate or evaluate Innova datasets")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--repetition", type=int)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cases = load_cases(args.dataset)
    if args.predictions is None:
        by_type: dict[str, int] = defaultdict(int)
        by_split: dict[str, int] = defaultdict(int)
        for case in cases:
            by_type[case.evaluation_type] += 1
            by_split[case.example.split] += 1
        report: dict[str, Any] = {
            "schema_version": "2.0",
            "valid": True,
            "case_count": len(cases),
            "case_count_by_type": dict(sorted(by_type.items())),
            "case_count_by_split": dict(sorted(by_split.items())),
            "categories": sorted({case.example.category for case in cases}),
        }
    else:
        report = evaluate(
            cases,
            load_predictions(args.predictions, repetition=args.repetition),
            top_k=args.top_k,
        )

    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
