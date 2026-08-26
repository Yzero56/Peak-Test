"""mock_server_webcam.py — mock_server.py의 웹캠 버전.

mock_server.py는 고정된 목업 이미지 하나만 준다(연결/배선 테스트용). 이건 그
대신 **이 컴퓨터의 실제 웹캠**을 board-a-door-container인 것처럼 서빙한다 —
실물 ESP32 없이도 진짜 물건(당근, 우유 등)을 카메라에 보여주고 Wa/YJ가
진짜로 인식하는지 볼 수 있다.

⚠ Claude Code 샌드박스 안에서는 macOS가 카메라 접근을 거부한다
("OpenCV: not authorized to capture video") — 이 스크립트는 **일반
터미널(Terminal.app/iTerm 등)에서 직접 실행해야** macOS가 카메라 접근 허용
팝업을 띄워준다. 처음 실행하면 팝업이 뜨는데 반드시 "허용"을 눌러야 함.

준비:
  pip install opencv-python-headless   (또는 opencv-python)

실행:
  python mock_server_webcam.py --port 9000
  # 카메라가 여러 개면(내장캠+USB캠 등) --camera-index로 선택 (기본 0)
  python mock_server_webcam.py --camera-index 1
"""

from __future__ import annotations

import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cv2

state_lock = threading.Lock()
door_open = True
latest_jpeg: bytes | None = None
camera_error: str | None = "카메라 준비 중"


def capture_loop(camera_index: int, mirror: bool) -> None:
    global latest_jpeg, camera_error
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        with state_lock:
            camera_error = f"카메라 {camera_index}번을 열 수 없습니다 — macOS 카메라 접근 권한을 확인하세요."
        print(f"[mock-webcam] {camera_error}")
        return
    print(f"[mock-webcam] 카메라 {camera_index}번 열림")
    while True:
        ok, frame = cap.read()
        if not ok:
            with state_lock:
                camera_error = "프레임 읽기 실패"
            time.sleep(0.3)
            continue
        if mirror:
            frame = cv2.flip(frame, 1)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            with state_lock:
                latest_jpeg = buf.tobytes()
                camera_error = None
        time.sleep(0.05)


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"[mock-webcam] {self.address_string()} {fmt % args}")

        def _send_jpeg(self):
            with state_lock:
                data, err = latest_jpeg, camera_error
            if data is None:
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write((err or "no frame yet").encode())
                return
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
                self.wfile.write(b"mock board-a-door-container (webcam): /door /capture /preview /jpg")
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("준비")[0])
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--camera-index", type=int, default=0)
    ap.add_argument("--no-mirror", action="store_true", help="좌우반전 끄기(기본은 셀피처럼 좌우반전)")
    args = ap.parse_args()

    threading.Thread(target=capture_loop, args=(args.camera_index, not args.no_mirror), daemon=True).start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    print(f"[mock-webcam] board-a-door-container 웹캠 시뮬레이터 http://{args.host}:{args.port} 에서 대기 중")
    print("[mock-webcam] 처음 실행 시 macOS가 카메라 접근 허용 팝업을 띄우면 '허용'을 누르세요.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
