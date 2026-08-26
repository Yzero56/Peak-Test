"""
collect.py — 실제 냉장고에 이미 마운트된 카메라(webcam_ap_capture.ino, /capture
엔드포인트)로 용기 종류 분류(Wa 브랜치) 재검증용 라벨링된 시험 사진을 모은다.

문틀에 이미 붙어있는 보드를 그대로 쓴다(재검증 전용 보드 없음) — 문 열림 판정용
카메라와 같은 물리 카메라로 용기 사진도 찍는 것뿐이라 새 하드웨어가 필요 없다.

사용 전: 이 컴퓨터를 FridgeCam Wi-Fi(AP 모드, 비번 FridgeCamTest)에 연결해야 함
(STA 모드로 바꿨다면 --esp-host를 fridgecam.local 등으로).

실행:
  ./.venv/bin/python tools/category_eval/collect.py --esp-host 192.168.4.1

브라우저에서 http://localhost:8610 접속 → 실제 텀블러/반찬 용기/생수병을 냉장고
안 카메라 앞에 놓고 해당 라벨 버튼을 누르면 그 순간 사진이 저장된다. 새로 산
물건, 학습 때 안 보여준 물건 위주로 찍어야 "재검증"의 의미가 있다(같은 물건을
계속 찍으면 낙관적으로 나옴).

저장 위치: data/category_eval_captures/<label>/<timestamp>.jpg
정확도 계산은 이 스크립트가 아니라 evaluate.py에서 한다(YOLO/DINOv2 모델을 매번
새로 불러오는 무거운 작업이라 분리함).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web_capture"))
from http_cam import HttpCamera  # noqa: E402


class LazyCamera:
    """HttpCamera는 생성 시점에 바로 연결을 확인해서 실패하면 예외를 던진다.
    이 페이지는 웹서버부터 띄워두고 사용자가 나중에 FridgeCam Wi-Fi에 붙으면
    그때 재연결되길 원하므로, 매 요청마다 연결이 없으면 다시 시도하는
    래퍼로 감쌌다."""

    def __init__(self, host: str):
        self.host = host
        self._camera: HttpCamera | None = None

    def _ensure(self) -> HttpCamera:
        if self._camera is None:
            self._camera = HttpCamera(self.host)
        return self._camera

    def preview(self) -> bytes:
        try:
            return self._ensure().preview()
        except Exception:
            self._camera = None
            raise

    def capture(self, quality: str = "standard") -> bytes:
        try:
            return self._ensure().capture(quality)
        except Exception:
            self._camera = None
            raise

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "category_eval_captures"

LABELS = [
    ("drink_container", "텀블러"),
    ("food_container", "반찬 용기"),
    ("water_bottle", "생수병"),
]

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>용기 종류 재검증 사진 수집</title>
<style>
*{box-sizing:border-box}body{font-family:-apple-system,Arial,sans-serif;background:#0f1216;color:#eee;
text-align:center;margin:0;padding:16px}h2{margin:6px 0}.sub{color:#adb6c2;font-size:13px;margin:4px 0 16px}
#cam{width:min(92vw,480px);aspect-ratio:1/1;object-fit:cover;border-radius:12px;background:#222}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;max-width:480px;margin:16px auto}
button.label{padding:18px 6px;font-size:16px;font-weight:bold;border:none;border-radius:12px;
background:#23324a;color:#eee;cursor:pointer}
button.label:active{background:#3478f6}
.count{font-size:12px;color:#9da7b4;margin-top:6px}
#toast{display:none;position:fixed;left:50%;top:12%;transform:translateX(-50%);z-index:20;
padding:14px 22px;border-radius:12px;background:#23a866;color:#fff;font-weight:bold;box-shadow:0 8px 30px #000a}
#toast.err{background:#c0392b}
</style></head><body>
<h2>🧊 용기 종류 재검증 사진 수집</h2>
<div class="sub">학습 때 안 보여준 새 물건으로, 실제 냉장고 안 위치에서 찍으세요</div>
<img id="cam" src="/preview.jpg">
<div class="grid">
""" + "".join(
    f'<button class="label" onclick="capture(\'{key}\')">{ko}<div class="count" id="c-{key}">-</div></button>'
    for key, ko in LABELS
) + r"""
</div>
<div id="toast"></div>
<script>
const cam=document.getElementById('cam');
setInterval(()=>{cam.src='/preview.jpg?t='+Date.now()},700);
function toast(text,err){const t=document.getElementById('toast');t.textContent=text;t.className=err?'err':'';t.style.display='block';clearTimeout(window.tt);window.tt=setTimeout(()=>t.style.display='none',1800)}
async function refreshCounts(){try{const r=await fetch('/counts');const d=await r.json();for(const k in d)document.getElementById('c-'+k).textContent=d[k]+'장'}catch(e){}}
async function capture(label){try{const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label})});const d=await r.json();if(d.ok){toast(d.label_ko+' 저장됨 ('+d.count+'번째)');refreshCounts()}else{toast(d.error||'실패',true)}}catch(e){toast('연결 실패: '+e.message,true)}}
refreshCounts();
</script></body></html>"""


def create_app(camera: LazyCamera) -> Flask:
    app = Flask(__name__)
    label_ko = dict(LABELS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, _ in LABELS:
        (OUT_DIR / key).mkdir(parents=True, exist_ok=True)

    @app.get("/")
    def index():
        return PAGE

    @app.get("/preview.jpg")
    def preview():
        try:
            data = camera.preview()
        except Exception as error:  # noqa: BLE001
            return Response(str(error), status=502)
        return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/counts")
    def counts():
        return jsonify({key: len(list((OUT_DIR / key).glob("*.jpg"))) for key, _ in LABELS})

    @app.post("/capture")
    def capture():
        payload = request.get_json(force=True, silent=True) or {}
        label = payload.get("label")
        if label not in label_ko:
            return jsonify({"ok": False, "error": f"알 수 없는 라벨: {label}"}), 400
        try:
            data = camera.capture("high")
        except Exception as error:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(error)}), 502
        filename = f"{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time()*1000)%1000:03d}.jpg"
        path = OUT_DIR / label / filename
        path.write_bytes(data)
        count = len(list((OUT_DIR / label).glob("*.jpg")))
        return jsonify({"ok": True, "label_ko": label_ko[label], "count": count, "path": str(path)})

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp-host", default="192.168.4.1", help="카메라 IP/호스트명 (기본 FridgeCam AP)")
    parser.add_argument("--port", type=int, default=8610, help="이 웹서버 포트")
    args = parser.parse_args()

    camera = LazyCamera(args.esp_host)
    print(f"서버 시작. http://localhost:{args.port} 접속")
    print(f"(카메라 {args.esp_host}는 화면을 열 때 연결을 시도합니다 — 이 컴퓨터가 "
          "FridgeCam Wi-Fi에 접속돼있어야 미리보기/촬영이 됩니다)")
    app = create_app(camera)
    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
