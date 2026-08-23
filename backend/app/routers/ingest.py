from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import live_scan
from app.database import get_db
from app.models import Device, DoorEvent, SensorReading, utcnow
from app.schemas import SensorIngest
from app.security import verify_device_token

router = APIRouter(prefix="/api/devices", tags=["ingest"])


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

    door_changed = False
    if payload.door_open is not None:
        last_event = db.execute(
            select(DoorEvent)
            .where(DoorEvent.device_id == device.id)
            .order_by(DoorEvent.changed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        door_changed = last_event is None or last_event.is_open != payload.door_open
        if door_changed:
            db.add(DoorEvent(device_id=device.id, is_open=payload.door_open, changed_at=now))

    device.last_seen_at = now
    db.commit()

    # 문이 열리면 자동 스캔 루프 시작, 닫히면 중단 — 실제 상태 전환일 때만 반응한다
    # (매 하트비트/센서 전송마다 스레드를 다시 만들지 않도록).
    if door_changed:
        if payload.door_open:
            live_scan.start(device.id)
        else:
            live_scan.stop(device.id)

    return {"ok": True}


@router.post("/{device_id}/heartbeat", status_code=status.HTTP_200_OK)
def ingest_heartbeat(
    request: Request,
    device: Device = Depends(get_authorized_device),
    db: Session = Depends(get_db),
) -> dict:
    """기기가 살아있고 어떤 IP에서 라이브 스트림(/stream, /capture)을 서빙 중인지 알려준다.

    IP는 기기가 스스로 보고하는 값이 아니라 이 요청의 실제 소스 주소를 사용한다.
    """
    device.ip_address = request.client.host if request.client else None
    device.last_seen_at = utcnow()
    db.commit()
    return {"ok": True}
