"""
server.py — 브라우저에서 ESP32S3+OV3660 카메라를 직접 셔터 누르듯 쓰기 위한 로컬 서버.

두 가지 연결 방식을 지원한다 (택 1):
  시리얼(USB 케이블):
    ./.venv/bin/python tools/web_capture/server.py --port /dev/tty.usbmodem1101
  WiFi(FridgeCam 핫스팟 — 이 컴퓨터가 먼저 FridgeCam에 접속돼있어야 함):
    ./.venv/bin/python tools/web_capture/server.py --esp-host 192.168.4.1

브라우저에서 http://localhost:8420 (같은 와이파이의 폰에서는 서버가 출력하는
LAN 주소)로 접속하면 실시간 미리보기 + 촬영 버튼이 있는 페이지가 뜬다.
찍은 사진은 기존 tools/capture_image.py와 동일한 파일명 규칙으로
data/raw_captures/ 에 저장되어 그대로 섞여 쌓인다.
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
import zipfile
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, request, send_file, send_from_directory, render_template
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from serial_cam import QUALITY_PRESETS, DEFAULT_QUALITY, SerialCamera, SerialCameraError  # noqa: E402
from http_cam import HttpCamera  # noqa: E402

# motion_capture/motion.py에서 이미 검증한 손 감지(MediaPipe HandLandmarker)를
# 그대로 재사용한다 — 이유: 녹화 버튼을 누르고 떼는 시점이 실제 "손이 물건을
# 만지는 순간"보다 앞뒤로 여유있게 걸리는 게 실측으로 확인됨(사람이 다가가고
# 물러나는 시간까지 녹화에 포함됨) — 그래서 첫/끝 프레임 그대로 pair를 만들면
# 정작 둘 다 "손 없는 빈 장면"이 되는 경우가 많았다. 대신 "손이 처음 보인
# 프레임"과 "손이 마지막으로 보인 프레임"을 실제로 찾아서 그걸로 pair를 만든다.
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MEDIAPIPE_AVAILABLE = True
except ImportError:
    _MEDIAPIPE_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "data" / "raw_captures"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR = ROOT / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
_HAND_MODEL_PATH = ROOT / "motion_capture" / "models" / "hand_landmarker.task"
_hand_landmarker = None
_hand_landmarker_load_failed = False

# ---- 크롭 영역 — Before/After로 in/out pair를 학습시킬 때, 냉장고 전체가 다
# 보이는 넓은 구도로 찍으면 물건 하나의 변화가 전체 프레임의 1~3%밖에 안 돼서
# 신호가 약했다(실측 확인). 카메라가 문틀에 고정돼 안 흔들리니, 선반 위치는
# 항상 같은 픽셀 좌표에 있다 — 그래서 크롭 영역을 한 번만 지정해두면 이후
# Before/After 촬영마다 자동으로 그 선반만 잘라서 저장한다. 나중에 실전
# 판정에서도 같은 좌표로 잘라서 넣으면 학습 때 구도와 항상 일치한다.
CROP_REGION_FILE = ROOT / "data" / "web_capture_crop_region.json"


def load_crop_region() -> dict | None:
    if CROP_REGION_FILE.exists():
        try:
            return json.loads(CROP_REGION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_crop_region(region: dict | None):
    if region is None:
        CROP_REGION_FILE.unlink(missing_ok=True)
    else:
        CROP_REGION_FILE.write_text(json.dumps(region))


crop_region = load_crop_region()  # {"x0":0-1, "y0":0-1, "x1":0-1, "y1":0-1} | None


def apply_crop(jpeg_bytes: bytes) -> bytes:
    """crop_region이 지정돼있으면 그 영역만 잘라서 돌려준다. 없으면 원본 그대로."""
    if crop_region is None:
        return jpeg_bytes
    try:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    except Exception:
        return jpeg_bytes
    w, h = img.size
    x0 = int(crop_region["x0"] * w)
    y0 = int(crop_region["y0"] * h)
    x1 = max(x0 + 1, int(crop_region["x1"] * w))
    y1 = max(y0 + 1, int(crop_region["y1"] * h))
    cropped = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

FNAME_RE = re.compile(r"^(?P<label>.+)_(?P<ts>\d+)_(?P<idx>\d{3})\.jpg$")

app = Flask(__name__, template_folder="templates")
camera = None  # SerialCamera | HttpCamera | None
backend = "serial"  # "serial" | "http"
serial_port = "/dev/tty.usbmodem1101"
serial_baud = 115200
esp_host = "192.168.4.1"
http_port = 8420

# ---- 녹화(연속 촬영) — "영상"을 통째로 넣는 대신, 한 동작(넣기/빼기/손만 등)
# 하는 동안 계속 프레임을 찍어서 같은 라벨로 쌓는다. 냉장고 IN/OUT 판정을
# 궤적/플로우 같은 휴리스틱 대신 실제 라벨 데이터로 학습시키기로 방향을
# 바꾼 것 — 사람이 동작을 반복 수행하면서 한 번에 여러 장을 라벨링하는 게
# 한 장씩 셔터 누르는 것보다 훨씬 빠르고 동작 중간 프레임들도 자연스럽게 잡힌다.
RECORD_INTERVAL_S = 0.12   # 프레임 사이 최소 간격 — 캡처 자체 왕복 시간이 있어 실제로는 이보다 느릴 수 있음
RECORD_MAX_S = 12.0        # 안전장치: 누르고 깜빡해도 무한정 안 찍히게 상한
record_lock = threading.Lock()
record_state = {
    "active": False,
    "label": None,
    "start_ts": None,
    "count": 0,
    "latest_bytes": None,
    "seq": 0,   # latest_bytes가 갱신될 때마다 증가 — 프론트가 캐시 무시하고 새로 받아오는 트리거
    "last_capture_ms": None,  # 방금 찍은 프레임의 캡처 왕복시간(ms) — 느려지면 바로 눈에 보이게
    "frames": [],   # [{filename, url, t: 세션 시작 대비 초, capture_ms}, ...] — 개발자 모드 필름스트립용
    "pair_url": None,  # 방금 세션의 비교 합성사진 — 있으면 URL
    "pair_mode": "none",  # "hand" = 손 감지된 첫/끝 프레임으로 만듦(신뢰도 높음) | "first_last" = 손 못 찾아서 폴백 | "none" = 아직 없음
}
record_stop_flag = threading.Event()
record_thread: threading.Thread | None = None
# 시리얼은 포트 하나를 공유하는 스트림이라, 녹화 스레드와 일반 미리보기 폴링이
# 동시에 요청을 넣으면 응답이 서로 섞여 깨질 수 있다(이 프로젝트에서 겪었던
# 시리얼/HTTP 프로토콜 깨짐 문제들과 같은 종류). 카메라 I/O는 항상 이 락 안에서만.
camera_io_lock = threading.Lock()


def ensure_camera():
    """camera가 None이면(초기 연결 실패, 또는 완전히 끊긴 뒤) 한 번 더 열어본다.
    시리얼이면 케이블이 빠졌다 다시 꽂힌 경우, WiFi면 FridgeCam 핫스팟에 아직
    안 붙었거나 잠깐 끊긴 경우 — 어느 쪽이든 서버 재시작 없이 다음 요청에서
    자동으로 재연결을 시도하게 하기 위함."""
    global camera
    if camera is not None:
        return camera
    try:
        if backend == "http":
            camera = HttpCamera(esp_host)
            print(f"[http] {esp_host} 재연결됨")
        else:
            camera = SerialCamera(serial_port, serial_baud)
            print(f"[serial] {serial_port} 재연결됨")
    except Exception as e:
        print(f"[{backend}] 재연결 시도 실패: {e}")
        camera = None
    return camera


def label_count(label: str) -> int:
    return sum(1 for f in CAPTURE_DIR.glob(f"{label}_*.jpg"))


def known_labels() -> list[str]:
    labels = {}
    for f in CAPTURE_DIR.glob("*.jpg"):
        m = FNAME_RE.match(f.name)
        if m:
            labels[m.group("label")] = labels.get(m.group("label"), 0) + 1
    return sorted(labels, key=lambda l: -labels[l])


def gallery_items(limit: int = 30):
    files = sorted(CAPTURE_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
    items = []
    for f in files[:limit]:
        m = FNAME_RE.match(f.name)
        items.append({
            "filename": f.name,
            "label": m.group("label") if m else "?",
            "url": f"/captures/{f.name}",
        })
    return items


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    cam = ensure_camera()
    lan_ip = local_lan_ip()
    return jsonify({
        "connected": cam is not None,
        "port": cam.port if cam else (esp_host if backend == "http" else serial_port),
        "backend": backend,
        "labels": known_labels(),
        "total_captures": sum(1 for _ in CAPTURE_DIR.glob("*.jpg")),
        "lan_url": f"http://{lan_ip}:{http_port}" if lan_ip else None,
    })


@app.post("/api/preview")
def preview():
    """저장하지 않고 미리보기용 프레임 한 장만 반환 (항상 저해상도 — 끊김 방지)."""
    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503
    try:
        with camera_io_lock:
            data = cam.preview()
    except SerialCameraError as e:
        global camera
        camera = None  # 다음 요청에서 ensure_camera()가 재연결을 다시 시도하게
        return jsonify({"error": str(e)}), 502
    return app.response_class(data, mimetype="image/jpeg")


@app.post("/api/capture")
def capture():
    """실제로 저장하는 촬영. body: {"label": "milk_carton", "quality": "fast"|"standard"|"high"}"""
    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503

    body = request.json or {}
    label = body.get("label", "").strip() or "untitled"
    label = re.sub(r"[^a-zA-Z0-9가-힣_-]", "-", label)
    quality = body.get("quality") if body.get("quality") in QUALITY_PRESETS else DEFAULT_QUALITY

    try:
        with camera_io_lock:
            data = cam.capture(quality)
    except SerialCameraError as e:
        global camera
        camera = None
        return jsonify({"error": str(e)}), 502

    idx = label_count(label) + 1
    fname = f"{label}_{int(time.time())}_{idx:03d}.jpg"
    (CAPTURE_DIR / fname).write_bytes(data)

    return jsonify({
        "ok": True,
        "filename": fname,
        "url": f"/captures/{fname}",
        "label": label,
        "quality": quality,
        "count": idx,
        "bytes": len(data),
    })


# ---- 선반 Before/After 촬영 — 손 인식 기반 pair는 "손이 물건을 쥔 채로 끝남"이라는
# 점에서 in/out이 구조적으로 비슷해 보여서 헷갈렸다(실측: out의 절반이 in으로
# 오분류, confusion matrix로 확인). 손 대신 "그 선반 자리에 물건이 있었는지
# 없는지"를 직접 사람이 정확한 타이밍에 두 장만 찍어서 비교하면, 흔들림도 없고
# 방향(생김/없어짐) 신호도 훨씬 명확해진다. before 찍고 → 동작하고 → after
# 찍으면 그 둘을 이어붙여 기존과 동일한 <label>-pair 라벨로 저장한다(같은 클래스에
# 그대로 합쳐짐).
beforeafter_lock = threading.Lock()
# 3단계 흐름 — ref(손 보이게 위치만 잡기) → before(손 뺀 채) → after(손 뺀 채).
# 예전엔 before 자체에서 손 인식을 했는데, 그러면 학습 이미지에 손이 항상
# 섞여서 "손이 물건 쥔 채로 끝남" 같은 방향(in/out)과 무관한 특징을 모델이
# 붙잡는 문제가 있었다(confusion matrix로 확인). 위치를 찾는 것과 실제 비교용
# 사진을 찍는 걸 분리해서, 학습 이미지 자체에는 손이 아예 안 들어가게 한다 —
# "그 자리에 물건이 있었는지 없는지"만 순수하게 남는다.
beforeafter_state = {"ref_box": None, "before_bytes": None, "before_ts": None, "label": None}


@app.post("/api/beforeafter/ref")
def beforeafter_ref():
    """위치 잡기 — 손을 뻗은 채로 한 장 찍어서 크롭 영역만 확정한다. 이 사진
    자체는 저장/학습에 안 쓰이고 영역 결정에만 쓰인다."""
    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503

    body = request.get_json(silent=True) or {}
    label = body.get("label", "").strip() or "untitled"
    label = re.sub(r"[^a-zA-Z0-9가-힣_-]", "-", label)
    quality = body.get("quality") if body.get("quality") in QUALITY_PRESETS else DEFAULT_QUALITY

    try:
        with camera_io_lock:
            data = cam.capture(quality)
    except SerialCameraError as e:
        global camera
        camera = None
        return jsonify({"error": str(e)}), 502

    box = _detect_hand_box(data)
    with beforeafter_lock:
        beforeafter_state.update({"ref_box": box, "before_bytes": None, "before_ts": None, "label": label})
        # 미리보기용으로 방금 찍은 원본(크롭 전)을 잠깐 들고 있는다 — before.jpg
        # 엔드포인트가 "위치가 이렇게 잡혔다"를 보여줄 때 씀. 수동 지정 폴백도
        # 이 원본 위에서 좌표를 찍는다.
        beforeafter_state["ref_raw"] = data

    return jsonify({"ok": True, "label": label, "hand_found": box is not None})


@app.get("/api/beforeafter/ref.jpg")
def beforeafter_ref_jpg():
    """위치 잡기 미리보기 — ref_box가 있으면 크롭된 모습 그대로, 없으면(손 못
    찾음) 원본 그대로 보여준다(수동 지정용)."""
    with beforeafter_lock:
        data = beforeafter_state.get("ref_raw")
        box = beforeafter_state["ref_box"]
    if data is None:
        return ("", 503)
    if box is not None:
        data = _crop_box(data, box)
    return app.response_class(data, mimetype="image/jpeg")


@app.post("/api/beforeafter/manual-box")
def beforeafter_manual_box():
    """위치 잡기에서 자동 손 인식이 실패했을 때 쓰는 폴백 — ref 원본 사진 위에서
    직접 두 번 클릭해서 영역을 지정하면 ref_box 자리에 그대로 들어간다."""
    with beforeafter_lock:
        if beforeafter_state.get("ref_raw") is None:
            return jsonify({"error": "먼저 위치 잡기를 찍어주세요"}), 400
    body = request.get_json(silent=True) or {}
    region = body.get("region")
    try:
        x0, y0, x1, y1 = float(region["x0"]), float(region["y0"]), float(region["x1"]), float(region["y1"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "region은 x0/y0/x1/y1(0~1) 숫자가 필요합니다"}), 400
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    # 실측 확인: 너무 낮은 기준(2%)이면 손가락 하나 삐끗해서 두 클릭이 거의
    # 겹칠 때 72x17px 같은 사실상 빈 크롭이 통과됐었다.
    if x1 - x0 < 0.15 or y1 - y0 < 0.15:
        return jsonify({"error": "영역이 너무 작습니다 — 최소 15% 이상으로 지정해주세요"}), 400
    box = (x0, y0, x1, y1)
    with beforeafter_lock:
        beforeafter_state["ref_box"] = box
    return jsonify({"ok": True})


@app.post("/api/beforeafter/before")
def beforeafter_before():
    with beforeafter_lock:
        ref_box = beforeafter_state["ref_box"]
        label = beforeafter_state["label"]
    if ref_box is None or label is None:
        return jsonify({"error": "먼저 위치 잡기를 완료해주세요"}), 400

    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503

    body = request.get_json(silent=True) or {}
    quality = body.get("quality") if body.get("quality") in QUALITY_PRESETS else DEFAULT_QUALITY

    try:
        with camera_io_lock:
            data = cam.capture(quality)
    except SerialCameraError as e:
        global camera
        camera = None
        return jsonify({"error": str(e)}), 502

    # 여기선 손 인식을 안 한다 — 사람이 손을 빼고 찍는다는 전제. ref_box를
    # 그대로 적용해서 "이 자리에 지금 뭐가 있나"만 잘라낸다.
    cropped = _crop_box(data, ref_box)
    with beforeafter_lock:
        beforeafter_state.update({"before_bytes": cropped, "before_ts": time.time()})

    return jsonify({"ok": True, "label": label})


@app.get("/api/beforeafter/before.jpg")
def beforeafter_before_jpg():
    with beforeafter_lock:
        data = beforeafter_state["before_bytes"]
    if data is None:
        return ("", 503)
    return app.response_class(data, mimetype="image/jpeg")


@app.post("/api/beforeafter/after")
def beforeafter_after():
    with beforeafter_lock:
        before_final = beforeafter_state["before_bytes"]
        before_ts = beforeafter_state["before_ts"]
        label = beforeafter_state["label"]
        ref_box = beforeafter_state["ref_box"]
    if before_final is None:
        return jsonify({"error": "먼저 Before를 찍어주세요"}), 400

    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503

    body = request.get_json(silent=True) or {}
    quality = body.get("quality") if body.get("quality") in QUALITY_PRESETS else DEFAULT_QUALITY

    try:
        with camera_io_lock:
            after_raw = cam.capture(quality)
    except SerialCameraError as e:
        global camera
        camera = None
        return jsonify({"error": str(e)}), 502

    after_final = _crop_box(after_raw, ref_box)  # before와 반드시 같은 영역

    idx = label_count(label) + 1
    bfname = f"{label}_{int(before_ts)}_{idx:03d}.jpg"
    (CAPTURE_DIR / bfname).write_bytes(before_final)

    idx = label_count(label) + 1
    afname = f"{label}_{int(time.time())}_{idx:03d}.jpg"
    (CAPTURE_DIR / afname).write_bytes(after_final)

    pair = _make_diff_composite(before_final, after_final)
    pair_url = None
    if pair:
        pair_label = f"{label}-pair"
        pidx = label_count(pair_label) + 1
        pfname = f"{pair_label}_{int(time.time())}_{pidx:03d}.jpg"
        (CAPTURE_DIR / pfname).write_bytes(pair)
        pair_url = f"/captures/{pfname}"

    diff_pct = _diff_percent(before_final, after_final)

    with beforeafter_lock:
        beforeafter_state.update({"ref_box": None, "before_bytes": None, "before_ts": None, "label": None, "ref_raw": None})

    return jsonify({"ok": True, "label": label, "pair_url": pair_url, "diff_pct": diff_pct})


@app.get("/api/beforeafter/status")
def beforeafter_status():
    with beforeafter_lock:
        return jsonify({
            "ref_set": beforeafter_state["ref_box"] is not None,
            "hand_found": beforeafter_state["ref_box"] is not None,
            "before_set": beforeafter_state["before_bytes"] is not None,
            "label": beforeafter_state["label"],
        })


@app.get("/api/crop-region")
def get_crop_region():
    return jsonify({"region": crop_region})


@app.post("/api/crop-region")
def set_crop_region():
    global crop_region
    body = request.get_json(silent=True) or {}
    region = body.get("region")
    if region is None:
        crop_region = None
        save_crop_region(None)
        return jsonify({"ok": True, "region": None})
    try:
        x0, y0, x1, y1 = float(region["x0"]), float(region["y0"]), float(region["x1"]), float(region["y1"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "region은 x0/y0/x1/y1(0~1) 숫자가 필요합니다"}), 400
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 0.15 or y1 - y0 < 0.15:
        return jsonify({"error": "영역이 너무 작습니다 — 최소 15% 이상으로 지정해주세요"}), 400
    crop_region = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
    save_crop_region(crop_region)
    return jsonify({"ok": True, "region": crop_region})


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
            delegate=mp_python.BaseOptions.Delegate.CPU,  # GPU 델리게이트는 이 맥에서 크래시남 (motion.py 주석 참고)
        )
        # 실측(냉장고 안쪽으로 손을 밀어넣는 자세라 MediaPipe가 흔히 안 보는 각도)
        # 결과 밝기 보정/샤픈/업스케일은 효과가 없었고, 임계값을 낮추는 것만
        # 소폭이나마 실제로 검출률을 올렸다(0.4→0.25, 22%→25%) — 그래서 이 값으로.
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options, num_hands=2,
            min_hand_detection_confidence=0.25, min_hand_presence_confidence=0.25,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        _hand_landmarker = mp_vision.HandLandmarker.create_from_options(options)
    except Exception:
        _hand_landmarker_load_failed = True
    return _hand_landmarker


def _has_hand(jpeg_bytes: bytes) -> bool:
    landmarker = _get_hand_landmarker()
    if landmarker is None:
        return False
    try:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        arr = np.asarray(img)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        result = landmarker.detect(mp_image)
    except Exception:
        return False
    return len(result.hand_landmarks) > 0


def _detect_hand_box(jpeg_bytes: bytes, padding: float = 0.6, min_size: float = 0.35) -> tuple | None:
    """손 랜드마크 바운딩박스를 넉넉하게 확장해서 돌려준다(0~1 정규화) — 손 자체가
    아니라 손이 활동하는 "그 주변 선반 영역"까지 보이는 게 목적이라 padding을
    크게 준다. 손이 카메라에서 멀어서 박스가 아주 작게 잡히면 물건이 프레임
    밖으로 밀려날 수 있어서 최소 크기(min_size)도 보장한다. 냉장고 전체 어디서
    활동하든 이 함수가 그 위치를 찾아주므로, 고정 크롭 한 칸에 갇히지 않고
    선반 전체를 커버할 수 있다."""
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
    """box(0~1 정규화 x0,y0,x1,y1)로 실제 프레임을 잘라서 돌려준다."""
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
    """정적 이미지 분류기(EI transfer-learning image)는 한 장짜리 사진만 보고는
    "넣는 중"과 "빼는 중"을 구분할 수가 없다 — 손에 우유팩 들고 있는 사진 한 장은
    넣으려는 건지 막 꺼낸 건지 똑같이 생겼다(방향은 시간에 따른 변화에만 있음).
    그래서 세션의 첫 프레임과 마지막 프레임을 나란히 이어붙인 "비교 사진" 한 장을
    추가로 만든다 — 이건 그 자체로 전/후 변화가 한 장에 다 담겨서 정적 이미지
    분류기로도 in/out 학습이 실제로 가능해진다."""
    try:
        a = Image.open(io.BytesIO(first_bytes)).convert("RGB")
        b = Image.open(io.BytesIO(last_bytes)).convert("RGB")
    except Exception:
        return None
    h = min(a.height, b.height)
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    gap = 6
    canvas = Image.new("RGB", (a.width + gap + b.width, h), (240, 60, 60))  # 갭은 눈에 띄는 빨간 줄로 구분
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + gap, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _make_diff_composite(before_bytes: bytes, after_bytes: bytes) -> bytes | None:
    """_make_pair_composite(좌우로 나란히 붙이기)의 후속 — 좌우 스왑 테스트로
    확인해보니 CNN이 "왼쪽과 오른쪽을 비교해라"를 실제로 배우지 못하고 있었다
    (순서를 바꿔도 예측이 거의 안 바뀜 = 장면 전체 느낌만 외운 것). 그래서 비교를
    모델한테 맡기지 않고 우리가 직접 계산해서 이미지 자체에 인코딩한다:
    R채널 = 밝아진 정도(물건이 새로 생겼을 후보), B채널 = 어두워진 정도(물건이
    없어졌을 후보), G=0. 로컬 프로토타입(간단한 grid-diff 특징 + RandomForest)에서
    baseline 52.5% 대비 70.1%, 그리고 좌우를 바꾸면 실제로 예측이 뒤집히는 것까지
    확인한 뒤 채택."""
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
    gb_c = gb - (gb.mean() - ga.mean())  # 전역 밝기(AEC 재조정) 보정
    diff = gb_c - ga  # 부호 있는 diff: + 밝아짐, - 어두워짐

    scale = 2.0
    r = np.clip(np.clip(diff, 0, None) * scale, 0, 255).astype(np.uint8)
    bch = np.clip(np.clip(-diff, 0, None) * scale, 0, 255).astype(np.uint8)
    g = np.zeros_like(r)
    diff_rgb = np.stack([r, g, bch], axis=-1)

    out_img = Image.fromarray(diff_rgb, mode="RGB")
    buf = io.BytesIO()
    out_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _diff_percent(before_bytes: bytes, after_bytes: bytes) -> float | None:
    """before/after 두 장이 실제로 얼마나 달라졌는지 %로 계산한다. 실측해보니
    어두운 조명 + 작은 물건 + 압축(빠름 화질)이 겹치면 사람 눈으로 축소된
    합성사진만 봐서는 진짜 변화가 있어도 놓치기 쉬웠다 — 그래서 After 찍자마자
    숫자로 바로 알려준다. 전역 밝기 변화(AEC 재조정)는 먼저 보정해서, 손 떨림/
    노출 차이가 아니라 국소적으로(그 선반 자리) 진짜 달라진 정도만 반영한다."""
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


def _record_loop(label: str, quality: str):
    """백그라운드 스레드 — 정지 신호가 오거나 RECORD_MAX_S를 넘을 때까지
    계속 촬영해서 기존 셔터 캡처와 동일한 규칙으로 저장한다. 한 번에 여러
    장을 찍으니 초 단위 타임스탬프로는 파일명이 겹칠 수 있어서(같은 라벨을
    1초에 여러 장) 밀리초 단위로 찍는다 — train_pipeline.py의 파일명 정규식은
    숫자 자릿수를 안 가려서(그냥 \\d+) 그대로 호환된다.

    프레임마다 실제 캡처 왕복시간(capture_ms)과 세션 시작 대비 경과(t)를
    같이 남긴다 — "찍겠다고 한 간격(RECORD_INTERVAL_S)"과 "실제로 걸린
    시간"이 다를 수 있다는 걸 실측으로 확인했기 때문에(연결 재사용 전엔
    프레임당 0.7~1.7초씩 걸림) 개발자 모드 UI에서 이 차이를 바로 보여준다.

    끝나면 첫/마지막 프레임을 이어붙인 "비교 사진"도 `<label>-pair`라는 별도
    라벨로 하나 더 저장한다 (_make_pair_composite 참고) — in/out처럼 방향이
    핵심인 라벨은 이 pair 쪽으로 학습하는 걸 권장."""
    global camera
    t0 = time.time()
    idx0 = label_count(label)
    n = 0
    first_bytes = None
    last_bytes = None
    while not record_stop_flag.is_set() and (time.time() - t0) < RECORD_MAX_S:
        cam = ensure_camera()
        if cam is None:
            break
        cap_t0 = time.time()
        try:
            with camera_io_lock:
                data = cam.capture(quality)
        except SerialCameraError:
            camera = None
            break
        capture_ms = round((time.time() - cap_t0) * 1000)
        n += 1
        if first_bytes is None:
            first_bytes = data
        last_bytes = data
        fname = f"{label}_{int(time.time() * 1000)}_{idx0 + n:03d}.jpg"
        (CAPTURE_DIR / fname).write_bytes(data)
        with record_lock:
            record_state["count"] = n
            record_state["latest_bytes"] = data
            record_state["seq"] += 1
            record_state["last_capture_ms"] = capture_ms
            record_state["frames"].append({
                "filename": fname, "url": f"/captures/{fname}",
                "t": round(time.time() - t0, 2), "capture_ms": capture_ms,
            })
        time.sleep(RECORD_INTERVAL_S)

    with record_lock:
        record_state["pair_url"] = None
        record_state["pair_mode"] = "none"
        saved_frames = list(record_state["frames"])

    if n >= 2 and first_bytes and last_bytes:
        # 실측해보니 사람이 녹화 버튼을 누르고/떼는 시점은 실제 "손이 물건을
        # 만지는 순간"보다 앞뒤로 여유가 있어서, 첫/끝 프레임을 그대로 쓰면
        # 둘 다 손 없는 빈 장면이 되는 경우가 많았다. 그래서 저장된 프레임들을
        # 순서대로 다시 훑어서 "손이 처음 보인 프레임"과 "손이 마지막으로
        # 보인 프레임"을 찾고, 있으면 그걸로 pair를 만든다 — 진짜 동작의
        # 시작/끝에 훨씬 가깝다. 손이 한 번도 안 잡히면 기존처럼 첫/끝 프레임으로
        # 폴백한다(이땐 pair_mode로 그렇다는 걸 UI에 표시해서 재촬영 여부 판단 가능).
        hand_first_bytes = hand_last_bytes = None
        for fr in saved_frames:
            try:
                data = (CAPTURE_DIR / fr["filename"]).read_bytes()
            except OSError:
                continue
            if _has_hand(data):
                if hand_first_bytes is None:
                    hand_first_bytes = data
                hand_last_bytes = data

        if hand_first_bytes and hand_last_bytes and hand_first_bytes != hand_last_bytes:
            pair_a, pair_b, pair_mode = hand_first_bytes, hand_last_bytes, "hand"
        else:
            pair_a, pair_b, pair_mode = first_bytes, last_bytes, "first_last"

        pair = _make_diff_composite(pair_a, pair_b)
        if pair:
            pair_label = f"{label}-pair"
            pidx = label_count(pair_label) + 1
            pfname = f"{pair_label}_{int(time.time() * 1000)}_{pidx:03d}.jpg"
            (CAPTURE_DIR / pfname).write_bytes(pair)
            with record_lock:
                record_state["pair_url"] = f"/captures/{pfname}"
                record_state["pair_mode"] = pair_mode

    with record_lock:
        record_state["active"] = False


@app.post("/api/record/start")
def record_start():
    global record_thread
    cam = ensure_camera()
    if cam is None:
        return jsonify({"error": "camera not connected — 케이블/포트 확인 후 다시 시도해주세요"}), 503

    body = request.get_json(silent=True) or {}
    label = body.get("label", "").strip() or "untitled"
    label = re.sub(r"[^a-zA-Z0-9가-힣_-]", "-", label)
    quality = body.get("quality") if body.get("quality") in QUALITY_PRESETS else DEFAULT_QUALITY

    with record_lock:
        if record_state["active"]:
            return jsonify({"error": "이미 녹화 중입니다"}), 409
        record_state.update({
            "active": True, "label": label, "start_ts": time.time(),
            "count": 0, "latest_bytes": None, "seq": 0,
            "last_capture_ms": None, "frames": [], "pair_url": None, "pair_mode": "none",
        })
    record_stop_flag.clear()
    record_thread = threading.Thread(target=_record_loop, args=(label, quality), daemon=True)
    record_thread.start()
    return jsonify({"ok": True, "label": label, "max_seconds": RECORD_MAX_S})


def _timing_summary(frames: list) -> dict:
    """찍힌 프레임들의 t(초) 값으로 간격 통계를 낸다 — 목표 간격(RECORD_INTERVAL_S)과
    실제 간격이 얼마나 벌어졌는지 개발자 모드 UI에 바로 보여주기 위함."""
    if len(frames) < 2:
        return {"avg_interval_s": None, "max_gap_s": None, "fps": None}
    ts = [f["t"] for f in frames]
    gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
    avg = sum(gaps) / len(gaps)
    return {
        "avg_interval_s": round(avg, 2),
        "max_gap_s": round(max(gaps), 2),
        "fps": round(1 / avg, 2) if avg > 0 else None,
    }


@app.post("/api/record/stop")
def record_stop():
    record_stop_flag.set()
    if record_thread is not None:
        # 정지 후 손 감지로 pair 프레임을 고르는 후처리(프레임당 20~50ms)가 있어서
        # 넉넉히 기다린다 — 2초는 프레임이 많을 때(모델 첫 로딩 포함) 부족했다.
        record_thread.join(timeout=8)
    with record_lock:
        frames = list(record_state["frames"])
        return jsonify({
            "ok": True, "label": record_state["label"], "count": record_state["count"],
            "frames": frames, "pair_url": record_state["pair_url"], "pair_mode": record_state["pair_mode"],
            **_timing_summary(frames),
        })


@app.get("/api/record/status")
def record_status():
    with record_lock:
        active = record_state["active"]
        s = {
            "active": active,
            "label": record_state["label"],
            "count": record_state["count"],
            "seq": record_state["seq"],
            "elapsed": round(time.time() - record_state["start_ts"], 1) if active and record_state["start_ts"] else None,
            "last_capture_ms": record_state["last_capture_ms"],
            "frames": list(record_state["frames"]),
            "pair_url": record_state["pair_url"],
            "pair_mode": record_state["pair_mode"],
        }
    s.update(_timing_summary(s["frames"]))
    return jsonify(s)


@app.get("/api/record/latest.jpg")
def record_latest_jpg():
    """녹화 중 방금 찍힌 프레임 — 미리보기 폴링과 별도로 "지금 뭘 찍고 있는지"를 그대로 보여준다."""
    with record_lock:
        data = record_state["latest_bytes"]
    if data is None:
        return ("", 503)
    return app.response_class(data, mimetype="image/jpeg")


@app.get("/api/gallery")
def gallery():
    return jsonify(gallery_items())


@app.post("/api/export")
def export():
    """라벨별로 data/raw_captures의 사진들을 data/exports/<label>.zip으로 묶는다.
    body: {"labels": ["egg", "soymilk"]} — 생략하면 현재 있는 라벨 전부."""
    body = request.get_json(silent=True) or {}
    labels = body.get("labels") or known_labels()
    if not labels:
        return jsonify({"error": "내보낼 사진이 없습니다"}), 400

    results = []
    for label in labels:
        files = sorted(CAPTURE_DIR.glob(f"{label}_*.jpg"))
        if not files:
            continue
        zip_path = EXPORT_DIR / f"{label}.zip"
        now = time.localtime()[:6]
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, f in enumerate(files, 1):
                # Edge Impulse 업로드 관례에 맞춘 이름: label.1.jpg, label.2.jpg ...
                # AP 수집기(webcam_ap_collect)가 만든 원본 파일의 mtime이 1980년 이전으로
                # 찍혀있어서(브라우저 zip 다운로드 시점 타임스탬프 버그) 그대로 쓰면
                # zipfile이 ValueError를 낸다 — 지금 시각으로 강제 지정한다.
                zinfo = zipfile.ZipInfo(filename=f"{label}.{i}.jpg", date_time=now)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zinfo, f.read_bytes())
        results.append({
            "label": label,
            "filename": zip_path.name,
            "path": str(zip_path.relative_to(ROOT)),
            "count": len(files),
        })

    if not results:
        return jsonify({"error": "해당 라벨의 사진을 찾지 못했습니다"}), 404

    return jsonify({"ok": True, "exports": results})


@app.get("/captures/<path:filename>")
def serve_capture(filename):
    return send_from_directory(CAPTURE_DIR, filename)


def local_lan_ip() -> str | None:
    """이 컴퓨터의 현재 WiFi IP. FridgeCam 핫스팟처럼 인터넷이 없는 네트워크에
    붙어있을 때도 동작해야 해서(8.8.8.8로 소켓 연결하는 트릭은 인터넷이 없으면
    막힐 수 있음) macOS 인터페이스 IP를 직접 물어본다. 매 상태 조회마다 새로
    계산해서, 서버를 안 껐다 켜도 와이파이를 바꾸면 바로 반영되게 한다."""
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


def main():
    global serial_port, serial_baud, esp_host, backend, http_port
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="ESP32 시리얼 포트 (USB 연결 시)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--esp-host", default=None,
                     help="ESP32 IP/호스트 (WiFi 연결 시, 예: 192.168.4.1 — FridgeCam 핫스팟에 먼저 접속돼있어야 함)")
    ap.add_argument("--http-port", type=int, default=8420, help="이 로컬 서버 자체가 뜰 포트")
    args = ap.parse_args()
    http_port = args.http_port

    if args.esp_host:
        backend = "http"
        esp_host = args.esp_host
    else:
        backend = "serial"
        serial_port = args.port or "/dev/tty.usbmodem1101"
        serial_baud = args.baud

    if ensure_camera() is not None:
        target = esp_host if backend == "http" else serial_port
        print(f"[{backend}] {target} 연결됨")
    else:
        print(f"[{backend}] 연결 실패 — 카메라 없이 서버만 띄웁니다. 요청 시마다 재연결을 다시 시도합니다.")

    lan_ip = local_lan_ip()
    print(f"\n  로컬:     http://localhost:{args.http_port}")
    if lan_ip:
        print(f"  같은 와이파이(폰 등): http://{lan_ip}:{args.http_port}\n")

    app.run(host="0.0.0.0", port=args.http_port, threaded=True)


if __name__ == "__main__":
    main()
