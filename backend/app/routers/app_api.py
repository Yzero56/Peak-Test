"""모바일 앱(RN/Expo)이 쓰는 JSON API. 관리자 대시보드(HTML)와는 별개 경로이며,
세션 로그인 대신 `X-App-Token` 헤더(관리자 비밀번호 재사용)로 인증한다.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import recipes as recipes_service
from app import services
from app.database import get_db
from app.models import InventoryItem
from app.schemas import ClimateOut, InventoryItemIn, InventoryItemOut, InventoryItemPatch, RecipeOut, ScanCandidateOut
from app.security import require_app_token

router = APIRouter(prefix="/api", tags=["app"], dependencies=[Depends(require_app_token)])

DEFAULT_SCAN_LOCATION = "냉장"
DEFAULT_SCAN_CATEGORY = "기타"
DEFAULT_SCAN_QUANTITY = "1개"
DEFAULT_SCAN_LEAD_DAYS = 7


def _to_out(item: InventoryItem) -> InventoryItemOut:
    return InventoryItemOut(
        id=item.id,
        name=item.name,
        category=item.category,
        quantity=item.quantity,
        expiresAt=item.expires_at,
        location=item.location,
    )


@router.get("/inventory", response_model=list[InventoryItemOut])
def list_inventory(db: Session = Depends(get_db)) -> list[InventoryItemOut]:
    stmt = select(InventoryItem).order_by(InventoryItem.expires_at)
    items = db.execute(stmt).scalars().all()
    return [_to_out(i) for i in items]


@router.post("/inventory", response_model=list[InventoryItemOut], status_code=status.HTTP_201_CREATED)
def create_inventory_items(payload: list[InventoryItemIn], db: Session = Depends(get_db)) -> list[InventoryItemOut]:
    created = [
        InventoryItem(
            name=p.name,
            category=p.category,
            quantity=p.quantity,
            expires_at=p.expiresAt,
            location=p.location,
        )
        for p in payload
    ]
    db.add_all(created)
    db.commit()
    for item in created:
        db.refresh(item)

    # 재료를 새로 넣은 시점 = 가스 이상 감지의 baseline을 다시 잡는 기준점.
    # (단일 냉장고 가정이라 device 종속 없이 전체 기기에 적용)
    for device in services.all_devices(db):
        services.set_gas_baseline(db, device)
    db.commit()

    return [_to_out(i) for i in created]


@router.patch("/inventory/{item_id}", response_model=InventoryItemOut)
def patch_inventory_item(item_id: int, payload: InventoryItemPatch, db: Session = Depends(get_db)) -> InventoryItemOut:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.expiresAt is not None:
        item.expires_at = payload.expiresAt
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/inventory/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    db.delete(item)
    db.commit()


@router.get("/climate", response_model=ClimateOut)
def climate(db: Session = Depends(get_db)) -> ClimateOut:
    reading = services.latest_climate_reading(db)
    if reading is None:
        return ClimateOut()
    return ClimateOut(temperatureC=reading.temperature_c, humidityPct=reading.humidity_pct)


@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes() -> list[RecipeOut]:
    """식품안전나라 레시피 DB에서 가져온 추천 레시피. 키 미설정/요청 실패 시 빈 리스트를
    반환하며, 앱은 이 경우 자체 목업 레시피로 폴백한다."""
    return [RecipeOut(**r) for r in recipes_service.fetch_recipes()]


@router.get("/scan-candidates", response_model=list[ScanCandidateOut])
def scan_candidates(db: Session = Depends(get_db)) -> list[ScanCandidateOut]:
    """가장 최근 스캔(캡처)에서 인식된 라벨들을 후보로 반환한다.

    VLM이 아직 카테고리/수량/보관위치까지는 주지 않는 목업 단계라 기본값으로 채운다
    (앱에서 선택 후 확인하는 화면이라 여기서는 후보만 제공하면 됨).
    """
    captures = services.recent_captures(db, limit=1)
    if not captures:
        return []
    default_expires = (date.today() + timedelta(days=DEFAULT_SCAN_LEAD_DAYS)).isoformat()
    return [
        ScanCandidateOut(
            name=obj.label,
            quantity=DEFAULT_SCAN_QUANTITY,
            expiresAt=default_expires,
            category=DEFAULT_SCAN_CATEGORY,
            location=DEFAULT_SCAN_LOCATION,
        )
        for obj in captures[0].objects
    ]
