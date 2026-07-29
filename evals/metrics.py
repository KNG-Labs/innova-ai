from __future__ import annotations

import json
from typing import Any, Sequence

from deepeval.metrics import BaseConversationalMetric, BaseMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import ConversationalTestCase, LLMTestCase
from pydantic import BaseModel, ConfigDict, Field


RETRIEVAL_TOP_K = 10

FACT_EVALUATION_STEPS = (
    "Оценивай смысл, а не буквальное совпадение слов.",
    "Для каждого обязательного факта отдельно реши, следует ли он из ответа.",
    "Не засчитывай факт, если ответ противоречит ему или оставляет ключевую часть "
    "неподтверждённой.",
)
FORBIDDEN_EVALUATION_STEPS = (
    "Оценивай утверждения и их перефразирования по смыслу.",
    "Для каждого запрещённого утверждения отдельно реши, присутствует ли оно в "
    "ответе явно или неявно.",
    "Не считай упоминание обнаружением, если ассистент явно отрицает запрещённое "
    "утверждение.",
)
BUSINESS_EVALUATION_STEPS = (
    "Проверь весь transcript и оцени поведение ассистента в контексте предыдущих "
    "реплик.",
    "Если пользователь задал FAQ, ответ по существу должен идти до нового вопроса "
    "квалификации.",
    "Проверь корректность отказа, отсутствие лишних вопросов и соблюдение "
    "обязательных/запрещённых смыслов.",
    "Не оценивай state, intent, missing fields и поля лида: они проверяются "
    "детерминированными guardrails.",
)


class FactVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    covered: bool
    reason: str


class RequiredFactVerdicts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[FactVerdict]


class ClaimVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    detected: bool
    reason: str


class ForbiddenClaimVerdicts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[ClaimVerdict]


class BusinessVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    reason: str


def unique_at_k(document_ids: Sequence[str], top_k: int = RETRIEVAL_TOP_K) -> list[str]:
    return list(dict.fromkeys(document_ids))[:top_k]


class _SingleTurnMetric(BaseMetric):
    threshold = 1.0
    async_mode = True
    include_reason = True

    def _finish(self, score: float, reason: str) -> float:
        self.score = score
        self.reason = reason
        self.success = self.is_successful()
        return score


class _ConversationalMetric(BaseConversationalMetric):
    threshold = 1.0
    async_mode = True
    include_reason = True

    def _finish(self, score: float, reason: str) -> float:
        self.score = score
        self.reason = reason
        self.success = self.is_successful()
        return score


class RetrievalRecallAt10(_SingleTurnMetric):
    @property
    def __name__(self) -> str:
        return "retrieval_recall@10"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        relevance, retrieved = _retrieval_labels(test_case)
        score = len(set(retrieved).intersection(relevance)) / len(relevance)
        return self._finish(
            score, f"Найдено {int(score * len(relevance))}/{len(relevance)}"
        )

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


class RetrievalMRRAt10(_SingleTurnMetric):
    @property
    def __name__(self) -> str:
        return "retrieval_mrr@10"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        relevance, retrieved = _retrieval_labels(test_case)
        rank = next(
            (
                index
                for index, item in enumerate(retrieved, start=1)
                if item in relevance
            ),
            None,
        )
        score = 0.0 if rank is None else 1.0 / rank
        return self._finish(
            score,
            "Релевантный документ не найден"
            if rank is None
            else f"Первый релевантный документ на позиции {rank}",
        )

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


class ContextPrecisionAt10(_SingleTurnMetric):
    @property
    def __name__(self) -> str:
        return "context_precision@10"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        relevance, retrieved = _retrieval_labels(test_case)
        hit_count = sum(item in relevance for item in retrieved)
        score = hit_count / len(retrieved) if retrieved else 0.0
        return self._finish(
            score, f"Релевантно {hit_count}/{len(retrieved)} возвращённых документов"
        )

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


class AbstentionAccuracyAt10(_SingleTurnMetric):
    @property
    def __name__(self) -> str:
        return "abstention_accuracy@10"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        _relevance, retrieved = _retrieval_labels(test_case)
        score = float(not retrieved)
        return self._finish(
            score, "Retrieval воздержался" if score else "Retrieval вернул контекст"
        )

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


class RequiredFactCoverage(_SingleTurnMetric):
    def __init__(self, judge: DeepEvalBaseLLM) -> None:
        self.judge = judge
        self.model = judge
        self.evaluation_model = judge.get_model_name()

    @property
    def __name__(self) -> str:
        return "required_fact_coverage"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        verdicts = self.judge.generate(
            _fact_prompt(test_case), schema=RequiredFactVerdicts
        )
        return self._apply_verdicts(test_case, verdicts)

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        verdicts = await self.judge.a_generate(
            _fact_prompt(test_case), schema=RequiredFactVerdicts
        )
        return self._apply_verdicts(test_case, verdicts)

    def _apply_verdicts(self, test_case: LLMTestCase, value: str | BaseModel) -> float:
        verdicts = _coerce_schema(value, RequiredFactVerdicts).verdicts
        facts = _metadata(test_case).get("required_facts", [])
        by_index = {item.index: item for item in verdicts}
        covered = sum(
            bool(by_index.get(index) and by_index[index].covered)
            for index in range(len(facts))
        )
        reasons = [
            f"{index}: {by_index[index].reason}"
            for index in range(len(facts))
            if index in by_index
        ]
        return self._finish(
            covered / len(facts),
            "; ".join(reasons) or "Judge не вернул verdicts",
        )


class ForbiddenClaimRate(_SingleTurnMetric):
    threshold = 0.0

    def __init__(self, judge: DeepEvalBaseLLM) -> None:
        self.judge = judge
        self.model = judge
        self.evaluation_model = judge.get_model_name()

    def is_successful(self) -> bool:
        if self.error is not None or self.score is None:
            self.success = False
        else:
            self.success = self.score <= self.threshold
        return self.success

    @property
    def __name__(self) -> str:
        return "forbidden_claim_rate"

    def measure(self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any) -> float:
        verdicts = self.judge.generate(
            _forbidden_prompt(test_case), schema=ForbiddenClaimVerdicts
        )
        return self._apply_verdicts(test_case, verdicts)

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        verdicts = await self.judge.a_generate(
            _forbidden_prompt(test_case), schema=ForbiddenClaimVerdicts
        )
        return self._apply_verdicts(test_case, verdicts)

    def _apply_verdicts(self, test_case: LLMTestCase, value: str | BaseModel) -> float:
        verdicts = _coerce_schema(value, ForbiddenClaimVerdicts).verdicts
        claims = _metadata(test_case).get("forbidden_claims", [])
        by_index = {item.index: item for item in verdicts}
        detected = sum(
            bool(by_index.get(index) and by_index[index].detected)
            for index in range(len(claims))
        )
        reasons = [
            f"{index}: {by_index[index].reason}"
            for index in range(len(claims))
            if index in by_index
        ]
        return self._finish(
            detected / len(claims),
            "; ".join(reasons) or "Judge не вернул verdicts",
        )


class BusinessDialogueSuccess(_ConversationalMetric):
    def __init__(self, judge: DeepEvalBaseLLM) -> None:
        self.judge = judge
        self.model = judge
        self.evaluation_model = judge.get_model_name()

    @property
    def __name__(self) -> str:
        return "business_dialogue_success"

    def measure(
        self, test_case: ConversationalTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        verdict = self.judge.generate(
            _business_prompt(test_case), schema=BusinessVerdict
        )
        return self._apply_verdict(test_case, verdict)

    async def a_measure(
        self, test_case: ConversationalTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        verdict = await self.judge.a_generate(
            _business_prompt(test_case), schema=BusinessVerdict
        )
        return self._apply_verdict(test_case, verdict)

    def _apply_verdict(
        self, test_case: ConversationalTestCase, value: str | BaseModel
    ) -> float:
        verdict = _coerce_schema(value, BusinessVerdict)
        guardrails = _metadata(test_case).get("guardrails", {})
        failed = sorted(name for name, passed in guardrails.items() if not passed)
        success = verdict.success and not failed
        reason = verdict.reason
        if failed:
            reason += "; exact guardrails failed: " + ", ".join(failed)
        return self._finish(float(success), reason)


class CaseCollectedMetric(_SingleTurnMetric):
    """Internal threshold metric required by DeepEval; omitted from summaries."""

    threshold = 1.0
    include_reason = False

    @property
    def __name__(self) -> str:
        return "_case_collected"

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self._finish(1.0, "")

    async def a_measure(
        self, test_case: LLMTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


class ConversationalCaseCollectedMetric(_ConversationalMetric):
    threshold = 1.0
    include_reason = False

    @property
    def __name__(self) -> str:
        return "_case_collected"

    def measure(
        self,
        test_case: ConversationalTestCase,
        *args: Any,
        **kwargs: Any,
    ) -> float:
        return self._finish(1.0, "")

    async def a_measure(
        self, test_case: ConversationalTestCase, *_args: Any, **_kwargs: Any
    ) -> float:
        return self.measure(test_case)


def _metadata(test_case: LLMTestCase | ConversationalTestCase) -> dict[str, Any]:
    return test_case.metadata or {}


def _retrieval_labels(test_case: LLMTestCase) -> tuple[set[str], list[str]]:
    metadata = _metadata(test_case)
    relevance = set(metadata.get("relevance", {}))
    retrieved = unique_at_k(metadata.get("retrieved_document_ids", []))
    return relevance, retrieved


def _fact_prompt(test_case: LLMTestCase) -> str:
    metadata = _metadata(test_case)
    return _judge_prompt(
        steps=FACT_EVALUATION_STEPS,
        payload={
            "answer": test_case.actual_output or "",
            "required_facts": metadata.get("required_facts", []),
        },
        instruction=(
            "Верни ровно один verdict для каждого required_fact. index — его "
            "позиция, начиная с 0."
        ),
    )


def _forbidden_prompt(test_case: LLMTestCase) -> str:
    metadata = _metadata(test_case)
    return _judge_prompt(
        steps=FORBIDDEN_EVALUATION_STEPS,
        payload={
            "answer": test_case.actual_output or "",
            "forbidden_claims": metadata.get("forbidden_claims", []),
        },
        instruction=(
            "Верни ровно один verdict для каждого forbidden_claim. index — его "
            "позиция, начиная с 0."
        ),
    )


def _business_prompt(test_case: ConversationalTestCase) -> str:
    metadata = _metadata(test_case)
    transcript = [
        {"role": turn.role, "content": turn.content} for turn in test_case.turns
    ]
    return _judge_prompt(
        steps=BUSINESS_EVALUATION_STEPS,
        payload={
            "transcript": transcript,
            "semantic_expectations": metadata.get("semantic_expectations", {}),
        },
        instruction="Верни единый semantic verdict для полного диалога.",
    )


def _judge_prompt(
    *, steps: Sequence[str], payload: dict[str, Any], instruction: str
) -> str:
    return (
        "Ты независимый judge русскоязычного ассистента автодилера.\n"
        "Шаги оценки:\n- "
        + "\n- ".join(steps)
        + "\n"
        + instruction
        + "\nДанные:\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _coerce_schema[T: BaseModel](value: str | BaseModel, schema: type[T]) -> T:
    if isinstance(value, schema):
        return value
    if isinstance(value, str):
        return schema.model_validate_json(value)
    return schema.model_validate(value.model_dump())
