from uuid import UUID

from fastapi import APIRouter, Depends

from app.di import get_knowledge_ingestion_service
from app.schemas.knowledge_schema import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentListItem,
)
from app.service.knowledge_ingestion_service import KnowledgeIngestionService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.post("/documents", status_code=201)
async def create_document(
    payload: list[KnowledgeDocumentCreate],
    service: KnowledgeIngestionService = Depends(get_knowledge_ingestion_service),
) -> dict[str, list[UUID]]:
    document_ids = await service.ingest_many(payload)
    return {"document_ids": document_ids}


@router.get("/documents", response_model=list[KnowledgeDocumentListItem])
async def list_documents(
    service: KnowledgeIngestionService = Depends(get_knowledge_ingestion_service),
) -> list[KnowledgeDocumentListItem]:
    return await service.list_documents()


@router.post("/reindex")
async def reindex(
    service: KnowledgeIngestionService = Depends(get_knowledge_ingestion_service),
) -> dict[str, int]:
    count = await service.reindex()
    return {"reindexed_documents": count}
