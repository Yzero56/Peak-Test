"""demo_panel.py — 발표용 통합 대시보드 한 장.

지금은 백엔드(8000)·mock 보드(9000)·YJ(8601)·Wa(5007)·앱(8081)이 전부 따로 떨어진
탭이라 발표 중에 알트탭을 반복해야 한다. 이 스크립트는 그걸 전부 **탭 하나**에
모아 보여준다. 레이아웃은 실제 시연 순서 그대로 위→아래로 읽힌다:

  1~3단계: [카메라 미리보기 + (mock 전용) 문 열기/닫기 버튼] [YJ 최신 판정 · Wa 최근 인식]
  4단계:   [웹 대시보드 — 진짜 화면 iframe]   [앱 — 진짜 화면 iframe]
           [최근 이벤트 로그]

즉 "냉장고 OUT → (동시에) 용기인식 → 백엔드 등록 → 웹 대시보드에서 확인"과
"만든 음식 IN → 용기인식 → 백엔드 등록 → 웹 대시보드에서 확인" 두 사이클 다,
카메라/인식 증명(위)과 그 결과가 반영된 실제 화면(아래)을 화면 전환 없이 한 번에
보여준다. 대시보드·앱은 재고 요약을 흉내낸 게 아니라 진짜 그 서비스를 iframe으로
그대로 띄운 것 — 재고 테이블 대신 이걸 넣은 이유.

⚠ **문 열기/닫기는 실제 시스템에서 버튼이 아니다.** 실물 보드에서는 리드스위치가
문 상태를 자동으로 감지해서 GET /door에 반영할 뿐, 수동으로 열고 닫는 조작 자체가
없다. 그 버튼은 mock_server.py(리드스위치가 없는 순수 소프트웨어 시뮬레이터)를
붙였을 때만 "문이 열렸다고 치자"를 흉내내기 위한 테스트 전용 기능이다 — 이 페이지가
서버사이드로 보드의 "/"를 찔러서 mock인지 실물인지 자동 판별하고(`is_mock`),
실물 보드일 때는 그 버튼을 아예 숨기고 리드스위치가 감지한 실제 상태만 읽기 전용으로
보여준다.

mock에 붙어서 버튼을 누르면: door=open 토글 -> Wa 인식을 몇 번 자동 트리거
(실물 카메라가 있으면 그동안 물건을 보여주면 됨) -> 문 닫기 -> YJ가 판정하고
bridge가 매칭할 시간을 준 뒤 재고 목록이 자동 갱신된다. 즉 "문 열고 → 물건
보여주고 → 문 닫고 → 대시보드에 반영되는" 실제 시연 흐름을 하드웨어 없이 리허설할 수
있다. 실물 보드가 붙으면 이 버튼 없이도 진짜 리드스위치로 똑같은 흐름이 자동으로 돈다.

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
    "app": "http://localhost:8081",
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
#log{font-size:12px;color:var(--muted);max-height:120px;overflow-y:auto;font-family:ui-monospace,monospace;line-height:1.6}
.wide{grid-column:1/-1}
.stat{font-size:13px;margin:4px 0}
.tabs{display:flex;gap:8px;margin-bottom:18px}
.tabs button{padding:10px 18px;border-radius:10px;border:1px solid var(--line);background:var(--panel);
  color:var(--muted);cursor:pointer;font-size:13.5px;font-weight:700;font-family:inherit}
.tabs button.active{border-color:var(--accent);color:#fff;background:linear-gradient(180deg,#1a2740,var(--panel))}
.tabs button .num{display:inline-flex;width:18px;height:18px;border-radius:50%;background:var(--line);
  align-items:center;justify-content:center;font-size:10.5px;margin-right:7px}
.tabs button.active .num{background:var(--accent)}
.scene{display:none}
.scene.active{display:block}
.iframe-grid{display:grid;grid-template-columns:1.6fr 1fr;gap:14px;height:calc(100vh - 150px)}
@media(max-width:900px){.iframe-grid{grid-template-columns:1fr;height:auto}}
.iframe-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.iframe-card .label{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  padding:10px 14px;border-bottom:1px solid var(--line)}
.iframe-card iframe{border:0;width:100%;flex:1;min-height:420px;background:#fff}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}
.fsbtn{background:var(--panel);border:1px solid var(--line);color:var(--text);padding:9px 16px;border-radius:9px;
  cursor:pointer;font-size:13px;font-weight:700;font-family:inherit;flex:none}
.fsbtn:hover{border-color:var(--accent)}
body.fs{padding:0}
body.fs .topbar,body.fs .tabs{display:none}
body.fs .scene{padding:14px}
body.fs .iframe-grid{height:100vh}
</style></head><body>
<div class="topbar">
  <div>
    <h1>🧊 PEAK Smart — 라이브 데모 패널</h1>
    <div class="sub">발표 중 버튼으로 전환하세요 — 스크롤 없이 화면 하나가 꽉 차게 바뀝니다.</div>
  </div>
  <button class="fsbtn" onclick="toggleFullscreen()">⤢ 전체화면 (F11도 가능)</button>
</div>

<div class="tabs">
  <button id="tabBtn1" class="active" onclick="showScene(1)"><span class="num">1</span>식재료 OUT/IN + 용기인식 (카메라)</button>
  <button id="tabBtn2" onclick="showScene(2)"><span class="num">2</span>백엔드 등록 → 대시보드 · 앱 확인</button>
</div>

<div id="scene1" class="scene active">
<div class="grid">
  <div class="card">
    <h2>카메라 (board-a)</h2>
    <img id="cam" src="/proxy/camera.jpg">
    <button id="doorBtn" class="doorbtn" onclick="toggleDoor()">🚪 (mock) 문 열기</button>
    <div id="doorHint" class="stat" style="color:var(--muted);font-size:12px"></div>
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
    <h2>최근 이벤트 로그</h2>
    <div id="log"></div>
  </div>
</div>
</div>

<div id="scene2" class="scene">
<div class="iframe-grid">
  <div class="iframe-card">
    <div class="label">앱</div>
    <iframe src="/proxy/app-page"></iframe>
  </div>
  <div class="iframe-card">
    <div class="label">웹 대시보드</div>
    <iframe src="/proxy/dashboard-page"></iframe>
  </div>
</div>
</div>
<script>
function toggleFullscreen(){
  if(!document.fullscreenElement){ document.documentElement.requestFullscreen(); document.body.classList.add('fs'); }
  else{ document.exitFullscreen(); document.body.classList.remove('fs'); }
}
document.addEventListener('fullscreenchange', ()=>{ if(!document.fullscreenElement) document.body.classList.remove('fs'); });

function showScene(n){
  document.getElementById('scene1').classList.toggle('active', n===1);
  document.getElementById('scene2').classList.toggle('active', n===2);
  document.getElementById('tabBtn1').classList.toggle('active', n===1);
  document.getElementById('tabBtn2').classList.toggle('active', n===2);
}
let doorOpen = false, waLoopTimer = null;
function pill(el, text, cls){ el.textContent = text; el.className = 'pill ' + cls; }
function logLine(msg){
  const el = document.getElementById('log');
  const t = new Date().toLocaleTimeString('ko-KR');
  el.innerHTML = `[${t}] ${msg}<br>` + el.innerHTML;
}

let isMockBoard = null;  // null=아직 모름, true=mock_server.py, false=실물 보드(리드스위치)

async function refreshBoardMode(){
  try{
    const r = await fetch('/proxy/board-info'); const d = await r.json();
    isMockBoard = d.is_mock;
    const btn = document.getElementById('doorBtn'), hint = document.getElementById('doorHint');
    if(isMockBoard){
      btn.style.display = '';
      hint.textContent = '⚠ mock 서버 전용 테스트 버튼 — 실물 보드에선 리드스위치가 자동 감지하고 이 버튼은 없음';
    }else{
      btn.style.display = 'none';
      hint.textContent = '실물 리드스위치가 문 상태를 자동으로 감지 중 (버튼 없음)';
    }
  }catch(e){ /* 보드 자체가 안 잡히면 refreshDoor() 쪽에서 이미 '연결 안 됨' 표시함 */ }
}

async function refreshDoor(){
  try{
    const r = await fetch('/proxy/door'); const d = await r.json();
    doorOpen = d.open;
    pill(document.getElementById('doorState'), doorOpen?'열림':'닫힘', doorOpen?'warn':'good');
    document.getElementById('doorBtn').textContent = doorOpen ? '🚪 (mock) 문 닫기' : '🚪 (mock) 문 열기';
  }catch(e){ pill(document.getElementById('doorState'), '연결 안 됨', 'bad'); }
}

async function toggleDoor(){
  const btn = document.getElementById('doorBtn'); btn.disabled = true;
  const next = !doorOpen;
  await fetch('/proxy/door', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({open: next})});
  logLine(next ? '🚪 문 열림 — Wa 인식 시작 (실물 카메라면 지금 물건을 보여주세요)' : '🚪 문 닫힘 — YJ 판정 + bridge 매칭 대기 중');
  await refreshDoor();
  if(next){ startWaLoop(); } else { stopWaLoop(); logLine('⏳ 대시보드·앱은 자체적으로 몇 초 내 자동 갱신됩니다'); }
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

document.getElementById('cam').addEventListener('error', function(){ this.src = this.src; });
setInterval(()=>{ document.getElementById('cam').src = '/proxy/camera.jpg?t=' + Date.now(); }, 700);
setInterval(refreshDoor, 1500);
setInterval(refreshBoardMode, 5000);
setInterval(refreshYJ, 1500);
refreshDoor(); refreshYJ(); refreshBoardMode();
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
            elif path == "/proxy/board-info":
                # mock_server.py의 "/" 응답엔 "mock"이라는 단어가 들어있고, 실물
                # board-a-door-container.ino의 "/" 응답엔 없다 — 이걸로 구분해서
                # mock일 때만 문 열기/닫기 테스트 버튼을 보여준다(실물 리드스위치가
                # 있을 땐 그 버튼 자체가 오해를 부르므로 숨김).
                status, body = _get(f"{CONFIG['board']}/")
                is_mock = status < 400 and b"mock" in body.lower()
                self._send(200, "application/json", json.dumps({"is_mock": is_mock}).encode())
            elif path == "/proxy/yj-status":
                status, body = _get(f"{CONFIG['yj']}/api/status")
                self._send(status if status < 400 else 503, "application/json", body)
            elif path == "/proxy/dashboard":
                status, body = _get(f"{CONFIG['backend']}/api/v1/dashboard/summary")
                self._send(status if status < 400 else 503, "application/json", body)
            elif path == "/proxy/dashboard-page":
                # 대시보드/앱은 API 응답만 있는 게 아니라 자체 JS·CSS 에셋을 상대경로로
                # 물고 오는 완전한 페이지라, 이 서버가 내용을 대신 fetch해서 재서빙하면
                # (다른 proxy/* 처럼) 그 상대경로들이 이 프록시 기준으로 깨진다. 그래서
                # 내용을 프록시하는 대신, iframe이 실제 origin으로 바로 이동하도록
                # 리다이렉트만 해준다 — CONFIG(=--backend-url 등 인자)를 그대로 반영하기
                # 위한 간접 참조일 뿐, 페이지 자체는 항상 진짜 서버가 직접 서빙한다.
                self.send_response(302)
                self.send_header("Location", f"{CONFIG['backend']}/dashboard/")
                self.end_headers()
            elif path == "/proxy/app-page":
                self.send_response(302)
                self.send_header("Location", CONFIG["app"])
                self.end_headers()
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
    ap.add_argument("--app-url", default=CONFIG["app"])
    args = ap.parse_args()
    CONFIG.update(backend=args.backend_url, board=args.board_url, yj=args.yj_url, wa=args.wa_url, app=args.app_url)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler())
    print(f"[demo-panel] http://localhost:{args.port} 에서 대기 중")
    print(f"[demo-panel]   backend={CONFIG['backend']} board={CONFIG['board']} yj={CONFIG['yj']} wa={CONFIG['wa']} app={CONFIG['app']}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
