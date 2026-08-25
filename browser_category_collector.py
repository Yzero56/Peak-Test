"""ESP32의 기존 /jpg 카메라를 이용하는 노트북용 종류 분류 데이터 수집기."""

from __future__ import annotations

import argparse
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template_string, request

from live_container_recognition import fetch_jpg, make_jpg_url


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "category_collection_raw"

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>종류 분류 데이터 수집기</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#101319;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:5px}.sub{color:#aeb7c3;font-size:14px;margin:7px 0 14px}#cam{width:min(92vw,520px);aspect-ratio:1/1;object-fit:cover;border-radius:14px;background:#222}
.panel{width:min(92vw,520px);margin:12px auto;background:#1b212b;border-radius:13px;padding:14px}.row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
input,button{font-size:17px;padding:11px 14px;border:0;border-radius:9px}input{width:100%;margin:8px 0;background:#f4f6f8;color:#111}
button{background:#3478f6;color:white;font-weight:bold;cursor:pointer}button.food{background:#f08a36}button.burst{background:#21a468}button:disabled{opacity:.45}
#status{min-height:24px;color:#cbd2dc;margin-top:10px}.count{font-size:22px;font-weight:bold}.tip{font-size:13px;color:#ffd18b;line-height:1.5}
</style></head><body><h2>📷 텀블러·반찬 용기 데이터 수집</h2>
<div class="sub">보드는 카메라만 켜 두고, 사진은 이 노트북에 바로 저장합니다.</div>
<img id="cam" src="/camera.jpg"><div class="panel">
<div class="row"><button onclick="preset('텀블러')">텀블러</button><button class="food" onclick="preset('용기')">반찬 용기</button></div>
<input id="label" value="텀블러_새물건1" placeholder="예: 텀블러_새물건1 또는 용기_새물건2">
<div class="row"><button onclick="capture(1)">1장 저장</button><button class="burst" onclick="capture(20)">20장 연속 저장</button><button class="burst" onclick="capture(50)">50장 연속 저장</button></div>
<div id="status">라벨을 정한 뒤 물건을 천천히 돌리면서 연속 저장하세요.</div></div>
<div class="panel"><div class="count"><span id="total">0</span>장 저장됨</div><div id="folder"></div></div>
<div class="panel tip">같은 물건은 같은 라벨을 유지하세요. 다른 물건으로 바꾸면 새물건 번호도 바꾸세요.<br>여러 각도와 손 위치를 조금씩 바꾸면 학습에 도움이 됩니다.</div>
<script>
const cam=document.getElementById('cam'),statusEl=document.getElementById('status');
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),450);
function preset(kind){const old=document.getElementById('label').value;const m=old.match(/새물건\d+/);document.getElementById('label').value=kind+'_'+(m?m[0]:'새물건1')}
async function refresh(){const r=await fetch('/stats'),d=await r.json();document.getElementById('total').textContent=d.total;document.getElementById('folder').textContent=d.folder}
async function capture(count){const label=document.getElementById('label').value.trim();if(!label){alert('라벨을 입력하세요');return}document.querySelectorAll('button').forEach(b=>b.disabled=true);statusEl.textContent=`${count}장 저장 중... 물건을 천천히 돌려주세요.`;
 try{const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label,count})}),d=await r.json();if(!r.ok)throw Error(d.error);statusEl.textContent=`완료: ${d.label} 사진 ${d.saved}장 저장 (${d.failed}장 실패)`;await refresh()}catch(e){statusEl.textContent='오류: '+e.message}finally{document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
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
        label = label.rstrip(". ")
        if not label:
            raise ValueError("라벨을 입력하세요.")
        return label[:80]

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

    def total(self) -> int:
        return sum(1 for path in self.output.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"})


def create_app(collector: Collector) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(PAGE)

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
        return jsonify(total=collector.total(), folder=str(collector.output))

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="노트북용 텀블러·반찬 용기 사진 수집기")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=5004)
    args = parser.parse_args()
    collector = Collector(args.address, args.output)
    print(f"카메라: {collector.camera_url}")
    print(f"저장 폴더: {collector.output}")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(collector).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
