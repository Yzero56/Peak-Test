"""demo_panel.py — 발표용 통합 대시보드 한 장.

지금은 백엔드(8000)·mock 보드(9000)·YJ(8601)·Wa(5007)가 전부 따로 떨어진 탭이라
발표 중에 알트탭을 반복해야 한다. 이 스크립트는 그 넷을 전부 서버사이드로
대신 호출해서(=CORS 문제 없음, 각 서버 코드 수정 없음) 결과를 **탭 하나**에
모아 보여준다:

  [카메라 미리보기 + 문 열기/닫기 버튼] [YJ 최신 판정] [Wa 최근 인식]
  [재고 목록(실시간)]                                  [최근 이벤트 로그]

문 열기 버튼을 누르면: mock 보드 door=open 토글 -> Wa 인식을 몇 번 자동 트리거
(실물 카메라가 있으면 그동안 물건을 보여주면 됨) -> 문 닫기 -> YJ가 판정하고
bridge가 매칭할 시간을 준 뒤 재고 목록이 자동 갱신된다. 즉 "문 열고 → 물건
보여주고 → 문 닫고 → 대시보드에 반영되는" 실제 시연 흐름을 버튼 하나로 리허설할 수 있다.

실행:
  python dev/demo_panel.py --port 9500
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

CONFIG = {
    "backend": "http://localhost:8000",
    "board": "http://localhost:9000",
    "yj": "http://localhost:8601",
    "wa": "http://localhost:5007",
}

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PEAK Smart 라이브 데모</title>
<style>
:root{--bg:#0b0d10;--panel:#14171c;--line:#242830;--text:#eef1f5;--muted:#8b93a1;--good:#33d17a;--warn:#f5b942;--bad:#f5546a;--accent:#3f8cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,"Pretendard","Noto Sans KR",sans-serif;padding:18px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.card h2{font-size:14px;margin:0 0 10px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.04em}
#cam{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:10px;background:#000;display:block}
.doorbtn{width:100%;margin-top:10px;padding:14px;font-size:16px;font-weight:800;border:none;border-radius:10px;
  background:var(--accent);color:#fff;cursor:pointer}
.doorbtn:disabled{opacity:.5;cursor:default}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700}
.pill.good{background:rgba(51,209,122,.15);color:var(--good)}
.pill.warn{background:rgba(245,185,66,.15);color:var(--warn)}
.pill.bad{background:rgba(245,84,106,.15);color:var(--bad)}
.pill.idle{background:rgba(139,147,161,.15);color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-weight:600}
#log{font-size:12px;color:var(--muted);max-height:160px;overflow-y:auto;font-family:ui-monospace,monospace;line-height:1.6}
.wide{grid-column:1/-1}
.stat{font-size:13px;margin:4px 0}
</style></head><body>
<h1>🧊 PEAK Smart — 라이브 데모 패널</h1>
<div class="sub">문 열기 버튼 하나로 냉장고 OUT/IN → 인식 → 백엔드 등록 → 대시보드 반영까지 한 화면에서 확인</div>
<div class="grid">
  <div class="card">
    <h2>카메라 (board-a)</h2>
    <img id="cam" src="/proxy/camera.jpg">
    <button id="doorBtn" class="doorbtn" onclick="toggleDoor()">🚪 문 열기</button>
    <div class="stat">문 상태: <span id="doorState" class="pill idle">확인 중</span></div>
  </div>
  <div class="card">
    <h2>인식 상태</h2>
    <div class="stat">YJ (IN/OUT): <span id="yjState" class="pill idle">-</span></div>
    <div class="stat" id="yjResult">최근 판정 없음</div>
    <hr style="border-color:var(--line);margin:10px 0">
    <div class="stat">Wa (용기/물건): <span id="waState" class="pill idle">-</span></div>
    <div id="waResult" class="stat">-</div>
  </div>
  <div class="card wide">
    <h2>재고 (백엔드 실시간)</h2>
    <table><thead><tr><th>이름</th><th>상태</th><th>container_id</th><th>D-day</th></tr></thead>
      <tbody id="inventoryBody"></tbody></table>
  </div>
  <div class="card wide">
    <h2>최근 이벤트 로그</h2>
    <div id="log"></div>
  </div>
</div>
<script>
let doorOpen = false, waLoopTimer = null;
function pill(el, text, cls){ el.textContent = text; el.className = 'pill ' + cls; }
function logLine(msg){
  const el = document.getElementById('log');
  const t = new Date().toLocaleTimeString('ko-KR');
  el.innerHTML = `[${t}] ${msg}<br>` + el.innerHTML;
}

async function refreshDoor(){
  try{
    const r = await fetch('/proxy/door'); const d = await r.json();
    doorOpen = d.open;
    pill(document.getElementById('doorState'), doorOpen?'열림':'닫힘', doorOpen?'warn':'good');
    document.getElementById('doorBtn').textContent = doorOpen ? '🚪 문 닫기' : '🚪 문 열기';
  }catch(e){ pill(document.getElementById('doorState'), '연결 안 됨', 'bad'); }
}

async function toggleDoor(){
  const btn = document.getElementById('doorBtn'); btn.disabled = true;
  const next = !doorOpen;
  await fetch('/proxy/door', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({open: next})});
  logLine(next ? '🚪 문 열림 — Wa 인식 시작 (실물 카메라면 지금 물건을 보여주세요)' : '🚪 문 닫힘 — YJ 판정 + bridge 매칭 대기 중');
  await refreshDoor();
  if(next){ startWaLoop(); } else { stopWaLoop(); setTimeout(refreshInventory, 6000); }
  btn.disabled = false;
}

async function refreshYJ(){
  try{
    const r = await fetch('/proxy/yj-status'); const d = await r.json();
    pill(document.getElementById('yjState'), d.session_active?'세션 진행 중':(d.connected?'연결됨':'연결 안 됨'),
         d.session_active?'warn':(d.connected?'good':'bad'));
    const res = d.latest_result;
    document.getElementById('yjResult').textContent = res
      ? `최근 판정: ${res.label ?? '(' + (res.reason||'실패') + ')'} ${res.confidence!=null?'('+(res.confidence*100).toFixed(0)+'%)':''}`
      : '최근 판정 없음';
  }catch(e){ pill(document.getElementById('yjState'), '연결 안 됨', 'bad'); }
}

async function waClassifyOnce(){
  try{
    const r = await fetch('/proxy/wa-classify', {method:'POST'}); const d = await r.json();
    if(d.status === 'ok' && d.objects && d.objects.length){
      pill(document.getElementById('waState'), '인식됨', 'good');
      document.getElementById('waResult').textContent = d.objects.map(o=>`${o.label} (${(o.confidence*100).toFixed(0)}%)`).join(', ');
      logLine('📦 Wa 인식: ' + d.objects.map(o=>o.label).join(', '));
    }else{
      pill(document.getElementById('waState'), '탐색 중', 'idle');
      document.getElementById('waResult').textContent = d.message || '아직 못 찾음';
    }
  }catch(e){ pill(document.getElementById('waState'), '연결 안 됨', 'bad'); }
}
function startWaLoop(){ stopWaLoop(); waClassifyOnce(); waLoopTimer = setInterval(waClassifyOnce, 1200); }
function stopWaLoop(){ if(waLoopTimer){ clearInterval(waLoopTimer); waLoopTimer = null; } }

async function refreshInventory(){
  try{
    const r = await fetch('/proxy/dashboard'); const d = await r.json();
    const body = document.getElementById('inventoryBody');
    body.innerHTML = (d.items||[]).map(i => `<tr>
      <td>${i.display_name}</td>
      <td><span class="pill ${i.expiry_status==='expired'?'bad':(i.expiry_status==='expiring_soon'?'warn':'good')}">${i.status}</span></td>
      <td>${i.container_id ?? '-'}</td>
      <td>${i.days_remaining ?? '-'}</td>
    </tr>`).join('');
  }catch(e){}
}

document.getElementById('cam').addEventListener('error', function(){ this.src = this.src; });
setInterval(()=>{ document.getElementById('cam').src = '/proxy/camera.jpg?t=' + Date.now(); }, 700);
setInterval(refreshDoor, 1500);
setInterval(refreshYJ, 1500);
setInterval(refreshInventory, 2500);
refreshDoor(); refreshYJ(); refreshInventory();
</script>
</body></html>"""


def _get(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 599, str(e).encode()


def _post(url: str, body: bytes | None = None, timeout: float = 8.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body or b"", method="POST")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 599, str(e).encode()


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, status: int, content_type: str, body: bytes):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE.encode())
            elif path == "/proxy/camera.jpg":
                status, body = _get(f"{CONFIG['board']}/jpg")
                self._send(status if status < 400 else 503, "image/jpeg", body)
            elif path == "/proxy/door":
                status, body = _get(f"{CONFIG['board']}/door")
                self._send(status if status < 400 else 503, "application/json", body)
            elif path == "/proxy/yj-status":
                status, body = _get(f"{CONFIG['yj']}/api/status")
                self._send(status if status < 400 else 503, "application/json", body)
            elif path == "/proxy/dashboard":
                status, body = _get(f"{CONFIG['backend']}/api/v1/dashboard/summary")
                self._send(status if status < 400 else 503, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/proxy/door":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    want_open = json.loads(raw).get("open", True)
                except Exception:
                    want_open = True
                status, body = _post(f"{CONFIG['board']}/debug/door?open={'true' if want_open else 'false'}")
                self._send(status if status < 400 else 503, "application/json", body)
            elif path == "/proxy/wa-classify":
                status, body = _post(f"{CONFIG['wa']}/classify-next")
                self._send(status if status < 400 else 503, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("실행")[0])
    ap.add_argument("--port", type=int, default=9500)
    ap.add_argument("--backend-url", default=CONFIG["backend"])
    ap.add_argument("--board-url", default=CONFIG["board"])
    ap.add_argument("--yj-url", default=CONFIG["yj"])
    ap.add_argument("--wa-url", default=CONFIG["wa"])
    args = ap.parse_args()
    CONFIG.update(backend=args.backend_url, board=args.board_url, yj=args.yj_url, wa=args.wa_url)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler())
    print(f"[demo-panel] http://localhost:{args.port} 에서 대기 중")
    print(f"[demo-panel]   backend={CONFIG['backend']} board={CONFIG['board']} yj={CONFIG['yj']} wa={CONFIG['wa']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
