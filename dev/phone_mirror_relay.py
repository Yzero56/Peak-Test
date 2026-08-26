"""phone_mirror_relay.py — 실제 폰 화면을 데모 패널에 실시간으로 보여주기 위한 릴레이.

React Native(Expo Go)에서 앱 화면을 직접 캡처해서 보내는 건 매우 까다롭다(네이티브
모듈이 필요해서 Expo Go로는 안 되고, dev client를 새로 빌드해야 함 — 이 컴퓨터엔
Xcode 시뮬레이터도 제대로 안 깔려있어서 지금 당장은 무리). 그래서 대신 **OS 자체
미러링 도구로 폰을 이 맥의 창 하나로 띄우고, 그 창을 캡처해서 전송**한다 —
이 방식은 iOS/Android 둘 다 된다(둘 다 "이 맥에 뜬 미러링 창을 캡처"까지만
플랫폼별로 다르고, 그 다음은 완전히 동일한 코드다):

  1a. iOS  — macOS 기본 앱 QuickTime Player로 iPhone을 USB로 미러링
      (파일 > 새로운 동영상 녹화 > 녹화 버튼 옆 화살표에서 카메라를 iPhone으로 선택.
      "새로운 화면 기록"이 아니라 "새로운 동영상 녹화"임에 주의)
  1b. Android — scrcpy로 USB 미러링 (`brew install scrcpy android-platform-tools`,
      USB 디버깅 켠 뒤 터미널에서 `scrcpy` 실행하면 창이 뜬다)
  2. 그 미러링 창을 dev/screen_capture_sender.py로 캡처해서 이 릴레이 서버로
     WebSocket으로 계속 전송한다 (iOS/Android 무관 — 그냥 화면의 한 영역을 캡처할 뿐)
  3. 이 릴레이는 받은 최신 프레임을 HTTP로 서빙한다 — demo_panel.py가 mock 카메라를
     보여줄 때와 똑같은 방식(<img src="/latest.jpg">)으로 그대로 갖다 쓸 수 있다.

⚠ 1번(미러링 도구 실행)과 2번(화면 캡처)은 macOS 화면 기록 권한이 필요해서 이
Claude Code 세션(샌드박스) 안에서는 실행할 수 없다 — 반드시 사용자가 일반
터미널에서 직접 실행해야 한다. 이 릴레이 서버 자체는 여기서 실행해도 된다
(캡처 권한이 필요 없음).

실행 (릴레이 서버 — 이 컴퓨터 어디서든, 이 세션에서 실행해도 됨):
  pip install websockets
  python dev/phone_mirror_relay.py --ws-port 9600 --http-port 9601

실행 (화면 캡처 전송 — 반드시 일반 터미널에서, 화면 기록 권한 허용 필요):
  pip install mss websockets
  python dev/screen_capture_sender.py --relay ws://localhost:9600/ingest

데모 패널에서 보기:
  http://localhost:9601/latest.jpg  (또는 demo_panel.py의 "📱 실물 폰 미러링" 토글)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import websockets

STATE_LOCK = threading.Lock()
STATE = {
    "latest_frame": None,      # bytes | None
    "frame_count": 0,
    "last_frame_at": None,     # ISO string
    "sender_connected": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ingest_handler(websocket):
    global STATE
    with STATE_LOCK:
        STATE["sender_connected"] = True
    print(f"[relay] 송신 클라이언트 연결됨: {websocket.remote_address}")
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue  # 텍스트 프레임은 무시(제어 메시지 확장 여지만 남겨둠)
            with STATE_LOCK:
                STATE["latest_frame"] = bytes(message)
                STATE["frame_count"] += 1
                STATE["last_frame_at"] = _now()
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        with STATE_LOCK:
            STATE["sender_connected"] = False
        print("[relay] 송신 클라이언트 연결 끊김")


def make_http_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/latest.jpg":
                with STATE_LOCK:
                    frame = STATE["latest_frame"]
                if frame is None:
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"no frame yet - screen_capture_sender.py still connected?")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
            elif path == "/status":
                with STATE_LOCK:
                    body = json.dumps({
                        "sender_connected": STATE["sender_connected"],
                        "frame_count": STATE["frame_count"],
                        "last_frame_at": STATE["last_frame_at"],
                    }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def run_http_server(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), make_http_handler())
    print(f"[relay] HTTP: http://localhost:{port}/latest.jpg  (상태: /status)")
    server.serve_forever()


async def run_ws_server(port: int) -> None:
    print(f"[relay] WebSocket 수신 대기: ws://localhost:{port}/ingest")
    async with websockets.serve(ingest_handler, "0.0.0.0", port, max_size=10 * 1024 * 1024):
        await asyncio.Future()  # 영원히 대기


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("실행")[0])
    ap.add_argument("--ws-port", type=int, default=9600)
    ap.add_argument("--http-port", type=int, default=9601)
    args = ap.parse_args()

    threading.Thread(target=run_http_server, args=(args.http_port,), daemon=True).start()
    try:
        asyncio.run(run_ws_server(args.ws_port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
