from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.detection import SensorReading
from app.schemas.sensor import SensorReadingCreate, SensorReadingResponse

router = APIRouter(prefix="/sensor-readings", tags=["sensor-readings"])


@router.post("", response_model=SensorReadingResponse, status_code=status.HTTP_201_CREATED)
async def create_sensor_reading(
    data: SensorReadingCreate,
    session: AsyncSession = Depends(get_db),
) -> SensorReadingResponse:
    reading = SensorReading(**data.model_dump(exclude={"recorded_at"}))
    if data.recorded_at is not None:
        reading.recorded_at = data.recorded_at
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return SensorReadingResponse.model_validate(reading)


@router.get("", response_model=list[SensorReadingResponse])
async def list_sensor_readings(
    device_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[SensorReadingResponse]:
    query = select(SensorReading)
    if device_id is not None:
        query = query.where(SensorReading.device_id == device_id)
    query = query.order_by(SensorReading.recorded_at.desc()).limit(limit)
    readings = (await session.scalars(query)).all()
    return [SensorReadingResponse.model_validate(reading) for reading in readings]


@router.get("/latest", response_model=SensorReadingResponse)
async def latest_sensor_reading(
    device_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> SensorReadingResponse:
    query = select(SensorReading)
    if device_id is not None:
        query = query.where(SensorReading.device_id == device_id)
    reading = await session.scalar(query.order_by(SensorReading.recorded_at.desc()).limit(1))
    if reading is None:
        raise HTTPException(status_code=404, detail="no_sensor_reading")
    return SensorReadingResponse.model_validate(reading)
