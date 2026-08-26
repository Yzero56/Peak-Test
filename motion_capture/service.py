"""
service.py — 1번 파트(ESP32 영상 캡처 & In/Out 모션 판정)의 러닝타임 서비스.

webcam_ap_capture.ino(ESP32)가 내놓는 /preview를 계속 폴링해서 motion.py의
MotionDetector에 먹이고, 결과(이벤트 시작/종료, In/Out 판정)를 REST + 대시보드로
보여준다.

지금은 노트북에서 돌리지만(개발 단계), FastAPI로 짜둬서 3번 파트 백엔드가
생기면 그대로 옮기거나 붙여쓸 수 있게 했다. ESP32와의 통신 방식(HTTP GET
/preview)도 나중에 STA 모드로 바뀌어도 그대로 재사용된다 — 바뀌는 건 IP뿐.

실행:
  ./.venv/bin/python motion_capture/service.py --esp-host 192.168.4.1
"""
import argparse
import io
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from motion import MotionDetector, MotionEvent  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = ROOT / "data" / "events"
EVENTS_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_LOG = EVENTS_DIR / "events.jsonl"

app = FastAPI(title="Fridge-AI Motion Service")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

detector = MotionDetector()
state_lock = threading.Lock()
shared = {
    "connected": False,
    "last_ratio": 0.0,
    "last_state": "idle",
    "last_error": None,
    "poll_count": 0,
    "poll_ms": 0.0,
    "door_open": None,  # True/False = 리드스위치 있음, None = 아직 배선 안 됨(구형 펌웨어) — 항상 폴링 취급
    "live_bbox": None,  # 세션 진행 중 "지금 이 프레임에서 바뀐 곳" — 실시간 추적 박스 표시용
    "live_ratio": 0.0,       # 개발자 모드용 — 이번 프레임에서 바뀐 픽셀 비율(원본 마스크 기준)
    "hand_seen": False,      # 이번 세션에서 손이 한 번이라도 감지됐는지
    "hand_boxes": [],        # 이번 프레임에서 감지된 손 박스들(0~1 정규화) — 빨간 박스로 그릴 용도
    "session_start_ts": None,  # 문 열린 시각(에폭) — 프론트에서 경과시간/카운트다운 표시용
    "live_crop_seq": 0,      # 라이브 크롭이 갱신될 때마다 증가 — 프론트가 캐시 무시하고 새로 받아오는 트리거
}
latest_frame: bytes | None = None  # 모션 분석용으로 받아온 프레임을 대시보드 미리보기에도 그대로 재사용
latest_live_crop: bytes | None = None  # 세션 중 방금 잡힌 "물체 후보" 크롭 — 개발자 모드에서 실시간으로 보여줌
rotation_degrees = 0  # 0/90/180/270 — 화면 미리보기와 모션 분석 둘 다 이 회전이 적용된 프레임을 본다

esp_host = "192.168.4.1"
poll_interval = 0.2
http_port = 8500

_ROTATE_OP = {
    90: Image.Transpose.ROTATE_270,   # PIL은 반시계 기준이라, 화면상 "시계방향 90도"는 ROTATE_270에 대응
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def rotate_jpeg(jpeg_bytes: bytes, degrees: int) -> bytes:
    """카메라 마운트 각도가 애매할 때 화면/분석 기준을 맞추기 위한 회전.
    모션 감지(motion.py)의 위/아래 축 판정도 이 회전 이후 프레임을 보게 되므로,
    화면에서 똑바로 보이게 맞추면 In/Out 판정 기준도 같이 맞는다."""
    op = _ROTATE_OP.get(degrees % 360)
    if op is None:  # 0도
        return jpeg_bytes
    img = Image.open(io.BytesIO(jpeg_bytes)).transpose(op)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
stop_flag = threading.Event()


def local_lan_ip() -> str | None:
    """이 컴퓨터의 현재 WiFi IP. FridgeCam처럼 인터넷 없는 네트워크에서도
    동작해야 해서 macOS 인터페이스 IP를 직접 물어본다 (web_capture/server.py와 동일)."""
    for iface in ("en0", "en1"):
        try:
            out = subprocess.run(
                ["ipconfig", "getifaddr", iface],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            if out:
                return out
        except (OSError, subprocess.SubprocessError):
            continue
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def save_event(ev: MotionEvent):
    if ev.start_frame:
        (EVENTS_DIR / f"{ev.id}_start.jpg").write_bytes(ev.start_frame)
    if ev.end_frame:
        (EVENTS_DIR / f"{ev.id}_end.jpg").write_bytes(ev.end_frame)
    if ev.start_crop:
        (EVENTS_DIR / f"{ev.id}_start_crop.jpg").write_bytes(ev.start_crop)
    if ev.end_crop:
        (EVENTS_DIR / f"{ev.id}_end_crop.jpg").write_bytes(ev.end_crop)
    if ev.best_crop:
        (EVENTS_DIR / f"{ev.id}_best_crop.jpg").write_bytes(ev.best_crop)
    # 세션 내내 손 등장 이후 찍힌 프레임별 크롭을 전부 저장 — 로그 페이지에서
    # "5초 동안 실제로 뭘 찍었는지" 필름스트립으로 훑어볼 수 있게. 개수는
    # max_session_frames로 이미 상한이 있음(detector 쪽에서).
    for i, fr in enumerate(ev.frames):
        if fr["crop"]:
            (EVENTS_DIR / f"{ev.id}_frame_{i:03d}.jpg").write_bytes(fr["crop"])
    with open(EVENTS_LOG, "a") as f:
        f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")


def check_door() -> bool | None:
    """ESP32의 /door를 확인한다. 리드스위치가 아직 안 배선됐으면(핀이 플로팅 없이
    INPUT_PULLUP이라 항상 HIGH) 그냥 계속 "열림"이 오고, 구형 펌웨어라 /door 자체가
    없으면 None(=알 수 없음, 안전하게 항상 폴링하는 쪽으로 취급)."""
    try:
        r = requests.get(f"http://{esp_host}/door", timeout=2)
        if r.status_code == 200:
            return bool(r.json().get("open", True))
    except requests.exceptions.RequestException:
        pass
    return None


def fetch_preview_frame() -> bytes | None:
    """/preview 한 장 받아서 회전 적용 후 돌려준다. 실패하면 shared 상태만 갱신하고 None."""
    global latest_frame
    try:
        r = requests.get(f"http://{esp_host}/preview", timeout=3)
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            frame = rotate_jpeg(r.content, rotation_degrees) if rotation_degrees else r.content
            with state_lock:
                shared["connected"] = True
                shared["last_error"] = None
                shared["poll_count"] += 1
                latest_frame = frame
            return frame
        with state_lock:
            shared["connected"] = False
            shared["last_error"] = f"HTTP {r.status_code}"
    except requests.exceptions.RequestException as e:
        with state_lock:
            shared["connected"] = False
            shared["last_error"] = str(e)
    return None


def poll_loop():
    """문열림 → 계산 시작(세션 추적) → 문닫힘 → 판정.

    문이 열려있는 동안 계속 프레임을 추적해서(motion.track_session_frame) 매번
    "지금 이 프레임에서 바뀐 곳" 박스를 shared["live_bbox"]에 올린다 — 프론트엔드가
    이걸 실시간 추적 박스로 그린다(오브젝트 트래킹 화면처럼). 문이 닫히면 그동안
    쌓인 궤적/플로우/시작-끝 비교를 종합해서 세션당 딱 한 번 판정한다.

    리드스위치가 아직 없으면(door_open이 계속 None) 세션 개념 자체가 성립하지
    않으니, 그냥 라이브 화면만 계속 보여주고 판정은 안 한다."""
    global latest_live_crop
    door_open_last = None  # 직전 루프의 문 상태 — 전환 감지용

    while not stop_flag.is_set():
        t0 = time.time()
        door_open = check_door()
        is_open = True if door_open is None else door_open  # 리드스위치 없으면 라이브만
        has_switch = door_open is not None

        with state_lock:
            shared["door_open"] = door_open  # None 그대로 노출 — UI에서 "리드스위치 없음"으로 구분

        if has_switch and door_open_last is False and is_open is True:
            # 문이 방금 열렸다 — 세션 시작
            frame = fetch_preview_frame()
            if frame:
                detector.start_session(frame, t0)
                with state_lock:
                    shared["live_bbox"] = None
                    shared["live_ratio"] = 0.0
                    shared["hand_seen"] = False
                    shared["hand_boxes"] = []
                    shared["session_start_ts"] = t0

        elif has_switch and door_open_last is True and is_open is False:
            # 문이 방금 닫혔다 — 마지막 프레임으로 세션 종료 + 한 번만 판정
            frame = fetch_preview_frame()
            if frame:
                ev = detector.end_session(frame, t0)
                if ev:
                    save_event(ev)
            with state_lock:
                shared["live_bbox"] = None
                shared["hand_seen"] = False
                shared["hand_boxes"] = []
                shared["session_start_ts"] = None

        elif is_open:
            # 문 열려있는 동안: 세션 있으면 프레임마다 추적(실시간 박스), 없으면 그냥 라이브만
            frame = fetch_preview_frame()
            if frame:
                if has_switch and detector.session_event is not None:
                    result = detector.track_session_frame(frame, t0)
                    with state_lock:
                        shared["live_bbox"] = result["bbox"]
                        shared["live_ratio"] = result["ratio"]
                        shared["hand_seen"] = result["hand_seen"]
                        shared["hand_boxes"] = [list(b) for b in result["hand_boxes"]]
                        if result.get("crop"):
                            latest_live_crop = result["crop"]
                            shared["live_crop_seq"] += 1
        else:
            time.sleep(poll_interval)
            continue

        door_open_last = is_open
        elapsed = time.time() - t0
        time.sleep(max(0.0, poll_interval - elapsed))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="status.html", context={})


@app.get("/log", response_class=HTMLResponse)
def log_page(request: Request):
    return templates.TemplateResponse(request=request, name="log.html", context={})


def read_event_log(limit: int = 200, classification: str | None = None) -> list[dict]:
    """data/events/events.jsonl에서 직접 읽는다 — 서비스 재시작으로 메모리(detector.events)가
    비워져도 여기 기록은 남아있어서, "지금까지 기록된 것 전부"를 보려면 이쪽이 진짜 소스다."""
    if not EVENTS_LOG.exists():
        return []
    rows = []
    with open(EVENTS_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if classification:
        # final_classification이 메인 판정(플로우 우선, 폴백 궤적) — 플로우 도입 이전 기록엔
        # 없어서 그때는 classification(궤적 판정)으로 대체
        rows = [r for r in rows if r.get("final_classification", r.get("classification")) == classification]
    rows.reverse()  # 최신 먼저
    return rows[:limit]


@app.get("/api/frame.jpg")
def frame_jpg():
    """모션 분석용으로 폴링 중인 최신 프레임을 그대로 내려준다 — 대시보드 실시간 미리보기용.
    ESP32에 따로 요청을 더 보내지 않고 이미 받아온 걸 재사용한다."""
    with state_lock:
        data = latest_frame
    if data is None:
        return Response(status_code=503)
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/live_crop.jpg")
def live_crop_jpg():
    """세션 진행 중 방금 잡힌 "물체 후보" 크롭을 그대로 내려준다 — 개발자 모드에서
    "지금 이걸 크롭하고 있다"를 문 닫히기 전에 실시간으로 보여주는 용도.
    (crop이 너무 늦다는 피드백 대응 — 세션 끝날 때까지 기다리지 않고 매 프레임 갱신됨)"""
    with state_lock:
        data = latest_live_crop
    if data is None:
        return Response(status_code=503)
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/rotation")
def get_rotation():
    return JSONResponse({"degrees": rotation_degrees})


@app.post("/api/rotation")
async def set_rotation(request: Request):
    global rotation_degrees
    body = await request.json()
    degrees = body.get("degrees")
    if degrees not in (0, 90, 180, 270):
        return JSONResponse({"error": "degrees는 0/90/180/270 중 하나여야 합니다"}, status_code=400)
    rotation_degrees = degrees
    return JSONResponse({"degrees": rotation_degrees})


@app.get("/api/status")
def status():
    with state_lock:
        s = dict(shared)
    s["esp_host"] = esp_host
    s["total_events"] = len(detector.events)
    s["rotation"] = rotation_degrees
    lan_ip = local_lan_ip()
    s["lan_url"] = f"http://{lan_ip}:{http_port}" if lan_ip else None
    return JSONResponse(s)


@app.get("/api/events")
def events(limit: int = 30):
    recent = list(reversed(detector.events[-limit:]))
    return JSONResponse([e.to_dict() for e in recent])


@app.get("/api/log")
def log_api(limit: int = 200, classification: str | None = None):
    """로그 페이지용 — data/events/events.jsonl 전체(재시작 이전 기록 포함)에서 읽는다."""
    rows = read_event_log(limit=limit, classification=classification)
    all_rows = read_event_log(limit=100000)
    counts = {"in": 0, "out": 0, "unknown": 0}       # final_classification 기준 (실제 채택되는 답)
    flow_counts = {"in": 0, "out": 0, "unknown": 0}
    # 4개 신호(carry/flow/trajectory/state)를 각각 집계 — 방법 전환 이후 실측
    # 데이터로 어떤 신호가 실제로 잘 맞는지 눈으로 비교하려는 용도.
    signal_counts = {
        "carry": {"in": 0, "out": 0, "unknown": 0},
        "flow": {"in": 0, "out": 0, "unknown": 0},
        "trajectory": {"in": 0, "out": 0, "unknown": 0},
        "state": {"in": 0, "out": 0, "unknown": 0},
    }
    agree = disagree = both_confident_disagree = 0
    for r in all_rows:
        final_c = r.get("final_classification", r.get("classification", "unknown"))
        c = r.get("classification", "unknown")
        fc = r.get("flow_classification")  # 옵티컬 플로우 도입 이전 기록엔 없음
        counts[final_c] = counts.get(final_c, 0) + 1
        for key, field_name in (("carry", "carry_classification"), ("flow", "flow_classification"),
                                 ("trajectory", "classification"), ("state", "state_classification")):
            v = r.get(field_name)
            if v in signal_counts[key]:
                signal_counts[key][v] += 1
        if fc is not None:
            flow_counts[fc] = flow_counts.get(fc, 0) + 1
            if c == fc:
                agree += 1
            else:
                disagree += 1
                if c != "unknown" and fc != "unknown":
                    both_confident_disagree += 1
    compared = agree + disagree
    agreement = {
        "compared": compared,
        "agree": agree,
        "disagree": disagree,
        "both_confident_disagree": both_confident_disagree,
        "agree_rate": round(agree / compared, 2) if compared else None,
    }
    return JSONResponse({
        "events": rows, "counts": counts, "flow_counts": flow_counts,
        "signal_counts": signal_counts, "agreement": agreement,
    })


@app.get("/events/{event_id}/{which}.jpg")
def event_frame(event_id: str, which: str):
    if which not in ("start", "end", "start_crop", "end_crop", "best_crop"):
        return Response(status_code=404)
    path = EVENTS_DIR / f"{event_id}_{which}.jpg"
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/events/{event_id}/frame/{idx}.jpg")
def event_frame_by_index(event_id: str, idx: int):
    """개발자 모드 필름스트립용 — 세션 중 손 등장 이후 프레임별로 저장된 크롭 하나."""
    path = EVENTS_DIR / f"{event_id}_frame_{idx:03d}.jpg"
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


def main():
    global esp_host, poll_interval, http_port
    ap = argparse.ArgumentParser()
    ap.add_argument("--esp-host", default="192.168.4.1", help="ESP32 IP (webcam_ap_capture.ino 기준)")
    ap.add_argument("--interval", type=float, default=0.2, help="프레임 폴링 간격(초)")
    ap.add_argument("--http-port", type=int, default=8500, help="이 서비스 자체 포트")
    args = ap.parse_args()

    esp_host = args.esp_host
    poll_interval = args.interval
    http_port = args.http_port

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()

    print(f"\n  모션 서비스: http://localhost:{args.http_port}")
    print(f"  ESP32 대상: http://{esp_host} (폴링 간격 {poll_interval}s)\n")

    uvicorn.run(app, host="0.0.0.0", port=args.http_port)


if __name__ == "__main__":
    main()
