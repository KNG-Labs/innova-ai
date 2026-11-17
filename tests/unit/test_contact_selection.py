import pytest

from app.privacy import PiiSanitizer
from app.schemas.agent_schema import ContactPreference, LeadIntentStatus
from app.service.agent_service import _apply_local_privacy_result
from tests.factories import agent_decision

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "selection",
    [
        None,
        {"phone": "+79991234567"},
        {"phone": "[PHONE_99]"},
        {"phone": "[KB_CONTACT_1]"},
        {"phone": "[EMAIL_1]"},
        {"email": "[PHONE_1]"},
        {"name": "[PHONE_1]"},
    ],
)
def test_only_existing_current_candidates_of_the_right_type_are_accepted(selection):
    pii = PiiSanitizer()
    message = pii.sanitize_text("Телефон компании +79991234567")
    decision = _apply_local_privacy_result(
        agent_decision(extracted_contact=selection),
        pii=pii,
        local_contact={},
        contact_candidates=message.candidates,
        knowledge_contacts={"[KB_CONTACT_1]": "+79991234567"},
    )
    assert decision.extracted_contact is None


@pytest.mark.parametrize("source", ["seed", "history", "literal"])
def test_tokens_outside_current_candidates_cannot_be_selected(source):
    pii = PiiSanitizer()
    if source == "seed":
        pii.seed_contacts({"phone": "+79991234567"})
    elif source == "history":
        pii.sanitize_text("Мой телефон +79991234567")
    message = pii.sanitize_text("Это [PHONE_1]?")
    decision = _apply_local_privacy_result(
        agent_decision(extracted_contact={"phone": "[PHONE_1]"}),
        pii=pii,
        local_contact={},
        contact_candidates=message.candidates,
        knowledge_contacts={},
    )
    assert decision.extracted_contact is None


def test_selected_phone_wins_over_a_later_third_party_phone():
    pii = PiiSanitizer()
    message = pii.sanitize_text(
        "Мой телефон +79991234567, телефон компании +79997778801"
    )
    decision = _apply_local_privacy_result(
        agent_decision(extracted_contact={"phone": "[PHONE_1]"}),
        pii=pii,
        local_contact={},
        contact_candidates=message.candidates,
        knowledge_contacts={},
    )
    assert decision.extracted_contact == {"phone": "+79991234567"}
    assert len(message.candidates) == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"contact_preference": ContactPreference.REFUSAL},
        {"lead_intent_status": LeadIntentStatus.DECLINED},
    ],
)
def test_refusal_does_not_accept_contact_candidates(overrides):
    pii = PiiSanitizer()
    message = pii.sanitize_text("Мой телефон +79991234567")
    decision = _apply_local_privacy_result(
        agent_decision(extracted_contact={"phone": "[PHONE_1]"}, **overrides),
        pii=pii,
        local_contact=message.contacts,
        contact_candidates=message.candidates,
        knowledge_contacts={},
    )
    assert decision.extracted_contact is None
