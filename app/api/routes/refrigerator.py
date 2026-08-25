from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.detection import Detection
from app.models.food import FoodImage, FoodItem, FoodItemStatus
from app.schemas.refrigerator import RefrigeratorEventCreate, RefrigeratorEventResponse
from app.api.routes.food_items import to_response

router = APIRouter(prefix="/events/refrigerator", tags=["refrigerator-events"])


async def find_item(session: AsyncSession, data: RefrigeratorEventCreate) -> FoodItem | None:
    item = await session.scalar(
        select(FoodItem)
        .where(FoodItem.container_id == data.container_id, FoodItem.status != FoodItemStatus.DISCARDED)
        .order_by(FoodItem.created_at.desc())
    )
    if item is not None:
        return item
    return await session.scalar(
        select(FoodItem)
        .where(FoodItem.display_name == data.food_name, FoodItem.status != FoodItemStatus.DISCARDED)
        .order_by(FoodItem.created_at.desc())
    )


@router.post("", response_model=RefrigeratorEventResponse, status_code=status.HTTP_201_CREATED)
async def process_refrigerator_event(
    data: RefrigeratorEventCreate,
    session: AsyncSession = Depends(get_db),
) -> RefrigeratorEventResponse:
    if data.image_id is not None and await session.get(FoodImage, data.image_id) is None:
        raise HTTPException(status_code=404, detail="image_not_found")

    timestamp = data.timestamp or datetime.now(timezone.utc)
    box = data.bounding_box
    detection = Detection(
        image_id=data.image_id,
        device_id=data.device_id,
        container_id=data.container_id,
        label=data.food_name,
        confidence=data.confidence,
        bbox_x=box.x if box else None,
        bbox_y=box.y if box else None,
        bbox_width=box.width if box else None,
        bbox_height=box.height if box else None,
        motion_direction=data.motion_direction,
        detected_at=timestamp,
    )
    session.add(detection)

    item = await find_item(session, data)
    if data.motion_direction == "out":
        if item is None:
            raise HTTPException(status_code=404, detail="food_item_not_found_for_out_event")
        item.status = FoodItemStatus.CONSUMED
        action = "consumed"
    elif item is not None and item.status == FoodItemStatus.CONSUMED:
        item.status = FoodItemStatus.ACTIVE
        item.container_id = data.container_id
        action = "restored"
    elif item is not None and item.status == FoodItemStatus.ACTIVE:
        action = "already_present"
    else:
        item = FoodItem(
            display_name=data.food_name,
            category=data.category,
            container_id=data.container_id,
            quantity=data.quantity,
            unit=data.unit,
            storage_type=data.storage_type,
            expires_at=data.expiration_date,
            status=FoodItemStatus.ACTIVE,
        )
        session.add(item)
        action = "registered"

    await session.commit()
    await session.refresh(item)
    await session.refresh(detection)
    return RefrigeratorEventResponse(
        event_id=detection.id,
        action=action,
        food_id=item.id,
        container_id=data.container_id,
        food_name=item.display_name,
        motion_direction=data.motion_direction,
        timestamp=timestamp,
    )
