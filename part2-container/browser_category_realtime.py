"""학습에 없던 물건을 텀블러/반찬 용기로 실시간 분류하는 시험 프로그램."""

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
LOG_PATH = ROOT / "category_realtime_log.csv"
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
<meta name="viewport" content="width=device-width,initial-scale=1"><title>용기 종류 실시간 분류</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f1216;color:#eee;text-align:center;margin:0;padding:16px}h2{margin:4px}.sub{color:#adb6c2;font-size:13px;margin:8px 0 14px}
#wrap{position:relative;display:inline-block;width:min(92vw,480px)}#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tag{position:absolute;left:0;top:0;padding:8px 13px;border-radius:12px 0 10px 0;background:#596270;font-weight:bold;font-size:18px}.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:15px}
#result{font-size:28px;font-weight:bold;min-height:36px}#status{color:#bdc5d0;font-size:14px;line-height:1.5;margin-top:8px}#meta{font-size:13px;color:#9da7b4;margin-top:8px}
#notice{display:none;position:fixed;z-index:20;left:50%;top:10%;transform:translateX(-50%);width:min(88vw,540px);padding:20px;border-radius:14px;background:#23a866;color:#fff;font-size:25px;font-weight:bold;box-shadow:0 8px 30px #000a}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#36d67e;margin-right:7px;box-shadow:0 0 9px #36d67e}.tip{color:#ffd38a;font-size:13px}
</style></head><body><div id="notice"></div><h2>🧊 용기 종류 실시간 분류</h2><div class="sub"><span class="dot"></span>버튼 없이 텀블러·반찬 용기를 계속 확인 중</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas><div id="tag">카메라 대기</div></div>
<div class="panel"><div id="result">새 물건을 보여주세요</div><div id="status">첫 분석은 AI 모델 준비 때문에 오래 걸릴 수 있습니다.</div><div id="meta"></div></div>
<div class="panel tip">학습 사진에 없던 새로운 텀블러와 반찬 용기로 시험하세요.<br>최근 5번 중 같은 종류가 3번 나오면 확정합니다.</div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');let history=[],confirmed=null,misses=0;
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),350);
function draw(d){const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);if(!d.box)return;const [x1,y1,x2,y2]=d.box;ctx.strokeStyle='#38e58f';ctx.lineWidth=4;ctx.strokeRect(x1*r.width/d.width,y1*r.height/d.height,(x2-x1)*r.width/d.width,(y2-y1)*r.height/d.height)}
function notify(text){const n=document.getElementById('notice');n.textContent=text;n.style.display='block';clearTimeout(window.nt);window.nt=setTimeout(()=>n.style.display='none',3500)}
function handle(d){const result=document.getElementById('result'),status=document.getElementById('status'),tag=document.getElementById('tag'),meta=document.getElementById('meta');
 if(d.status==='ok'){misses=0;history.push(d.label);if(history.length>5)history.shift();const count=history.filter(x=>x===d.label).length;draw(d);tag.textContent=`확인 중 ${d.label_ko} (${count}/3)`;tag.style.background='#3478f6';meta.textContent=`종류 확률 ${(d.confidence*100).toFixed(0)}% · YOLO ${(d.detection_confidence*100).toFixed(0)}%`;
  if(count>=3){result.textContent=`${d.label_ko} 인식 성공!`;status.textContent='여러 화면에서 같은 종류로 확인했습니다.';tag.textContent=d.label_ko;tag.style.background='#23a866';if(confirmed!==d.label){confirmed=d.label;notify(`${d.label_ko} 인식 성공!`)}}else{result.textContent='종류 확인 중...';status.textContent='같은 결과가 반복되는지 확인하고 있습니다.'}
 }else{misses++;history.push(null);if(history.length>5)history.shift();tag.textContent='물체 탐색 중';tag.style.background='#646d79';status.textContent=d.message||'다음 화면을 계속 확인합니다.';if(misses>=5){confirmed=null;result.textContent='새 물건을 보여주세요';meta.textContent='';ctx.clearRect(0,0,canvas.width,canvas.height)}}}
async function loop(){try{const r=await fetch('/classify-next',{method:'POST'}),d=await r.json();handle(d)}catch(e){document.getElementById('status').textContent='카메라 연결 대기 중: '+e.message}setTimeout(loop,180)}loop();
</script></body></html>"""


class CategoryRealtimeService:
    def __init__(self, address: str, model_path: Path, log_path: Path):
        self.camera_url = make_jpg_url(address)
        self.model_path, self.log_path = model_path, log_path
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

    def detect(self, frame):
        result = self.detector.predict(frame, conf=0.02, imgsz=320, max_det=4,
                                       agnostic_nms=True, verbose=False)[0]
        candidates=[]
        for box, confidence, class_id in zip(result.boxes.xyxy,result.boxes.conf,result.boxes.cls):
            coords=tuple(int(round(float(v))) for v in box)
            if self._valid_detection(frame,coords):
                x1,y1,x2,y2=coords
                candidates.append(ContainerDetection(coords,float(confidence),
                                  self.detector.names[int(class_id)],frame[y1:y2,x1:x2].copy()))
        return max(candidates,key=lambda item:item.confidence) if candidates else None

    def append_log(self, result):
        header=not self.log_path.exists() or self.log_path.stat().st_size==0
        with self.log_path.open('a',newline='',encoding='utf-8-sig') as handle:
            writer=csv.writer(handle)
            if header: writer.writerow(['timestamp','label','confidence','yolo_confidence','prompt'])
            writer.writerow([datetime.now().astimezone().isoformat(timespec='milliseconds'),
                             result['label'],f"{result['confidence']:.6f}",
                             f"{result['detection_confidence']:.6f}",result['prompt']])

    def classify(self):
        with self.analysis_lock:
            self.models(); frame=self.frame(); detection=self.detect(frame)
            if detection is None: raise ValueError("현재 화면에서 용기를 찾지 못했습니다.")
            pil=Image.fromarray(cv2.cvtColor(detection.crop,cv2.COLOR_BGR2RGB))
            vector=self.embedder.extract_pil_images([pil])[0]
            classifier=self.classifier_bundle['classifier']; probabilities=classifier.predict_proba([vector])[0]
            index=int(probabilities.argmax()); label=str(classifier.classes_[index])
            result={'status':'ok','label':label,'label_ko':KOREAN_LABELS[label],
                    'confidence':float(probabilities[index]),'detection_confidence':detection.confidence,
                    'prompt':detection.prompt,'box':list(detection.box),'width':frame.shape[1],'height':frame.shape[0]}
            self.append_log(result); return result


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
    parser=argparse.ArgumentParser(description='텀블러·반찬 용기 실시간 종류 분류')
    parser.add_argument('address',nargs='?',default='192.168.4.1');parser.add_argument('--model',type=Path,default=MODEL_PATH)
    parser.add_argument('--log',type=Path,default=LOG_PATH);parser.add_argument('--port',type=int,default=5003)
    args=parser.parse_args();service=CategoryRealtimeService(args.address,args.model,args.log)
    print('종류 분류 서버가 ESP32 카메라 연결을 기다립니다.');print(f'브라우저 주소: http://127.0.0.1:{args.port}')
    create_app(service).run(host='127.0.0.1',port=args.port,threaded=True,debug=False)


if __name__=='__main__': main()
