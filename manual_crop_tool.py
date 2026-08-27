"""마우스로 박스를 그려서 사진을 수동으로 잘라내는 도구.

사용법:
  python manual_crop_tool.py

instance_dataset_prepared/prepare_report.json에서 "자동 크롭 실패(원본 그대로 사용)"로
표시된 사진들을 라벨 상관없이 전부 모아서, 한 장씩 차례로 띄워준다. 라벨은 자동으로
알고 있으니 신경 쓸 필요 없이 크롭만 계속하면 되고, 결과는 알아서
instance_dataset_manual_crop/<그 사진의 라벨>/ 에 저장된다.
이미 저장된(=이미 크롭한) 사진은 자동으로 건너뛰어서, 중간에 종료했다가 다시 실행해도
이어서 할 수 있다.

조작법 (사진이 뜬 창에서):
  - 마우스 드래그: 박스 그리기
  - ENTER 또는 SPACE: 지금 그린 박스로 잘라서 저장하고 다음 사진
  - c: 다시 그리기 (박스 취소)
  - s: 이 사진 건너뛰기 (저장 안 함, 다음에 또 뜸)
  - q 또는 ESC: 종료 (그때까지 한 건 저장되어 있음, 나중에 이어서 가능)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "instance_dataset_prepared" / "prepare_report.json"
OUTPUT = ROOT / "instance_dataset_manual_crop"


def load_todo() -> list[tuple[str, Path]]:
    rows = json.loads(REPORT.read_text(encoding="utf-8"))
    todo = []
    for row in rows:
        if row["status"] != "fallback_full_image":
            continue
        label = row["label"]
        source = Path(row["source"])
        destination = OUTPUT / label / source.name
        if destination.exists():
            continue  # 이미 크롭 완료된 것
        todo.append((label, source))
    return todo


def main() -> None:
    todo = load_todo()
    if not todo:
        print("크롭할 사진이 없습니다 (전부 완료됐거나 prepare_report.json이 없음).")
        return
    print(f"수동 크롭 대상 {len(todo)}장 남음. ENTER=저장+다음, c=다시그리기, s=건너뛰기, q=종료")

    window = "수동 크롭 (드래그로 박스 그리기)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    saved = skipped = 0
    for index, (label, path) in enumerate(todo, start=1):
        frame = cv2.imdecode(np.fromfile(str(path), dtype="uint8"), cv2.IMREAD_COLOR)
        if frame is None:
            print(f"[{index}/{len(todo)}] 읽기 실패, 건너뜀: {path}")
            skipped += 1
            continue

        while True:
            display = frame.copy()
            cv2.putText(
                display, f"[{index}/{len(todo)}] {label} / {path.name}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
            )
            box = cv2.selectROI(window, display, showCrosshair=True, fromCenter=False)
            x, y, w, h = box
            if w == 0 or h == 0:
                print(f"[{index}/{len(todo)}] 박스 없음 -> 건너뜀")
                skipped += 1
                break

            crop = frame[y:y + h, x:x + w].copy()
            cv2.imshow(window, crop)
            key = cv2.waitKey(0) & 0xFF

            if key in (13, 32):  # ENTER / SPACE
                out_dir = OUTPUT / label
                out_dir.mkdir(parents=True, exist_ok=True)
                destination = out_dir / path.name
                cv2.imencode(".jpg", crop)[1].tofile(str(destination))
                print(f"[{index}/{len(todo)}] 저장: {label}/{destination.name} ({w}x{h})")
                saved += 1
                break
            elif key == ord("c"):
                continue
            elif key == ord("s"):
                print(f"[{index}/{len(todo)}] 건너뜀")
                skipped += 1
                break
            elif key in (ord("q"), 27):
                cv2.destroyAllWindows()
                print(f"\n중단: 저장 {saved}장, 건너뜀 {skipped}장. 나중에 다시 실행하면 이어서 됩니다.")
                return

    cv2.destroyAllWindows()
    print(f"\n완료: 저장 {saved}장, 건너뜀 {skipped}장 -> {OUTPUT}")


if __name__ == "__main__":
    main()
