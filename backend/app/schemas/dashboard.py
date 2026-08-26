from datetime import datetime

from pydantic import BaseModel

from app.schemas.food import FoodItemResponse


class DashboardSummaryResponse(BaseModel):
    total_active: int
    fresh: int
    expiring_soon: int
    expired: int
    unknown_expiry: int
    items: list[FoodItemResponse]
    temperature: float | None = None
    humidity: float | None = None
    sensor_device_id: str | None = None
    sensor_recorded_at: datetime | None = None
