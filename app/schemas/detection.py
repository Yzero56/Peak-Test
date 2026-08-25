import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """0~1로 정규화된 bounding box."""

    x: Decimal = Field(ge=0, le=1)
    y: Decimal = Field(ge=0, le=1)
    width: Decimal = Field(gt=0, le=1)
    height: Decimal = Field(gt=0, le=1)


class DetectionInput(BaseModel):
    """2번 파트 객체 탐지 결과 1건."""

    label: str = Field(min_length=1, max_length=100)
    confidence: Decimal = Field(ge=0, le=1)
    bounding_box: BoundingBox | None = None
    container_id: str | None = Field(default=None, max_length=64)


class DetectionBatchCreate(BaseModel):
    """1번 파트 캡처 이벤트 + 2번 파트 탐지 결과를 함께 수신한다."""

    image_id: uuid.UUID | None = None
    device_id: str | None = Field(default=None, max_length=64)
    motion_direction: Literal["in", "out"] | None = None
    detected_at: datetime | None = None
    detections: list[DetectionInput] = Field(min_length=1)


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID | None
    device_id: str | None
    container_id: str | None
    label: str
    confidence: Decimal
    motion_direction: str | None
    recognition_status: str | None
    similarity: Decimal | None
    embedding_model: str | None
    detected_at: datetime
    bounding_box: BoundingBox | None = None
