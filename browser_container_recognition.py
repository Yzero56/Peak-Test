"""AP 카메라 영상과 YOLO·DINOv2 결과를 한 브라우저 페이지에 표시한다."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template_string

from container_detector import ContainerDetector
from container_pipeline import analyze_frame
from container_registry import DEFAULT_DB, DEFAULT_THRESHOLD, ContainerDatabase, DinoV2Embedder
from live_container_recognition import fetch_jpg, make_jpg_url


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PAGE = r"""
<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>냉장고 용기 실시간 인식</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#111;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:4px 0 14px}.sub{color:#999;font-size:13px;margin-bottom:12px}
#wrap{position:relative;display:inline-block;width:min(92vw,480px)}
#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:10px;display:block;background:#222}
#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tag{position:absolute;left:0;top:0;background:#4c8bf5;color:#fff;font-weight:bold;padding:6px 12px;border-radius:10px 0 10px 0;font-size:17px}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b1b1b;border-radius:10px;padding:12px}
.bar{display:flex;align-items:center;margin:7px 0;font-size:14px}.bar span{width:120px;text-align:right;padding-right:9px}
.track{flex:1;background:#333;border-radius:5px;height:18px;overflow:hidden}.fill{height:100%;width:0%;background:#4c8bf5;transition:width .3s}
.bar b{width:52px;text-align:left;padding-left:7px}button{border:0;border-radius:8px;padding:12px 22px;background:#4c8bf5;color:white;font-weight:bold;font-size:16px;cursor:pointer}
button:disabled{background:#555;cursor:wait}#status{color:#aaa;font-size:13px;margin-top:10px;min-height:18px}
#list{text-align:left;font-size:14px;line-height:1.7}.new{color:#f5a64c}.matched{color:#4cf58b}
</style></head><body>
<h2>🔍 냉장고 용기 실시간 인식</h2>
<div class="sub">ESP32 AP 카메라 + YOLO 위치 탐지 + DINOv2 재식별</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas><div id="tag">분석 대기</div></div>
<div class="panel">
  <button id="analyze" onclick="analyzeNow()">현재 용기 분석</button>
  <div id="status">용기를 화면에 놓고 버튼을 누르세요.</div>
</div>
<div class="panel" id="bars">
  <div class="bar"><span>용기 탐지 확률</span><div class="track"><div id="detectFill" class="fill"></div></div><b id="detectValue">-</b></div>
  <div class="bar"><span>기존 용기 유사도</span><div class="track"><div id="similarFill" class="fill" style="background:#4cf58b"></div></div><b id="similarValue">-</b></div>
</div>
<div class="panel"><b>등록된 용기</b><div id="list">아직 없음</div></div>
<script>
const cam=document.getElementById('cam'), canvas=document.getElementById('overlay'), ctx=canvas.getContext('2d');
let busy=false;
setInterval(()=>{if(!busy)cam.src='/camera.jpg?t='+Date.now()},500);
function drawBoxes(items,w,h){
  const rect=cam.getBoundingClientRect(); canvas.width=rect.width; canvas.height=rect.height; ctx.clearRect(0,0,canvas.width,canvas.height);
  const sx=canvas.width/w, sy=canvas.height/h;
  for(const item of items){const [x1,y1,x2,y2]=item.box; const color=item.status==='matched'?'#4cf58b':'#f5a64c';
    ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(x1*sx,y1*sy,(x2-x1)*sx,(y2-y1)*sy);}
}
function setBar(prefix,value,color){const pct=Math.max(0,Math.min(100,value*100));document.getElementById(prefix+'Fill').style.width=pct.toFixed(0)+'%';
  document.getElementById(prefix+'Fill').style.background=color;document.getElementById(prefix+'Value').textContent=pct.toFixed(0)+'%';}
async function analyzeNow(){
  const btn=document.getElementById('analyze');busy=true;btn.disabled=true;btn.textContent='AI 분석 중...';document.getElementById('status').textContent='첫 분석은 모델 준비 때문에 시간이 걸릴 수 있습니다.';
  try{const r=await fetch('/analyze',{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'분석 실패');
    if(!d.results.length){document.getElementById('tag').textContent='용기 없음';document.getElementById('status').textContent='용기를 찾지 못했습니다.';drawBoxes([],d.width,d.height);}
    else{const top=d.results[0],isNew=top.status==='registered';const tag=document.getElementById('tag');tag.textContent=(isNew?'NEW ':'MATCH ')+top.container_id;
      tag.style.background=isNew?'#f5a64c':'#31b86b';setBar('detect',top.detection_confidence,'#4c8bf5');
      setBar('similar',top.identity_similarity===null?0:top.identity_similarity,'#4cf58b');document.getElementById('similarValue').textContent=top.identity_similarity===null?'신규':(top.identity_similarity*100).toFixed(0)+'%';
      document.getElementById('status').textContent=isNew?'처음 본 용기로 새로 등록했습니다.':'전에 본 용기로 인식했습니다.';drawBoxes(d.results,d.width,d.height);}
    updateList(d.containers);
  }catch(e){document.getElementById('status').textContent=e.message;}
  finally{busy=false;btn.disabled=false;btn.textContent='현재 용기 분석';cam.src='/camera.jpg?t='+Date.now();}
}
function updateList(items){document.getElementById('list').innerHTML=items.length?items.map(x=>`<div><b>${x.container_id}</b> · 내용물 ${x.content||'미입력'} · 확인 ${x.observation_count}회</div>`).join(''):'아직 없음';}
fetch('/containers').then(r=>r.json()).then(updateList).catch(()=>{});
</script></body></html>
"""


class RecognitionService:
    def __init__(self, camera_address: str, db_path: Path, threshold: float):
        self.camera_url = make_jpg_url(camera_address)
        self.db_path = db_path
        self.threshold = threshold
        self.camera_lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.latest_frame = None
        self.camera_error = "카메라 연결 대기 중"
        self.detector = None
        self.embedder = None
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        """ESP32에는 이 작업 하나만 접근하고 최신 사진을 노트북에 보관한다."""
        while True:
            try:
                frame = fetch_jpg(self.camera_url)
                with self.camera_lock:
                    self.latest_frame = frame
                    self.camera_error = ""
                time.sleep(0.15)
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
            self.detector = ContainerDetector()
            self.embedder = DinoV2Embedder()
            print("AI 모델 준비 완료")

    def containers(self):
        database = ContainerDatabase(self.db_path)
        try:
            return [dict(row) for row in database.list_containers()]
        finally:
            database.close()

    def analyze(self):
        with self.analysis_lock:
            self.models()
            frame = self.frame()
            database = ContainerDatabase(self.db_path)
            try:
                results, _ = analyze_frame(
                    frame, database, self.detector, self.embedder, self.threshold
                )
            finally:
                database.close()
            return results, frame.shape[1], frame.shape[0], self.containers()


def create_app(service: RecognitionService):
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(PAGE)

    @app.get("/camera.jpg")
    def camera_jpg():
        try:
            frame = service.frame()
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError("JPEG 변환 실패")
            return Response(encoded.tobytes(), mimetype="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception as error:
            return jsonify(error=str(error)), 503

    @app.post("/analyze")
    def analyze():
        started = time.perf_counter()
        try:
            results, width, height, containers = service.analyze()
            return jsonify(results=results, width=width, height=height,
                           containers=containers,
                           elapsed_seconds=round(time.perf_counter() - started, 2))
        except Exception as error:
            return jsonify(error=str(error)), 500

    @app.get("/containers")
    def containers():
        return jsonify(service.containers())

    return app


def main():
    parser = argparse.ArgumentParser(description="브라우저 기반 ESP32 용기 인식 화면")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    service = RecognitionService(args.address, args.db, args.identity_threshold)
    print("ESP32 카메라 연결 대기 중입니다. 보드 연결 후 ESP32-Camera Wi-Fi로 전환하세요.")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(service).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
