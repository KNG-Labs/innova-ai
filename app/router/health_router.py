from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.di import get_db_session


router = APIRouter()


@router.get("/health", include_in_schema=False, response_model=None)
async def health(
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, str] | JSONResponse:
    try:
        await db_session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )

    return {"status": "ok"}
