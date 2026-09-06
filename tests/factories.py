from typing import Any

from app.domain import MISSING_ALL
from app.schemas.agent_schema import AgentDecision, DialogState


def agent_decision(**overrides: Any) -> AgentDecision:
    return AgentDecision(
        **{
            "answer": "ok",
            "intent": "general",
            "next_state": DialogState.FAQ,
            "qualification_patch": {},
            "missing_fields": MISSING_ALL,
            "lead_ready": False,
            **overrides,
        }
    )
