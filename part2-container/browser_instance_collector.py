"""냉장고 내부 실사용 용기를 물건 단위(개별 인스턴스)로 라벨링해 수집하는 데이터 수집기.

browser_category_collector.py를 기반으로, 라벨 히스토리(이미 쓴 라벨을 버튼으로 바로
재선택)와 물건별 저장 개수 표시를 추가해서 "텀블러_스텐360", "용기_락앤락사각" 같은
개별 물건 라벨을 반복 촬영하기 편하게 만들었다. 한 번에 물건 하나만 넣고 찍는 것을 전제로 한다.
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
DEFAULT_OUTPUT = ROOT / "instance_dataset_raw"

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>용기 개별 물건 라벨링 수집기</title>
<style>
*{box-sizing:border-box}body{font-family:Arial,sans-serif;background:#101319;color:#eee;text-align:center;margin:0;padding:16px}
h2{margin:5px}.sub{color:#aeb7c3;font-size:14px;margin:7px 0 14px}#cam{width:min(92vw,520px);aspect-ratio:1/1;object-fit:cover;border-radius:14px;background:#222}
.panel{width:min(92vw,520px);margin:12px auto;background:#1b212b;border-radius:13px;padding:14px;text-align:left}.row{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
input,button{font-size:17px;padding:11px 14px;border:0;border-radius:9px}input{width:100%;margin:8px 0;background:#f4f6f8;color:#111}
button{background:#3478f6;color:white;font-weight:bold;cursor:pointer}button.burst{background:#21a468}button:disabled{opacity:.45}
#status{min-height:24px;color:#cbd2dc;margin-top:10px;text-align:center}.count{font-size:22px;font-weight:bold}.tip{font-size:13px;color:#ffd18b;line-height:1.5}
#history{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}#history button{background:#2a3341;font-size:13px;padding:7px 10px;font-weight:normal}
#labelStats{font-size:13px;color:#cbd2dc;line-height:1.6;max-height:160px;overflow-y:auto}
</style></head><body><h2>🏷️ 용기 개별 물건 라벨링 수집기</h2>
<div class="sub">물건을 <b>하나씩만</b> 넣고, 물건마다 고유한 라벨로 30~50장씩 찍으세요.</div>
<img id="cam" src="/camera.jpg"><div class="panel">
<input id="label" placeholder="예: 텀블러_스텐360, 용기_락앤락사각">
<div id="history"></div>
<div class="row"><button onclick="capture(1)">1장 저장</button><button class="burst" onclick="capture(30)">30장 연속 저장</button><button class="burst" onclick="capture(50)">50장 연속 저장</button></div>
<div id="status">라벨을 정한 뒤 물건을 천천히 돌리면서 연속 저장하세요.</div></div>
<div class="panel"><div class="count"><span id="total">0</span>장 저장됨</div><div id="folder" style="font-size:12px;color:#8a93a0;margin:4px 0 10px"></div><div id="labelStats"></div></div>
<div class="panel tip">같은 물건은 항상 같은 라벨을 쓰세요(오타/띄어쓰기까지 동일해야 같은 물건으로 인식됨).<br>회전·선반 위치를 바꿔가며, 다른 용기와 같이 놓인 사진도 몇 장 섞으면 좋습니다.<br>새 물건으로 바꿀 때는 반드시 라벨도 바꾸세요.</div>
<script>
const cam=document.getElementById('cam'),statusEl=document.getElementById('status'),labelEl=document.getElementById('label');
setInterval(()=>cam.src='/camera.jpg?t='+Date.now(),450);
function pick(label){labelEl.value=label}
async function refresh(){
 const r=await fetch('/stats'),d=await r.json();
 document.getElementById('total').textContent=d.total;
 document.getElementById('folder').textContent=d.folder;
 document.getElementById('history').innerHTML=d.labels.map(l=>`<button onclick="pick('${l.label.replace(/'/g,"\\'")}')">${l.label} (${l.count})</button>`).join('');
 document.getElementById('labelStats').innerHTML=d.labels.length?('라벨별 저장 수: '+d.labels.map(l=>`${l.label}=${l.count}`).join(', ')):'아직 저장된 사진 없음';
}
async function capture(count){const label=labelEl.value.trim();if(!label){alert('라벨을 입력하세요');return}document.querySelectorAll('button').forEach(b=>b.disabled=true);statusEl.textContent=`${count}장 저장 중... 물건을 천천히 돌려주세요.`;
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
                    frame = cv2.flip(fetch_jpg(self.camera_url), 0)
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

    def label_counts(self) -> list[dict]:
        counts = Counter()
        for path in self.output.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}:
                counts[path.parent.name] += 1
        return [
            {"label": label, "count": count}
            for label, count in sorted(counts.items(), key=lambda kv: kv[0].lower())
        ]

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
            frame = cv2.flip(fetch_jpg(collector.camera_url), 0)
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
        return jsonify(total=collector.total(), folder=str(collector.output), labels=collector.label_counts())

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="냉장고 내부 용기 개별 물건 라벨링 수집기")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=5006)
    args = parser.parse_args()
    collector = Collector(args.address, args.output)
    print(f"카메라: {collector.camera_url}")
    print(f"저장 폴더: {collector.output}")
    print(f"브라우저 주소: http://127.0.0.1:{args.port}")
    create_app(collector).run(host="127.0.0.1", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
