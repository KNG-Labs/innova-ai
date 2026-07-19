import pytest
from uuid import uuid4

from app.client.crm_client import build_crm_payload

pytestmark = pytest.mark.unit


def test_maps_domain_fields_not_legacy() -> None:
    lead_id, session_id = uuid4(), uuid4()
    payload = build_crm_payload(
        lead_id=lead_id,
        session_id=session_id,
        qualification={
            "car_model": "Toyota Camry",
            "budget": "до 3 млн",
            "purchase_type": "кредит",
            "source_channel": "website",
        },
        contact={"name": "Иван", "phone": "+79991234567", "email": None},
        summary="Хочет Camry в кредит",
    )
    assert payload.car_model == "Toyota Camry"
    assert payload.purchase_type == "кредит"
    assert payload.budget == "до 3 млн"
    assert payload.contact_name == "Иван"
    assert payload.contact_email is None
    assert payload.source == "website"


def test_defaults_source_to_website_when_missing() -> None:
    payload = build_crm_payload(
        lead_id=uuid4(),
        session_id=uuid4(),
        qualification={"car_model": "BMW X5"},
        contact=None,
        summary=None,
    )
    assert payload.source == "website"
    assert payload.contact_name is None
