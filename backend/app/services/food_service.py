import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.food import FoodItem, FoodItemStatus
from app.schemas.food import FoodItemCreate, FoodItemUpdate


async def get_food_item(session: AsyncSession, item_id: uuid.UUID) -> FoodItem | None:
    return await session.scalar(
        select(FoodItem).where(
            FoodItem.id == item_id,
            FoodItem.status != FoodItemStatus.DISCARDED,
        )
    )


async def create_food_item(session: AsyncSession, data: FoodItemCreate) -> FoodItem:
    next_id = (await session.scalar(select(func.max(FoodItem.legacy_id)))) or 0
    item = FoodItem(**data.model_dump(), legacy_id=next_id + 1)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_food_item(
    session: AsyncSession, item: FoodItem, data: FoodItemUpdate
) -> FoodItem:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def discard_food_item(session: AsyncSession, item: FoodItem) -> None:
    item.status = FoodItemStatus.DISCARDED
    await session.commit()
