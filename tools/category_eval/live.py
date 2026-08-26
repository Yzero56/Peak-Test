"""
live.py — 사진을 모아뒀다가 나중에 채점하는 게 아니라, 지금 카메라에 뭘 비추면
Wa 종류 분류기(category_classifier.joblib)가 그 자리에서 뭐라고 판정하는지
바로 보여주는 페이지. "일단 되는지 보자"용.

origin/Wa:browser_category_realtime.py와 로직은 동일(같은 프롬프트, 같은 탐지
필터, 같은 분류기)하고, 카메라 소스만 이미 마운트된 collect.py의 LazyCamera
(/preview 엔드포인트)로 바꿨다.

실행 (이미 collect.py를 이 IP로 띄워봤다면 같은 --esp-host):
  ./.venv/bin/python tools/category_eval/live.py --esp-host 192.168.4.1

브라우저에서 http://localhost:8611 접속 → 카메라 앞에 물건 들이대면 실시간으로
탐지 박스 + 예측 종류 + 확신도가 뜬다. 저장/기록은 안 하고 화면에만 보여준다
(기록이 필요해지면 그때 collect.py+evaluate.py로 넘어가면 됨).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web_capture"))
from dinov2_embedder import DinoV2Embedder  # noqa: E402
from collect import LazyCamera  # noqa: E402

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "category_classifier.joblib"
WEIGHTS_DIR = Path(__file__).resolve().parents[2] / "weights"
YOLO_WEIGHTS = WEIGHTS_DIR / "yolov8m-worldv2.pt"

KOREAN_LABELS = {"drink_container": "텀블러", "food_container": "반찬 용기", "water_bottle": "생수병"}
PROMPTS = [
    "food storage container", "plastic food container", "lunch box", "plastic box",
    "tumbler", "travel mug", "coffee mug", "drinking cup", "water bottle",
]

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>용기 종류 실시간 인식</title>
<style>
*{box-sizing:border-box}body{font-family:-apple-system,Arial,sans-serif;background:#0f1216;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:4px}.sub{color:#adb6c2;font-size:13px;margin:8px 0 14px}
#wrap{position:relative;display:inline-block;width:min(92vw,480px)}#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}
#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tag{position:absolute;left:0;top:0;padding:8px 13px;border-radius:12px 0 10px 0;background:#596270;font-weight:bold;font-size:18px}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:15px}
#result{font-size:28px;font-weight:bold;min-height:36px}#status{color:#bdc5d0;font-size:14px;line-height:1.5;margin-top:8px}
#meta{font-size:13px;color:#9da7b4;margin-top:8px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#36d67e;margin-right:7px;box-shadow:0 0 9px #36d67e}
</style></head><body>
<h2>🧊 용기 종류 실시간 인식</h2>
<div class="sub"><span class="dot"></span>버튼 없이 계속 판정 중</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas><div id="tag">카메라 대기</div></div>
<div class="panel"><div id="result">대기 중</div><div id="status">모델 준비 중일 수 있습니다 (첫 판정은 느릴 수 있음)</div><div id="meta"></div></div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),400);
function draw(d){const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);if(!d.box)return;const [x1,y1,x2,y2]=d.box;ctx.strokeStyle='#38e58f';ctx.lineWidth=4;ctx.strokeRect(x1*r.width/d.width,y1*r.height/d.height,(x2-x1)*r.width/d.width,(y2-y1)*r.height/d.height)}
function handle(d){const result=document.getElementById('result'),status=document.getElementById('status'),tag=document.getElementById('tag'),meta=document.getElementById('meta');
 if(d.status==='ok'){draw(d);result.textContent=d.label_ko;status.textContent='종류 확신도 '+(d.confidence*100).toFixed(0)+'%';tag.textContent=d.label_ko;tag.style.background='#3478f6';meta.textContent=`YOLO 탐지 확신도 ${(d.detection_confidence*100).toFixed(1)}% · 프롬프트: ${d.prompt}`}
 else if(d.status==='no_camera'){tag.textContent='카메라 연결 안 됨';tag.style.background='#c0392b';result.textContent='카메라 확인 필요';status.textContent=d.message||''}
 else{tag.textContent='물체 탐색 중';tag.style.background='#646d79';result.textContent='물건을 카메라 앞에 놓아주세요';status.textContent=d.message||'';meta.textContent='';ctx.clearRect(0,0,canvas.width,canvas.height)}}
async function loop(){try{const r=await fetch('/classify-next',{method:'POST'}),d=await r.json();handle(d)}catch(e){document.getElementById('status').textContent='서버 연결 대기 중: '+e.message}setTimeout(loop,250)}loop();
</script></body></html>"""


class LiveService:
    def __init__(self, camera: LazyCamera):
        self.camera = camera
        self.lock = threading.Lock()
        self.latest_frame = None
        self.camera_error = "카메라 연결 대기 중"
        self.detector = None
        self.embedder = None
        self.classifier = None
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while True:
            try:
                data = self.camera.preview()
                frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError("JPEG 디코딩 실패")
                with self.lock:
                    self.latest_frame, self.camera_error = frame, ""
                time.sleep(0.15)
            except Exception as error:  # noqa: BLE001
                with self.lock:
                    self.camera_error = str(error)
                time.sleep(0.7)

    def frame(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy(), None
            return None, self.camera_error

    def ensure_models(self):
        if self.detector is None:
            print("YOLO-World·DINOv2·분류기 준비 중...")
            from ultralytics import YOLOWorld

            WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
            self.detector = YOLOWorld(str(YOLO_WEIGHTS))
            self.detector.set_classes(PROMPTS)
            self.embedder = DinoV2Embedder()
            self.classifier = joblib.load(MODEL_PATH)["classifier"]
            print("준비 완료")

    @staticmethod
    def _valid(frame, box) -> bool:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0:
            return False
        area = bw * bh / float(width * height)
        return 0.015 <= area <= 0.85 and bw / width < 0.97 and bh / height < 0.97

    def classify(self) -> dict:
        frame, error = self.frame()
        if frame is None:
            return {"status": "no_camera", "message": error}
        self.ensure_models()
        result = self.detector.predict(frame, conf=0.02, imgsz=320, max_det=4,
                                        agnostic_nms=True, verbose=False)[0]
        candidates = []
        for box, confidence, class_id in zip(result.boxes.xyxy, result.boxes.conf, result.boxes.cls):
            coords = tuple(int(round(float(v))) for v in box)
            if self._valid(frame, coords):
                candidates.append((coords, float(confidence), self.detector.names[int(class_id)]))
        if not candidates:
            return {"status": "no_detection", "message": "화면에서 물체를 못 찾았습니다."}
        box, detection_confidence, prompt = max(candidates, key=lambda item: item[1])
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        vector = self.embedder.extract_pil_images([pil])[0]
        probabilities = self.classifier.predict_proba([vector])[0]
        index = int(probabilities.argmax())
        label = str(self.classifier.classes_[index])
        return {
            "status": "ok", "label": label, "label_ko": KOREAN_LABELS[label],
            "confidence": float(probabilities[index]), "detection_confidence": detection_confidence,
            "prompt": prompt, "box": list(box), "width": frame.shape[1], "height": frame.shape[0],
        }


def create_app(service: LiveService) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/camera.jpg")
    def camera_jpg():
        frame, error = service.frame()
        if frame is None:
            return Response(error or "카메라 없음", status=502)
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return Response("JPEG 인코딩 실패", status=500)
        return Response(encoded.tobytes(), mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/classify-next")
    def classify_next():
        try:
            return jsonify(service.classify())
        except Exception as error:  # noqa: BLE001
            return jsonify({"status": "error", "message": str(error)}), 500

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp-host", default="192.168.4.1", help="카메라 IP/호스트명 (기본 FridgeCam AP)")
    parser.add_argument("--port", type=int, default=8611, help="이 웹서버 포트")
    args = parser.parse_args()

    camera = LazyCamera(args.esp_host)
    service = LiveService(camera)
    print(f"서버 시작. http://localhost:{args.port} 접속")
    app = create_app(service)
    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
