"""seed_demo_data.py — 시연 직전 DB를 깨끗한 "준비된" 상태로 만든다.

우리가 통합 작업 중에 직접 쏜 테스트 이벤트(우유, tumbler-01/07/99, item1/item2,
당근/당근2 등)가 그대로 DB에 남아있으면 시연 때 지저분해 보인다. 이 스크립트는:

  1. 기존 FoodItem / Detection / SensorReading을 전부 지우고
  2. Wa의 개별 물건 분류기(instance_classifier.joblib)가 실제로 인식하는 12개
     클래스 라벨을 container_id로 그대로 써서, 신선/임박/만료/미확인 상태가
     골고루 섞인 재고를 심는다 (그래야 대시보드가 D-day 색상별로 다양하게 보이고,
     시연 중 웹캠으로 그 12종 중 하나를 인식시켰을 때 "이미 있던 재료"로 자연스럽게
     매칭됨).
  3. board-b-sensor가 보낼 법한 온습도 값도 하나 미리 심어서 앱 홈 화면 온습도
     카드가 "-"로 비어있지 않게 한다.

실행 (backend/ 안에서):
  ./.venv/bin/python scripts/seed_demo_data.py
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import shutil
from pathlib import Path

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal, close_db
from app.models.analysis import AnalysisJob
from app.models.detection import Detection, SensorReading
from app.models.food import DateSource, FoodImage, FoodItem, FoodItemStatus, StorageType

TODAY = date.today()

# label(=Wa instance_classifier.joblib의 실제 클래스, container_id로도 그대로 씀),
# 표시 이름, 카테고리, 보관 위치, 유통기한(오늘로부터 며칠 뒤 — None이면 "미확인"),
# 날짜 출처
ITEMS = [
    ("달걀곽", "달걀 한 판", "dairy", StorageType.REFRIGERATOR, 14, DateSource.LABEL),
    ("당근", "당근", "vegetable", StorageType.REFRIGERATOR, 9, DateSource.LABEL),
    ("라떼", "라떼", "dairy", StorageType.REFRIGERATOR, 2, DateSource.LABEL),  # 임박
    ("반찬용기", "밑반찬", "other", StorageType.REFRIGERATOR, None, DateSource.UNKNOWN),  # 미확인
    ("밥용기", "즉석밥", "other", StorageType.ROOM, -1, DateSource.LABEL),  # 만료
    ("사이다", "사이다", "other", StorageType.ROOM, 180, DateSource.LABEL),
    ("스팸", "스팸", "meat", StorageType.ROOM, 3, DateSource.LABEL),  # 임박(개봉 가정)
    ("아메리카노", "아메리카노", "other", StorageType.REFRIGERATOR, 5, DateSource.LABEL),
    ("우유", "우유", "dairy", StorageType.REFRIGERATOR, 4, DateSource.LABEL),
    ("종이팩음료", "두유", "other", StorageType.REFRIGERATOR, 7, DateSource.LABEL),
    ("콜라", "콜라", "other", StorageType.ROOM, 200, DateSource.LABEL),
    ("파&마늘", "대파·마늘", "vegetable", StorageType.REFRIGERATOR, 2, DateSource.LABEL),  # 임박
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Detection))
        await session.execute(delete(SensorReading))
        await session.execute(delete(AnalysisJob))
        await session.execute(delete(FoodImage))
        await session.execute(delete(FoodItem))

        for label, display_name, category, storage, days_offset, date_source in ITEMS:
            expires_at = TODAY + timedelta(days=days_offset) if days_offset is not None else None
            session.add(FoodItem(
                display_name=display_name,
                category=category,
                container_id=label,
                quantity=1,
                storage_type=storage,
                expires_at=expires_at,
                date_source=date_source,
                confidence=Decimal("0.95") if date_source == DateSource.LABEL else None,
                status=FoodItemStatus.ACTIVE,
            ))

        session.add(SensorReading(
            device_id="board-b-sensor",
            temperature=Decimal("3.80"),
            humidity=Decimal("52.00"),
            gas_resistance_ohm=118000,
            door_open=False,
            recorded_at=datetime.now(timezone.utc),
        ))

        await session.commit()

    if settings.storage_backend == "local":
        uploads_dir = Path(settings.local_storage_path)
        if uploads_dir.exists():
            shutil.rmtree(uploads_dir)
            uploads_dir.mkdir(parents=True, exist_ok=True)
            print(f"🗑  {uploads_dir} 안의 테스트 업로드 이미지도 비움.")

    print(f"✅ 재고 {len(ITEMS)}개 + 센서값 1개로 초기화 완료.")
    for label, display_name, *_ in ITEMS:
        print(f"   - {display_name} (container_id={label})")
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
