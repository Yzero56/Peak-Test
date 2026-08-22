import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app import services
from app.config import get_settings
from app.database import get_db
from app.models import Capture, Device
from app.schemas import DeviceCreate
from app.security import generate_device_token, hash_token, require_login
from app.templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


def _device_card(db: Session, device: Device) -> dict:
    reading = services.latest_reading(db, device.id)
    return {
        "device": device,
        "online": services.is_online(device),
        "reading": reading,
        "gas_status": services.classify_gas(reading.gas_resistance_ohm) if reading else "알 수 없음",
    }


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    captures = services.recent_captures(db, limit=12)
    return templates.TemplateResponse(
        request,
        "dashboard/overview.html",
        {"device_cards": devices, "captures": captures},
    )


@router.get("/partials/overview", response_class=HTMLResponse)
def overview_partial(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    captures = services.recent_captures(db, limit=12)
    return templates.TemplateResponse(
        request,
        "dashboard/_overview_body.html",
        {"device_cards": devices, "captures": captures},
    )


@router.get("/devices/new", response_class=HTMLResponse)
def new_device_form(request: Request):
    return templates.TemplateResponse(request, "dashboard/device_new.html", {})


@router.post("/devices", response_class=HTMLResponse)
def create_device(
    request: Request,
    device_id: str = Form(..., alias="id"),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    payload = DeviceCreate(id=device_id, name=name)
    if db.get(Device, payload.id) is not None:
        return templates.TemplateResponse(
            request,
            "dashboard/device_new.html",
            {"error": f"'{payload.id}' 기기 ID가 이미 존재해요."},
            status_code=status.HTTP_409_CONFLICT,
        )

    token = generate_device_token()
    device = Device(id=payload.id, name=payload.name, token_hash=hash_token(token))
    db.add(device)
    db.commit()

    return templates.TemplateResponse(request, "dashboard/device_created.html", {"device": device, "token": token})


@router.get("/devices/{device_id}", response_class=HTMLResponse)
def device_detail(request: Request, device_id: str, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    readings = services.recent_readings(db, device_id, limit=50)
    chart_points = [
        {
            "t": r.recorded_at.isoformat(),
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
        }
        for r in reversed(readings)
    ]
    return templates.TemplateResponse(
        request,
        "dashboard/device_detail.html",
        {
            "device": device,
            "online": services.is_online(device),
            "readings": readings,
            "latest": readings[0] if readings else None,
            "gas_status": services.classify_gas(readings[0].gas_resistance_ohm) if readings else "알 수 없음",
            "door_events": services.recent_door_events(db, device_id),
            "captures": services.recent_captures(db, device_id, limit=24),
            "chart_points_json": json.dumps(chart_points),
        },
    )


@router.get("/captures", response_class=HTMLResponse)
def captures_list(request: Request, device_id: str | None = None, db: Session = Depends(get_db)):
    captures = services.recent_captures(db, device_id, limit=60)
    return templates.TemplateResponse(
        request,
        "dashboard/captures.html",
        {"captures": captures, "devices": services.all_devices(db), "selected_device_id": device_id},
    )


@router.get("/captures/{capture_id}", response_class=HTMLResponse)
def capture_detail(request: Request, capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    return templates.TemplateResponse(request, "dashboard/capture_detail.html", {"capture": capture})


@router.get("/media/captures/{capture_id}")
def capture_image(capture_id: int, db: Session = Depends(get_db)):
    capture = db.get(Capture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="Capture not found")
    path = get_settings().media_path / capture.image_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(path)
