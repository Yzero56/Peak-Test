from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.food_items import to_response
from app.core.database import get_db
from app.models.detection import SensorReading
from app.models.food import FoodItem, FoodItemStatus
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import build_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    session: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    result = await session.scalars(
        select(FoodItem)
        .where(FoodItem.status == FoodItemStatus.ACTIVE)
        .order_by(FoodItem.expires_at.asc().nullslast(), FoodItem.created_at.desc())
    )
    summary = build_dashboard_summary(result.all())
    summary["items"] = [to_response(item) for item in summary["items"]]
    latest_sensor = await session.scalar(
        select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(1)
    )
    if latest_sensor:
        summary.update(
            temperature=latest_sensor.temperature,
            humidity=latest_sensor.humidity,
            sensor_device_id=latest_sensor.device_id,
            sensor_recorded_at=latest_sensor.recorded_at,
        )
    return DashboardSummaryResponse.model_validate(summary)
