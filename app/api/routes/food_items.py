import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.food import FoodItem, FoodItemStatus, StorageType
from app.schemas.food import FoodItemCreate, FoodItemResponse, FoodItemUpdate
from app.schemas.expiry import ExpiryResponse
from app.services.expiry_service import get_expiry_status
from app.services.cooking_service import get_cooking_status
from app.services.food_service import (
    create_food_item,
    discard_food_item,
    get_food_item,
    update_food_item,
)

router = APIRouter(prefix="/food-items", tags=["food-items"])


def to_response(item: FoodItem) -> FoodItemResponse:
    days_remaining, expiry_status = get_expiry_status(item.expires_at)
    cooking_status = get_cooking_status(item)
    response = FoodItemResponse.model_validate(
        {
            "id": item.id,
            "product_id": item.product_id,
            "display_name": item.display_name,
            "category": item.category,
            "quantity": item.quantity,
            "unit": item.unit,
            "storage_type": item.storage_type,
            "purchased_at": item.purchased_at,
            "opened_at": item.opened_at,
            "manufactured_at": item.manufactured_at,
            "expires_at": item.expires_at,
            "date_source": item.date_source,
            "confidence": item.confidence,
            "status": item.status,
            "notes": item.notes,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "container_id": item.container_id,
            "food_id": item.id,
            "food_name": item.display_name,
            "expiration_date": item.expires_at,
            "stored_at": item.created_at,
            "d_day": days_remaining,
            "days_remaining": days_remaining,
            "expiry_status": expiry_status,
            "can_cook": cooking_status["can_cook"],
            "requires_confirmation": cooking_status["requires_confirmation"],
        }
    )
    response.days_remaining = days_remaining
    response.expiry_status = expiry_status
    return response


def to_legacy_response(item: FoodItem) -> dict:
    """4번 앱의 기존 숫자 ID/필드명을 유지하는 compatibility payload."""
    days_remaining, _ = get_expiry_status(item.expires_at)
    category = {
        "vegetable": "채소", "meat": "육류·계란", "dairy": "유제품",
        "seafood": "수산물", "other": "기타",
    }.get(item.category or "other", "기타")
    storage_value = item.storage_type.value if hasattr(item.storage_type, "value") else item.storage_type
    location = {"refrigerator": "냉장", "freezer": "냉동", "room": "실온"}[storage_value]
    return {
        "id": item.legacy_id,
        "name": item.display_name,
        "category": category,
        "quantity": item.unit or str(item.quantity),
        "expiresAt": item.expires_at.isoformat() if item.expires_at else "",
        "location": location,
    }


async def get_legacy_item(session: AsyncSession, item_id: int) -> FoodItem | None:
    return await session.scalar(select(FoodItem).where(FoodItem.legacy_id == item_id))


@router.post("", response_model=FoodItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: FoodItemCreate,
    session: AsyncSession = Depends(get_db),
) -> FoodItemResponse:
    return to_response(await create_food_item(session, data))


@router.get("", response_model=list[FoodItemResponse])
async def list_items(
    item_status: FoodItemStatus = Query(FoodItemStatus.ACTIVE, alias="status"),
    storage_type: StorageType | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[FoodItemResponse]:
    query = select(FoodItem).where(FoodItem.status == item_status)
    if storage_type:
        query = query.where(FoodItem.storage_type == storage_type)
    query = query.order_by(FoodItem.expires_at.asc().nullslast(), FoodItem.created_at.desc())
    items = (await session.scalars(query)).all()
    return [to_response(item) for item in items]


@router.get("/{item_id}", response_model=FoodItemResponse)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> FoodItemResponse:
    item = await get_food_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Food item not found")
    return to_response(item)


@router.get("/{item_id}/expiry", response_model=ExpiryResponse)
async def get_item_expiry(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> ExpiryResponse:
    item = await get_food_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Food item not found")
    days_remaining, expiry_status = get_expiry_status(item.expires_at)
    return ExpiryResponse(
        expires_at=item.expires_at,
        days_remaining=days_remaining,
        expiry_status=expiry_status,
        date_source=item.date_source.value,
        confidence=item.confidence,
    )


@router.patch("/{item_id}", response_model=FoodItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: FoodItemUpdate,
    session: AsyncSession = Depends(get_db),
) -> FoodItemResponse:
    item = await get_food_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Food item not found")
    return to_response(await update_food_item(session, item, data))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    item = await get_food_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Food item not found")
    await discard_food_item(session, item)
