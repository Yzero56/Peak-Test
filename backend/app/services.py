from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.detection import detect_objects
from app.models import Capture, DetectedObject, Device, DoorEvent, SensorReading, utcnow

ONLINE_WITHIN = timedelta(minutes=5)
KST_OFFSET = timedelta(hours=9)


def to_kst(value):
    """DB에는 naive UTC(utcnow())로 저장되므로, 화면에 보여줄 때만 KST로 변환한다."""
    if value is None:
        return None
    return value + KST_OFFSET


def is_online(device: Device) -> bool:
    if device.last_seen_at is None:
        return False
    return utcnow() - device.last_seen_at <= ONLINE_WITHIN


GAS_ANOMALY_DROP_PCT = 30.0  # baseline 대비 이 %만큼 떨어지면 "이상 신호"로 본다


def set_gas_baseline(db: Session, device: Device) -> None:
    """재료 투입 시점(재고 추가)의 가스 저항값을 baseline으로 저장한다.

    절대 임계값이 아니라 이 baseline 대비 하락폭으로 이상을 감지하기 위함 —
    기기/환경마다 평상시 가스 저항값 자체가 달라 절대값 기준은 오탐이 잦다.
    """
    reading = latest_reading(db, device.id)
    if reading is None or reading.gas_resistance_ohm is None:
        return
    device.baseline_gas_resistance_ohm = reading.gas_resistance_ohm
    device.baseline_gas_set_at = utcnow()


def gas_anomaly(device: Device, resistance_ohm: float | None) -> bool:
    """baseline 대비 하락폭이 GAS_ANOMALY_DROP_PCT% 이상이면 이상 신호로 본다.

    아직 재료를 넣은 적이 없어 baseline이 없으면 판단하지 않는다(오탐 방지).
    """
    if resistance_ohm is None or not device.baseline_gas_resistance_ohm:
        return False
    drop_pct = (device.baseline_gas_resistance_ohm - resistance_ohm) / device.baseline_gas_resistance_ohm * 100
    return drop_pct >= GAS_ANOMALY_DROP_PCT


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


def save_capture(db: Session, device: Device, image_bytes: bytes) -> Capture:
    """기기의 스캔 결과를 저장한다. 쌓아두지 않고 기기당 최신 1건만 남긴다."""
    settings = get_settings()
    device_dir = settings.media_path / "captures" / device.id
    device_dir.mkdir(parents=True, exist_ok=True)
    dest = device_dir / "latest.jpg"

    old_captures = list(db.execute(select(Capture).where(Capture.device_id == device.id)).scalars().all())
    for old in old_captures:
        db.delete(old)
    db.flush()

    dest.write_bytes(image_bytes)

    now = utcnow()
    capture = Capture(device_id=device.id, captured_at=now, image_path=f"captures/{device.id}/latest.jpg")
    db.add(capture)
    db.flush()

    for detection in detect_objects(dest):
        db.add(DetectedObject(capture_id=capture.id, label=detection.label, confidence=detection.confidence))

    device.last_seen_at = now
    db.commit()
    db.refresh(capture)
    return capture
