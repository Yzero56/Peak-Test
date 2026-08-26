import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.cooking import CookingStatusResponse
from app.services.cooking_service import get_cooking_status
from app.services.food_service import get_food_item

router = APIRouter(prefix="/food-items", tags=["cooking"])


@router.get("/{item_id}/cooking-status", response_model=CookingStatusResponse)
async def cooking_status(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> CookingStatusResponse:
    item = await get_food_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Food item not found")
    return CookingStatusResponse.model_validate(get_cooking_status(item))
