"""냉장고 실사용 물건별(개별 인스턴스) 원본 사진을 YOLO-World로 자동 크롭해 학습셋을 만든다.

instance_dataset_raw/<라벨>/*.jpg 를 읽어서 물건 부분만 잘라낸 뒤
instance_dataset_prepared/{train,val,test}/<라벨>/ 로 나눠 저장한다.
라벨 폴더 하나 = 물건 하나(고유 인스턴스)이므로 prepare_category_dataset.py와 달리
물건 단위 그룹핑 없이 사진 단위로 train/val/test를 나눈다.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLOWorld

from container_detector import DEFAULT_MODEL, read_image, write_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "instance_dataset_raw"
OUTPUT = ROOT / "instance_dataset_prepared"
SPLIT_RATIOS = {"test": 0.15, "val": 0.15}
RANDOM_SEED = 20260827

# 라벨별로 YOLO-World에게 어떤 프롬프트로 찾으라고 알려줄지 지정.
# 목록에 없는 새 라벨은 GENERIC_PROMPTS로 대체된다.
PROMPTS_BY_LABEL = {
    "달걀곽": ["egg tray", "carton", "box", "package"],
    "라떼": ["latte", "coffee cup", "paper cup", "tumbler", "cup"],
    "밥용기": ["rice container", "plastic container", "box", "tupperware"],
    "사이다": ["soda can", "soda bottle", "plastic bottle", "can"],
    "스팸": ["spam can", "can", "tin can", "metal can", "canned food"],
    "아메리카노": ["coffee cup", "cup", "paper cup", "disposable cup"],
    "우유": ["milk carton", "milk bottle", "carton"],
    "종이팩음료": ["juice carton", "paper carton", "drink carton"],
    "콜라": ["cola can", "soda can", "plastic bottle", "can"],
}
# YOLO-World가 열린-어휘 특성상 신뢰도 0.001까지 낮춰도 박스 자체를 못 찾는 라벨
# (채소류, 밋밋한 플라스틱 통). 사진마다 촬영 위치/거리가 달라 고정 중앙 크롭도
# 못 쓰므로, 이 라벨들은 원본 사진 전체를 그대로 학습에 사용한다(아래 fallback 경로).
GENERIC_PROMPTS = ["food item", "container", "bottle", "can", "carton", "vegetable"]
DETECT_IMGSZ = 640


def label_photo_paths(label_dir: Path) -> list[Path]:
    return sorted(
        path for path in label_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


def make_splits(labels: list[str]) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    rng = random.Random(RANDOM_SEED)
    for label in labels:
        paths = label_photo_paths(RAW / label)
        shuffled = paths[:]
        rng.shuffle(shuffled)
        n = len(shuffled)
        test_count = max(1, round(n * SPLIT_RATIOS["test"])) if n >= 3 else 0
        val_count = max(1, round(n * SPLIT_RATIOS["val"])) if n >= 3 else 0
        for index, path in enumerate(shuffled):
            if index < test_count:
                split = "test"
            elif index < test_count + val_count:
                split = "val"
            else:
                split = "train"
            mapping[(label, path.name)] = split
    return mapping


def valid_box(box, width: int, height: int) -> bool:
    x1, y1, x2, y2 = box
    box_width, box_height = x2 - x1, y2 - y1
    if box_width <= 0 or box_height <= 0:
        return False
    area_ratio = box_width * box_height / float(width * height)
    return 0.01 <= area_ratio <= 0.95 and box_width / width < 0.98 and box_height / height < 0.98


def padded_crop(frame, box, padding: float = 0.06):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    pad_x, pad_y = int((x2 - x1) * padding), int((y2 - y1) * padding)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    return frame[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)


def main() -> None:
    labels = sorted(p.name for p in RAW.iterdir() if p.is_dir())
    if not labels:
        raise SystemExit(f"{RAW} 에 라벨 폴더가 없습니다. 먼저 데이터를 수집하세요.")
    print(f"라벨 {len(labels)}개: {labels}", flush=True)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "debug_boxes").mkdir(parents=True)

    split_map = make_splits(labels)
    model = YOLOWorld(str(DEFAULT_MODEL))
    active_label = None
    rows, accepted, rejected = [], 0, 0
    sources = [(label, path) for label in labels for path in label_photo_paths(RAW / label)]
    print(f"총 {len(sources)}장 자동 크롭 시작", flush=True)

    for index, (label, path) in enumerate(sources, start=1):
        frame = read_image(path)
        height, width = frame.shape[:2]
        split = split_map[(label, path.name)]
        row = {"source": str(path), "label": label, "split": split, "status": "rejected"}

        if label != active_label:
            model.set_classes(PROMPTS_BY_LABEL.get(label, GENERIC_PROMPTS))
            active_label = label
        prediction = model.predict(
            frame, conf=0.02, imgsz=DETECT_IMGSZ, max_det=4, agnostic_nms=True, verbose=False
        )[0]
        candidates = []
        for box_tensor, confidence, class_id in zip(
            prediction.boxes.xyxy, prediction.boxes.conf, prediction.boxes.cls
        ):
            box = tuple(int(round(float(value))) for value in box_tensor)
            if valid_box(box, width, height):
                candidates.append((float(confidence), int(class_id), box))

        if candidates:
            confidence, class_id, box = max(candidates, key=lambda item: item[0])
            crop, padded_box = padded_crop(frame, box)
            destination = OUTPUT / split / label / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_image(destination, crop)

            annotated = frame.copy()
            x1, y1, x2, y2 = padded_box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 3)
            debug_path = OUTPUT / "debug_boxes" / label / path.name
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            write_image(debug_path, annotated)
            row.update(status="accepted", crop=str(destination), confidence=f"{confidence:.6f}")
            accepted += 1
        else:
            # 못 찾으면 원본 전체를 그대로 사용 (촬영 사진이 이미 물건 위주 클로즈업이라 안전).
            destination = OUTPUT / split / label / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_image(destination, frame)
            row.update(status="fallback_full_image", crop=str(destination))
            rejected += 1
        rows.append(row)
        if index % 20 == 0 or index == len(sources):
            print(f"진행 {index}/{len(sources)} (크롭 성공 {accepted}, 원본 사용 {rejected})", flush=True)

    counts = Counter((row["label"], row["split"]) for row in rows)
    for label in labels:
        print(f"{label}: train={counts[(label,'train')]} val={counts[(label,'val')]} test={counts[(label,'test')]}")

    (OUTPUT / "prepare_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("완료. instance_dataset_prepared/ 확인하세요.", flush=True)


if __name__ == "__main__":
    main()
