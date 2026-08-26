from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", summary="서비스 상태 확인")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db", summary="데이터베이스 연결 확인")
async def database_health_check(
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
    return {"status": "ok", "database": "ok"}
