import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.detection import Detection
from app.models.food import FoodImage
from app.schemas.detection import BoundingBox, DetectionBatchCreate, DetectionResponse

router = APIRouter(prefix="/detections", tags=["detections"])


def to_response(detection: Detection) -> DetectionResponse:
    bounding_box = None
    if detection.bbox_width is not None and detection.bbox_height is not None:
        bounding_box = BoundingBox(
            x=detection.bbox_x,
            y=detection.bbox_y,
            width=detection.bbox_width,
            height=detection.bbox_height,
        )
    response = DetectionResponse.model_validate(detection)
    response.bounding_box = bounding_box
    return response


@router.post("", response_model=list[DetectionResponse], status_code=status.HTTP_201_CREATED)
async def create_detections(
    data: DetectionBatchCreate,
    session: AsyncSession = Depends(get_db),
) -> list[DetectionResponse]:
    if data.image_id is not None:
        image = await session.get(FoodImage, data.image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="image_not_found")

    created: list[Detection] = []
    for item in data.detections:
        box = item.bounding_box
        detection = Detection(
            image_id=data.image_id,
            device_id=data.device_id,
            container_id=item.container_id,
            label=item.label,
            confidence=item.confidence,
            bbox_x=box.x if box else None,
            bbox_y=box.y if box else None,
            bbox_width=box.width if box else None,
            bbox_height=box.height if box else None,
            motion_direction=data.motion_direction,
        )
        if data.detected_at is not None:
            detection.detected_at = data.detected_at
        session.add(detection)
        created.append(detection)

    await session.commit()
    for detection in created:
        await session.refresh(detection)
    return [to_response(detection) for detection in created]


@router.get("", response_model=list[DetectionResponse])
async def list_detections(
    image_id: uuid.UUID | None = None,
    device_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[DetectionResponse]:
    query = select(Detection)
    if image_id is not None:
        query = query.where(Detection.image_id == image_id)
    if device_id is not None:
        query = query.where(Detection.device_id == device_id)
    query = query.order_by(Detection.detected_at.desc()).limit(limit)
    detections = (await session.scalars(query)).all()
    return [to_response(detection) for detection in detections]
