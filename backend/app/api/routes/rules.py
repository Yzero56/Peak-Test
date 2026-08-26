from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.food import ShelfLifeRule, StorageType
from app.schemas.rules import ShelfLifeRuleResponse

router = APIRouter(prefix="/shelf-life-rules", tags=["shelf-life-rules"])


@router.get("", response_model=list[ShelfLifeRuleResponse])
async def list_rules(
    category: str | None = None,
    storage_type: StorageType | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[ShelfLifeRuleResponse]:
    query = select(ShelfLifeRule).where(ShelfLifeRule.active.is_(True))
    if category:
        query = query.where(ShelfLifeRule.category == category)
    if storage_type:
        query = query.where(ShelfLifeRule.storage_type == storage_type)
    query = query.order_by(ShelfLifeRule.category, ShelfLifeRule.storage_type)
    rules = (await session.scalars(query)).all()
    return [ShelfLifeRuleResponse.model_validate(rule) for rule in rules]
