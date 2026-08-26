"""손으로 돌려 등록하고 다시 알아보는 2차 브라우저 AI 프로토타입."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string
from PIL import Image

from container_detector import ContainerDetector
from container_registry import DinoV2Embedder
from container_registry_v2 import (
    DEFAULT_DB_V2, DEFAULT_LOG_V2, DEFAULT_THRESHOLD_V2,
    ContainerDatabaseV2, append_log, select_representative_vectors,
)
from live_container_recognition import fetch_jpg, make_jpg_url

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DEBUG_ROOT = ROOT / "v2_registration_debug"


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>용기 AI 2차 프로토타입</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#101216;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:4px}.sub{color:#aeb5c0;font-size:13px;margin:8px 0 14px}#wrap{position:relative;display:inline-block;width:min(92vw,480px)}
#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tag{position:absolute;left:0;top:0;padding:7px 12px;border-radius:12px 0 10px 0;background:#56606f;font-weight:bold}
#countdown{display:none;position:absolute;inset:0;align-items:center;justify-content:center;font-size:92px;font-weight:bold;color:#fff;text-shadow:0 3px 14px #000;background:#0003;border-radius:12px;pointer-events:none}
#notice{display:none;position:fixed;z-index:20;left:50%;top:12%;transform:translateX(-50%);width:min(88vw,520px);padding:18px;border-radius:14px;background:#23a866;color:white;font-size:22px;font-weight:bold;box-shadow:0 8px 30px #0009}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:13px}.buttons{display:flex;gap:9px;justify-content:center;flex-wrap:wrap}
button{border:0;border-radius:9px;padding:12px 16px;color:#fff;font-size:15px;font-weight:bold;cursor:pointer;background:#3478f6}button.register{background:#e18a26}button:disabled{background:#59616d;cursor:wait}
#status{margin-top:11px;min-height:38px;color:#c9d0da;line-height:1.5}.progress{height:12px;background:#343b46;border-radius:8px;overflow:hidden;margin-top:10px}.progress div{height:100%;width:0;background:#e18a26;transition:width .15s}
#result{font-size:18px;font-weight:bold;margin:5px}.meta{font-size:13px;color:#aeb5c0}#list{text-align:left;line-height:1.8;font-size:14px}.tip{color:#ffd38a;font-size:13px;line-height:1.55}
</style></head><body><div id="notice"></div><h2>🧊 용기 AI 2차 프로토타입</h2>
<div class="sub">손에 든 용기 · 10초 다각도 등록 · 갤러리 재인식</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas><div id="tag">카메라 대기</div><div id="countdown"></div></div>
<div class="panel"><div class="buttons"><button id="recognize" onclick="recognize()">기존 용기 인식</button><button class="register" id="register" onclick="registerNew()">새 용기 등록 촬영</button></div>
<div id="status">용기를 손으로 들고 화면 중앙에 보여주세요.</div><div class="progress"><div id="progress"></div></div></div>
<div class="panel"><div id="result">아직 분석하지 않음</div><div id="meta" class="meta"></div></div>
<div class="panel tip">새 용기 등록 시 버튼을 누른 직후부터 10초 동안 용기를 천천히 좌우로 돌리세요.<br>약 100장을 촬영하고 YOLO가 용기를 찾은 모든 사진의 특징을 저장합니다.</div>
<div class="panel"><b>2차 DB에 등록된 용기</b><div id="list">아직 없음</div></div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');let busy=false;
// AI 작업 중에도 서버에 저장된 최신 카메라 프레임을 계속 보여준다.
setInterval(()=>{cam.src='/camera.jpg?t='+Date.now()},350);
function buttons(disabled){busy=disabled;document.getElementById('recognize').disabled=disabled;document.getElementById('register').disabled=disabled}
function box(item,w,h,color){const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);if(!item||!item.box)return;const [x1,y1,x2,y2]=item.box;ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(x1*r.width/w,y1*r.height/h,(x2-x1)*r.width/w,(y2-y1)*r.height/h)}
function list(items){document.getElementById('list').innerHTML=items.length?items.map(x=>`<div><b>${x.container_id}</b> · 대표 모습 ${x.vector_count}개 · 마지막 확인 ${x.last_seen}</div>`).join(''):'아직 없음'}
function notify(text,color='#23a866'){const n=document.getElementById('notice');n.textContent=text;n.style.background=color;n.style.display='block';clearTimeout(window.noticeTimer);window.noticeTimer=setTimeout(()=>n.style.display='none',3500)}
function show(d){list(d.containers||[]);const item=d.result;if(!item)return;const matched=item.status==='matched',registered=item.status==='registered';document.getElementById('tag').textContent=registered?'NEW '+item.container_id:matched?'MATCH '+item.container_id:'UNKNOWN';document.getElementById('tag').style.background=registered?'#e18a26':matched?'#28a96b':'#c54b54';document.getElementById('result').textContent=registered?`${item.container_id} 새로 등록 완료`:matched?`${item.container_id}로 인식`:'등록되지 않은 용기';const shape=item.dino_similarity==null?'-':(item.dino_similarity*100).toFixed(0)+'%',color=item.color_similarity==null?'-':(item.color_similarity*100).toFixed(0)+'%';document.getElementById('meta').textContent=`종합 ${item.similarity==null?'-':(item.similarity*100).toFixed(0)+'%'} · 외형 ${shape} · 색상 ${color} · YOLO ${(item.detection_confidence*100).toFixed(0)}%`;box(item,d.width,d.height,registered?'#ffad45':matched?'#38e58f':'#ff6670');if(matched)notify(`${item.container_id} 용기 인식 성공!`);if(registered)notify(`${item.container_id} 새 용기 등록 성공!`,'#e18a26')}
async function recognize(){buttons(true);document.getElementById('status').textContent='현재 화면을 1차 방식으로 등록 벡터들과 비교하고 있습니다.';try{const r=await fetch('/recognize',{method:'POST'}),d=await r.json();if(!r.ok)throw Error(d.error);show(d);document.getElementById('status').textContent=d.result.status==='unknown'?'등록된 용기와 충분히 비슷하지 않습니다.':'등록된 벡터 중 가까운 3개의 평균으로 확인했습니다.'}catch(e){document.getElementById('status').textContent=e.message}finally{buttons(false);cam.src='/camera.jpg?t='+Date.now()}}
async function registerNew(){if(!confirm('이 용기를 새로운 ID로 등록할까요? 확인을 누른 뒤 10초 동안 천천히 돌려주세요.'))return;buttons(true);const p=document.getElementById('progress'),cd=document.getElementById('countdown');p.style.width='0%';cd.style.display='flex';cd.textContent='10';document.getElementById('status').textContent='촬영 시작! 화면을 보면서 용기를 천천히 좌우로 돌려주세요.';const started=Date.now();const timer=setInterval(()=>{const elapsed=(Date.now()-started)/1000,remain=Math.max(0,Math.ceil(10-elapsed));p.style.width=Math.min(100,elapsed/10*100)+'%';cd.textContent=remain>0?remain:'AI';if(elapsed>=10){document.getElementById('status').textContent='촬영 완료. YOLO 탐지와 벡터 저장을 진행 중입니다.'}},100);try{const r=await fetch('/register',{method:'POST'}),d=await r.json();if(!r.ok)throw Error(d.error);show(d);document.getElementById('status').textContent=`등록 완료: 총 ${d.captured_frames}장 중 YOLO가 찾은 ${d.detected_frames}장의 벡터 ${d.result.vector_count}개를 모두 저장했습니다.`;}catch(e){document.getElementById('status').textContent=e.message}finally{clearInterval(timer);p.style.width='100%';cd.style.display='none';buttons(false);cam.src='/camera.jpg?t='+Date.now()}}
fetch('/containers').then(r=>r.json()).then(list).catch(()=>{});
</script></body></html>"""


class RecognitionServiceV2:
    def __init__(self, camera_address: str, db_path: Path, log_path: Path,
                 threshold: float, capture_seconds: float = 10.0):
        self.camera_url = make_jpg_url(camera_address)
        self.db_path, self.log_path = db_path, log_path
        self.threshold, self.capture_seconds = threshold, capture_seconds
        self.camera_lock, self.analysis_lock = threading.Lock(), threading.Lock()
        self.latest_frame = None
        self.camera_error = "카메라 연결 대기 중"
        self.detector = self.embedder = None
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while True:
            try:
                frame = fetch_jpg(self.camera_url)
                with self.camera_lock:
                    self.latest_frame, self.camera_error = frame, ""
                time.sleep(0.12)
            except Exception as error:
                with self.camera_lock:
                    self.camera_error = str(error)
                time.sleep(0.7)

    def frame(self, wait_seconds: float = 8.0):
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            with self.camera_lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
                error = self.camera_error
            time.sleep(0.1)
        raise ConnectionError(f"ESP32 최신 사진이 없습니다: {error}")

    def models(self):
        if self.detector is None:
            print("YOLO와 DINOv2 모델 준비 중...")
            self.detector, self.embedder = ContainerDetector(), DinoV2Embedder()
            print("AI 모델 준비 완료")

    def containers(self):
        db = ContainerDatabaseV2(self.db_path)
        try:
            return db.list_containers()
        finally:
            db.close()

    @staticmethod
    def _pil(crop):
        return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

    @staticmethod
    def _usable_detection(frame, detection) -> bool:
        """너무 작거나 화면 전체·가장자리를 배경째 잡은 네모를 제외한다."""
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = detection.box
        box_width, box_height = x2 - x1, y2 - y1
        area_ratio = (box_width * box_height) / float(width * height)
        center_x, center_y = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
        centered = abs(center_x - 0.5) <= 0.38 and abs(center_y - 0.5) <= 0.38
        touches_both_horizontal_edges = x1 <= 2 and x2 >= width - 2
        touches_both_vertical_edges = y1 <= 2 and y2 >= height - 2
        background_sized = box_width / width >= 0.94 or box_height / height >= 0.94
        return (
            0.025 <= area_ratio <= 0.78
            and centered
            and not touches_both_horizontal_edges
            and not touches_both_vertical_edges
            and not background_sized
        )

    @staticmethod
    def _sharp_enough(crop) -> bool:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var()) >= 8.0

    @staticmethod
    def _diverse_enough(crops) -> tuple[bool, int]:
        """첫 모습과 확실히 다른 프레임이 충분한지 검사한다."""
        if not crops:
            return False, 0
        reference = cv2.resize(cv2.cvtColor(crops[0], cv2.COLOR_BGR2GRAY), (64, 64))
        different = 0
        for crop in crops[1:]:
            current = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (64, 64))
            if float(cv2.absdiff(reference, current).mean()) >= 4.0:
                different += 1
        required = min(10, max(4, len(crops) // 10))
        return different >= required, different

    @staticmethod
    def _save_debug_images(container_id, frames, detections, identity_crops, identity_boxes):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = DEBUG_ROOT / f"{container_id}_{stamp}"
        original_dir, crop_dir = folder / "original_with_boxes", folder / "identity_crops"
        original_dir.mkdir(parents=True, exist_ok=True)
        crop_dir.mkdir(parents=True, exist_ok=True)
        for index, (frame, detection, crop, identity_box) in enumerate(
            zip(frames, detections, identity_crops, identity_boxes), start=1
        ):
            annotated = frame.copy()
            x1, y1, x2, y2 = detection.box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 100, 0), 2)
            cx1, cy1, cx2, cy2 = identity_box
            cv2.rectangle(annotated, (cx1, cy1), (cx2, cy2), (0, 220, 0), 2)
            cv2.imencode(".jpg", annotated)[1].tofile(original_dir / f"frame_{index:03d}.jpg")
            cv2.imencode(".jpg", crop)[1].tofile(crop_dir / f"crop_{index:03d}.jpg")
        return folder

    @staticmethod
    def _color_vector(crop):
        """전체와 윗부분(뚜껑)의 HSV 색상 분포를 결합한다."""
        if isinstance(crop, Image.Image):
            source = np.asarray(crop.convert("RGB"))
            hsv = cv2.cvtColor(source, cv2.COLOR_RGB2HSV)
        else:
            source = np.asarray(crop)
            hsv = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)
        upper = hsv[:max(1, hsv.shape[0] // 2), :]
        parts = []
        for image in (hsv, upper):
            hist = cv2.calcHist([image], [0, 1], None, [24, 16], [0, 180, 0, 256]).reshape(-1)
            parts.append(hist)
        vector = np.concatenate(parts).astype(np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def recognize(self):
        with self.analysis_lock:
            self.models()
            frame = self.frame()
            detections = self.detector.detect(frame)
            if not detections:
                append_log(self.log_path, event="no_detection", container_id=None,
                           similarity=None, detection_confidence=None)
                raise ValueError("용기를 찾지 못했습니다. 화면 중앙에 용기 전체가 보이게 해주세요.")
            usable = [item for item in detections if self._usable_detection(frame, item)]
            if not usable:
                raise ValueError("YOLO 네모가 화면 전체나 배경을 너무 많이 포함했습니다. 용기를 더 가까이 중앙에 보여주세요.")
            detection = max(usable, key=lambda item: item.confidence)
            identity_crop = detection.crop
            vector = self.embedder.extract_pil_images([self._pil(identity_crop)])[0]
            db = ContainerDatabaseV2(self.db_path)
            try:
                result = db.recognize(vector, self._color_vector(identity_crop), self.threshold)
            finally:
                db.close()
            result.update(detection_confidence=detection.confidence, box=list(detection.box))
            append_log(self.log_path, event=result["status"], container_id=result["container_id"],
                       similarity=result["similarity"], detection_confidence=detection.confidence,
                       detail=f"dino={result.get('dino_similarity')} color={result.get('color_similarity')}")
            return result, frame

    def register(self):
        with self.analysis_lock:
            self.models()
            frames = []
            deadline = time.monotonic() + self.capture_seconds
            while time.monotonic() < deadline:
                frames.append(self.frame().copy())
                time.sleep(0.1)
            crops, confidences, boxes = [], [], []
            accepted_frames, accepted_detections, identity_boxes = [], [], []
            for frame in frames:
                # 등록은 사용자가 화면을 확인하고 직접 누르므로 기본 2% 후보를 사용한다.
                detections = self.detector.detect(frame)
                if not detections:
                    continue
                detection = max(detections, key=lambda item: item.confidence)
                if not self._usable_detection(frame, detection):
                    continue
                identity_crop, identity_box = detection.crop, detection.box
                if not self._sharp_enough(identity_crop):
                    continue
                crops.append(identity_crop)
                confidences.append(detection.confidence)
                boxes.append(detection.box)
                accepted_frames.append(frame)
                accepted_detections.append(detection)
                identity_boxes.append(identity_box)
            if not crops:
                append_log(self.log_path, event="registration_failed", container_id=None,
                           similarity=None, detection_confidence=None,
                           detail=f"captured={len(frames)} detected=0")
                raise ValueError(
                    f"10초 동안 {len(frames)}장을 촬영했지만 YOLO가 용기 위치를 찾지 못했습니다. "
                    "용기 전체가 보이게 다시 시도하세요."
                )
            diverse, different_count = self._diverse_enough(crops)
            if not diverse:
                append_log(self.log_path, event="registration_failed", container_id=None,
                           similarity=None, detection_confidence=max(confidences),
                           detail=f"captured={len(frames)} accepted={len(crops)} diverse={different_count}")
                raise ValueError(
                    f"용기 사진 {len(crops)}장은 찾았지만 서로 다른 모습은 {different_count}장뿐입니다. "
                    "용기를 앞·옆·뒤가 보이도록 더 크게 돌리며 다시 등록하세요."
                )
            vectors = list(
                self.embedder.extract_pil_images([self._pil(crop) for crop in crops], batch_size=16)
            )
            representatives = vectors
            colors = [self._color_vector(crop) for crop in crops]
            db = ContainerDatabaseV2(self.db_path)
            try:
                result = db.register_gallery(representatives, colors)
            finally:
                db.close()
            best_index = max(range(len(confidences)), key=confidences.__getitem__)
            debug_folder = self._save_debug_images(
                result["container_id"], accepted_frames, accepted_detections,
                crops, identity_boxes,
            )
            result.update(detection_confidence=confidences[best_index], box=list(boxes[best_index]))
            append_log(self.log_path, event="registered", container_id=result["container_id"],
                       similarity=None, detection_confidence=confidences[best_index],
                       detail=f"captured={len(frames)} accepted={len(crops)} stored={len(representatives)} debug={debug_folder}")
            return result, frames[-1], len(frames), len(crops)


def create_app(service: RecognitionServiceV2):
    app = Flask(__name__)
    @app.get("/")
    def index(): return render_template_string(PAGE)
    @app.get("/camera.jpg")
    def camera_jpg():
        try:
            frame = service.frame(); ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok: raise ValueError("JPEG 변환 실패")
            return Response(encoded.tobytes(), mimetype="image/jpeg", headers={"Cache-Control":"no-store"})
        except Exception as error: return jsonify(error=str(error)), 503
    @app.get("/containers")
    def containers(): return jsonify(service.containers())
    @app.post("/recognize")
    def recognize():
        try:
            result, frame = service.recognize()
            return jsonify(result=result, width=frame.shape[1], height=frame.shape[0], containers=service.containers())
        except Exception as error: return jsonify(error=str(error)), 400
    @app.post("/register")
    def register():
        try:
            result, frame, captured, detected = service.register()
            return jsonify(result=result, width=frame.shape[1], height=frame.shape[0],
                           captured_frames=captured, detected_frames=detected,
                           containers=service.containers())
        except Exception as error: return jsonify(error=str(error)), 400
    return app


def main():
    parser = argparse.ArgumentParser(description="용기 AI 2차 프로토타입")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_V2)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_V2)
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD_V2)
    parser.add_argument("--capture-seconds", type=float, default=10.0)
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    service = RecognitionServiceV2(args.address, args.db, args.log, args.identity_threshold, args.capture_seconds)
    print("2차 프로토타입이 ESP32 카메라 연결을 기다립니다.")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(service).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__": main()
