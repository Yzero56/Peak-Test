import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.food import StorageType
from app.schemas.detection import BoundingBox


class RefrigeratorEventCreate(BaseModel):
    """1번/2번 파트가 전달하는 냉장고 반입·반출 이벤트."""

    container_id: str = Field(min_length=1, max_length=64)
    motion_direction: Literal["in", "out"]
    food_name: str | None = Field(default=None, max_length=200)
    image_id: uuid.UUID | None = None
    device_id: str | None = Field(default=None, max_length=64)
    timestamp: datetime | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    recognition_status: Literal["new", "matched", "unknown"] = "unknown"
    similarity: Decimal | None = Field(default=None, ge=0, le=1)
    embedding_model: str | None = Field(default=None, max_length=100)
    bounding_box: BoundingBox | None = None
    category: str | None = Field(default=None, max_length=50)
    storage_type: StorageType = StorageType.REFRIGERATOR
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str | None = Field(default=None, max_length=20)
    expiration_date: date | None = None


class RefrigeratorEventResponse(BaseModel):
    event_id: uuid.UUID
    action: Literal["consumed", "registered", "restored", "already_present"]
    food_id: uuid.UUID
    container_id: str
    food_name: str
    motion_direction: Literal["in", "out"]
    timestamp: datetime
