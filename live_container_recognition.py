"""ESP32 카메라 영상에서 YOLO → DINOv2 → DB 용기 인식을 실행한다."""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from container_detector import ContainerDetector
from container_pipeline import analyze_frame
from container_registry import DEFAULT_DB, DEFAULT_THRESHOLD, ContainerDatabase, DinoV2Embedder


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def make_jpg_url(address: str) -> str:
    address = address.strip().rstrip("/")
    if not address.startswith(("http://", "https://")):
        address = "http://" + address
    if address.endswith("/stream"):
        address = address[: -len("/stream")]
    if not address.endswith("/jpg"):
        address += "/jpg"
    return address


def fetch_jpg(url: str, timeout: float = 4.0) -> np.ndarray:
    separator = "&" if "?" in url else "?"
    request = urllib.request.Request(
        f"{url}{separator}t={time.time_ns()}", headers={"Cache-Control": "no-cache"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = np.frombuffer(response.read(), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("카메라 사진을 해석하지 못했습니다.")
    return frame


def draw_results(frame, results):
    display = frame.copy()
    for item in results:
        x1, y1, x2, y2 = item["box"]
        color = (0, 200, 0) if item["status"] == "matched" else (0, 165, 255)
        cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
        similarity = item["identity_similarity"]
        suffix = "NEW" if similarity is None else f"{similarity:.2f}"
        cv2.putText(
            display, f"{item['container_id']} {suffix}", (x1, max(18, y1 - 7)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA,
        )
    return display


def print_results(results):
    if not results:
        print("용기를 찾지 못했습니다.")
    for item in results:
        if item["status"] == "registered":
            print(f"새 용기 등록: {item['container_id']}")
        else:
            print(f"기존 용기 인식: {item['container_id']} (유사도 {item['identity_similarity']:.4f})")
        print(f"  YOLO 탐지 확률: {item['detection_confidence']:.4f}")
        print(f"  내용물: {item['content'] or '아직 입력하지 않음'}")


def run(address: str, db_path: Path, identity_threshold: float, auto_seconds: float):
    url = make_jpg_url(address)
    print(f"카메라 사진 주소: {url}")
    print("카메라 연결을 먼저 확인합니다...")
    try:
        frame = fetch_jpg(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise SystemExit(
            f"카메라에 연결하지 못했습니다: {error}\n"
            "ESP32 전원, PC의 Wi-Fi 연결, 브라우저 카메라 주소를 확인하세요."
        )

    print(f"카메라 연결 성공: {frame.shape[1]}x{frame.shape[0]}")
    print("YOLO와 DINOv2 모델을 준비합니다...")
    detector = ContainerDetector()
    embedder = DinoV2Embedder()
    database = ContainerDatabase(db_path)
    last_results = []
    last_analysis = 0.0
    auto_enabled = auto_seconds > 0
    status = "SPACE analyze | A auto | L list | Q quit"

    try:
        while True:
            try:
                frame = fetch_jpg(url)
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                print(f"프레임 수신 실패, 다시 시도합니다: {error}")
                time.sleep(0.5)
                continue

            display = draw_results(frame, last_results)
            cv2.rectangle(display, (0, 0), (display.shape[1], 30), (0, 0, 0), -1)
            cv2.putText(display, status, (7, 20), cv2.FONT_HERSHEY_SIMPLEX,
                        0.42, (80, 255, 80), 1, cv2.LINE_AA)
            cv2.imshow("ESP32 Container Recognition", display)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("a"):
                auto_enabled = not auto_enabled
                status = f"AUTO {'ON' if auto_enabled else 'OFF'} | SPACE analyze | Q quit"
                print(f"자동 분석: {'켜짐' if auto_enabled else '꺼짐'}")
            if key == ord("l"):
                rows = database.list_containers()
                print("\n등록된 용기 목록:")
                if not rows:
                    print("  아직 등록된 용기가 없습니다.")
                for row in rows:
                    print(f"  {row['container_id']} | 내용물: {row['content'] or '미입력'} | "
                          f"본 횟수: {row['observation_count']}")

            manual_request = key == 32
            automatic_request = (auto_enabled and auto_seconds > 0
                                 and time.monotonic() - last_analysis >= auto_seconds)
            if manual_request or automatic_request:
                print("\n현재 화면 분석 중...")
                last_results, _ = analyze_frame(
                    frame, database, detector, embedder, identity_threshold
                )
                last_analysis = time.monotonic()
                print_results(last_results)
    finally:
        database.close()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="ESP32 실시간 영상에서 용기를 탐지·등록·재식별합니다."
    )
    parser.add_argument("address", help="카메라 주소: 192.168.4.1, xiao.local 또는 전체 http 주소")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--auto-seconds", type=float, default=0.0,
                        help="0이면 수동 분석, 5처럼 지정하면 해당 초 간격 자동 분석")
    args = parser.parse_args()
    run(args.address, args.db, args.identity_threshold, args.auto_seconds)


if __name__ == "__main__":
    main()
