from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.detection import detect_objects
from app.models import Capture, DetectedObject, Device, DoorEvent, SensorReading, utcnow
from app.schemas import SensorIngest
from app.security import verify_device_token

router = APIRouter(prefix="/api/devices", tags=["ingest"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def get_authorized_device(
    device_id: str,
    x_device_token: str = Header(...),
    db: Session = Depends(get_db),
) -> Device:
    device = db.get(Device, device_id)
    if device is None or not verify_device_token(device, x_device_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device or token")
    return device


@router.post("/{device_id}/sensors", status_code=status.HTTP_201_CREATED)
def ingest_sensor_reading(
    payload: SensorIngest,
    device: Device = Depends(get_authorized_device),
    db: Session = Depends(get_db),
) -> dict:
    now = utcnow()
    db.add(
        SensorReading(
            device_id=device.id,
            recorded_at=now,
            door_open=payload.door_open,
            temperature_c=payload.temperature_c,
            humidity_pct=payload.humidity_pct,
            gas_resistance_ohm=payload.gas_resistance_ohm,
        )
    )

    if payload.door_open is not None:
        last_event = db.execute(
            select(DoorEvent)
            .where(DoorEvent.device_id == device.id)
            .order_by(DoorEvent.changed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last_event is None or last_event.is_open != payload.door_open:
            db.add(DoorEvent(device_id=device.id, is_open=payload.door_open, changed_at=now))

    device.last_seen_at = now
    db.commit()
    return {"ok": True}


@router.post("/{device_id}/captures", status_code=status.HTTP_201_CREATED)
async def ingest_capture(
    device: Device = Depends(get_authorized_device),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image type")

    settings = get_settings()
    device_dir = settings.media_path / "captures" / device.id
    device_dir.mkdir(parents=True, exist_ok=True)

    now = utcnow()
    extension = Path(file.filename or "").suffix or ".jpg"
    filename = f"{now:%Y%m%dT%H%M%S}_{uuid4().hex[:8]}{extension}"
    dest = device_dir / filename
    dest.write_bytes(await file.read())

    detections = detect_objects(dest)

    capture = Capture(device_id=device.id, captured_at=now, image_path=f"captures/{device.id}/{filename}")
    db.add(capture)
    db.flush()
    for detection in detections:
        db.add(DetectedObject(capture_id=capture.id, label=detection.label, confidence=detection.confidence))

    device.last_seen_at = now
    db.commit()

    return {
        "capture_id": capture.id,
        "detected": [{"label": d.label, "confidence": d.confidence} for d in detections],
    }
