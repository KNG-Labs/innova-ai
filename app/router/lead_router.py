from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.di import get_lead_service
from app.schemas.lead_schema import LeadListItem, LeadResponse
from app.service.lead_service import LeadService, LeadNotFoundError
from app.di import get_lead_delivery_service
from app.service.lead_delivery_service import (
    LeadNotDeliverableError,
)
from app.service.lead_delivery_service import LeadDeliveryService

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=list[LeadListItem])
async def list_leads(
    status: str | None = None,
    lead_service: LeadService = Depends(get_lead_service),
) -> list[LeadListItem]:
    return await lead_service.list_leads(status=status)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID,
    lead_service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    try:
        return await lead_service.get_lead(lead_id)
    except LeadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )


"""
Уточнение: query-параметр status в list_leads затеняет импортированный fastapi.status внутри этой функции.
Безопасно: list_leads fastapi.status не использует, а get_lead берёт модульный status.
Оставил status ради чистого ?status=ready в URL
"""


@router.post("/{lead_id}/deliver", response_model=LeadResponse)
async def deliver_lead(
    lead_id: UUID,
    delivery_service: LeadDeliveryService = Depends(get_lead_delivery_service),
) -> LeadResponse:
    try:
        lead = await delivery_service.deliver(lead_id)
    except LeadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found"
        )
    except LeadNotDeliverableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead is not in a deliverable status (draft)",
        )
    return LeadResponse(
        id=lead.id,
        session_id=lead.session_id,
        user_id=lead.user_id,
        status=lead.status,
        qualification=lead.qualification,
        contact=lead.contact,
        summary=lead.summary,
        last_delivery_error=lead.last_delivery_error,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )
