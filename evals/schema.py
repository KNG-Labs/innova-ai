from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EvaluationType = Literal["retrieval", "generation", "business"]
DatasetSplit = Literal["calibration", "test", "regression"]
ExpectedBehavior = Literal[
    "answer_only",
    "answer_before_qualification",
    "abstain",
]


class ExpectedFields(BaseModel):
    """Expected structured extraction for business evals."""

    model_config = ConfigDict(extra="forbid")

    car_model: str | None = None
    budget: str | None = None
    purchase_type: str | None = None
    contact: str | None = None


class GoldenExample(BaseModel):
    """One typed evaluation case.

    Type-specific requirements are enforced by ``GoldenDataset`` because the
    example itself does not know which runner will execute it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    split: DatasetSplit
    category: str = Field(min_length=1)
    question: str = Field(min_length=1)

    answerable: bool | None = None
    relevance: dict[str, int] = Field(default_factory=dict)
    required_facts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_behavior: ExpectedBehavior | None = None
    expected_max_questions: int | None = Field(default=None, ge=0)

    expected_intent: str | None = None
    expected_fields: ExpectedFields | None = None
    setup_messages: list[str] = Field(default_factory=list)
    expected_state: str | None = None
    expected_missing_fields: list[str] | None = None

    @field_validator("category", "question")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator(
        "expected_intent",
        "expected_state",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None

    @field_validator("setup_messages", "required_facts", "forbidden_claims")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        if any(not value for value in normalized):
            raise ValueError("text list items must not be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("text list items must be unique")
        return normalized

    @field_validator("relevance")
    @classmethod
    def validate_relevance(cls, values: dict[str, int]) -> dict[str, int]:
        if any(not document_id.strip() for document_id in values):
            raise ValueError("relevance document IDs must not be blank")
        if any(grade not in {1, 2, 3} for grade in values.values()):
            raise ValueError("relevance grades must be 1, 2, or 3")
        return values


class GoldenDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"]
    name: str = Field(min_length=1)
    evaluation_type: EvaluationType
    description: str | None = None
    cases: list[GoldenExample] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> "GoldenDataset":
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique within a dataset")

        for case in self.cases:
            if self.evaluation_type in {"retrieval", "generation"}:
                if case.answerable is None:
                    raise ValueError(
                        f"{case.id}: answerable is required for {self.evaluation_type}"
                    )
                if case.answerable != bool(case.relevance):
                    raise ValueError(
                        f"{case.id}: answerable must match non-empty relevance"
                    )
            elif case.answerable is not None or case.relevance:
                raise ValueError(
                    f"{case.id}: business cases must not define retrieval labels"
                )

            if self.evaluation_type == "retrieval":
                forbidden = {
                    "expected_intent": case.expected_intent,
                    "expected_fields": case.expected_fields,
                    "expected_state": case.expected_state,
                    "expected_missing_fields": case.expected_missing_fields,
                }
                populated = [
                    name for name, value in forbidden.items() if value is not None
                ]
                if populated:
                    raise ValueError(
                        f"{case.id}: retrieval case has non-retrieval fields: {populated}"
                    )
                if (
                    case.required_facts
                    or case.forbidden_claims
                    or case.expected_behavior
                ):
                    raise ValueError(
                        f"{case.id}: retrieval case must contain only retrieval labels"
                    )

            if self.evaluation_type == "generation" and not (
                case.required_facts or case.forbidden_claims
            ):
                raise ValueError(f"{case.id}: generation case has no answer labels")

            if self.evaluation_type == "business" and not any(
                (
                    case.expected_intent,
                    case.expected_fields,
                    case.expected_state,
                    case.expected_missing_fields is not None,
                    case.expected_behavior,
                    case.required_facts,
                    case.forbidden_claims,
                )
            ):
                raise ValueError(f"{case.id}: business case has no expectations")
        return self


class PredictionFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    car_model: str | None = None
    budget: str | None = None
    purchase_type: str | None = None
    contact: str | dict[str, str | None] | None = None


class EvaluationPrediction(BaseModel):
    """Normalized output contract consumed by evaluation runners."""

    model_config = ConfigDict(extra="ignore")

    id: str
    answer: str | None = None
    retrieved_document_ids: list[str] = Field(default_factory=list)
    intent: str | None = None
    fields: PredictionFields | None = None
    state: str | None = None
    missing_fields: list[str] | None = None
    latency_ms: float | None = Field(default=None, ge=0)
