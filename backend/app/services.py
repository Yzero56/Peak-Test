from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture, Device, DoorEvent, SensorReading, utcnow

ONLINE_WITHIN = timedelta(minutes=5)


def is_online(device: Device) -> bool:
    if device.last_seen_at is None:
        return False
    return utcnow() - device.last_seen_at <= ONLINE_WITHIN


def classify_gas(resistance_ohm: float | None) -> str:
    """BME680 가스 저항값 기반 임계값 분류 (placeholder).

    저항이 낮을수록 VOC 농도가 높다고 가정한 데모용 추정치이며, 실제 임계값은
    하드웨어 캘리브레이션 후 조정이 필요하다.
    """
    if resistance_ohm is None:
        return "알 수 없음"
    if resistance_ohm < 20_000:
        return "위험"
    if resistance_ohm < 50_000:
        return "주의"
    return "정상"


def all_devices(db: Session) -> list[Device]:
    return list(db.execute(select(Device).order_by(Device.name)).scalars().all())


def latest_reading(db: Session, device_id: str) -> SensorReading | None:
    stmt = (
        select(SensorReading)
        .where(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def recent_readings(db: Session, device_id: str, limit: int = 50) -> list[SensorReading]:
    stmt = (
        select(SensorReading)
        .where(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def recent_door_events(db: Session, device_id: str, limit: int = 20) -> list[DoorEvent]:
    stmt = (
        select(DoorEvent)
        .where(DoorEvent.device_id == device_id)
        .order_by(DoorEvent.changed_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def recent_captures(db: Session, device_id: str | None = None, limit: int = 24) -> list[Capture]:
    stmt = select(Capture).order_by(Capture.captured_at.desc()).limit(limit)
    if device_id:
        stmt = stmt.where(Capture.device_id == device_id)
    return list(db.execute(stmt).scalars().all())
