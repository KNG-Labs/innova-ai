from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievalCandidate:
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    title: str
    score: float
    content: str


@dataclass(frozen=True)
class SourceSelection:
    source_id: UUID
    source_title: str
    candidates: tuple[RetrievalCandidate, ...]


def select_source(
    *,
    candidates: list[RetrievalCandidate],
    required_source_id: UUID | None = None,
    max_chunks: int = 2,
) -> SourceSelection | None:
    """Выбрать один документ и не более двух уникальных чанков из него."""

    sources = _group_by_source(candidates)
    if required_source_id is not None:
        selected_candidates = sources.get(required_source_id)
    else:
        selected_candidates = _best_source(sources)
    if not selected_candidates:
        return None

    selected = tuple(selected_candidates[:max_chunks])
    return SourceSelection(
        source_id=selected[0].document_id,
        source_title=selected[0].title,
        candidates=selected,
    )


def _group_by_source(
    candidates: list[RetrievalCandidate],
) -> dict[UUID, list[RetrievalCandidate]]:
    grouped: dict[UUID, list[RetrievalCandidate]] = defaultdict(list)
    seen_content: dict[UUID, set[str]] = defaultdict(set)

    for candidate in sorted(candidates, key=_candidate_sort_key):
        normalized_content = candidate.content.strip()
        if normalized_content in seen_content[candidate.document_id]:
            continue
        seen_content[candidate.document_id].add(normalized_content)
        grouped[candidate.document_id].append(candidate)

    return dict(grouped)


def _best_source(
    grouped: dict[UUID, list[RetrievalCandidate]],
) -> list[RetrievalCandidate] | None:
    if not grouped:
        return None
    source_id = min(
        grouped,
        key=lambda item: (
            -grouped[item][0].score,
            grouped[item][0].chunk_index,
            item.hex,
        ),
    )
    return grouped[source_id]


def _candidate_sort_key(candidate: RetrievalCandidate) -> tuple[float, int, str]:
    return (-candidate.score, candidate.chunk_index, candidate.chunk_id.hex)
