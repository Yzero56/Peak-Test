import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SensorReadingCreate(BaseModel):
    """4번 파트 BME680 측정값. 모든 측정 필드는 선택이다."""

    device_id: str = Field(min_length=1, max_length=64)
    temperature: Decimal | None = Field(default=None, ge=-50, le=100)
    humidity: Decimal | None = Field(default=None, ge=0, le=100)
    gas_resistance_ohm: int | None = Field(default=None, ge=0)
    door_open: bool | None = None
    recorded_at: datetime | None = None


class SensorReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: str
    temperature: Decimal | None
    humidity: Decimal | None
    gas_resistance_ohm: int | None
    door_open: bool | None
    recorded_at: datetime
