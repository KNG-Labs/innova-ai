import pytest

from app.client.token_usage import (
    AgentTokenUsage,
    normalize_actual_usage,
    usage_delta,
)


pytestmark = pytest.mark.unit


def test_normalizes_ag2_per_model_usage() -> None:
    usage = normalize_actual_usage(
        {
            "total_cost": 0,
            "model-a": {
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
                "cost": 0,
            },
            "model-b": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
                "cost": 0,
            },
        }
    )
    assert usage == AgentTokenUsage(
        prompt_tokens=12,
        completion_tokens=4,
        total_tokens=16,
    )


def test_ag2_usage_delta_uses_cumulative_before_and_after() -> None:
    before = {
        "model": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        }
    }
    after = {
        "model": {
            "prompt_tokens": 115,
            "completion_tokens": 24,
            "total_tokens": 139,
        }
    }
    assert usage_delta(before, after) == AgentTokenUsage(
        prompt_tokens=15,
        completion_tokens=4,
        total_tokens=19,
        calls=1,
    )


def test_ag2_usage_snapshot_is_independent_from_mutable_cumulative_summary() -> None:
    cumulative = {
        "model": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        }
    }
    before = normalize_actual_usage(cumulative)

    cumulative["model"].update(
        prompt_tokens=115,
        completion_tokens=24,
        total_tokens=139,
    )

    assert usage_delta(before, cumulative) == AgentTokenUsage(
        prompt_tokens=15,
        completion_tokens=4,
        total_tokens=19,
        calls=1,
    )


def test_planner_and_main_agent_usage_add_without_judge_usage() -> None:
    planner = AgentTokenUsage(
        prompt_tokens=10, completion_tokens=2, total_tokens=12, calls=1
    )
    main = AgentTokenUsage(
        prompt_tokens=20, completion_tokens=5, total_tokens=25, calls=1
    )
    assert (planner + main).as_metadata() == {
        "prompt_tokens": 30,
        "completion_tokens": 7,
        "total_tokens": 37,
        "calls": 2,
        "complete": True,
    }
