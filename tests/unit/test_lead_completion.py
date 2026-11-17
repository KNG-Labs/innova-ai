import json

import pytest

from app.schemas.agent_schema import ContactPreference, DialogState, LeadIntentStatus
from app.client.ag2_agent_client import _FALLBACK_DECISION, _parse_reply
from app.service.state_machine import resolve_next_state
from tests.factories import agent_decision

pytestmark = pytest.mark.unit

_QUALIFICATION = {
    "car_model": "Toyota Camry",
    "budget": "3000000",
    "purchase_type": "наличные",
}
_CONTACT = {"phone": "+79991234567"}


def test_generation_failure_marker_is_internal_and_survives_local_copy():
    decision = _parse_reply(
        json.dumps(
            {
                **agent_decision().model_dump(),
                "_generation_failed": True,
                "generation_failed": True,
            }
        )
    )

    assert decision.generation_failed is False
    assert _FALLBACK_DECISION.model_copy(
        update={"extracted_contact": _CONTACT}
    ).generation_failed
    assert "generation_failed" not in _FALLBACK_DECISION.model_dump_json()


@pytest.mark.parametrize(
    "suggested", [DialogState.GREETING, DialogState.CONTACT_CAPTURE]
)
def test_new_contact_completes_confirmed_lead_independently_of_suggestion(suggested):
    decision = agent_decision(next_state=suggested, extracted_contact=_CONTACT)

    assert (
        resolve_next_state(
            DialogState.CONTACT_CAPTURE, decision, _QUALIFICATION, _CONTACT
        )
        == DialogState.LEAD_READY
    )


@pytest.mark.parametrize(
    ("current", "qualification", "overrides", "expected"),
    [
        (DialogState.GREETING, _QUALIFICATION, {}, DialogState.GREETING),
        (DialogState.FAQ, _QUALIFICATION, {}, DialogState.FAQ),
        (DialogState.QUALIFICATION, _QUALIFICATION, {}, DialogState.QUALIFICATION),
        (
            DialogState.CONTACT_CAPTURE,
            {"car_model": "Toyota Camry"},
            {},
            DialogState.CONTACT_CAPTURE,
        ),
        (
            DialogState.CONTACT_CAPTURE,
            _QUALIFICATION,
            {"extracted_contact": None},
            DialogState.CONTACT_CAPTURE,
        ),
        (
            DialogState.CONTACT_CAPTURE,
            _QUALIFICATION,
            {"next_state": DialogState.CLOSED},
            DialogState.CLOSED,
        ),
        (
            DialogState.CONTACT_CAPTURE,
            _QUALIFICATION,
            {"contact_preference": ContactPreference.REFUSAL},
            DialogState.CONTACT_CAPTURE,
        ),
        (
            DialogState.CONTACT_CAPTURE,
            _QUALIFICATION,
            {"lead_intent_status": LeadIntentStatus.DECLINED},
            DialogState.CONTACT_CAPTURE,
        ),
    ],
)
def test_complete_fields_alone_do_not_override_intent_or_cancellation(
    current, qualification, overrides, expected
):
    decision = agent_decision(
        **{
            "next_state": DialogState.GREETING,
            "extracted_contact": _CONTACT,
            **overrides,
        }
    )

    assert resolve_next_state(current, decision, qualification, _CONTACT) == expected


@pytest.mark.parametrize("contact", [None, _CONTACT])
@pytest.mark.parametrize(
    "overrides",
    [
        {"contact_preference": ContactPreference.REFUSAL},
        {"lead_intent_status": LeadIntentStatus.DECLINED},
    ],
)
def test_refusal_blocks_model_lead_ready_with_new_or_existing_contact(
    contact, overrides
):
    decision = agent_decision(
        next_state=DialogState.LEAD_READY, extracted_contact=contact, **overrides
    )

    assert (
        resolve_next_state(
            DialogState.CONTACT_CAPTURE, decision, _QUALIFICATION, _CONTACT
        )
        == DialogState.CONTACT_CAPTURE
    )
