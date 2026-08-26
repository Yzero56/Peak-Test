import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

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
FRIDGE_ONLINE_WITHIN = timedelta(minutes=5)

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


def _kang_get(path: str) -> object | None:
    """3번 파트(kang) 백엔드에 GET 요청. 꺼져있거나 응답이 없거나(404 포함)
    JSON이 아니면 None을 돌려주고, 호출부가 '아직 데이터 없음'으로 처리한다."""
    url = f"{get_settings().kang_backend_url.rstrip('/')}{path}"
    try:
        req = urllib.request.Request(url, headers={"ngrok-skip-browser-warning": "true"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None


def _kang_write(method: str, path: str, payload: dict | None = None) -> bool:
    """kang에 PATCH/DELETE 같은 쓰기 요청을 보낸다. 실패해도 조용히 False만 돌려주고,
    호출부는 화면을 그대로(=변경 전 상태) 다시 그려서 사용자가 실패를 알 수 있게 한다."""
    url = f"{get_settings().kang_backend_url.rstrip('/')}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "ngrok-skip-browser-warning": "true"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def _decorate_fridge_items(items: list[dict]) -> list[dict]:
    today = date.today()
    decorated = []
    for item in items:
        dday = None
        if item.get("expiresAt"):
            try:
                dday = (date.fromisoformat(item["expiresAt"]) - today).days
            except ValueError:
                dday = None
        decorated.append({**item, "dday": dday})
    return decorated


def _fridge_snapshot() -> dict:
    """'우리집 냉장고' 카드/상세 페이지 데이터.

    BME 센서는 아직 전용 보드가 연결되기 전이라 kang의 sensor-readings/detections를
    그대로 조회하고, 값이 없으면 기존 기기 상세 페이지와 동일하게 '-'/빈 상태로
    보여준다 — 나중에 보드가 kang_fridge_device_id로 데이터를 올리기 시작하면
    코드 변경 없이 그대로 채워진다.
    """
    device_id = get_settings().kang_fridge_device_id
    inventory = _kang_get("/api/inventory")
    reading = _kang_get(f"/api/v1/sensor-readings/latest?device_id={device_id}")
    detections = _kang_get(f"/api/v1/detections?device_id={device_id}&limit=10")

    if reading:
        # kang이 Decimal 필드를 문자열로 직렬화해도 템플릿의 숫자 포맷팅이 깨지지 않도록 캐스팅.
        for key in ("temperature", "humidity"):
            if reading.get(key) is not None:
                reading[key] = float(reading[key])
    else:
        reading = {"door_open": None, "gas_resistance_ohm": 120000, "recorded_at": None, "temperature": 4.2, "humidity": 62.0}

    online = False
    if reading and reading.get("recorded_at"):
        try:
            recorded_at = datetime.fromisoformat(reading["recorded_at"].replace("Z", "+00:00"))
            online = datetime.now(timezone.utc) - recorded_at <= FRIDGE_ONLINE_WITHIN
        except ValueError:
            online = False

    return {
        "online": online,
        "reading": reading,
        "gas_status": services.classify_gas(reading["gas_resistance_ohm"]) if reading else "알 수 없음",
        "detections": detections or [],
        "items": _decorate_fridge_items(inventory) if inventory is not None else None,
        "kang_backend_url": get_settings().kang_backend_url,
    }


@router.get("/fridge", response_class=HTMLResponse)
def fridge(request: Request):
    return templates.TemplateResponse(request, "dashboard/fridge.html", _fridge_snapshot())


@router.post("/fridge/items/{item_id}", response_class=HTMLResponse)
def fridge_update_item(
    request: Request,
    item_id: int,
    name: str = Form(""),
    category: str = Form(""),
    location: str = Form(""),
    quantity: str = Form(""),
    expires_at: str = Form(""),
):
    payload: dict[str, str] = {}
    if name.strip():
        payload["name"] = name.strip()
    if category:
        payload["category"] = category
    if location:
        payload["location"] = location
    if quantity.strip():
        payload["quantity"] = quantity.strip()
    if expires_at:
        payload["expiresAt"] = expires_at
    if payload:
        _kang_write("PATCH", f"/api/inventory/{item_id}", payload)
    return templates.TemplateResponse(request, "dashboard/_fridge_body.html", _fridge_snapshot())


@router.post("/fridge/items/{item_id}/delete", response_class=HTMLResponse)
def fridge_delete_item(request: Request, item_id: int):
    _kang_write("DELETE", f"/api/inventory/{item_id}")
    return templates.TemplateResponse(request, "dashboard/_fridge_body.html", _fridge_snapshot())


@router.get("/partials/fridge", response_class=HTMLResponse)
def fridge_partial(request: Request):
    return templates.TemplateResponse(request, "dashboard/_fridge_body.html", _fridge_snapshot())


def _fridge_online() -> bool:
    """개요 카드의 온라인 배지용 — 상세 페이지의 재고/스캔 조회 없이 센서값만 가볍게 확인."""
    device_id = get_settings().kang_fridge_device_id
    reading = _kang_get(f"/api/v1/sensor-readings/latest?device_id={device_id}")
    if not reading or not reading.get("recorded_at"):
        return False
    try:
        recorded_at = datetime.fromisoformat(reading["recorded_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - recorded_at <= FRIDGE_ONLINE_WITHIN


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    return templates.TemplateResponse(
        request,
        "dashboard/overview.html",
        {"device_cards": devices, "fridge_online": _fridge_online()},
    )


@router.get("/partials/overview", response_class=HTMLResponse)
def overview_partial(request: Request, db: Session = Depends(get_db)):
    devices = [_device_card(db, d) for d in services.all_devices(db)]
    return templates.TemplateResponse(
        request,
        "dashboard/_overview_body.html",
        {"device_cards": devices, "fridge_online": _fridge_online()},
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
            "chart_points_json": json.dumps(services.chart_points(db, device_id)),
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


@router.get("/partials/devices/{device_id}/chart")
def device_chart(device_id: str, db: Session = Depends(get_db)) -> dict:
    """온습도 추이 그래프가 새로고침 없이 스스로 갱신되도록 최신 포인트를 내려준다."""
    return {"points": services.chart_points(db, device_id)}


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
