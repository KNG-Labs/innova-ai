from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from time import perf_counter
from typing import Any, Iterable
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import build_embedding_client
from app.db.session import create_engine, create_session_maker
from app.models.knowledge_model import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge_schema import KnowledgeDocumentCreate
from app.service.knowledge_ingestion_service import (
    KnowledgeIngestionService,
    chunk_text,
)
from app.service.knowledge_retrieval_service import KnowledgeRetrievalService
from evals.runners.evaluate import LoadedCase, evaluate, load_cases
from evals.schema import EvaluationPrediction, PredictionFields


_EVALUATION_TYPES = {"retrieval", "generation", "business"}
_RETRIEVAL_METRIC_PREFIXES = (
    "retrieval_",
    "context_precision@",
    "abstention_accuracy@",
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _anonymous_id(case_id: str) -> str:
    return f"eval-{uuid4().hex[:12]}-{case_id}"[:128]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _dataset_sha256(path: Path) -> str:
    files = [path] if path.is_file() else sorted(path.rglob("*.dataset.json*"))
    digest = hashlib.sha256()
    for file_path in files:
        digest.update(
            str(
                file_path.relative_to(path) if path.is_dir() else file_path.name
            ).encode()
        )
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_metadata() -> dict[str, Any]:
    environment_commit = os.getenv("EVAL_GIT_COMMIT", "").strip()
    environment_dirty = os.getenv("EVAL_GIT_DIRTY", "").strip().lower()
    if environment_commit or environment_dirty:
        dirty_values = {"true": True, "1": True, "false": False, "0": False}
        return {
            "commit": environment_commit or None,
            "dirty": dirty_values.get(environment_dirty),
        }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )

    try:
        revision = run("rev-parse", "HEAD")
        status = run("status", "--porcelain")
    except OSError:
        return {"commit": None, "dirty": None}
    return {
        "commit": revision.stdout.strip() if revision.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
    }


async def _collect_api_case(
    client: httpx.AsyncClient, case: LoadedCase
) -> EvaluationPrediction:
    started = perf_counter()
    anonymous_id = _anonymous_id(case.example.id)
    response_payload: dict[str, Any] | None = None

    for content in [*case.example.setup_messages, case.example.question]:
        response = await client.post(
            "/message",
            json={
                "anonymous_id": anonymous_id,
                "channel": "website",
                "content": content,
            },
        )
        response.raise_for_status()
        response_payload = response.json()

    if response_payload is None:  # pragma: no cover - schema requires a question
        raise RuntimeError(f"Case {case.example.id} did not produce an API response")

    qualification: dict[str, Any] = {}
    contact: dict[str, Any] | str | None = None
    lead_id = response_payload.get("lead_id")
    if lead_id:
        lead_response = await client.get(f"/leads/{lead_id}")
        lead_response.raise_for_status()
        lead = lead_response.json()
        qualification = lead.get("qualification") or {}
        contact = lead.get("contact")

    return EvaluationPrediction(
        id=case.example.id,
        answer=response_payload.get("answer"),
        intent=response_payload.get("intent"),
        fields=PredictionFields(
            car_model=qualification.get("car_model"),
            budget=qualification.get("budget"),
            purchase_type=qualification.get("purchase_type"),
            contact=contact,
        ),
        state=response_payload.get("state"),
        missing_fields=response_payload.get("missing_fields"),
        latency_ms=(perf_counter() - started) * 1000,
    )


async def collect_api_predictions(
    cases: list[LoadedCase],
    api_base_url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[EvaluationPrediction]:
    """Collect generation/business predictions through the public API."""

    owns_client = client is None
    current_client = client or httpx.AsyncClient(
        base_url=api_base_url.rstrip("/"), timeout=90.0
    )
    try:
        predictions: list[EvaluationPrediction] = []
        for case in cases:
            predictions.append(await _collect_api_case(current_client, case))
        return predictions
    finally:
        if owns_client:
            await current_client.aclose()


def _load_corpus(corpus_path: Path) -> list[dict[str, str]]:
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Evaluation corpus must be a JSON array")
    documents = [KnowledgeDocumentCreate.model_validate(item) for item in payload]
    titles = [document.title for document in documents]
    if len(titles) != len(set(titles)):
        raise ValueError("Evaluation corpus contains duplicate titles")
    return [document.model_dump() for document in documents]


def _load_manifest(
    path: Path, corpus_path: Path
) -> tuple[dict[str, str], list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "2.0":
        raise ValueError("Corpus manifest schema_version must be 2.0")
    corpus_hash = _sha256_file(corpus_path)
    if payload.get("source_sha256") != corpus_hash:
        raise ValueError(
            "Corpus hash differs from manifest; regenerate the frozen manifest"
        )

    source_documents = _load_corpus(corpus_path)
    source_by_title = {document["title"]: document for document in source_documents}
    manifest_documents = payload.get("documents")
    if not isinstance(manifest_documents, list):
        raise ValueError("Corpus manifest documents must be a list")

    title_to_id: dict[str, str] = {}
    stable_ids: set[str] = set()
    for item in manifest_documents:
        title = item.get("title")
        stable_id = item.get("id")
        if not isinstance(title, str) or not isinstance(stable_id, str):
            raise ValueError("Every manifest document requires string id and title")
        if title in title_to_id or stable_id in stable_ids:
            raise ValueError("Corpus manifest IDs and titles must be unique")
        source = source_by_title.get(title)
        if source is None:
            raise ValueError(f"Manifest title is absent from corpus: {title}")
        content_hash = _sha256_bytes(source["content"].encode("utf-8"))
        if item.get("content_sha256") != content_hash:
            raise ValueError(f"Content hash differs for manifest document: {title}")
        expected_chunks = [
            f"{stable_id}#{index}"
            for index, _chunk in enumerate(chunk_text(source["content"]))
        ]
        if item.get("chunk_ids") != expected_chunks:
            raise ValueError(f"Chunk IDs differ for manifest document: {title}")
        title_to_id[title] = stable_id
        stable_ids.add(stable_id)

    if set(title_to_id) != set(source_by_title):
        missing = sorted(set(source_by_title) - set(title_to_id))
        raise ValueError(f"Corpus manifest does not cover the entire corpus: {missing}")
    return title_to_id, source_documents


def _assert_eval_database(database_url: str, *, allow_non_eval_database: bool) -> str:
    database_name = make_url(database_url).database or ""
    if not allow_non_eval_database and not database_name.endswith(("_eval", "_test")):
        raise RuntimeError(
            "Refusing to reset a non-evaluation database. Use a database ending in "
            "'_eval' or '_test', or pass --allow-non-eval-database explicitly."
        )
    return database_name


async def _reset_corpus(
    service: KnowledgeIngestionService,
    db_session: AsyncSession,
    source_documents: list[dict[str, str]],
) -> None:
    await db_session.execute(delete(KnowledgeChunk))
    await db_session.execute(delete(KnowledgeDocument))
    await db_session.commit()
    await service.ingest_many(
        [
            KnowledgeDocumentCreate.model_validate(document)
            for document in source_documents
        ]
    )


async def _verify_database_corpus(
    db_session: AsyncSession, source_documents: list[dict[str, str]]
) -> None:
    result = await db_session.execute(
        select(
            KnowledgeDocument.title, KnowledgeDocument.source, KnowledgeDocument.content
        )
    )
    database_documents = sorted(result.all())
    expected_documents = sorted(
        (document["title"], document["source"], document["content"])
        for document in source_documents
    )
    if database_documents != expected_documents:
        raise RuntimeError(
            "Database knowledge corpus is not the exact frozen evaluation corpus"
        )


async def collect_retrieval_predictions(
    cases: list[LoadedCase],
    *,
    database_url: str,
    manifest_path: Path,
    corpus_path: Path,
    prepare_corpus: bool,
    allow_non_eval_database: bool = False,
    top_k: int = 3,
    min_score: float = 0.2,
) -> list[EvaluationPrediction]:
    """Run production retrieval against the exact frozen evaluation corpus."""

    _assert_eval_database(database_url, allow_non_eval_database=allow_non_eval_database)
    title_to_id, source_documents = _load_manifest(manifest_path, corpus_path)
    engine = create_engine(database_url)
    session_maker = create_session_maker(engine)
    embedding_client = build_embedding_client()
    try:
        async with session_maker() as db_session:
            ingestion = KnowledgeIngestionService(db_session, embedding_client)
            if prepare_corpus:
                await _reset_corpus(ingestion, db_session, source_documents)
            else:
                await _verify_database_corpus(db_session, source_documents)

            retrieval = KnowledgeRetrievalService(
                db_session,
                embedding_client,
                top_k=top_k,
                min_score=min_score,
            )
            predictions: list[EvaluationPrediction] = []
            for case in cases:
                started = perf_counter()
                chunks = await retrieval.retrieve(case.example.question)
                document_ids: list[str] = []
                for retrieved in chunks:
                    document = await db_session.get(
                        KnowledgeDocument, retrieved.document_id
                    )
                    if document is None:
                        continue
                    stable_document_id = title_to_id.get(document.title)
                    if stable_document_id is None:
                        raise RuntimeError(
                            f"Retrieved document outside frozen corpus: {document.title}"
                        )
                    document_ids.append(stable_document_id)
                predictions.append(
                    EvaluationPrediction(
                        id=case.example.id,
                        retrieved_document_ids=_unique(document_ids),
                        latency_ms=(perf_counter() - started) * 1000,
                    )
                )
            return predictions
    finally:
        await engine.dispose()


async def prepare_evaluation_corpus(
    *,
    database_url: str,
    manifest_path: Path,
    corpus_path: Path,
    allow_non_eval_database: bool = False,
) -> None:
    _assert_eval_database(database_url, allow_non_eval_database=allow_non_eval_database)
    _title_to_id, source_documents = _load_manifest(manifest_path, corpus_path)
    engine = create_engine(database_url)
    session_maker = create_session_maker(engine)
    embedding_client = build_embedding_client()
    try:
        async with session_maker() as db_session:
            ingestion = KnowledgeIngestionService(db_session, embedding_client)
            await _reset_corpus(ingestion, db_session, source_documents)
    finally:
        await engine.dispose()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Innova AI and calculate reproducible evaluation metrics"
    )
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets"))
    parser.add_argument(
        "--evaluation-type",
        action="append",
        choices=sorted(_EVALUATION_TYPES),
        help="May be repeated; defaults to every type found in the dataset",
    )
    parser.add_argument(
        "--split",
        action="append",
        choices=["calibration", "test", "regression"],
        help="May be repeated; defaults to every split found in the dataset",
    )
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("INNOVA_EVAL_API_URL", "http://localhost:8000"),
    )
    parser.add_argument("--database-url", default=os.getenv("EVAL_DATABASE_URL"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/datasets/retrieval/corpus_manifest.json"),
    )
    parser.add_argument(
        "--corpus", type=Path, default=Path("docs/RAG/Данные для RAG.txt")
    )
    parser.add_argument("--skip-corpus-prepare", action="store_true")
    parser.add_argument("--allow-non-eval-database", action="store_true")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.2)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--predictions-output", type=Path)
    return parser.parse_args()


def _metric_group_across_runs(
    groups: list[dict[str, dict[str, float | int]]],
    *,
    fixed_retrieval: bool = False,
) -> dict[str, dict[str, float | int]]:
    names = sorted({name for group in groups for name in group})
    result: dict[str, dict[str, float | int]] = {}
    for name in names:
        metric_groups = [group for group in groups if name in group]
        if fixed_retrieval and name.startswith(_RETRIEVAL_METRIC_PREFIXES):
            metric_groups = metric_groups[:1]
        values = [float(group[name]["value"]) for group in metric_groups]
        case_counts = [int(group[name]["n"]) for group in metric_groups]
        if len(set(case_counts)) != 1:
            raise ValueError(f"Metric {name} has different case counts across runs")
        result[name] = {
            "value": round(fmean(values), 4),
            "n": case_counts[0],
            "observation_n": sum(case_counts),
            "runs": len(values),
            "run_stddev": round(pstdev(values), 4) if len(values) > 1 else 0.0,
        }
    return result


def _merge_reports(
    reports: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    fixed_retrieval: bool = False,
) -> dict[str, Any]:
    if len(reports) == 1:
        report = reports[0]
        report["metadata"] = metadata
        report["run_count"] = 1
        return report

    prediction_counts = [int(report["prediction_count"]) for report in reports]
    missing_counts = [int(report["missing_prediction_count"]) for report in reports]
    if len(set(prediction_counts)) != 1 or len(set(missing_counts)) != 1:
        raise ValueError("Prediction counts differ across evaluation runs")

    grouped_sections: dict[str, Any] = {}
    for section in ("metrics_by_type", "splits", "categories"):
        group_names = sorted({name for report in reports for name in report[section]})
        grouped_sections[section] = {
            name: _metric_group_across_runs(
                [
                    report[section][name]
                    for report in reports
                    if name in report[section]
                ],
                fixed_retrieval=fixed_retrieval,
            )
            for name in group_names
        }
    cases_by_id: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        for case in report["cases"]:
            cases_by_id.setdefault(case["id"], []).append(case)
    merged_cases = []
    for case_id, run_cases in sorted(cases_by_id.items()):
        first = run_cases[0]
        metric_names = sorted({name for case in run_cases for name in case["metrics"]})
        case_metrics: dict[str, dict[str, float | int]] = {}
        for metric_name in metric_names:
            selected_cases = run_cases
            if fixed_retrieval and first["evaluation_type"] == "retrieval":
                selected_cases = run_cases[:1]
            values = [
                float(case["metrics"][metric_name])
                for case in selected_cases
                if metric_name in case["metrics"]
            ]
            case_metrics[metric_name] = {
                "value": round(fmean(values), 4),
                "n": 1,
                "observation_n": len(values),
                "runs": len(values),
                "run_stddev": round(pstdev(values), 4) if len(values) > 1 else 0.0,
            }
        merged_cases.append(
            {
                "id": case_id,
                "dataset": first["dataset"],
                "evaluation_type": first["evaluation_type"],
                "split": first["split"],
                "category": first["category"],
                "metrics": case_metrics,
            }
        )
    return {
        "schema_version": "2.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "metadata": metadata,
        "run_count": len(reports),
        "case_count": reports[0]["case_count"],
        "prediction_count": prediction_counts[0],
        "prediction_observation_count": sum(prediction_counts),
        "missing_prediction_count": missing_counts[0],
        "missing_prediction_observation_count": sum(missing_counts),
        "unexpected_prediction_ids": sorted(
            {
                prediction_id
                for report in reports
                for prediction_id in report["unexpected_prediction_ids"]
            }
        ),
        "metrics": _metric_group_across_runs(
            [report["metrics"] for report in reports],
            fixed_retrieval=fixed_retrieval,
        ),
        **grouped_sections,
        "operational_by_run": [report["operational"] for report in reports],
        "runs": [
            {
                "repetition": index,
                "generated_at": report["generated_at"],
                "metrics": report["metrics"],
            }
            for index, report in enumerate(reports, start=1)
        ],
        "cases": merged_cases,
    }


def _run_metadata(
    args: argparse.Namespace, *, duration_seconds: float
) -> dict[str, Any]:
    database_name = make_url(args.database_url).database if args.database_url else None
    llm_provider = os.getenv("LLM_PROVIDER", "stub")
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fake")
    return {
        "git": _git_metadata(),
        "dataset_sha256": _dataset_sha256(args.dataset),
        "corpus_sha256": _sha256_file(args.corpus),
        "manifest_sha256": _sha256_file(args.manifest),
        "llm": {
            "provider": llm_provider,
            "model": os.getenv("AG2_MODEL") if llm_provider == "ag2" else None,
        },
        "embedding": {
            "provider": embedding_provider,
            "model": (
                os.getenv("EMBEDDING_MODEL")
                if embedding_provider == "openrouter"
                else None
            ),
        },
        "retrieval": {"top_k": args.top_k, "min_score": args.min_score},
        "api_base_url": args.api_base_url,
        "database_name": database_name,
        "repetitions": args.repetitions,
        "selected_splits": sorted(args.split or ["calibration", "test", "regression"]),
        "duration_seconds": round(duration_seconds, 3),
    }


def _default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    commit = _git_metadata().get("commit") or "unknown"
    return Path("evals/reports/runs") / f"{timestamp}-{str(commit)[:8]}.json"


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.repetitions < 1:
        raise ValueError("--repetitions must be at least 1")
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1")
    if not -1.0 <= args.min_score <= 1.0:
        raise ValueError("--min-score must be between -1 and 1")

    cases = load_cases(args.dataset)
    selected_types = set(args.evaluation_type or _EVALUATION_TYPES)
    selected_splits = set(args.split or {"calibration", "test", "regression"})
    selected_cases = [
        case
        for case in cases
        if case.evaluation_type in selected_types
        and case.example.split in selected_splits
    ]
    if not selected_cases:
        raise ValueError("No evaluation cases matched the selected types")

    started = perf_counter()
    retrieval_cases = [
        case for case in selected_cases if case.evaluation_type == "retrieval"
    ]
    api_cases = [case for case in selected_cases if case.evaluation_type != "retrieval"]

    if retrieval_cases and not args.database_url:
        raise RuntimeError("EVAL_DATABASE_URL is required for retrieval evaluation")
    if not args.skip_corpus_prepare and args.database_url:
        await prepare_evaluation_corpus(
            database_url=args.database_url,
            manifest_path=args.manifest,
            corpus_path=args.corpus,
            allow_non_eval_database=args.allow_non_eval_database,
        )

    fixed_retrieval_predictions: list[EvaluationPrediction] = []
    if retrieval_cases:
        fixed_retrieval_predictions = await collect_retrieval_predictions(
            retrieval_cases,
            database_url=args.database_url,
            manifest_path=args.manifest,
            corpus_path=args.corpus,
            prepare_corpus=False,
            allow_non_eval_database=args.allow_non_eval_database,
            top_k=args.top_k,
            min_score=args.min_score,
        )
    reports: list[dict[str, Any]] = []
    predictions_by_run: list[list[EvaluationPrediction]] = []
    for _repetition in range(args.repetitions):
        api_predictions = (
            await collect_api_predictions(api_cases, args.api_base_url)
            if api_cases
            else []
        )
        predictions = [*fixed_retrieval_predictions, *api_predictions]
        predictions_by_run.append(predictions)
        reports.append(
            evaluate(
                selected_cases,
                {prediction.id: prediction for prediction in predictions},
                top_k=args.top_k,
            )
        )

    metadata = _run_metadata(args, duration_seconds=perf_counter() - started)
    report = _merge_reports(reports, metadata, fixed_retrieval=True)
    output = args.output or _default_output_path()
    predictions_output = args.predictions_output or output.with_name(
        f"{output.stem}.predictions.json"
    )
    _write_json(
        predictions_output,
        {
            "schema_version": "2.0",
            "metadata": metadata,
            "runs": [
                {
                    "repetition": repetition,
                    "predictions": [
                        prediction.model_dump(mode="json") for prediction in predictions
                    ],
                }
                for repetition, predictions in enumerate(predictions_by_run, start=1)
            ],
        },
    )
    _write_json(output, report)
    report["report_path"] = str(output)
    report["predictions_path"] = str(predictions_output)
    return report


def main() -> None:
    load_dotenv()
    args = _parse_args()
    report = asyncio.run(_run(args))
    print(
        json.dumps(
            {
                "case_count": report["case_count"],
                "missing_prediction_count": report["missing_prediction_count"],
                "metrics": report["metrics"],
                "report_path": report["report_path"],
                "predictions_path": report["predictions_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
