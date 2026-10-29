from uuid import uuid4

import httpx
import pytest

from app.client.crm_client import AmoCrmLeadDeliveryClient, build_crm_payload

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "note_result", [httpx.ConnectError("offline"), httpx.ReadTimeout("late"), 500]
)
async def test_note_failure_does_not_repeat_lead_creation(note_result) -> None:
    paths = []

    async def handle(request):
        paths.append(request.url.path)
        if request.url.path == "/api/v4/leads/complex":
            return httpx.Response(200, json=[{"id": 123}])
        if isinstance(note_result, Exception):
            raise note_result
        return httpx.Response(note_result, text="note failed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        crm = AmoCrmLeadDeliveryClient(
            http_client=http, base_url="https://crm.example", access_token="test-only"
        )
        await crm.deliver_lead(
            build_crm_payload(
                lead_id=uuid4(),
                session_id=uuid4(),
                qualification={},
                contact=None,
                summary="Test note",
            )
        )

    assert paths == ["/api/v4/leads/complex", "/api/v4/leads/123/notes"]
