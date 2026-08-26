"""mock_server.py — board-a-door-container.ino의 HTTP 계약을 흉내내는 순수 파이썬
시뮬레이터. 실제 ESP32 보드 없이 YJ/Wa의 기존 파이썬 클라이언트(수정 없이)를
붙여서 소프트웨어 배선(연결·에러 처리·매칭 로직)을 테스트할 때 쓴다.

⚠ 진짜 냉장고 사진을 찍는 게 아니다 — 고정된 목업 이미지(mock_placeholder.jpg)만
반환하므로, 여기서 나오는 IN/OUT·용기 종류 판정 결과는 의미 없다(모델이 실제로
로드·추론되는지, 파이프라인이 안 죽는지 정도만 확인 가능). 실제 판정 결과를
보려면 진짜 ESP32 하드웨어가 필요하다.

계약(firmware/board-a-door-container/board-a-door-container.ino와 동일):
  GET  /                          -> 200 텍스트
  GET  /door                      -> {"open": bool}
  GET  /capture?quality=standard  -> JPEG (quality 파라미터는 무시하고 같은 이미지 반환)
  GET  /preview                   -> JPEG
  GET  /jpg                       -> JPEG (Wa 계약)
  POST /debug/door?open=true|false -> 문 상태를 수동으로 바꾼다(테스트용, 실제
                                       보드에는 없는 디버그 전용 엔드포인트)

실행:
  python mock_server.py --port 9000
  # 다른 터미널에서 문 상태 토글:
  curl -X POST "http://localhost:9000/debug/door?open=false"
"""

from __future__ import annotations

import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

JPEG_PATH = Path(__file__).parent / "mock_placeholder.jpg"

state_lock = threading.Lock()
door_open = True


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[mock] {self.address_string()} {fmt % args}")

        def _send_jpeg(self):
            data = JPEG_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, body: str):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"mock board-a-door-container: /door /capture /preview /jpg")
            elif parsed.path == "/door":
                with state_lock:
                    self._send_json('{"open": %s}' % ("true" if door_open else "false"))
            elif parsed.path in ("/capture", "/preview", "/jpg"):
                self._send_jpeg()
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/debug/door":
                global door_open
                qs = parse_qs(parsed.query)
                val = qs.get("open", ["true"])[0].lower()
                with state_lock:
                    door_open = val in ("1", "true", "yes", "open")
                self._send_json('{"open": %s}' % ("true" if door_open else "false"))
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("계약")[0])
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    if not JPEG_PATH.exists():
        raise SystemExit(f"{JPEG_PATH} 가 없습니다 — 이 파일과 같은 폴더에 있어야 합니다.")

    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    print(f"[mock] board-a-door-container 시뮬레이터 http://{args.host}:{args.port} 에서 대기 중")
    print(f"[mock]   GET  /door, /capture?quality=, /preview, /jpg")
    print(f"[mock]   POST /debug/door?open=true|false  (테스트용 수동 토글)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
