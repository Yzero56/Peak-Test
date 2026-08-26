"""학습에 없던 물건 여러 개를 동시에 텀블러/반찬 용기/생수병으로 실시간 분류하는 시험 프로그램.

browser_category_realtime.py(단일 물체 버전)를 복사해 다중 물체를 지원하도록 수정함.
원본은 그대로 보존."""

from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import joblib
from flask import Flask, Response, jsonify, render_template_string
from PIL import Image
from ultralytics import YOLOWorld

from container_detector import DEFAULT_MODEL, ContainerDetection
from container_registry import DinoV2Embedder
from live_container_recognition import fetch_jpg, make_jpg_url

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "category_classifier.joblib"
LOG_PATH = ROOT / "category_realtime_multi_log.csv"
MAX_OBJECTS = 6
PROMPTS = [
    "food storage container", "plastic food container", "lunch box", "plastic box",
    "tumbler", "travel mug", "coffee mug", "drinking cup", "water bottle",
]
KOREAN_LABELS = {
    "drink_container": "텀블러",
    "food_container": "반찬 용기",
    "water_bottle": "생수병",
}

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>용기 종류 실시간 다중 분류</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f1216;color:#eee;text-align:center;margin:0;padding:16px}h2{margin:4px}.sub{color:#adb6c2;font-size:13px;margin:8px 0 14px}
#wrap{position:relative;display:inline-block;width:min(92vw,480px)}#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:15px}
#status{color:#bdc5d0;font-size:14px;line-height:1.5}#list{margin-top:10px;text-align:left}
#list div{padding:8px 10px;margin:6px 0;border-radius:8px;background:#262d38;font-size:15px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#36d67e;margin-right:7px;box-shadow:0 0 9px #36d67e}.tip{color:#ffd38a;font-size:13px}
</style></head><body><h2>🧊 용기 종류 실시간 다중 분류</h2><div class="sub"><span class="dot"></span>화면에 보이는 물체를 전부 동시에 확인 중</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas></div>
<div class="panel"><div id="status">첫 분석은 AI 모델 준비 때문에 오래 걸릴 수 있습니다.</div><div id="list"></div></div>
<div class="panel tip">학습 사진에 없던 새로운 텀블러·반찬 용기·생수병을 여러 개 동시에 보여주세요.<br>매 화면마다 찾은 물체를 전부 각각 표시합니다(프레임 간 안정화는 하지 않음).</div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),350);
function draw(d){
 const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);
 if(!d.objects)return;
 const sx=r.width/d.width, sy=r.height/d.height;
 d.objects.forEach(o=>{
  const [x1,y1,x2,y2]=o.box, bx=x1*sx, by=y1*sy, bw=(x2-x1)*sx, bh=(y2-y1)*sy;
  ctx.strokeStyle='#38e58f';ctx.lineWidth=3;ctx.strokeRect(bx,by,bw,bh);
  const text=`${o.label_ko} ${(o.confidence*100).toFixed(0)}%`;
  ctx.font='bold 15px Arial';const tw=ctx.measureText(text).width+10;
  ctx.fillStyle='#38e58f';ctx.fillRect(bx,Math.max(0,by-20),tw,20);
  ctx.fillStyle='#0f1216';ctx.fillText(text,bx+5,Math.max(14,by-6));
 });
}
function handle(d){
 const status=document.getElementById('status'),list=document.getElementById('list');
 if(d.status==='ok'){
  draw(d);
  status.textContent=`이번 화면에서 물체 ${d.objects.length}개 인식`;
  list.innerHTML=d.objects.map(o=>`<div>${o.label_ko} — 종류 확률 ${(o.confidence*100).toFixed(0)}% · YOLO ${(o.detection_confidence*100).toFixed(0)}%</div>`).join('');
 }else{
  ctx.clearRect(0,0,canvas.width,canvas.height);list.innerHTML='';
  status.textContent=d.message||'물체를 찾지 못했습니다.';
 }
}
async function loop(){try{const r=await fetch('/classify-next',{method:'POST'}),d=await r.json();handle(d)}catch(e){document.getElementById('status').textContent='카메라 연결 대기 중: '+e.message}setTimeout(loop,220)}loop();
</script></body></html>"""


class CategoryRealtimeMultiService:
    def __init__(self, address: str, model_path: Path, log_path: Path, max_objects: int = MAX_OBJECTS):
        self.camera_url = make_jpg_url(address)
        self.model_path, self.log_path = model_path, log_path
        self.max_objects = max_objects
        self.frame_lock, self.analysis_lock = threading.Lock(), threading.Lock()
        self.latest_frame = None; self.camera_error = "카메라 연결 대기 중"
        self.detector = self.embedder = self.classifier_bundle = None
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
        raise ConnectionError(f"ESP32 최신 사진이 없습니다: {error}")

    def models(self):
        if self.detector is None:
            print("YOLO·DINOv2·종류 분류 모델 준비 중...")
            self.detector = YOLOWorld(str(DEFAULT_MODEL)); self.detector.set_classes(PROMPTS)
            self.embedder = DinoV2Embedder(); self.classifier_bundle = joblib.load(self.model_path)
            print("종류 분류 모델 준비 완료")

    @staticmethod
    def _valid_detection(frame, box):
        height, width = frame.shape[:2]; x1, y1, x2, y2 = box
        bw, bh = x2-x1, y2-y1; area = bw*bh/float(width*height)
        return bw>0 and bh>0 and 0.015<=area<=0.85 and bw/width<0.97 and bh/height<0.97

    def detect_all(self, frame):
        result = self.detector.predict(frame, conf=0.02, imgsz=320, max_det=self.max_objects,
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

    def append_log(self, objects):
        header=not self.log_path.exists() or self.log_path.stat().st_size==0
        with self.log_path.open('a',newline='',encoding='utf-8-sig') as handle:
            writer=csv.writer(handle)
            if header: writer.writerow(['timestamp','object_index','object_count','label','confidence','yolo_confidence','prompt'])
            stamp=datetime.now().astimezone().isoformat(timespec='milliseconds')
            for index, obj in enumerate(objects, start=1):
                writer.writerow([stamp,index,len(objects),obj['label'],f"{obj['confidence']:.6f}",
                                 f"{obj['detection_confidence']:.6f}",obj['prompt']])

    def classify(self):
        with self.analysis_lock:
            self.models(); frame=self.frame(); detections=self.detect_all(frame)
            if not detections: raise ValueError("현재 화면에서 용기를 찾지 못했습니다.")
            crops=[Image.fromarray(cv2.cvtColor(detection.crop,cv2.COLOR_BGR2RGB)) for detection in detections]
            vectors=self.embedder.extract_pil_images(crops)
            classifier=self.classifier_bundle['classifier']
            objects=[]
            for detection, vector in zip(detections, vectors):
                probabilities=classifier.predict_proba([vector])[0]
                index=int(probabilities.argmax()); label=str(classifier.classes_[index])
                objects.append({'label':label,'label_ko':KOREAN_LABELS[label],
                                'confidence':float(probabilities[index]),
                                'detection_confidence':detection.confidence,
                                'prompt':detection.prompt,'box':list(detection.box)})
            self.append_log(objects)
            return {'status':'ok','objects':objects,'width':frame.shape[1],'height':frame.shape[0]}


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
    parser=argparse.ArgumentParser(description='텀블러·반찬 용기·생수병 실시간 다중 물체 종류 분류')
    parser.add_argument('address',nargs='?',default='192.168.4.1');parser.add_argument('--model',type=Path,default=MODEL_PATH)
    parser.add_argument('--log',type=Path,default=LOG_PATH);parser.add_argument('--port',type=int,default=5005)
    parser.add_argument('--max-objects',type=int,default=MAX_OBJECTS)
    args=parser.parse_args();service=CategoryRealtimeMultiService(args.address,args.model,args.log,args.max_objects)
    print('다중 물체 종류 분류 서버가 ESP32 카메라 연결을 기다립니다.');print(f'브라우저 주소: http://127.0.0.1:{args.port}')
    create_app(service).run(host='127.0.0.1',port=args.port,threaded=True,debug=False)


if __name__=='__main__': main()
