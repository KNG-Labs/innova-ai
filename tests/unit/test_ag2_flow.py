import pytest
from app.client.ag2_agent_client import (
    FakeAg2AgentClient,
    AgentDecision,
    _parse_reply,
    _FALLBACK_DECISION,
)
from app.schemas.agent_schema import DialogState
from app.service.state_machine import resolve_next_state, is_lead_ready

pytestmark = pytest.mark.unit

def test_parse_reply_valid_json():
    raw = '{"answer":"Привет","intent":"pricing","next_state":"FAQ","qualification_data":{},"missing_fields":["service"],"lead_ready":false}'
    result = _parse_reply(raw)
    assert result.answer == "Привет"
    assert result.next_state == DialogState.FAQ


def test_parse_reply_invalid_json_returns_fallback():
    result = _parse_reply("не json вообще")
    assert result == _FALLBACK_DECISION


def test_parse_reply_empty_returns_fallback():
    result = _parse_reply(None)
    assert result == _FALLBACK_DECISION


def test_parse_reply_strips_code_fence():
    raw = '```json\n{"answer":"ok","intent":"general","next_state":"GREETING","qualification_data":{},"missing_fields":[],"lead_ready":false}\n```'
    result = _parse_reply(raw)
    assert result.answer == "ok"


# StateMachine


def test_state_machine_allows_valid_transition():
    decision = AgentDecision(
        answer="ok",
        intent="general",
        next_state=DialogState.FAQ,
        qualification_data={},
        missing_fields=[],
        lead_ready=False,
    )
    result = resolve_next_state(DialogState.GREETING, decision)
    assert result == DialogState.FAQ


def test_state_machine_blocks_lead_ready_without_contact():
    decision = AgentDecision(
        answer="ok",
        intent="lead_request",
        next_state=DialogState.LEAD_READY,
        qualification_data={"service": "SEO"},
        extracted_contact=None,
        missing_fields=[],
        lead_ready=True,
    )
    result = resolve_next_state(DialogState.QUALIFICATION, decision)
    assert result == DialogState.CONTACT_CAPTURE


def test_is_lead_ready_true():
    data = {
        "service": "SEO",
        "deadline": "2 недели",
        "budget": "50k"
    }
    contact = {
        "phone": "+77777"
    }
    assert is_lead_ready(data, contact) is True



def test_is_lead_ready_false_missing_qual():
    qual = {"service": "SEO", "deadline": None, "budget": None}
    contact = {"phone": "+7999"}
    assert is_lead_ready(qual, contact) is False


def test_is_lead_ready_false_no_contact():
    qual = {"service": "SEO", "deadline": "2 недели", "budget": "50k"}
    assert is_lead_ready(qual, None) is False


def test_is_lead_ready_false_empty_contact():
    qual = {"service": "SEO", "deadline": "2 недели", "budget": "50k"}
    assert is_lead_ready(qual, {"phone": None}) is False


# --- Unit: FakeAg2AgentClient ---


@pytest.mark.asyncio
async def test_fake_client_returns_default():
    client = FakeAg2AgentClient()
    result = await client.decide(
        user_message="тест", history=[], current_state="GREETING", qualification_data={}
    )
    assert isinstance(result, AgentDecision)
    assert result.intent == "general"


@pytest.mark.asyncio
async def test_fake_client_returns_scripted_sequence():
    responses = [
        AgentDecision(
            answer="Привет!",
            intent="general",
            next_state=DialogState.FAQ,
            qualification_data={},
            missing_fields=[],
            lead_ready=False,
        ),
        AgentDecision(
            answer="Хорошо, уточните бюджет",
            intent="pricing",
            next_state=DialogState.QUALIFICATION,
            qualification_data={"service": "SEO"},
            missing_fields=["budget", "contact"],
            lead_ready=False,
        ),
    ]
    client = FakeAg2AgentClient(responses=responses)

    r1 = await client.decide(
        user_message="Привет",
        history=[],
        current_state="GREETING",
        qualification_data={},
    )
    r2 = await client.decide(
        user_message="Хочу SEO", history=[], current_state="FAQ", qualification_data={}
    )

    assert r1.next_state == DialogState.FAQ
    assert r2.qualification_data["service"] == "SEO"
