from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.food_items import get_legacy_item, to_legacy_response
from app.core.database import get_db
from app.models.detection import SensorReading
from app.models.food import DateSource, FoodItem, FoodItemStatus, StorageType
from app.services import recipe_service

router = APIRouter(prefix="/inventory", tags=["legacy-inventory"])
scan_router = APIRouter(prefix="/scan-candidates", tags=["legacy-scan"])
recipe_router = APIRouter(prefix="/recipes", tags=["legacy-recipes"])
# 온습도는 kang 브랜치엔 없는, 이 통합본에서만 추가한 레거시 엔드포인트 —
# board-b-sensor(BME680)가 POST /api/v1/sensor-readings로 올린 최신값을 그대로 내려준다.
climate_router = APIRouter(prefix="/climate", tags=["legacy-climate"])


def parse_payload(data: dict) -> dict:
    location = {"냉장": StorageType.REFRIGERATOR, "냉동": StorageType.FREEZER, "실온": StorageType.ROOM}
    category = {"채소": "vegetable", "육류·계란": "meat", "유제품": "dairy", "수산물": "seafood", "기타": "other"}
    return {
        "display_name": data["name"],
        "category": category.get(data.get("category"), data.get("category")),
        "quantity": 1,
        "unit": data.get("quantity"),
        "storage_type": location[data.get("location", "냉장")],
        "expires_at": date.fromisoformat(data["expiresAt"]) if data.get("expiresAt") else None,
        "date_source": DateSource.MANUAL if data.get("expiresAt") else DateSource.UNKNOWN,
        "status": FoodItemStatus.ACTIVE,
    }


@router.get("", response_model=list[dict])
async def list_inventory(session: AsyncSession = Depends(get_db)) -> list[dict]:
    items = (await session.scalars(select(FoodItem).where(FoodItem.status == FoodItemStatus.ACTIVE))).all()
    return [to_legacy_response(item) for item in items]


@router.post("", response_model=list[dict], status_code=status.HTTP_201_CREATED)
async def create_inventory(data: list[dict], session: AsyncSession = Depends(get_db)) -> list[dict]:
    created = []
    for payload in data:
        item = FoodItem(**parse_payload(payload))
        next_id = (await session.scalar(select(FoodItem.legacy_id).order_by(FoodItem.legacy_id.desc()).limit(1))) or 0
        item.legacy_id = next_id + 1
        session.add(item)
        await session.flush()
        created.append(item)
    await session.commit()
    return [to_legacy_response(item) for item in created]


@router.patch("/{item_id}", response_model=dict)
async def update_inventory(item_id: int, data: dict, session: AsyncSession = Depends(get_db)) -> dict:
    item = await get_legacy_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if "quantity" in data:
        item.unit = data["quantity"]
    if "expiresAt" in data:
        item.expires_at = data["expiresAt"] or None
        item.date_source = DateSource.MANUAL if item.expires_at else DateSource.UNKNOWN
    await session.commit()
    return to_legacy_response(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory(item_id: int, session: AsyncSession = Depends(get_db)) -> None:
    item = await get_legacy_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    item.status = FoodItemStatus.DISCARDED
    await session.commit()


@scan_router.get("", response_model=list[dict])
async def scan_candidates() -> list[dict]:
    # The existing HJ app treats an empty result as a valid no-candidate response.
    return []


@climate_router.get("", response_model=dict)
async def climate(session: AsyncSession = Depends(get_db)) -> dict:
    """앱 홈 화면 온습도 카드용 — board-b-sensor가 올린 가장 최근 측정값 하나."""
    reading = await session.scalar(select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(1))
    if reading is None:
        return {"temperatureC": None, "humidityPct": None}
    return {
        "temperatureC": float(reading.temperature) if reading.temperature is not None else None,
        "humidityPct": float(reading.humidity) if reading.humidity is not None else None,
    }


@recipe_router.get("", response_model=list[dict])
async def list_recipes() -> list[dict]:
    return await recipe_service.get_recipes()
