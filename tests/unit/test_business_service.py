import pytest

from app.service.business_service import DialogPolicy
from app.service.intent_detector.base_intent_detector import Intent


@pytest.mark.unit
@pytest.mark.parametrize(
    ("intent", "expected_next_step"),
    [
        ("lead_request", "collect_contact"),
        ("pricing", "send_pricing_summary"),
        ("support", "ask_support_details"),
        ("general", "continue_dialogue"),
    ],
)
def test_dialog_policy_returns_next_step_for_intent(intent: Intent, expected_next_step):
    policy = DialogPolicy()

    result = policy.next_step_for(intent)

    assert result == expected_next_step
