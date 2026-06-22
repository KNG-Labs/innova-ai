import logging
from typing import Any, Protocol
from uuid import UUID
import httpx

_logger = logging.getLogger(__name__)

class CrmPayload:
    def __init__(
        self,
        lead_id: UUID,
        source: str,
        contact_name: str | None,
        contact_phone: str | None,
        contact_email: str | None,
        car_model: str | None,
        budget: str | None,
        purchase_type: str | None,
        summary: str | None,
        session_id: UUID,
    ) -> None:
        self.lead_id = lead_id
        self.source = source
        self.contact_name = contact_name
        self.contact_phone = contact_phone
        self.contact_email = contact_email
        self.car_model = car_model
        self.budget = budget
        self.purchase_type = purchase_type
        self.summary = summary
        self.session_id = session_id


def build_crm_payload(
    *,
    lead_id: UUID,
    session_id: UUID,
    qualification: dict[str, Any] | None,
    contact: dict[str, Any] | None,
    summary: str | None,
) -> CrmPayload:
    """Маппинг Innova-домена -> CRM payload. Единственная точка маппинга.

    Домен: car_model / budget / purchase_type (см. app/domain.py).
    Внешние данные недоверенные -> .get с None по умолчанию.
    """
    qual = qualification or {}
    cont = contact or {}
    return CrmPayload(
        lead_id=lead_id,
        session_id=session_id,
        source=qual.get("source_channel") or "website",
        contact_name=cont.get("name"),
        contact_phone=cont.get("phone"),
        contact_email=cont.get("email"),
        car_model=qual.get("car_model"),
        budget=qual.get("budget"),
        purchase_type=qual.get("purchase_type"),
        summary=summary,
    )


class CrmClient(Protocol):
    async def deliver_lead(self, payload: CrmPayload) -> None: ...


class FakeCrmClient:
    """Заглушка для тестов без реальных CRM токенов."""

    def __init__(self, *, fail: bool = False) -> None:
        self.delivered: list[CrmPayload] = []
        self._fail = fail

    async def deliver_lead(self, payload: CrmPayload) -> None:
        if self._fail:
            raise RuntimeError("fake CRM rejected the lead")
        self.delivered.append(payload)


class WebhookLeadDeliveryClient:
    """Backup/debug destination: один POST с плоским payload."""

    def __init__(self, *, http_client: httpx.AsyncClient, url: str) -> None:
        self._http = http_client
        self._url = url

    async def deliver_lead(self, payload: CrmPayload) -> None:
        resp = await self._http.post(self._url, json=_payload_to_dict(payload))
        if resp.status_code >= 300:
            raise RuntimeError(f"webhook {resp.status_code}: {resp.text[:500]}")


class AmoCrmLeadDeliveryClient:
    """Создаёт сделку+контакт одним вызовом /api/v4/leads/complex.
    Долгоживущий токен в Bearer — без OAuth-flow."""

    def __init__(
        self, *, http_client: httpx.AsyncClient, base_url: str, access_token: str
    ) -> None:
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._token = access_token

    async def deliver_lead(self, payload: CrmPayload) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        resp = await self._http.post(
            f"{self._base_url}/api/v4/leads/complex",
            headers=headers,
            json=self._to_complex_body(payload),
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"amoCRM {resp.status_code}: {resp.text[:500]}")

        note = self._note_text(payload)
        if not note:
            return

        # id сделки из ответа complex
        try:
            lead_amo_id = resp.json()[0]["id"]
        except (ValueError, KeyError, IndexError, TypeError):
            _logger.warning("amoCRM: не прочитал id сделки, примечание пропущено")
            return

        # note best-effort: сделка уже создана, доставку из-за note не валим
        note_resp = await self._http.post(
            f"{self._base_url}/api/v4/leads/{lead_amo_id}/notes",
            headers=headers,
            json=[{"note_type": "common", "params": {"text": note}}],
        )
        if note_resp.status_code >= 300:
            _logger.warning(
                "amoCRM note %s: %s", note_resp.status_code, note_resp.text[:300]
            )

    @staticmethod
    def _note_text(payload: CrmPayload) -> str:
        lines: list[str] = []
        if payload.summary:
            lines.append(f"Резюме: {payload.summary}")
        if payload.budget:
            lines.append(f"Бюджет: {payload.budget}")
        if payload.purchase_type:
            lines.append(f"Способ покупки: {payload.purchase_type}")
        return "\n".join(lines)

    @staticmethod
    def _to_complex_body(payload: CrmPayload) -> list[dict[str, Any]]:
        cf: list[dict[str, Any]] = []
        if payload.contact_phone:
            cf.append(
                {"field_code": "PHONE", "values": [{"value": payload.contact_phone}]}
            )
        if payload.contact_email:
            cf.append(
                {"field_code": "EMAIL", "values": [{"value": payload.contact_email}]}
            )

        contact: dict[str, Any] = {"name": payload.contact_name or "Аноним"}
        if cf:
            contact["custom_fields_values"] = cf

        lead_name = f"Innova лид — {payload.car_model or 'авто'}"
        return [{"name": lead_name, "_embedded": {"contacts": [contact]}}]


def _payload_to_dict(payload: CrmPayload) -> dict[str, Any]:
    return {
        "lead_id": str(payload.lead_id),
        "source": payload.source,
        "contact_name": payload.contact_name,
        "contact_phone": payload.contact_phone,
        "contact_email": payload.contact_email,
        "car_model": payload.car_model,
        "budget": payload.budget,
        "purchase_type": payload.purchase_type,
        "summary": payload.summary,
        "session_id": str(payload.session_id),
    }
