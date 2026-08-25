"""AP 브라우저 영상을 보면서 Enter로 현재 용기를 분석하는 시험 프로그램."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from container_detector import ContainerDetector
from container_pipeline import analyze_frame
from container_registry import DEFAULT_DB, DEFAULT_THRESHOLD, ContainerDatabase, DinoV2Embedder
from live_container_recognition import fetch_jpg, make_jpg_url, print_results


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="브라우저 화면의 현재 용기를 분석합니다.")
    parser.add_argument("address", nargs="?", default="192.168.4.1")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    url = make_jpg_url(args.address)
    print(f"카메라 확인 중: {url}")
    frame = fetch_jpg(url)
    print(f"카메라 연결 성공: {frame.shape[1]}x{frame.shape[0]}")
    print("AI 모델을 준비합니다. 잠시 기다려 주세요...")
    detector = ContainerDetector()
    embedder = DinoV2Embedder()
    print("준비 완료!")
    print("브라우저에서 용기를 확인한 뒤 Enter를 누르세요. L=목록, Q=종료")

    while True:
        command = input("\n명령 [Enter/L/Q]: ").strip().lower()
        if command == "q":
            break
        database = ContainerDatabase(args.db)
        try:
            if command == "l":
                rows = database.list_containers()
                if not rows:
                    print("아직 등록된 용기가 없습니다.")
                for row in rows:
                    print(f"{row['container_id']} | 내용물: {row['content'] or '미입력'} | "
                          f"본 횟수: {row['observation_count']}")
                continue
            print("현재 카메라 화면을 분석 중...")
            frame = fetch_jpg(url)
            results, _ = analyze_frame(
                frame, database, detector, embedder, args.identity_threshold
            )
            print_results(results)
        finally:
            database.close()
    print("AI 검사를 종료했습니다.")


if __name__ == "__main__":
    main()
