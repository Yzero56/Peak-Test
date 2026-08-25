"""2차 DB를 그대로 사용하는 버튼 없는 실시간 용기 인식 시험 프로그램."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template_string

from browser_container_recognition_v2 import RecognitionServiceV2
from container_registry_v2 import DEFAULT_THRESHOLD_V2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>실시간 용기 자동 인식</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f1216;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:4px}.sub{color:#aeb5c0;font-size:13px;margin:8px 0 14px}#wrap{position:relative;display:inline-block;width:min(92vw,480px)}
#cam{width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222;display:block}#overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#tag{position:absolute;left:0;top:0;padding:8px 13px;border-radius:12px 0 10px 0;background:#56606f;font-weight:bold;font-size:18px}
.panel{width:min(92vw,480px);margin:12px auto;background:#1b2028;border-radius:12px;padding:14px}#result{font-size:24px;font-weight:bold;min-height:32px}
#status{color:#bdc5d0;font-size:14px;line-height:1.5;margin-top:8px}.meta{font-size:13px;color:#9da7b4;margin-top:8px}
#notice{display:none;position:fixed;z-index:20;left:50%;top:10%;transform:translateX(-50%);width:min(88vw,540px);padding:20px;border-radius:14px;background:#23a866;color:#fff;font-size:24px;font-weight:bold;box-shadow:0 8px 30px #000a}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#36d67e;margin-right:7px;box-shadow:0 0 9px #36d67e}.tip{color:#ffd38a;font-size:13px}
</style></head><body><div id="notice"></div><h2>🧊 실시간 용기 자동 인식</h2>
<div class="sub"><span class="dot"></span>버튼 없이 AI가 계속 확인 중</div>
<div id="wrap"><img id="cam" src="/camera.jpg"><canvas id="overlay"></canvas><div id="tag">카메라 대기</div></div>
<div class="panel"><div id="result">용기를 보여주세요</div><div id="status">AI 모델을 준비하고 있습니다. 첫 결과는 오래 걸릴 수 있습니다.</div><div id="meta" class="meta"></div></div>
<div class="panel tip">최근 분석에서 같은 용기가 3번 확인되면 인식을 확정합니다.<br>한두 번 용기를 놓쳐도 다음 화면에서 계속 확인합니다.</div>
<script>
const cam=document.getElementById('cam'),canvas=document.getElementById('overlay'),ctx=canvas.getContext('2d');
let history=[],confirmed=null,misses=0,running=true;
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),350);
function draw(item,w,h,color){const r=cam.getBoundingClientRect();canvas.width=r.width;canvas.height=r.height;ctx.clearRect(0,0,r.width,r.height);if(!item||!item.box)return;const [x1,y1,x2,y2]=item.box;ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(x1*r.width/w,y1*r.height/h,(x2-x1)*r.width/w,(y2-y1)*r.height/h)}
function notify(text){const n=document.getElementById('notice');n.textContent=text;n.style.display='block';clearTimeout(window.nt);window.nt=setTimeout(()=>n.style.display='none',3500)}
function handle(d){const result=document.getElementById('result'),status=document.getElementById('status'),tag=document.getElementById('tag'),meta=document.getElementById('meta');
  if(d.status==='matched'){
    misses=0;history.push(d.container_id);if(history.length>5)history.shift();const count=history.filter(x=>x===d.container_id).length;
    draw(d,d.width,d.height,'#38e58f');tag.textContent=`확인 중 ${d.container_id} (${count}/3)`;tag.style.background='#3478f6';
    meta.textContent=`종합 ${(d.similarity*100).toFixed(0)}% · 외형 ${(d.dino_similarity*100).toFixed(0)}% · 색상 ${(d.color_similarity*100).toFixed(0)}% · YOLO ${(d.detection_confidence*100).toFixed(0)}%`;
    if(count>=3){result.textContent=`${d.container_id} 용기 인식 성공!`;status.textContent='여러 화면에서 같은 용기로 확인했습니다.';tag.textContent='MATCH '+d.container_id;tag.style.background='#23a866';if(confirmed!==d.container_id){confirmed=d.container_id;notify(`${d.container_id} 용기 인식 성공!`)}}
    else{result.textContent='용기 확인 중...';status.textContent='같은 ID가 반복되는지 계속 확인합니다.'}
  }else{
    misses++;history.push(null);if(history.length>5)history.shift();draw(null,1,1,'');
    tag.textContent=d.status==='unknown'?'등록 용기와 비교 중':'용기 탐색 중';tag.style.background='#646d79';
    status.textContent=d.message||'현재 화면에서는 확정하지 못했지만 다음 화면을 계속 확인합니다.';
    if(misses>=5){confirmed=null;result.textContent='용기를 보여주세요';meta.textContent=''}
  }
}
async function loop(){if(!running)return;try{const r=await fetch('/recognize-next',{method:'POST'}),d=await r.json();handle(d)}catch(e){document.getElementById('status').textContent='카메라 연결을 기다리는 중: '+e.message}setTimeout(loop,180)}
loop();
</script></body></html>"""


def create_app(service: RecognitionServiceV2):
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

    @app.post("/recognize-next")
    def recognize_next():
        started = time.perf_counter()
        try:
            result, frame = service.recognize()
            result.update(width=frame.shape[1], height=frame.shape[0],
                          elapsed_seconds=round(time.perf_counter() - started, 2))
            return jsonify(result)
        except ValueError as error:
            return jsonify(status="no_detection", message=str(error),
                           elapsed_seconds=round(time.perf_counter() - started, 2))
        except Exception as error:
            return jsonify(status="camera_error", message=str(error)), 503

    return app


def main():
    parser = argparse.ArgumentParser(description="버튼 없는 실시간 용기 자동 인식")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--db", type=Path, default=ROOT / "containers_v2_improved.db")
    parser.add_argument("--log", type=Path, default=ROOT / "realtime_recognition_log.csv")
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD_V2)
    parser.add_argument("--port", type=int, default=5002)
    args = parser.parse_args()
    service = RecognitionServiceV2(args.address, args.db, args.log, args.identity_threshold)
    print("실시간 인식 프로그램이 ESP32 카메라 연결을 기다립니다.")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(service).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()

