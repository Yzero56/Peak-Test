"""주방 재료(양파/대파/당근/김치)를 실시간으로 인식하면서, 처음 보는 물건이면
용기 단위로 자동 등록하고 DB에 기록하는 스트리밍 서버.

browser_pantry_realtime_multi.py의 인식 로직 + pantry_registry.py의 등록 로직을 합쳤다.
당근/대파/양파는 "A용기", 김치는 "김치용기"로 자동 분류되어 등록된다.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2
import joblib
import numpy as np
from flask import Flask, Response, jsonify, render_template_string
from PIL import Image
from ultralytics import YOLOWorld

from container_detector import DEFAULT_MODEL, ContainerDetection
from container_registry import DinoV2Embedder
from live_container_recognition import fetch_jpg, make_jpg_url
from pantry_registry import PantryRegistry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "pantry_classifier.joblib"
MAX_OBJECTS = 6
CONFIDENCE_THRESHOLD = 0.6  # 이 이상 확신할 때만 등록 처리 (오인식으로 신규 등록되는 것 방지)

# 당근(주황)/대파(초록)는 색이 뚜렷해서, 분류기가 헷갈려도 색으로 바로잡는 안전장치.
CARROT_ORANGE_HUE_RANGE = (5, 22)  # OpenCV HSV hue (0~179 스케일) 기준 주황색 범위
CARROT_ORANGE_MIN_FRACTION = 0.35  # 크롭 픽셀 중 이 비율 이상 주황이면 당근으로 강제 판정
CARROT_OVERRIDE_CONFIDENCE = 0.9

SCALLION_GREEN_HUE_RANGE = (35, 85)  # OpenCV HSV hue 기준 초록색 범위 (대파 잎)
SCALLION_GREEN_MIN_FRACTION = 0.30  # 크롭 픽셀 중 이 비율 이상 초록이면 대파로 강제 판정
SCALLION_OVERRIDE_CONFIDENCE = 0.9


def _hue_fraction(crop_bgr: np.ndarray, hue_range: tuple[int, int]) -> float:
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (hue >= hue_range[0]) & (hue <= hue_range[1]) & (sat >= 80) & (val >= 60)
    return float(mask.mean())


def orange_fraction(crop_bgr: np.ndarray) -> float:
    return _hue_fraction(crop_bgr, CARROT_ORANGE_HUE_RANGE)


def green_fraction(crop_bgr: np.ndarray) -> float:
    return _hue_fraction(crop_bgr, SCALLION_GREEN_HUE_RANGE)


# 양파는 하얗고 둥글어서(색+모양) 판단. 용기까지 하얗게 걸릴 수 있어 채도/밝기
# 조건을 촘촘하게 잡고, "둥글다"는 크롭의 가로세로 비율이 정사각형에 가까운지로 근사한다.
ONION_WHITE_SAT_MAX = 60      # 채도가 낮아야(색이 옅어야) 흰색으로 침
ONION_WHITE_VAL_MIN = 150     # 밝아야 흰색으로 침
ONION_WHITE_MIN_FRACTION = 0.45
ONION_ROUND_ASPECT_TOLERANCE = 0.25  # |가로/세로 - 1| 이 이 값 이하면 "둥글다"로 취급
ONION_OVERRIDE_CONFIDENCE = 0.85


def white_fraction(crop_bgr: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    mask = (sat <= ONION_WHITE_SAT_MAX) & (val >= ONION_WHITE_VAL_MIN)
    return float(mask.mean())


def is_roundish(crop_bgr: np.ndarray) -> bool:
    height, width = crop_bgr.shape[:2]
    if height == 0 or width == 0:
        return False
    return abs((width / height) - 1.0) <= ONION_ROUND_ASPECT_TOLERANCE
PROMPTS = [
    "ball", "onion", "round vegetable", "white onion",
    "green onion", "scallion", "leek",
    "carrot",
    "kimchi", "food", "fermented vegetable", "bowl of food",
]

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>주방 재료 인식 + 신규 등록</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f1216;color:#eee;text-align:center;margin:0;padding:16px}h2{margin:4px}.sub{color:#adb6c2;font-size:13px;margin:8px 0 14px}
#wrap{position:relative;display:inline-block;width:min(92vw,480px)}#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:15px;text-align:left}
#status{color:#bdc5d0;font-size:14px;line-height:1.5;text-align:center}#list div{padding:8px 10px;margin:6px 0;border-radius:8px;background:#262d38;font-size:15px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#36d67e;margin-right:7px;box-shadow:0 0 9px #36d67e}
.new{color:#38e58f;font-weight:bold}.known{color:#8aa0b8}
#db div{padding:6px 10px;margin:4px 0;border-radius:8px;background:#20262f;font-size:14px}
h3{margin:0 0 8px;font-size:15px;color:#ffd38a}
</style></head><body><h2>🥬 주방 재료 인식 + 신규 등록</h2><div class="sub"><span class="dot"></span>양파/대파/당근 → A용기, 김치 → 김치용기 자동 등록</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas></div>
<div class="panel"><div id="status" style="text-align:center">첫 분석은 AI 모델 준비 때문에 오래 걸릴 수 있습니다.</div><div id="list"></div></div>
<div class="panel"><h3>📋 등록된 DB 현황</h3><div id="db"></div></div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),350);
function draw(d){
 const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);
 if(!d.objects)return;
 const sx=r.width/d.width, sy=r.height/d.height;
 d.objects.forEach(o=>{
  const [x1,y1,x2,y2]=o.box, bx=x1*sx, by=y1*sy, bw=(x2-x1)*sx, bh=(y2-y1)*sy;
  ctx.strokeStyle=o.registration && o.registration.status==='registered' ? '#ffb347' : '#38e58f';
  ctx.lineWidth=3;ctx.strokeRect(bx,by,bw,bh);
  const text=`${o.label} ${(o.confidence*100).toFixed(0)}%`;
  ctx.font='bold 15px Arial';const tw=ctx.measureText(text).width+10;
  ctx.fillStyle=ctx.strokeStyle;ctx.fillRect(bx,Math.max(0,by-20),tw,20);
  ctx.fillStyle='#0f1216';ctx.fillText(text,bx+5,Math.max(14,by-6));
 });
}
function renderDb(rows){
 document.getElementById('db').innerHTML = rows.length ? rows.map(r=>
   `<div>${r.container_name} — ${r.item_label} (관찰 ${r.seen_count}회, 등록: ${r.registered_at})</div>`
 ).join('') : '<div>아직 등록된 물건 없음</div>';
}
function handle(d){
 const status=document.getElementById('status'),list=document.getElementById('list');
 if(d.status==='ok'){
  draw(d);
  status.textContent=`이번 화면에서 재료 ${d.objects.length}개 인식`;
  list.innerHTML=d.objects.map(o=>{
    if(!o.registration) return `<div>${o.label} — 확률 ${(o.confidence*100).toFixed(0)}% (확신도 낮아 등록 보류)</div>`;
    const cls = o.registration.status==='registered' ? 'new' : 'known';
    const tag = o.registration.status==='registered' ? '🆕 신규 등록!' : '이미 등록됨';
    return `<div class="${cls}">${o.label} → ${o.registration.container_name} — ${tag} (관찰 ${o.registration.seen_count}회)</div>`;
  }).join('');
  renderDb(d.db);
 }else{
  ctx.clearRect(0,0,canvas.width,canvas.height);
  status.textContent=d.message||'재료를 찾지 못했습니다.';
 }
}
async function loop(){try{const r=await fetch('/classify-next',{method:'POST'}),d=await r.json();handle(d)}catch(e){document.getElementById('status').textContent='카메라 연결 대기 중: '+e.message}setTimeout(loop,250)}loop();
</script></body></html>"""


class PantryRegistrationService:
    def __init__(self, address: str, model_path: Path, max_objects: int = MAX_OBJECTS):
        self.camera_url = make_jpg_url(address)
        self.model_path = model_path
        self.max_objects = max_objects
        self.frame_lock, self.analysis_lock = threading.Lock(), threading.Lock()
        self.latest_frame = None; self.camera_error = "카메라 연결 대기 중"
        self.detector = self.embedder = self.classifier_bundle = None
        self.registry = PantryRegistry()
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while True:
            try:
                frame = fetch_jpg(self.camera_url)
                with self.frame_lock: self.latest_frame, self.camera_error = frame, ""
                time.sleep(0.12)
            except Exception as error:
                with self.frame_lock: self.camera_error = str(error)
                time.sleep(0.7)

    def frame(self, wait_seconds=8.0):
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            with self.frame_lock:
                if self.latest_frame is not None: return self.latest_frame.copy()
                error = self.camera_error
            time.sleep(0.1)
        raise ConnectionError(f"카메라 최신 사진이 없습니다: {error}")

    def models(self):
        if self.detector is None:
            print("YOLO·DINOv2·재료 분류 모델 준비 중...")
            self.detector = YOLOWorld(str(DEFAULT_MODEL)); self.detector.set_classes(PROMPTS)
            self.embedder = DinoV2Embedder(); self.classifier_bundle = joblib.load(self.model_path)
            print("재료 분류 모델 준비 완료")

    @staticmethod
    def _valid_detection(frame, box):
        height, width = frame.shape[:2]; x1, y1, x2, y2 = box
        bw, bh = x2-x1, y2-y1; area = bw*bh/float(width*height)
        return bw>0 and bh>0 and 0.01<=area<=0.9 and bw/width<0.98 and bh/height<0.98

    def detect_all(self, frame):
        result = self.detector.predict(frame, conf=0.01, imgsz=640, max_det=self.max_objects,
                                       agnostic_nms=True, verbose=False)[0]
        candidates=[]
        for box, confidence, class_id in zip(result.boxes.xyxy,result.boxes.conf,result.boxes.cls):
            coords=tuple(int(round(float(v))) for v in box)
            if self._valid_detection(frame,coords):
                x1,y1,x2,y2=coords
                candidates.append(ContainerDetection(coords,float(confidence),
                                  self.detector.names[int(class_id)],frame[y1:y2,x1:x2].copy()))
        candidates.sort(key=lambda item:item.confidence, reverse=True)
        return candidates

    def classify(self):
        with self.analysis_lock:
            self.models(); frame=self.frame(); detections=self.detect_all(frame)
            if not detections: raise ValueError("현재 화면에서 재료를 찾지 못했습니다.")
            crops=[Image.fromarray(cv2.cvtColor(detection.crop,cv2.COLOR_BGR2RGB)) for detection in detections]
            vectors=self.embedder.extract_pil_images(crops)
            classifier=self.classifier_bundle['classifier']
            objects=[]
            for detection, vector in zip(detections, vectors):
                probabilities=classifier.predict_proba([vector])[0]
                index=int(probabilities.argmax()); label=str(classifier.classes_[index])
                confidence=float(probabilities[index])

                orange = orange_fraction(detection.crop)
                green = green_fraction(detection.crop)
                white = white_fraction(detection.crop)
                if orange >= CARROT_ORANGE_MIN_FRACTION:
                    label, confidence = "당근", max(confidence, CARROT_OVERRIDE_CONFIDENCE)
                elif green >= SCALLION_GREEN_MIN_FRACTION:
                    label, confidence = "대파", max(confidence, SCALLION_OVERRIDE_CONFIDENCE)
                elif white >= ONION_WHITE_MIN_FRACTION and is_roundish(detection.crop):
                    label, confidence = "양파", max(confidence, ONION_OVERRIDE_CONFIDENCE)

                registration = self.registry.observe(label) if confidence >= CONFIDENCE_THRESHOLD else None
                objects.append({'label':label, 'confidence':confidence,
                                'detection_confidence':detection.confidence,
                                'box':list(detection.box), 'registration':registration})
            return {'status':'ok','objects':objects,'width':frame.shape[1],'height':frame.shape[0],
                    'db':self.registry.snapshot()}


def create_app(service):
    app=Flask(__name__)
    @app.get('/')
    def index(): return render_template_string(PAGE)
    @app.get('/camera.jpg')
    def camera_jpg():
        try:
            frame=service.frame(); ok,encoded=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])
            if not ok: raise ValueError('JPEG 변환 실패')
            return Response(encoded.tobytes(),mimetype='image/jpeg',headers={'Cache-Control':'no-store'})
        except Exception as error: return jsonify(error=str(error)),503
    @app.post('/classify-next')
    def classify_next():
        try: return jsonify(service.classify())
        except ValueError as error: return jsonify(status='no_detection',message=str(error))
        except Exception as error: return jsonify(status='camera_error',message=str(error)),503
    return app


def main():
    parser=argparse.ArgumentParser(description='주방 재료 인식 + 용기 단위 신규 등록 스트리밍')
    parser.add_argument('address',nargs='?',default='192.168.4.1')
    parser.add_argument('--model',type=Path,default=MODEL_PATH)
    parser.add_argument('--port',type=int,default=5010)
    parser.add_argument('--max-objects',type=int,default=MAX_OBJECTS)
    args=parser.parse_args();service=PantryRegistrationService(args.address,args.model,args.max_objects)
    print('주방 재료 인식+등록 서버가 카메라 연결을 기다립니다.');print(f'브라우저 주소: http://127.0.0.1:{args.port}')
    create_app(service).run(host='127.0.0.1',port=args.port,threaded=True,debug=False)


if __name__=='__main__': main()
