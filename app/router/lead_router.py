from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.di import get_lead_service
from app.schemas.lead_schema import LeadListItem, LeadResponse
from app.service.lead_service import LeadNotFoundError, LeadService

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
