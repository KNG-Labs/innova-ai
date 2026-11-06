"""Collect real RAG answers, then score them with DeepEval's Jev metrics."""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from deepeval import evaluate
from deepeval.dataset import Golden
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import TypeSafeModel
from deepeval.test_case import LLMTestCase
from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.di import close_app_state, init_app_state
from app.privacy import PiiSanitizer
from app.schemas.agent_schema import AgentMessageRequest
from app.schemas.knowledge_schema import KnowledgeDocumentCreate, RetrievedChunk
from app.service.agent_service import AgentService
from app.service.knowledge_ingestion_service import KnowledgeIngestionService
from app.service.knowledge_retrieval_service import (
    KnowledgeRetrievalService,
    format_chunks_for_prompt,
)

DATASET = Path("evals/datasets/generation/golden.dataset.json")
CORPUS = Path("docs/RAG/Данные для RAG.txt")
THRESHOLD = 0.7


class ReportedTypeSafeModel(TypeSafeModel):
    def __init__(self, model: str, **kwargs):
        self.response_models: set[str] = set()
        super().__init__(model=model, **kwargs)

    def _from_sdk_response(self, response):
        # DeepEval 4.3.3 otherwise discards the model returned by TypeSafe.
        self.response_models.add(response.model)
        return super()._from_sdk_response(response)


def load_goldens(path: Path, split: str, limit: int) -> list[Golden]:
    goldens = [Golden.model_validate(row) for row in json.loads(path.read_text())]
    names = [golden.name for golden in goldens]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("Golden names must be non-empty and unique")
    selected = [
        golden
        for golden in goldens
        if (golden.additional_metadata or {}).get("split") == split
        and (golden.additional_metadata or {}).get("answerable") is True
    ]
    if not selected:
        raise ValueError("No answerable generation cases match the split")
    return selected[:limit]


def require_eval_database(url: str) -> None:
    if not url:
        raise ValueError("Set EVAL_DATABASE_URL to a temporary PostgreSQL database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (
        parsed.database or ""
    ).endswith(("_test", "_eval")):
        raise ValueError("Use a temporary PostgreSQL database ending in _test or _eval")


class RecordingRetrieval(KnowledgeRetrievalService):
    """Keep the chunks returned to AgentService, without running search again."""

    chunks: tuple[RetrievedChunk, ...] = ()

    async def retrieve(self, query: str) -> tuple[RetrievedChunk, ...]:
        self.chunks = await super().retrieve(query)
        return self.chunks


def safe_case(case: LLMTestCase) -> LLMTestCase:
    payload = PiiSanitizer().sanitize_value(case.model_dump(mode="json"))
    PiiSanitizer.ensure_safe(payload)
    return LLMTestCase.model_validate(payload)


async def collect_cases(
    goldens: list[Golden], database_url: str, corpus: Path
) -> list[LLMTestCase]:
    require_eval_database(database_url)
    # Force all application resources into the same isolated evaluation run.
    os.environ.update(
        DATABASE_URL=database_url,
        TEST_DATABASE_URL=database_url,
        PYTHON_DOTENV_DISABLED="1",
        LEAD_DELIVERY_PROVIDER="disabled",
        REDIS_URL="",
        LANGFUSE_TRACING_ENABLED="false",
    )
    app = FastAPI()
    cases: list[LLMTestCase] = []
    try:
        await init_app_state(app)
        async with app.state.db_session_maker() as db:
            documents = [
                KnowledgeDocumentCreate.model_validate(row)
                for row in json.loads(corpus.read_text())
            ]
            await KnowledgeIngestionService(db, app.state.embedding_client).replace_all(
                documents
            )
            for golden in goldens:
                retrieval = RecordingRetrieval(
                    db,
                    app.state.embedding_client,
                    top_k=int(os.getenv("RAG_TOP_K", "5")),
                    min_score=float(os.getenv("RAG_MIN_SCORE", "0.2")),
                )
                service = AgentService(
                    db_session=db,
                    llm_client=app.state.llm_client,
                    queue_client=app.state.queue_client,
                    delivery_provider="disabled",
                    retrieval=retrieval,
                )
                response = await service.handle_message(
                    AgentMessageRequest(
                        anonymous_id=f"eval-{uuid4().hex}", content=golden.input
                    )
                )
                cases.append(
                    safe_case(
                        LLMTestCase(
                            name=golden.name,
                            input=golden.input,
                            actual_output=response.answer,
                            retrieval_context=[
                                format_chunks_for_prompt((chunk,))
                                for chunk in retrieval.chunks
                            ],
                            metadata={
                                "split": (golden.additional_metadata or {}).get(
                                    "split"
                                ),
                                "category": (golden.additional_metadata or {}).get(
                                    "category"
                                ),
                            },
                        )
                    )
                )
                print(f"Collected {golden.name}: {len(retrieval.chunks)} chunks")
    finally:
        await close_app_state(app)
    return cases


def score_cases(cases: list[LLMTestCase], output: Path) -> bool:
    if not cases or len({case.name for case in cases}) != len(cases):
        raise ValueError("Test cases must be non-empty and have unique names")
    cases = [safe_case(case) for case in cases]
    requested_model = os.getenv("EVAL_JEV_MODEL", "jev-latest")
    model = ReportedTypeSafeModel(model=requested_model)
    grounded = [case for case in cases if case.retrieval_context]
    missing_context = [case.name for case in cases if not case.retrieval_context]
    results = {"faithfulness_skipped_no_context": missing_context}
    passed = not missing_context
    try:
        for name, metric_class, selected in (
            ("answer_relevancy", AnswerRelevancyMetric, cases),
            ("faithfulness", FaithfulnessMetric, grounded),
        ):
            if not selected:
                continue
            result = evaluate(
                test_cases=selected,
                metrics=[
                    metric_class(
                        threshold=THRESHOLD,
                        eval_mode="system_one",
                        system_one_model=model,
                    )
                ],
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
        manifest_path = output / "manifest.json"
        manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        )
        manifest["judge"] = {
            "provider": "typesafe",
            "requested_model": requested_model,
            "response_models": sorted(model.response_models),
            "deepeval_version": version("deepeval"),
            "typesafe_sdk_version": version("typesafe-sdk"),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
    (output / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    )
    if missing_context:
        print(f"Faithfulness skipped (no context): {missing_context}")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument(
        "--split", choices=["calibration", "test", "regression"], default="test"
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.collect_only and args.predictions:
        parser.error("--collect-only and --predictions cannot be combined")
    if not args.collect_only and not os.getenv("TYPESAFE_API_KEY"):
        parser.error("Set TYPESAFE_API_KEY or run uv with --env-file .env")
    output = args.output or Path("evals/reports") / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    output.mkdir(parents=True, exist_ok=False)
    if args.predictions:
        cases = [
            safe_case(LLMTestCase.model_validate(row))
            for row in json.loads(args.predictions.read_text())
        ]
        manifest = {
            "predictions_sha256": hashlib.sha256(
                args.predictions.read_bytes()
            ).hexdigest()
        }
    else:
        database_url = os.environ.get("EVAL_DATABASE_URL", "")
        require_eval_database(database_url)
        goldens = load_goldens(args.dataset, args.split, args.limit)
        cases = asyncio.run(collect_cases(goldens, database_url, CORPUS))
        manifest = {
            "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "agent_sha256": hashlib.sha256(
                Path("app/client/ag2_agent_client.py").read_bytes()
            ).hexdigest(),
            "split": args.split,
            "llm_provider": os.getenv("LLM_PROVIDER", "stub"),
            "agent_model": os.getenv("AG2_MODEL"),
            "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "fake"),
            "embedding_model": os.getenv("EMBEDDING_MODEL"),
            "rag_top_k": int(os.getenv("RAG_TOP_K", "5")),
            "rag_min_score": float(os.getenv("RAG_MIN_SCORE", "0.2")),
        }
    (output / "test_cases.json").write_text(
        json.dumps(
            [case.model_dump(mode="json") for case in cases],
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    manifest.update(
        case_count=len(cases),
        threshold=THRESHOLD,
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Reports: {output}")
    if not args.collect_only and not score_cases(cases, output):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
