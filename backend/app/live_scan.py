"""문 열림/닫힘에 따른 자동 스캔 루프.

리드스위치가 door_open=true를 보고하면 기기별로 백그라운드 스레드를 하나 띄워
문이 닫힐 때까지 몇 초 간격으로 기기의 /capture를 가져와 인식·저장한다
(services.save_capture가 이미 "기기당 최신 1건만 유지"를 보장하므로 여기서는
그냥 반복 호출만 하면 된다). door_open=false가 오면 스레드를 멈춘다.
"""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request

from app import services
from app.database import SessionLocal
from app.models import Device

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 4
FETCH_TIMEOUT_SECONDS = 5

_stop_flags: dict[str, threading.Event] = {}
_lock = threading.Lock()


def is_active(device_id: str) -> bool:
    with _lock:
        flag = _stop_flags.get(device_id)
    return flag is not None and not flag.is_set()


def start(device_id: str) -> None:
    with _lock:
        existing = _stop_flags.get(device_id)
        if existing is not None and not existing.is_set():
            return
        stop_flag = threading.Event()
        _stop_flags[device_id] = stop_flag

    threading.Thread(target=_run, args=(device_id, stop_flag), daemon=True).start()


def stop(device_id: str) -> None:
    with _lock:
        flag = _stop_flags.get(device_id)
    if flag is not None:
        flag.set()


def _run(device_id: str, stop_flag: threading.Event) -> None:
    logger.info("[live-scan] %s 자동 스캔 시작", device_id)
    while not stop_flag.wait(SCAN_INTERVAL_SECONDS):
        db = SessionLocal()
        try:
            device = db.get(Device, device_id)
            if device is None or not device.ip_address or not services.is_online(device):
                continue
            try:
                req = urllib.request.Request(f"http://{device.ip_address}/capture")
                with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
                    image_bytes = resp.read()
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                continue
            services.save_capture(db, device, image_bytes)
        finally:
            db.close()
    logger.info("[live-scan] %s 자동 스캔 종료", device_id)
