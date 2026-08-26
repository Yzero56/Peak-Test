"""
server.py — 실제 냉장고 IN/OUT 판정 웹사이트 (리드스위치 연결 버전).

tools/web_capture/에서 데이터 수집하며 검증한 파이프라인을 그대로 자동화한다.
confusion matrix 14/14(100%) 나왔던 방법 — "손을 완전히 배제하고 그 자리
상태만 비교" — 을 사람 개입 없이 리드스위치 이벤트로 자동 수행한다:

  문 열림(리드스위치) → 그 순간 프레임을 손 없는 "before" 후보로 저장
  → 문 열려있는 동안 계속 프레임을 훑으며 손 위치를 찾아 크롭 영역(ref_box) 확정
    (한 번 확정되면 세션 끝까지 고정 — 이후 손이 어디 있든 무시)
  → 문 닫히기 직전 프레임을 "after" 후보로 계속 갱신
  → 문 닫힘 → before/after를 동일한 ref_box로 크롭 → 합성사진 생성
  → 로컬 TFLite 모델(model/model.eim)로 즉시 분류

분류를 클라우드 Edge Impulse API가 아니라 로컬 모델로 하는 이유: FridgeCam은
인터넷 없는 핫스팟이라, 이 컴퓨터가 ESP32에 붙어있는 동안은 클라우드를 못 쓴다
(실측으로 확인 — 크롭/손인식은 로컬이라 됐는데 분류만 매번 실패했음). 그래서
tools/edgeimpulse/train_pipeline.py로 학습한 모델을 "macOS(arm64), TFLite,
float32(양자화 안 함 — 정확도 손실 없게)"로 받아서 로컬에서 돌린다. 모델
파일은 model/model.eim — 없으면 아래 안내 참고해서 다시 받으면 됨:

  KEY=$(grep '^EI_API_KEY=' .env | cut -d= -f2-)
  curl -s -X POST "https://studio.edgeimpulse.com/v1/api/1094879/jobs/build-ondevice-model?type=runner-mac-arm64" \\
    -H "x-api-key: $KEY" -H "Content-Type: application/json" -d '{"engine":"tflite","modelType":"float32"}'
  # (job id로 폴링해서 끝날 때까지 기다린 다음)
  curl -s "https://studio.edgeimpulse.com/v1/api/1094879/deployment/download?type=runner-mac-arm64&engine=tflite&modelType=float32" \\
    -H "x-api-key: $KEY" -o tools/inout_classifier/model/model.eim
  chmod +x tools/inout_classifier/model/model.eim

실행:
  ./.venv/bin/python tools/inout_classifier/server.py --esp-host 192.168.4.1
"""
import argparse
import io
import json
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MEDIAPIPE_AVAILABLE = True
except ImportError:
    _MEDIAPIPE_AVAILABLE = False

try:
    from edge_impulse_linux.image import ImageImpulseRunner
    _EI_RUNNER_AVAILABLE = True
except ImportError:
    _EI_RUNNER_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "inout_sessions"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.jsonl"
_HAND_MODEL_PATH = ROOT / "motion_capture" / "models" / "hand_landmarker.task"
_EI_MODEL_PATH = Path(__file__).parent / "model" / "model.eim"

app = FastAPI(title="Fridge IN/OUT 판정")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

esp_host = "192.168.4.1"
poll_interval = 0.3
http_port = 8600
stop_flag = threading.Event()

# 리드스위치는 "열림/닫힘" 이진 신호일 뿐, 문이 실제로 얼마나 열렸는지는 모른다.
# 실측 확인: before는 열림 감지 후 0.6초만 기다려도 대체로 잘 나왔는데
# (문이 빨리 열리고 한동안 유지되는 듯), after는 "닫힘 감지 시점보다 0.6초
# 전"으로 고정해봐도 여전히 뿌옇게 닫히는 중인 사진이 찍혔다 — 문 닫는
# 속도가 매번 달라서 고정된 시간 여유로는 못 맞춘다. 그래서 after는 시간
# 대신 "화면이 흔들리기 시작하기 직전, 마지막으로 안정적이던 프레임"을
# 직접 찾는다(_pick_stable_frame) — 문이 움직이기 시작하면 프레임 간 변화가
# 확 커지는 걸 이용.
BEFORE_DELAY_S = 0.6   # 문 열림 감지 후 이만큼 지나야 "before"로 확정
FRAME_LOG_MAX_S = 8.0  # 세션 중 프레임 기록을 몇 초치 들고 있을지(문 여는 예산 5s 대비 여유)
# 실전 테스트에서 문을 빠르게 연속으로 여닫으면(리드스위치 바운스 포함) before/after가
# 서로 다른 세션의 프레임을 섞어서 쓰는 것처럼 보이는 오판정이 나왔다 — 너무 짧은 세션은
# 아예 판정하지 않고, 세션이 끝난 직후 잠깐은 새 세션 시작을 무시해서 재발을 막는다.
MIN_SESSION_DURATION_S = 1.2  # 이보다 짧게 열렸다 닫히면 노이즈로 보고 판정 안 함
SESSION_COOLDOWN_S = 1.0      # 세션 종료 직후 이 시간 동안은 새 세션 시작(문 열림)을 무시
STABLE_MOTION_THRESHOLD = 20   # 그레이스케일 픽셀 밝기차 임계값 — 이보다 크게 바뀐 픽셀을 "움직임"으로 침
STABLE_RATIO_THRESHOLD = 0.06  # 전체 픽셀 중 이 비율 미만이 움직였을 때만 "안정적"으로 판단
STABLE_DETAIL_RATIO = 0.3      # 세션 중 가장 또렷했던 프레임 대비 이 비율 이상 디테일이 있어야 "진짜 열린 선반"으로 인정


def _pick_stable_frame(frame_log: list) -> bytes | None:
    """frame_log(세션 중 계속 쌓인 원본 프레임들) 끝에서부터 거꾸로 훑어서,
    "화면이 안 흔들리고(모션 적음) + 선명한(디테일 있음)" 마지막 프레임을 찾는다.

    모션만 보면 안 되는 이유: 문이 완전히 닫혀서 멈춘 뒤에도(리드스위치가
    "닫힘"을 감지하기 직전 몇 프레임) 화면은 안 움직이지만 그건 "닫힌 문
    뒷면"이라 우리가 원하는 상태가 아니다 — 실측으로 확인(모션만으로 걸렀더니
    닫힌 프레임이 뽑힘). 그래서 디테일(선명도)도 같이 본다 — 닫힌 문 뒷면/
    벽처럼 밋밋한 곳은 라플라시안 분산이 선반 사진보다 10~30배 낮았다(실측)."""
    if not frame_log:
        return None
    if len(frame_log) == 1:
        return frame_log[0][1]

    def gray_small(jpeg_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("L").resize((60, 45))
        return np.asarray(img, dtype=np.uint8)

    grays = [gray_small(f) for _, f in frame_log]
    details = [float(cv2.Laplacian(g, cv2.CV_64F).var()) for g in grays]
    max_detail = max(details) if details else 0.0
    detail_floor = max_detail * STABLE_DETAIL_RATIO

    idx = len(frame_log) - 1
    while idx > 0:
        diff = np.abs(grays[idx].astype(np.int16) - grays[idx - 1].astype(np.int16))
        motion_ratio = float((diff > STABLE_MOTION_THRESHOLD).mean())
        if motion_ratio < STABLE_RATIO_THRESHOLD and details[idx] >= detail_floor:
            return frame_log[idx][1]
        idx -= 1
    return frame_log[0][1]

state_lock = threading.Lock()
shared = {
    "connected": False,
    "door_open": None,       # True/False/None(리드스위치 없음)
    "session_active": False,
    "session_elapsed": None,
    "hand_seen": False,      # 이번 세션에서 크롭 영역을 이미 확정했는지
    "last_error": None,
    "poll_count": 0,
    "latest_result": None,   # 가장 최근 판정 결과 (record_result가 채움)
}
latest_frame: bytes | None = None


def local_lan_ip() -> str | None:
    for iface in ("en0", "en1"):
        try:
            out = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True, timeout=2).stdout.strip()
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


# ---- 손 인식 (tools/web_capture/server.py와 동일 로직) ----
_hand_landmarker = None
_hand_landmarker_load_failed = False


def _get_hand_landmarker():
    global _hand_landmarker, _hand_landmarker_load_failed
    if _hand_landmarker is not None or _hand_landmarker_load_failed:
        return _hand_landmarker
    if not _MEDIAPIPE_AVAILABLE or not _HAND_MODEL_PATH.exists():
        _hand_landmarker_load_failed = True
        return None
    try:
        base_options = mp_python.BaseOptions(
            model_asset_path=str(_HAND_MODEL_PATH),
            delegate=mp_python.BaseOptions.Delegate.CPU,
        )
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options, num_hands=2,
            min_hand_detection_confidence=0.25, min_hand_presence_confidence=0.25,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        _hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)
    except Exception:
        _hand_landmarker_load_failed = True
    return _hand_landmarker


def _detect_hand_box(jpeg_bytes: bytes, padding: float = 0.6, min_size: float = 0.35) -> tuple | None:
    landmarker = _get_hand_landmarker()
    if landmarker is None:
        return None
    try:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        arr = np.asarray(img)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        result = landmarker.detect(mp_image)
    except Exception:
        return None
    if not result.hand_landmarks:
        return None
    xs, ys = [], []
    for lm in result.hand_landmarks:
        xs.extend(p.x for p in lm)
        ys.extend(p.y for p in lm)
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    pw, ph = (x1 - x0) * padding, (y1 - y0) * padding
    x0, x1 = x0 - pw, x1 + pw
    y0, y1 = y0 - ph, y1 + ph
    if x1 - x0 < min_size:
        cx = (x0 + x1) / 2
        x0, x1 = cx - min_size / 2, cx + min_size / 2
    if y1 - y0 < min_size:
        cy = (y0 + y1) / 2
        y0, y1 = cy - min_size / 2, cy + min_size / 2
    return (max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1))


def _crop_box(jpeg_bytes: bytes, box: tuple) -> bytes:
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    w, h = img.size
    x0, y0, x1, y1 = box
    px0, py0 = int(x0 * w), int(y0 * h)
    px1, py1 = max(px0 + 1, int(x1 * w)), max(py0 + 1, int(y1 * h))
    cropped = img.crop((px0, py0, px1, py1))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _make_pair_composite(first_bytes: bytes, last_bytes: bytes) -> bytes | None:
    try:
        a = Image.open(io.BytesIO(first_bytes)).convert("RGB")
        b = Image.open(io.BytesIO(last_bytes)).convert("RGB")
    except Exception:
        return None
    h = min(a.height, b.height)
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    gap = 6
    canvas = Image.new("RGB", (a.width + gap + b.width, h), (240, 60, 60))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + gap, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_diff_composite(before_bytes: bytes, after_bytes: bytes) -> bytes | None:
    """tools/web_capture/server.py의 _make_diff_composite와 동일 — 반드시 학습
    데이터를 만든 방식과 똑같이 만들어야 한다(전에 quality 프리셋 불일치로
    겪은 문제 반복 방지). 좌우로 나란히 붙이는 대신 signed diff를 색으로
    인코딩한다: R=밝아짐(생김 후보), B=어두워짐(없어짐 후보)."""
    try:
        a = Image.open(io.BytesIO(before_bytes)).convert("RGB")
        b = Image.open(io.BytesIO(after_bytes)).convert("RGB")
    except Exception:
        return None
    h = min(a.height, b.height)
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    w = min(a.width, b.width)
    if a.width != w:
        a = a.crop((a.width - w, 0, a.width, h))
    if b.width != w:
        b = b.crop((0, 0, w, h))

    ga = np.asarray(a.convert("L"), dtype=np.float32)
    gb = np.asarray(b.convert("L"), dtype=np.float32)
    gb_c = gb - (gb.mean() - ga.mean())
    diff = gb_c - ga

    scale = 2.0
    r = np.clip(np.clip(diff, 0, None) * scale, 0, 255).astype(np.uint8)
    bch = np.clip(np.clip(-diff, 0, None) * scale, 0, 255).astype(np.uint8)
    g = np.zeros_like(r)
    diff_rgb = np.stack([r, g, bch], axis=-1)

    out_img = Image.fromarray(diff_rgb, mode="RGB")
    buf = io.BytesIO()
    out_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# hand_only(손만 넣었다 뺀 것 = 실제로 아무것도 안 바뀐 것)를 CNN이 in/out과
# 같이 배우게 하면 클래스가 3개로 늘면서 안 그래도 적은 데이터(120장)가 더
# 쪼개진다. before/after 크롭 자체의 diff%로 "뭔가 바뀌긴 했나"를 먼저 걸러내면
# CNN은 "바뀐 게 들어간 건지 나온 건지"만 배우면 되는 훨씬 쉬운 이진 분류가
# 된다 — 그래서 hand_only는 학습 라벨에서 빼고 규칙(diff%)으로만 판정한다.
# 임계값은 아직 hand-free 방식으로 찍은 진짜 hand_only 샘플이 없어서 임시값 —
# 실제 데이터가 쌓이면 재보정 필요.
HAND_ONLY_DIFF_TH = 0.5


def _diff_percent(before_bytes: bytes, after_bytes: bytes) -> float | None:
    """tools/web_capture/server.py의 _diff_percent와 동일 — 전역 밝기 보정 후
    국소적으로(그 선반 자리) 진짜 달라진 픽셀 비율만 잰다."""
    try:
        a = Image.open(io.BytesIO(before_bytes)).convert("L")
        b = Image.open(io.BytesIO(after_bytes)).convert("L")
    except Exception:
        return None
    if a.size != b.size:
        b = b.resize(a.size)
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    shift = float(b.mean() - a.mean())
    diff = np.abs(a - (b - shift))
    mask = diff > 30
    return round(float(mask.mean()) * 100, 2)


# ---- ESP32 통신 ----
def check_door() -> bool | None:
    try:
        r = requests.get(f"http://{esp_host}/door", timeout=2)
        if r.status_code == 200:
            return bool(r.json().get("open", True))
    except requests.exceptions.RequestException:
        pass
    return None


def fetch_preview_frame() -> bytes | None:
    """/preview가 아니라 /capture?quality=standard를 쓴다 — 학습 데이터를
    tools/web_capture/의 Before/After로 "표준" 화질(quality=12)로 찍었는데,
    여기서 /preview(항상 quality=16, 더 압축됨)를 쓰면 실전에서 신호가 더
    뭉개져서 훈련 때와 다른 걸 보게 된다(실측: IN이 거의 다 OUT으로 오분류
    되는 편향의 원인으로 의심됨). 해상도는 둘 다 800x600으로 같고 압축률만
    다르므로, 화질만 맞추면 학습/실전 구도가 일치한다."""
    global latest_frame
    try:
        r = requests.get(f"http://{esp_host}/capture", params={"quality": "standard"}, timeout=5)
        if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
            with state_lock:
                shared["connected"] = True
                shared["last_error"] = None
                shared["poll_count"] += 1
            latest_frame = r.content
            return r.content
        with state_lock:
            shared["connected"] = False
            shared["last_error"] = f"HTTP {r.status_code}"
    except requests.exceptions.RequestException as e:
        with state_lock:
            shared["connected"] = False
            shared["last_error"] = str(e)
    return None


# ---- 로컬 TFLite 분류 (model/model.eim) ----
# FridgeCam 연결 중엔 인터넷이 없어서 클라우드 API를 못 쓴다(실측으로 확인 —
# 크롭/손인식은 로컬이라 됐는데 분류만 매번 실패했었음). 그래서 학습된 모델을
# "macOS arm64, float32(양자화 안 함)"로 받아서 로컬 서브프로세스로 돌린다.
# float32라 클라우드에서 나온 것과 정확도 차이가 없다(실측 비교: 82% vs 84%,
# 오차범위 안).
_ei_runner_lock = threading.Lock()
_ei_runner = None
_ei_runner_load_failed = False


def _get_ei_runner():
    global _ei_runner, _ei_runner_load_failed
    if _ei_runner is not None or _ei_runner_load_failed:
        return _ei_runner
    if not _EI_RUNNER_AVAILABLE or not _EI_MODEL_PATH.exists():
        _ei_runner_load_failed = True
        return None
    try:
        runner = ImageImpulseRunner(str(_EI_MODEL_PATH))
        runner.init()
        _ei_runner = runner
    except Exception as e:
        print(f"[classify_pair] 모델 로딩 실패: {type(e).__name__}: {e}")
        _ei_runner_load_failed = True
    return _ei_runner


# 정확도가 아직 100%가 아니라서(테스트셋 기준 73%), 애매한 판정을 확신하는 척
# 확정적으로 보여주는 게 제일 나쁘다 — 특히 시연처럼 사람이 결과를 지켜보는
# 상황에서는. confidence가 이 밑이면 "IN/OUT 중 하나로 확정" 대신
# "판단 애매함"으로 정직하게 보여준다(원래 점수는 그대로 다 보여줌).
# 0.65로 시작했다가 실전 재확인 후 0.5로 낮춤 — 실제로 0.5~0.65 구간이
# "애매함"으로 숨겨지고 있었는데, 라이브 테스트에서 이 구간 예측이 대부분
# 맞았음(사용자 확인). held-out 테스트 74장 기준:
#   th=0.5  -> 노출 64/74, 그중 정확도 76.6%  (채택 — 대부분 확정 답 보여줌)
#   th=0.55 -> 노출 57/74, 그중 정확도 78.9%
#   th=0.65 -> 노출 45/74, 그중 정확도 84.4%(너무 많이 숨겨짐 — 이전 값)
UNCERTAIN_CONFIDENCE_TH = 0.5


def classify_pair(pair_bytes: bytes, fname: str) -> dict | None:
    """합성사진을 로컬 모델로 바로 분류한다. 실패하면 None — 호출부가
    "판정 불가"로 표시."""
    runner = _get_ei_runner()
    if runner is None:
        return None
    try:
        img = Image.open(io.BytesIO(pair_bytes)).convert("RGB")
        arr = np.asarray(img)
        with _ei_runner_lock:  # .eim은 서브프로세스 하나라 동시 호출 안전하게 직렬화
            features, _cropped = runner.get_features_from_image_auto_studio_settings(arr)
            res = runner.classify(features)
        scores = res["result"]["classification"]
        label = max(scores, key=scores.get)
        confidence = round(scores[label], 3)
        if confidence < UNCERTAIN_CONFIDENCE_TH:
            label = "uncertain"
        return {"label": label, "confidence": confidence,
                "scores": {k: round(v, 3) for k, v in scores.items()}}
    except Exception as e:
        print(f"[classify_pair] 분류 예외: {type(e).__name__}: {e}")
        return None


# ---- 세션 상태 ----
session_lock = threading.Lock()
session = {
    "active": False, "start_ts": None,
    "start_frame": None,   # "before" 확정본 — BEFORE_DELAY_S 지난 뒤에만 채워짐
    "ref_box": None,
    "frame_log": [],       # [(ts, jpeg_bytes), ...] — after 선택용 버퍼
}


def record_result(pair_filename: str | None, result: dict | None, ref_box, start_ts: float, reason: str | None = None):
    entry = {
        "ts": start_ts,
        "pair_filename": pair_filename,
        "label": result["label"] if result else None,
        "confidence": result["confidence"] if result else None,
        "scores": result["scores"] if result else None,
        "ref_box": [round(v, 3) for v in ref_box] if ref_box else None,
        "reason": reason,
    }
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with state_lock:
        shared["latest_result"] = entry


def finish_session(close_ts: float):
    """session_lock 잡은 상태에서 호출."""
    start_frame = session["start_frame"]
    frame_log = session["frame_log"]
    ref_box = session["ref_box"]
    start_ts = session["start_ts"]
    session.update({"active": False, "start_frame": None, "ref_box": None, "frame_log": [], "start_ts": None})

    if start_ts is None:
        return

    if close_ts - start_ts < MIN_SESSION_DURATION_S:
        # 리드스위치 바운스나 순간적인 문 흔들림 — 진짜 in/out 동작이라기엔
        # 너무 짧다. 여기서 어설프게 판정하면 (문 다시 열림→기존 세션과
        # 뒤섞임) before/after가 서로 다른 순간을 비교하는 오판정으로 이어진
        # 사례가 실측으로 확인돼서, 아예 판정하지 않고 건너뛴다.
        record_result(None, None, ref_box, start_ts,
                      reason=f"세션이 너무 짧음({close_ts - start_ts:.2f}s) — 노이즈로 보고 건너뜀")
        return

    # before가 아직 확정 안 됐으면(문이 아주 잠깐 열렸다 닫힌 경우) 그나마
    # 있는 프레임 중 가장 이른 것으로 폴백한다.
    if start_frame is None and frame_log:
        start_frame = frame_log[0][1]
    if start_frame is None:
        record_result(None, None, ref_box, start_ts, reason="세션이 너무 짧아서 프레임을 못 찍음")
        return

    # after: 화면이 흔들리기(문이 닫히기) 시작하기 직전, 마지막으로 안정적이던
    # 프레임을 찾는다 — 고정 시간 여유 대신 실제 모션을 본다(문 닫는 속도가
    # 매번 달라서 고정값으론 못 맞췄음, 실측 확인).
    end_frame = _pick_stable_frame(frame_log)
    if end_frame is None:
        end_frame = start_frame

    if ref_box is None:
        record_result(None, None, None, start_ts, reason="세션 중 손을 못 찾아서 크롭 영역 확정 실패")
        return

    before_crop = _crop_box(start_frame, ref_box)
    after_crop = _crop_box(end_frame, ref_box)
    pair = _make_diff_composite(before_crop, after_crop)
    if pair is None:
        record_result(None, None, ref_box, start_ts, reason="합성사진 생성 실패")
        return

    ts_id = int(start_ts * 1000)
    pair_fname = f"session_{ts_id}.jpg"
    (DATA_DIR / pair_fname).write_bytes(pair)
    (DATA_DIR / f"session_{ts_id}_before.jpg").write_bytes(before_crop)
    (DATA_DIR / f"session_{ts_id}_after.jpg").write_bytes(after_crop)

    diff_pct = _diff_percent(before_crop, after_crop)
    if diff_pct is not None and diff_pct < HAND_ONLY_DIFF_TH:
        # 거의 안 바뀜 — CNN(in/out 이진 분류기)까지 갈 필요 없이 규칙으로 바로
        # hand_only-pair(아무 일도 없음) 처리
        result = {"label": "hand_only-pair", "confidence": 1.0,
                  "scores": {"hand_only-pair": 1.0, "in-pair": 0.0, "out-pair": 0.0},
                  "rule": f"diff% {diff_pct} < {HAND_ONLY_DIFF_TH}"}
        record_result(pair_fname, result, ref_box, start_ts, reason=None)
        return

    result = classify_pair(pair, pair_fname)
    reason = None if result else "로컬 모델 분류 실패 (model/model.eim 확인 필요)"
    record_result(pair_fname, result, ref_box, start_ts, reason=reason)


def poll_loop():
    door_open_last = None
    while not stop_flag.is_set():
        t0 = time.time()
        door_open = check_door()
        with state_lock:
            shared["door_open"] = door_open

        if door_open is None:
            time.sleep(poll_interval)
            continue

        just_opened = door_open_last is False and door_open is True
        just_closed = door_open_last is True and door_open is False

        if just_opened:
            # 문 열림 — 세션 시작. "before"는 바로 확정하지 않는다(문이 아직
            # 살짝만 열렸을 수 있어서) — 아래 공통 분기에서 BEFORE_DELAY_S 지난
            # 뒤에 확정한다.
            with session_lock:
                session.update({"active": True, "start_ts": t0, "start_frame": None,
                                 "ref_box": None, "frame_log": []})
            with state_lock:
                shared["session_active"] = True
                shared["hand_seen"] = False
                shared["session_elapsed"] = 0.0

        if just_closed:
            # 문 닫힘 — 여기서 새로 프레임을 찍지 않는다(이미 닫히는 중이라
            # 선반이 안 보임). 대신 문이 열려있는 동안 계속 쌓아둔 frame_log에서
            # "닫힘 감지보다 AFTER_MARGIN_S 이전" 프레임을 골라 판정한다.
            with session_lock:
                finish_session(close_ts=t0)
            with state_lock:
                shared["session_active"] = False
                shared["hand_seen"] = False
                shared["session_elapsed"] = None

        elif door_open:
            # 문이 열려있는 동안(방금 열린 틱 포함) — 프레임을 찍어서 기록하고,
            # before 확정 + 크롭 영역(ref_box) 탐지를 진행한다.
            frame = fetch_preview_frame()
            if frame:
                with session_lock:
                    if session["active"]:
                        session["frame_log"].append((t0, frame))
                        cutoff = t0 - FRAME_LOG_MAX_S
                        session["frame_log"] = [(ts, f) for ts, f in session["frame_log"] if ts >= cutoff]
                        if session["start_frame"] is None and (t0 - session["start_ts"]) >= BEFORE_DELAY_S:
                            session["start_frame"] = frame
                        if session["ref_box"] is None:
                            box = _detect_hand_box(frame)
                            if box is not None:
                                session["ref_box"] = box
                                with state_lock:
                                    shared["hand_seen"] = True
            with state_lock:
                if session.get("start_ts") is not None:
                    shared["session_elapsed"] = round(t0 - session["start_ts"], 1)
        elif not just_closed:
            time.sleep(poll_interval)
            door_open_last = door_open
            continue

        door_open_last = door_open
        elapsed = time.time() - t0
        time.sleep(max(0.0, poll_interval - elapsed))


def read_history(limit: int = 50) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    rows = []
    with open(HISTORY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.reverse()
    return rows[:limit]


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/api/status")
def status():
    with state_lock:
        s = dict(shared)
    s["esp_host"] = esp_host
    s["ei_ready"] = _EI_MODEL_PATH.exists() and _EI_RUNNER_AVAILABLE
    lan_ip = local_lan_ip()
    s["lan_url"] = f"http://{lan_ip}:{http_port}" if lan_ip else None
    return JSONResponse(s)


@app.get("/api/frame.jpg")
def frame_jpg():
    if latest_frame is None:
        return Response(status_code=503)
    return Response(content=latest_frame, media_type="image/jpeg")


@app.get("/api/history")
def history_api(limit: int = 50):
    return JSONResponse(read_history(limit))


@app.get("/sessions/{filename}")
def serve_session_file(filename: str):
    if not re.match(r"^session_\d+(_before|_after)?\.jpg$", filename):
        return Response(status_code=404)
    path = DATA_DIR / filename
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


def main():
    global esp_host, poll_interval, http_port
    ap = argparse.ArgumentParser()
    ap.add_argument("--esp-host", default="192.168.4.1")
    ap.add_argument("--interval", type=float, default=0.3)
    ap.add_argument("--http-port", type=int, default=8600)
    args = ap.parse_args()

    esp_host = args.esp_host
    poll_interval = args.interval
    http_port = args.http_port

    if not _EI_RUNNER_AVAILABLE:
        print("⚠ edge_impulse_linux 패키지가 없어서 분류는 건너뛰고 세션 감지/크롭까지만 동작합니다.")
    elif not _EI_MODEL_PATH.exists():
        print(f"⚠ {_EI_MODEL_PATH}가 없어서 분류는 건너뛰고 세션 감지/크롭까지만 동작합니다 "
              f"(파일 상단 docstring에 받는 방법 있음).")

    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()

    print(f"\n  IN/OUT 판정: http://localhost:{http_port}")
    print(f"  ESP32 대상: http://{esp_host} (폴링 간격 {poll_interval}s)\n")

    uvicorn.run(app, host="0.0.0.0", port=http_port)


if __name__ == "__main__":
    main()
