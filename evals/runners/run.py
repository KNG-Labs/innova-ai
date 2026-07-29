from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from time import perf_counter
from typing import Any, Awaitable, Callable, Iterable, Sequence, cast
from uuid import UUID, uuid4

import httpx
from deepeval.evaluate import (
    AsyncConfig,
    CacheConfig,
    DisplayConfig,
    evaluate as deepeval_evaluate,
)
from deepeval.models import DeepEvalBaseLLM
from deepeval.evaluate.types import EvaluationResult
from deepeval.metrics import BaseConversationalMetric, BaseMetric
from deepeval.test_case import ConversationalTestCase, LLMTestCase
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.client.embedding_client import build_embedding_client
from app.client.retrieval_planner_client import FakeRetrievalPlannerClient
from app.db.session import create_engine, create_session_maker
from app.models.knowledge_model import KnowledgeChunk, KnowledgeDocument
from app.models.message_model import Message
from app.schemas.knowledge_schema import KnowledgeDocumentCreate
from app.service.knowledge_ingestion_service import (
    KnowledgeIngestionService,
    chunk_text,
)
from app.service.knowledge_retrieval_service import KnowledgeRetrievalService
from evals.judge import OpenRouterJudge
from evals.metrics import (
    AbstentionAccuracyAt10,
    BusinessDialogueSuccess,
    CaseCollectedMetric,
    ContextPrecisionAt10,
    ConversationalCaseCollectedMetric,
    ForbiddenClaimRate,
    RequiredFactCoverage,
    RetrievalMRRAt10,
    RetrievalRecallAt10,
)
from evals.runners.evaluate import (
    LoadedCase,
    build_conversational_dataset,
    build_single_turn_dataset,
    load_cases,
)
from evals.schema import (
    EvaluationPrediction,
    PredictionFields,
    TokenUsage,
    TranscriptTurn,
)


_EVALUATION_TYPES = {"retrieval", "generation", "business"}
_UsageLoader = Callable[[list[str]], Awaitable[dict[str, dict[str, Any] | None]]]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _anonymous_id(case_id: str) -> str:
    return f"eval-{uuid4().hex[:12]}-{case_id}"[:128]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _dataset_sha256(path: Path) -> str:
    files = [path] if path.is_file() else sorted(path.rglob("*.dataset.json"))
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
            ["git", *args], check=False, capture_output=True, text=True
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
    client: httpx.AsyncClient,
    case: LoadedCase,
    *,
    usage_loader: _UsageLoader | None,
) -> EvaluationPrediction:
    started = perf_counter()
    anonymous_id = _anonymous_id(case.example.id)
    response_payload: dict[str, Any] | None = None
    transcript: list[TranscriptTurn] = []
    assistant_message_ids: list[str] = []

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
        assistant_message_id = str(response_payload["assistant_message_id"])
        assistant_message_ids.append(assistant_message_id)
        transcript.extend(
            [
                TranscriptTurn(role="user", content=content),
                TranscriptTurn(
                    role="assistant",
                    content=response_payload.get("answer", ""),
                    assistant_message_id=assistant_message_id,
                ),
            ]
        )

    if response_payload is None:  # pragma: no cover - question is required
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

    usage_by_id = (
        await usage_loader(assistant_message_ids) if usage_loader is not None else {}
    )
    turn_usage = [
        _token_usage_from_metadata(usage_by_id.get(message_id))
        for message_id in assistant_message_ids
    ]
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
        transcript=transcript,
        turn_token_usage=turn_usage,
    )


async def collect_api_predictions(
    cases: list[LoadedCase],
    api_base_url: str,
    *,
    database_url: str | None = None,
    client: httpx.AsyncClient | None = None,
    usage_loader: _UsageLoader | None = None,
) -> list[EvaluationPrediction]:
    """Collect API outputs and persisted application token usage."""

    owns_client = client is None
    current_client = client or httpx.AsyncClient(
        base_url=api_base_url.rstrip("/"), timeout=90.0
    )
    engine = None
    if usage_loader is None and database_url:
        engine = create_engine(database_url)
        session_maker = create_session_maker(engine)

        async def load_usage(
            message_ids: list[str],
        ) -> dict[str, dict[str, Any] | None]:
            async with session_maker() as db_session:
                result = await db_session.execute(
                    select(Message.id, Message.message_metadata).where(
                        Message.id.in_([UUID(value) for value in message_ids])
                    )
                )
                return {
                    str(message_id): metadata for message_id, metadata in result.all()
                }

        usage_loader = load_usage
    try:
        return [
            await _collect_api_case(current_client, case, usage_loader=usage_loader)
            for case in cases
        ]
    finally:
        if owns_client:
            await current_client.aclose()
        if engine is not None:
            await engine.dispose()


def _token_usage_from_metadata(metadata: dict[str, Any] | None) -> TokenUsage | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("eval_token_usage")
    if not isinstance(value, dict):
        return None
    return TokenUsage.model_validate(
        {
            name: value.get(name)
            for name in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "calls",
                "complete",
            )
        }
    )


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
    if payload.get("source_sha256") != _sha256_file(corpus_path):
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
        if item.get("content_sha256") != _sha256_bytes(
            source["content"].encode("utf-8")
        ):
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
            KnowledgeDocument.title,
            KnowledgeDocument.source,
            KnowledgeDocument.content,
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
    top_k: int = 10,
    min_score: float = 0.2,
) -> list[EvaluationPrediction]:
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
                FakeRetrievalPlannerClient(),
                top_k=top_k,
                min_score=min_score,
            )
            predictions: list[EvaluationPrediction] = []
            for case in cases:
                started = perf_counter()
                result = await retrieval.retrieve(case.example.question)
                document_ids: list[str] = []
                retrieval_context: list[str] = []
                for retrieved in result.chunks:
                    document = await db_session.get(
                        KnowledgeDocument, retrieved.document_id
                    )
                    if document is None:
                        continue
                    stable_id = title_to_id.get(document.title)
                    if stable_id is None:
                        raise RuntimeError(
                            f"Retrieved document outside frozen corpus: {document.title}"
                        )
                    document_ids.append(stable_id)
                    retrieval_context.append(retrieved.content)
                predictions.append(
                    EvaluationPrediction(
                        id=case.example.id,
                        retrieved_document_ids=_unique(document_ids),
                        retrieval_context=retrieval_context,
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
            await _reset_corpus(
                KnowledgeIngestionService(db_session, embedding_client),
                db_session,
                source_documents,
            )
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Innova evals through DeepEval 4.1.4"
    )
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets"))
    parser.add_argument(
        "--evaluation-type",
        action="append",
        choices=sorted(_EVALUATION_TYPES),
    )
    parser.add_argument(
        "--split",
        action="append",
        choices=["calibration", "test", "regression"],
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
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=0.2)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--require-independent-judge", action="store_true")
    return parser.parse_args()


def _default_results_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    commit = _git_metadata().get("commit") or "unknown"
    return Path("evals/reports/runs") / f"{timestamp}-{str(commit)[:8]}"


def _check_judge_independence(
    judge_model: str,
    agent_model: str,
    *,
    require_independent: bool,
) -> bool:
    self_judge = bool(judge_model and agent_model and judge_model == agent_model)
    if not self_judge:
        return False
    message = (
        "WARNING: EVAL_JUDGE_MODEL совпадает с AG2_MODEL; manifest помечен "
        "self_judge=true"
    )
    if require_independent:
        raise RuntimeError(message)
    print(message, file=sys.stderr)
    return True


def _run_deepeval(
    test_cases: Sequence[LLMTestCase] | Sequence[ConversationalTestCase],
    metrics: Sequence[BaseMetric] | Sequence[BaseConversationalMetric],
    *,
    results_dir: Path,
    identifier: str,
) -> EvaluationResult:
    return deepeval_evaluate(
        test_cases=cast(Any, list(test_cases)),
        metrics=cast(Any, list(metrics)),
        identifier=identifier,
        async_config=AsyncConfig(run_async=False),
        display_config=DisplayConfig(
            show_indicator=False,
            print_results=True,
            results_folder=str(results_dir),
            results_subfolder=f"deepeval/{identifier}",
            truncate_passing_cases=False,
            inspect_after_run=False,
            file_type="md",
            file_output_dir=str(results_dir),
        ),
        cache_config=CacheConfig(write_cache=False, use_cache=False),
    )


def _records_from_result(
    result: EvaluationResult, *, repetition: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for test_result in result.test_results:
        metadata = test_result.metadata or {}
        for metric in test_result.metrics_data or []:
            if metric.name == "_case_collected" or metric.score is None:
                continue
            records.append(
                {
                    "id": metadata.get("id") or test_result.name,
                    "dataset": metadata.get("dataset"),
                    "evaluation_type": metadata.get("evaluation_type"),
                    "split": metadata.get("split"),
                    "category": metadata.get("category"),
                    "metric": metric.name,
                    "score": float(metric.score),
                    "reason": metric.reason,
                    "repetition": repetition,
                }
            )
    return records


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_metric[record["metric"]].append(record)
    metrics: dict[str, dict[str, Any]] = {}
    for name, rows in sorted(by_metric.items()):
        values = [row["score"] for row in rows]
        run_means: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            run_means[row["repetition"]].append(row["score"])
        means = [fmean(items) for items in run_means.values()]
        metrics[name] = {
            "value": round(fmean(values), 4),
            "n": len({row["id"] for row in rows}),
            "observation_n": len(values),
            "runs": len(means),
            "run_stddev": round(pstdev(means), 4) if len(means) > 1 else 0.0,
        }

    cases: dict[str, dict[str, Any]] = {}
    for row in records:
        case = cases.setdefault(
            row["id"],
            {
                "id": row["id"],
                "dataset": row["dataset"],
                "evaluation_type": row["evaluation_type"],
                "split": row["split"],
                "category": row["category"],
                "metrics": defaultdict(list),
            },
        )
        case["metrics"][row["metric"]].append(
            {
                "score": row["score"],
                "reason": row["reason"],
                "repetition": row["repetition"],
            }
        )
    serialized_cases = []
    for case in cases.values():
        case["metrics"] = dict(case["metrics"])
        serialized_cases.append(case)
    return {
        "metrics": metrics,
        "cases": sorted(serialized_cases, key=lambda x: x["id"]),
    }


def _token_usage_summary(
    runs: list[list[EvaluationPrediction]],
    case_types: dict[str, str],
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for predictions in runs:
        for prediction in predictions:
            evaluation_type = case_types.get(prediction.id)
            if evaluation_type not in {"generation", "business"}:
                continue
            known_turns = [
                usage
                for usage in prediction.turn_token_usage
                if usage is not None and usage.complete
            ]
            expected_turn_n = max(
                len(prediction.turn_token_usage),
                sum(turn.role == "assistant" for turn in prediction.transcript),
                1,
            )
            missing_usage_n = expected_turn_n - len(known_turns)
            complete = missing_usage_n == 0
            samples.append(
                {
                    "evaluation_type": evaluation_type,
                    "complete": complete,
                    "missing_usage_n": missing_usage_n,
                    "prompt_tokens": sum(item.prompt_tokens for item in known_turns),
                    "completion_tokens": sum(
                        item.completion_tokens for item in known_turns
                    ),
                    "total_tokens": sum(item.total_tokens for item in known_turns),
                    "turns": known_turns,
                }
            )

    def summarize(selected: list[dict[str, Any]]) -> dict[str, Any]:
        complete = [item for item in selected if item["complete"]]
        turns = [turn for item in selected for turn in item["turns"]]
        return {
            "average_prompt_tokens_per_case": _mean_or_none(
                [item["prompt_tokens"] for item in complete]
            ),
            "average_completion_tokens_per_case": _mean_or_none(
                [item["completion_tokens"] for item in complete]
            ),
            "average_total_tokens_per_case": _mean_or_none(
                [item["total_tokens"] for item in complete]
            ),
            "average_total_tokens_per_assistant_turn": _mean_or_none(
                [item.total_tokens for item in turns]
            ),
            "case_n": len(complete),
            "expected_case_n": len(selected),
            "turn_n": len(turns),
            "missing_usage_n": sum(item["missing_usage_n"] for item in selected),
            "incomplete": len(complete) != len(selected),
        }

    overall = summarize(samples)
    return {
        "average_agent_token_usage": {
            "value": overall["average_total_tokens_per_case"],
            "n": overall["case_n"],
            "expected_n": overall["expected_case_n"],
            "incomplete": overall["incomplete"],
            "missing_usage_n": overall["missing_usage_n"],
        },
        "breakdown": {
            "overall": overall,
            "generation": summarize(
                [item for item in samples if item["evaluation_type"] == "generation"]
            ),
            "business": summarize(
                [item for item in samples if item["evaluation_type"] == "business"]
            ),
        },
    }


def _mean_or_none(values: list[int]) -> float | None:
    return round(fmean(values), 2) if values else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
    os.environ["CONFIDENT_API_KEY"] = ""
    os.environ["DEEPEVAL_NO_INSPECT_PROMPT"] = "1"
    if args.repetitions < 1:
        raise ValueError("--repetitions must be at least 1")
    if args.top_k != 10:
        raise ValueError("All retrieval metrics are fixed at K=10; use --top-k 10")
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
    retrieval_cases = [
        case for case in selected_cases if case.evaluation_type == "retrieval"
    ]
    api_cases = [case for case in selected_cases if case.evaluation_type != "retrieval"]
    if (retrieval_cases or api_cases) and not args.database_url:
        raise RuntimeError("EVAL_DATABASE_URL is required for evaluation")

    judge_model = os.getenv("EVAL_JUDGE_MODEL", "").strip()
    ag2_model = os.getenv("AG2_MODEL", "").strip()
    judge_needed = any(
        case.evaluation_type in {"generation", "business"} for case in selected_cases
    )
    if judge_needed and not judge_model and getattr(args, "judge", None) is None:
        raise RuntimeError("EVAL_JUDGE_MODEL is required for judge metrics")
    self_judge = _check_judge_independence(
        judge_model,
        ag2_model,
        require_independent=args.require_independent_judge,
    )
    judge = getattr(args, "judge", None)
    if judge_needed and judge is None:
        judge = OpenRouterJudge(judge_model)
    typed_judge = cast(DeepEvalBaseLLM, judge)

    started = perf_counter()
    results_dir = args.results_dir or _default_results_dir()
    results_dir.mkdir(parents=True, exist_ok=True)
    if not args.skip_corpus_prepare:
        await prepare_evaluation_corpus(
            database_url=args.database_url,
            manifest_path=args.manifest,
            corpus_path=args.corpus,
            allow_non_eval_database=args.allow_non_eval_database,
        )

    retrieval_predictions = (
        await collect_retrieval_predictions(
            retrieval_cases,
            database_url=args.database_url,
            manifest_path=args.manifest,
            corpus_path=args.corpus,
            prepare_corpus=False,
            allow_non_eval_database=args.allow_non_eval_database,
            top_k=10,
            min_score=args.min_score,
        )
        if retrieval_cases
        else []
    )
    prediction_runs: list[list[EvaluationPrediction]] = []
    records: list[dict[str, Any]] = []

    if retrieval_cases:
        by_id = {item.id: item for item in retrieval_predictions}
        dataset = build_single_turn_dataset(retrieval_cases, by_id)
        retrieval_test_cases = cast(list[LLMTestCase], dataset.test_cases)
        answerable = [
            test_case
            for test_case in retrieval_test_cases
            if (test_case.metadata or {}).get("answerable")
        ]
        unanswerable = [
            test_case
            for test_case in retrieval_test_cases
            if not (test_case.metadata or {}).get("answerable")
        ]
        if answerable:
            result = _run_deepeval(
                answerable,
                [
                    RetrievalRecallAt10(),
                    RetrievalMRRAt10(),
                    ContextPrecisionAt10(),
                    CaseCollectedMetric(),
                ],
                results_dir=results_dir,
                identifier="retrieval-answerable",
            )
            records.extend(_records_from_result(result, repetition=1))
        if unanswerable:
            result = _run_deepeval(
                unanswerable,
                [AbstentionAccuracyAt10(), CaseCollectedMetric()],
                results_dir=results_dir,
                identifier="retrieval-unanswerable",
            )
            records.extend(_records_from_result(result, repetition=1))

    for repetition in range(1, args.repetitions + 1):
        api_predictions = (
            await collect_api_predictions(
                api_cases,
                args.api_base_url,
                database_url=args.database_url,
            )
            if api_cases
            else []
        )
        prediction_runs.append([*retrieval_predictions, *api_predictions])
        predictions = {item.id: item for item in api_predictions}
        generation = [
            case for case in api_cases if case.evaluation_type == "generation"
        ]
        if generation:
            dataset = build_single_turn_dataset(generation, predictions)
            generation_test_cases = cast(list[LLMTestCase], dataset.test_cases)
            required = [
                item
                for item in generation_test_cases
                if (item.metadata or {}).get("required_facts")
            ]
            forbidden = [
                item
                for item in generation_test_cases
                if (item.metadata or {}).get("forbidden_claims")
            ]
            if required:
                result = _run_deepeval(
                    required,
                    [
                        RequiredFactCoverage(typed_judge),
                        CaseCollectedMetric(),
                    ],
                    results_dir=results_dir,
                    identifier=f"generation-required-r{repetition}",
                )
                records.extend(_records_from_result(result, repetition=repetition))
            if forbidden:
                result = _run_deepeval(
                    forbidden,
                    [ForbiddenClaimRate(typed_judge), CaseCollectedMetric()],
                    results_dir=results_dir,
                    identifier=f"generation-forbidden-r{repetition}",
                )
                records.extend(_records_from_result(result, repetition=repetition))
        business = [case for case in api_cases if case.evaluation_type == "business"]
        if business:
            dataset = build_conversational_dataset(business, predictions)
            result = _run_deepeval(
                cast(list[ConversationalTestCase], dataset.test_cases),
                [
                    BusinessDialogueSuccess(typed_judge),
                    ConversationalCaseCollectedMetric(),
                ],
                results_dir=results_dir,
                identifier=f"business-r{repetition}",
            )
            records.extend(_records_from_result(result, repetition=repetition))

    duration = perf_counter() - started
    token_summary = _token_usage_summary(
        prediction_runs,
        {case.example.id: case.evaluation_type for case in api_cases},
    )
    token_metric = token_summary["average_agent_token_usage"]
    if token_metric["incomplete"]:
        print(
            "WARNING: average_agent_token_usage incomplete; "
            f"missing usage for {token_metric['missing_usage_n']} assistant turn(s)",
            file=sys.stderr,
        )
    summarized = _summarize_records(records)
    summarized["metrics"]["average_agent_token_usage"] = token_metric
    manifest = {
        "schema_version": "3.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "git": _git_metadata(),
        "dataset_sha256": _dataset_sha256(args.dataset),
        "corpus_sha256": _sha256_file(args.corpus),
        "manifest_sha256": _sha256_file(args.manifest),
        "models": {
            "agent": ag2_model or None,
            "judge": judge_model
            or (judge.get_model_name() if judge is not None else None),
            "embedding": os.getenv("EMBEDDING_MODEL"),
        },
        "self_judge": self_judge,
        "retrieval": {"top_k": 10, "min_score": args.min_score},
        "repetitions": args.repetitions,
        "selected_splits": sorted(selected_splits),
        "selected_evaluation_types": sorted(selected_types),
        "duration_seconds": round(duration, 3),
        "operational": {"token_usage": token_summary},
    }
    report = {
        "schema_version": "3.0",
        "generated_at": manifest["generated_at"],
        "case_count": len(selected_cases),
        "prediction_count": len(
            {prediction.id for run in prediction_runs for prediction in run}
            or {prediction.id for prediction in retrieval_predictions}
        ),
        "prediction_observation_count": sum(len(run) for run in prediction_runs)
        or len(retrieval_predictions),
        **summarized,
        "operational": {"token_usage": token_summary},
    }
    _write_json(
        results_dir / "predictions.json",
        {
            "schema_version": "3.0",
            "runs": [
                {
                    "repetition": index,
                    "predictions": [
                        item.model_dump(mode="json") for item in predictions
                    ],
                }
                for index, predictions in enumerate(prediction_runs, start=1)
            ],
        },
    )
    _write_json(results_dir / "manifest.json", manifest)
    _write_json(results_dir / "summary.json", report)
    report["results_dir"] = str(results_dir)
    return report


def main() -> None:
    report = asyncio.run(_run(_parse_args()))
    print(
        json.dumps(
            {
                "case_count": report["case_count"],
                "metrics": report["metrics"],
                "results_dir": report["results_dir"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
