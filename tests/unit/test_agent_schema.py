import pytest
from pydantic import ValidationError

from app.schemas.agent_schema import AgentMessageRequest

pytestmark = pytest.mark.unit


def _req(**kw):
    base = {"anonymous_id": "abc123", "content": "привет"}
    base.update(kw)
    return AgentMessageRequest(**base)


def test_page_title_defaults_to_none():
    assert _req().page_title is None


def test_page_title_whitespace_collapsed_and_newlines_stripped():
    assert _req(page_title="  Toyota   Camry\n2024 ").page_title == "Toyota Camry 2024"


def test_page_title_blank_becomes_none():
    assert _req(page_title="   ").page_title is None


def test_page_title_truncated_not_rejected():
    assert _req(page_title="x" * 500).page_title == "x" * 200


def test_unknown_field_still_forbidden():
    # page_url мы намеренно НЕ принимаем — extra="forbid" должен это ловить
    with pytest.raises(ValidationError):
        _req(page_url="https://salon.ru/camry")
