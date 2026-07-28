from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.client.retrieval_planner_client import (
    FakeRetrievalPlannerClient,
    RetrievalMode,
    RetrievalPlan,
    _parse_retrieval_plan,
)
from app.schemas.knowledge_schema import RetrievedChunk
from app.service.knowledge_retrieval_service import (
    KnowledgeRetrievalService,
    format_chunks_for_prompt,
)
from app.service.retrieval_selector import RetrievalCandidate, select_source

pytestmark = pytest.mark.unit


TRADE_IN_ID = UUID("00000000-0000-0000-0000-000000000001")
CREDIT_ID = UUID("00000000-0000-0000-0000-000000000002")


def _candidate(
    document_id: UUID,
    title: str,
    content: str,
    score: float,
    *,
    chunk_index: int = 0,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        document_id=document_id,
        chunk_id=uuid4(),
        chunk_index=chunk_index,
        title=title,
        score=score,
        content=content,
    )


@pytest.mark.parametrize(
    ("raw", "mode", "query"),
    [
        (
            '{"mode":"last_source","query":"  Условия   программы Trade-in "}',
            RetrievalMode.LAST_SOURCE,
            "Условия программы Trade-in",
        ),
        (
            '{"mode":"current","query":"Условия автокредитования"}',
            RetrievalMode.CURRENT,
            "Условия автокредитования",
        ),
        ('{"mode":"none","query":"лишнее"}', RetrievalMode.NONE, ""),
    ],
)
def test_parse_retrieval_plan(raw: str, mode: RetrievalMode, query: str) -> None:
    plan = _parse_retrieval_plan(raw)

    assert plan.mode == mode
    assert plan.query == query


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '{"mode":"last_source","query":""}',
        '{"mode":"other","query":"Trade-in"}',
        '{"mode":"current","query":"Кредит","extra":true}',
    ],
)
def test_invalid_retrieval_plan_abstains(raw: str) -> None:
    assert _parse_retrieval_plan(raw) == RetrievalPlan.none()


def test_selection_restricts_last_source_and_returns_at_most_two_chunks() -> None:
    duplicate = "Оценка автомобиля бесплатна."
    selection = select_source(
        candidates=[
            _candidate(CREDIT_ID, "Кредит", "Взнос от 10%.", 0.99),
            _candidate(TRADE_IN_ID, "Trade-in", duplicate, 0.90, chunk_index=1),
            _candidate(TRADE_IN_ID, "Trade-in", duplicate, 0.89, chunk_index=2),
            _candidate(
                TRADE_IN_ID,
                "Trade-in",
                "Нужны ПТС и СТС.",
                0.80,
                chunk_index=3,
            ),
            _candidate(
                TRADE_IN_ID,
                "Trade-in",
                "Доплата фиксируется в договоре.",
                0.70,
                chunk_index=4,
            ),
        ],
        required_source_id=TRADE_IN_ID,
    )

    assert selection is not None
    assert selection.source_id == TRADE_IN_ID
    assert [item.content for item in selection.candidates] == [
        duplicate,
        "Нужны ПТС и СТС.",
    ]


def test_current_selection_uses_best_current_document() -> None:
    selection = select_source(
        candidates=[
            _candidate(CREDIT_ID, "Кредит", "Взнос от 10%.", 0.82),
            _candidate(TRADE_IN_ID, "Trade-in", "Оценка бесплатна.", 0.45),
        ]
    )

    assert selection is not None
    assert selection.source_id == CREDIT_ID


class _Embedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0] for _ in texts]


class _Repository:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.calls: list[tuple[int, UUID | None]] = []

    async def search_chunks(
        self,
        embedding,
        top_k,
        *,
        document_id: UUID | None = None,
    ):
        self.calls.append((top_k, document_id))
        rows = (
            [row for row in self.rows if row[0].document_id == document_id]
            if document_id is not None
            else self.rows
        )
        return rows[:top_k]


def _row(
    document_id: UUID,
    title: str,
    content: str,
    score: float,
    *,
    chunk_index: int = 0,
):
    return (
        SimpleNamespace(
            document_id=document_id,
            id=uuid4(),
            chunk_index=chunk_index,
            content=content,
        ),
        title,
        score,
    )


def _retrieval(
    rows,
    planner: FakeRetrievalPlannerClient | None = None,
):
    embedding = _Embedding()
    planner = planner or FakeRetrievalPlannerClient()
    service = KnowledgeRetrievalService(
        None,  # type: ignore[arg-type]
        embedding,
        planner,
        top_k=5,
        min_score=0.2,
    )
    repository = _Repository(rows)
    service._repo = repository
    return service, embedding, planner, repository


@pytest.mark.asyncio
async def test_without_saved_source_uses_original_query_without_planner() -> None:
    service, embedding, planner, repository = _retrieval(
        [_row(CREDIT_ID, "Кредитование", "Взнос.", 0.82)]
    )

    result = await service.retrieve("  Кредит  ")

    assert result.source_id == CREDIT_ID
    assert embedding.calls == [["Кредит"]]
    assert planner.calls == []
    assert repository.calls == [(5, None)]


@pytest.mark.asyncio
async def test_planner_continues_trade_in_with_rewritten_query_and_source_filter() -> (
    None
):
    planner = FakeRetrievalPlannerClient(
        [
            RetrievalPlan(
                mode=RetrievalMode.LAST_SOURCE,
                query="Условия программы Trade-in",
            )
        ]
    )
    service, embedding, planner, repository = _retrieval(
        [
            _row(CREDIT_ID, "Кредитование", "Взнос.", 0.99),
            _row(TRADE_IN_ID, "Trade-in", "Оценка.", 0.81),
        ],
        planner,
    )
    history = [{"role": "user", "content": str(index)} for index in range(8)]

    result = await service.retrieve(
        "А условия по нему?",
        last_source_id=TRADE_IN_ID,
        last_source_title="Trade-in",
        history=history,
    )

    assert result.source_id == TRADE_IN_ID
    assert embedding.calls == [["Условия программы Trade-in"]]
    assert repository.calls == [(5, TRADE_IN_ID)]
    assert planner.calls[0]["history"] == history[-6:]


@pytest.mark.asyncio
async def test_planner_switches_to_explicit_credit_topic() -> None:
    planner = FakeRetrievalPlannerClient(
        [
            RetrievalPlan(
                mode=RetrievalMode.CURRENT,
                query="Условия автокредитования",
            )
        ]
    )
    service, embedding, _, repository = _retrieval(
        [
            _row(CREDIT_ID, "Кредитование", "Взнос.", 0.82),
            _row(TRADE_IN_ID, "Trade-in", "Оценка.", 0.45),
        ],
        planner,
    )

    result = await service.retrieve(
        "Кредит",
        last_source_id=TRADE_IN_ID,
        last_source_title="Trade-in",
    )

    assert result.source_id == CREDIT_ID
    assert embedding.calls == [["Условия автокредитования"]]
    assert repository.calls == [(5, None)]


@pytest.mark.asyncio
async def test_none_plan_skips_embeddings_and_search() -> None:
    planner = FakeRetrievalPlannerClient([RetrievalPlan.none()])
    service, embedding, _, repository = _retrieval([], planner)

    result = await service.retrieve(
        "Спасибо",
        last_source_id=TRADE_IN_ID,
        last_source_title="Trade-in",
    )

    assert result == result.__class__()
    assert embedding.calls == []
    assert repository.calls == []


@pytest.mark.asyncio
async def test_planner_exception_skips_embeddings_and_search() -> None:
    planner = FakeRetrievalPlannerClient([TimeoutError("planner timeout")])
    service, embedding, _, repository = _retrieval([], planner)

    result = await service.retrieve(
        "А условия?",
        last_source_id=TRADE_IN_ID,
        last_source_title="Trade-in",
    )

    assert result.source_id is None
    assert embedding.calls == []
    assert repository.calls == []


@pytest.mark.asyncio
async def test_low_relevance_does_not_select_source() -> None:
    service, _, _, _ = _retrieval([_row(CREDIT_ID, "Кредитование", "Взнос.", 0.19)])

    result = await service.retrieve("Как приготовить домашний борщ?")

    assert result.source_id is None
    assert result.chunks == ()


def test_prompt_contains_only_selected_source_without_scores() -> None:
    prompt = format_chunks_for_prompt(
        (
            RetrievedChunk(
                document_id=TRADE_IN_ID,
                chunk_id=uuid4(),
                title="Программа Trade-in",
                score=0.9,
                content="Оценка бесплатна.",
            ),
            RetrievedChunk(
                document_id=TRADE_IN_ID,
                chunk_id=uuid4(),
                title="Программа Trade-in",
                score=0.8,
                content="Нужны ПТС и СТС.",
            ),
        )
    )

    assert prompt == (
        "[Источник: Программа Trade-in]\nОценка бесплатна.\n\n"
        "[Источник: Программа Trade-in]\nНужны ПТС и СТС."
    )
    assert "score=" not in prompt
