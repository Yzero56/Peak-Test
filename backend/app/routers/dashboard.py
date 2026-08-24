import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import live_scan, services
from app.config import get_settings
from app.database import get_db
from app.models import Capture, Device
from app.schemas import DeviceCreate
from app.security import generate_device_token, hash_token, require_login
from app.templating import templates

SCAN_TIMEOUT_SECONDS = 5

router = APIRouter(dependencies=[Depends(require_login)])


def _device_card(db: Session, device: Device) -> dict:
    reading = services.latest_reading(db, device.id)
    return {
        "device": device,
        "online": services.is_online(device),
        "reading": reading,
        "gas_status": services.classify_gas(reading.gas_resistance_ohm) if reading else "알 수 없음",
        "gas_anomaly": services.gas_anomaly(device, reading.gas_resistance_ohm if reading else None),
        "live_active": live_scan.is_active(device.id),
        # 문이 닫히면 기기가 카메라 전원 자체를 끄므로(전력 절약), 라이브 뷰 링크는
        # 온라인 여부와 별개로 door_open일 때만 의미가 있다.
        "camera_on": bool(reading and reading.door_open),
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
def device_detail(request: Request, device_id: str, scan_error: str | None = None, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    readings = services.recent_readings(db, device_id, limit=50)
    chart_points = [
        {
            # 차트 라벨이 문자열을 그대로 슬라이싱해서 시:분을 뽑아 쓰므로(JS Date 파싱 아님)
            # KST로 미리 변환한 값을 내려줘야 화면에 실제 시각이 맞게 뜬다.
            "t": services.to_kst(r.recorded_at).isoformat(),
            "temperature_c": r.temperature_c,
            "humidity_pct": r.humidity_pct,
        }
        for r in reversed(readings)
    ]
    captures = services.recent_captures(db, device_id, limit=1)
    return templates.TemplateResponse(
        request,
        "dashboard/device_detail.html",
        {
            "device": device,
            "online": services.is_online(device),
            "readings": readings,
            "latest": readings[0] if readings else None,
            "gas_status": services.classify_gas(readings[0].gas_resistance_ohm) if readings else "알 수 없음",
            "gas_anomaly": services.gas_anomaly(device, readings[0].gas_resistance_ohm if readings else None),
            "baseline_gas_resistance_ohm": device.baseline_gas_resistance_ohm,
            "door_events": services.recent_door_events(db, device_id),
            "capture": captures[0] if captures else None,
            "chart_points_json": json.dumps(chart_points),
            "scan_error": scan_error,
            "live_active": live_scan.is_active(device_id),
            "camera_on": bool(readings and readings[0].door_open),
        },
    )


@router.get("/partials/devices/{device_id}/status")
def device_status(device_id: str, db: Session = Depends(get_db)) -> dict:
    """라이브 뷰가 기기의 IP 변경(DHCP 재할당 등)과 카메라 전원 on/off(문 개폐)를
    폴링으로 스스로 따라가기 위한 엔드포인트. door_open은 문이 닫혔다가 다시 열릴 때
    (=카메라가 막 다시 켜졌을 때) 대시보드가 죽은 스트림 연결을 새로 맺도록 알려준다.
    """
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    reading = services.latest_reading(db, device_id)
    return {
        "online": services.is_online(device),
        "ip_address": device.ip_address,
        "door_open": reading.door_open if reading else None,
        "temperature_c": reading.temperature_c if reading else None,
        "humidity_pct": reading.humidity_pct if reading else None,
        "gas_status": services.classify_gas(reading.gas_resistance_ohm) if reading else "알 수 없음",
        "gas_anomaly": services.gas_anomaly(device, reading.gas_resistance_ohm if reading else None),
    }


@router.get("/partials/devices/{device_id}/live", response_class=HTMLResponse)
def device_live_partial(request: Request, device_id: str, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    captures = services.recent_captures(db, device_id, limit=1)
    return templates.TemplateResponse(
        request,
        "dashboard/_device_live_status.html",
        {
            "device": device,
            "capture": captures[0] if captures else None,
            "live_active": live_scan.is_active(device_id),
        },
    )


@router.post("/devices/{device_id}/scan")
def scan_device(device_id: str, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    if not device.ip_address or not services.is_online(device):
        return RedirectResponse(f"/devices/{device_id}?scan_error=offline", status_code=status.HTTP_303_SEE_OTHER)

    try:
        req = urllib.request.Request(f"http://{device.ip_address}/capture")
        with urllib.request.urlopen(req, timeout=SCAN_TIMEOUT_SECONDS) as resp:
            image_bytes = resp.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return RedirectResponse(f"/devices/{device_id}?scan_error=unreachable", status_code=status.HTTP_303_SEE_OTHER)

    services.save_capture(db, device, image_bytes)
    return RedirectResponse(f"/devices/{device_id}", status_code=status.HTTP_303_SEE_OTHER)


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
