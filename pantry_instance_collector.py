"""주방 찬장에 설치해 하늘에서 수직으로 내려다보는 카메라로, 재료(양파/대파/당근/김치)를
물건 단위로 라벨링해 수집하는 데이터 수집기. 냉장고 용기 인식 프로그램과는 별개.

browser_instance_collector.py를 기반으로, 자유 입력 대신 라벨 버튼 클릭 방식으로 바꿨다.
"""

from __future__ import annotations

import argparse
import re
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template_string, request

from live_container_recognition import fetch_jpg, make_jpg_url

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "pantry_dataset_raw"
LABELS = ["양파", "대파", "당근", "김치"]

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>주방 재료 데이터 수집기</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#101319;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:5px}.sub{color:#aeb7c3;font-size:14px;margin:7px 0 14px}#cam{width:min(92vw,520px);aspect-ratio:1/1;object-fit:cover;border-radius:14px;background:#222}
.panel{width:min(92vw,520px);margin:12px auto;background:#1b212b;border-radius:13px;padding:14px;text-align:left}.row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
button{font-size:17px;padding:12px 16px;border:0;border-radius:9px;background:#2a3341;color:#eee;font-weight:bold;cursor:pointer}
button.active{background:#3478f6}button.burst{background:#21a468}button:disabled{opacity:.45}
#status{min-height:24px;color:#cbd2dc;margin-top:10px;text-align:center}.count{font-size:22px;font-weight:bold}.tip{font-size:13px;color:#ffd18b;line-height:1.5}
#labelStats{font-size:13px;color:#cbd2dc;line-height:1.6;margin-top:8px}
</style></head><body><h2>🥬 주방 재료 데이터 수집기</h2>
<div class="sub">라벨 버튼을 누른 뒤, 그 재료 하나만 넣고 촬영하세요.</div>
<img id="cam" src="/camera.jpg"><div class="panel">
<div class="row" id="labelRow"></div>
<div id="chosen" style="text-align:center;margin:10px 0;color:#8ee6a8;font-weight:bold">라벨을 선택하세요</div>
<div class="row"><button onclick="capture(1)">1장 저장</button><button class="burst" onclick="capture(30)">30장 연속 저장</button><button class="burst" onclick="capture(40)">40장 연속 저장</button></div>
<div id="status">라벨 선택 후 재료를 조금씩 돌려가며 연속 저장하세요.</div></div>
<div class="panel"><div class="count"><span id="total">0</span>장 저장됨</div><div id="labelStats"></div></div>
<div class="panel tip">회전(15~20도씩)과 용기 안 위치 이동을 섞어서 찍으면 좋습니다.<br>실제 시연에 쓸 용기·조명 그대로 촬영하세요.</div>
<script>
const LABELS = %%LABELS_JSON%%;
let current = LABELS[0];
const cam=document.getElementById('cam'),statusEl=document.getElementById('status'),chosen=document.getElementById('chosen'),row=document.getElementById('labelRow');
row.innerHTML = LABELS.map(l=>`<button id="btn-${l}" onclick="pick('${l}')">${l}</button>`).join('');
function pick(l){current=l;chosen.textContent=`선택됨: ${l}`;LABELS.forEach(x=>document.getElementById('btn-'+x).classList.toggle('active',x===l))}
pick(current);
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),450);
async function refresh(){const r=await fetch('/stats'),d=await r.json();document.getElementById('total').textContent=d.total;
 document.getElementById('labelStats').innerHTML='라벨별 저장 수: '+LABELS.map(l=>`${l}=${d.counts[l]||0}`).join(', ')}
async function capture(count){document.querySelectorAll('button').forEach(b=>b.disabled=true);statusEl.textContent=`${count}장 저장 중... 재료를 천천히 돌려주세요.`;
 try{const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:current,count})}),d=await r.json();if(!r.ok)throw Error(d.error);statusEl.textContent=`완료: ${d.label} 사진 ${d.saved}장 저장 (${d.failed}장 실패)`;await refresh()}catch(e){statusEl.textContent='오류: '+e.message}finally{document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
refresh();
</script></body></html>"""


class Collector:
    def __init__(self, address: str, output: Path):
        self.camera_url = make_jpg_url(address)
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    @staticmethod
    def clean_label(label: str) -> str:
        label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", label.strip())
        if label not in LABELS:
            raise ValueError(f"라벨은 {LABELS} 중 하나여야 합니다.")
        return label

    def capture(self, label: str, count: int) -> tuple[str, int, int]:
        label = self.clean_label(label)
        count = max(1, min(int(count), 100))
        folder = self.output / label
        folder.mkdir(parents=True, exist_ok=True)
        saved = failed = 0
        with self.lock:
            for index in range(count):
                try:
                    frame = fetch_jpg(self.camera_url)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    path = folder / f"{label}_{stamp}_{index + 1:03d}.jpg"
                    if not cv2.imwrite(str(path), frame):
                        raise OSError("파일 저장 실패")
                    saved += 1
                except Exception:
                    failed += 1
                if index + 1 < count:
                    time.sleep(0.25)
        return label, saved, failed

    def label_counts(self) -> dict:
        counts = Counter()
        for path in self.output.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}:
                counts[path.parent.name] += 1
        return dict(counts)

    def total(self) -> int:
        return sum(1 for path in self.output.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"})


def create_app(collector: Collector) -> Flask:
    app = Flask(__name__)
    page = PAGE.replace("%%LABELS_JSON%%", str(LABELS).replace("'", '"'))

    @app.get("/")
    def index():
        return render_template_string(page)

    @app.get("/camera.jpg")
    def camera():
        try:
            frame = fetch_jpg(collector.camera_url)
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                raise ValueError("JPEG 변환 실패")
            return Response(encoded.tobytes(), mimetype="image/jpeg", headers={"Cache-Control": "no-store"})
        except Exception as error:
            return jsonify(error=str(error)), 503

    @app.post("/capture")
    def capture():
        try:
            data = request.get_json(silent=True) or {}
            label, saved, failed = collector.capture(data.get("label", ""), data.get("count", 1))
            return jsonify(label=label, saved=saved, failed=failed, total=collector.total())
        except Exception as error:
            return jsonify(error=str(error)), 400

    @app.get("/stats")
    def stats():
        return jsonify(total=collector.total(), folder=str(collector.output), counts=collector.label_counts())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="주방 재료(양파/대파/당근/김치) 데이터 수집기")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=5008)
    args = parser.parse_args()
    collector = Collector(args.address, args.output)
    print(f"카메라: {collector.camera_url}")
    print(f"저장 폴더: {collector.output}")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(collector).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
