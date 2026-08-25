"""종류별 원본 사진을 YOLO-World로 자동 크롭하고 물건 단위로 분리한다."""

from __future__ import annotations

import csv
import json
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLOWorld

from container_detector import DEFAULT_MODEL, read_image, write_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "category_dataset_prepared_v2"
CLASS_FOLDERS = {
    "food_container": [ROOT / "학습용 데이터" / "용기", ROOT / "학습용 데이터" / "밥용기"],
    "drink_container": [ROOT / "학습용 데이터" / "텀블러"],
    "water_bottle": [ROOT / "학습용 데이터" / "생수병"],
}


def class_photo_paths(class_name: str) -> list[Path]:
    return sorted(path for folder in CLASS_FOLDERS[class_name] for path in folder.glob("*.jpg"))
PROMPTS_BY_CLASS = {
    "food_container": [
        "food storage container", "plastic food container", "lunch box",
        "plastic box", "food bowl",
    ],
    "drink_container": [
        "tumbler", "travel mug", "coffee mug", "drinking cup",
    ],
    "water_bottle": [
        "water bottle", "plastic water bottle", "bottle",
    ],
}


def object_id(path: Path) -> str:
    """2.1.jpg, box1 (2).jpg 같은 이름에서 실제 물건 ID를 얻는다."""
    stem = path.stem.lower().strip()
    match = re.match(r"(.+?)(?:\s*\(\d+\)|\.\d+)$", stem)
    return (match.group(1) if match else stem).strip()


def make_splits() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    mapping: dict[tuple[str, str], str] = {}
    strategies: dict[str, str] = {}
    rng = random.Random(20260825)
    for class_name in CLASS_FOLDERS:
        paths = class_photo_paths(class_name)
        groups = sorted({object_id(path) for path in paths})
        rng.shuffle(groups)
        if len(groups) >= 3:
            test_id, val_id = groups[0], groups[1]
            for path in paths:
                group = object_id(path)
                mapping[(class_name, path.name)] = (
                    "test" if group == test_id else "val" if group == val_id else "train"
                )
            strategies[class_name] = "object_id_split"
        else:
            # 물건이 한 종류뿐인 신규 클래스는 임시로 사진 단위 분리한다.
            shuffled = paths[:]
            rng.shuffle(shuffled)
            test_count = max(1, round(len(shuffled) * 0.15))
            val_count = max(1, round(len(shuffled) * 0.15))
            for index, path in enumerate(shuffled):
                split = "test" if index < test_count else "val" if index < test_count + val_count else "train"
                mapping[(class_name, path.name)] = split
            strategies[class_name] = "image_split_single_object_limitation"
    return mapping, strategies


def valid_box(box, width: int, height: int) -> bool:
    x1, y1, x2, y2 = box
    box_width, box_height = x2 - x1, y2 - y1
    if box_width <= 0 or box_height <= 0:
        return False
    area_ratio = box_width * box_height / float(width * height)
    return 0.01 <= area_ratio <= 0.90 and box_width / width < 0.97 and box_height / height < 0.97


def padded_crop(frame, box, padding: float = 0.06):
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    pad_x, pad_y = int((x2 - x1) * padding), int((y2 - y1) * padding)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    return frame[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "debug_boxes").mkdir(parents=True)
    split_map, split_strategies = make_splits()

    model = YOLOWorld(str(DEFAULT_MODEL))
    active_class = None
    rows = []
    sources = [
        (class_name, path)
        for class_name in CLASS_FOLDERS
        for path in class_photo_paths(class_name)
    ]
    print(f"총 {len(sources)}장 자동 크롭 시작", flush=True)
    for index, (class_name, path) in enumerate(sources, start=1):
        if class_name != active_class:
            model.set_classes(PROMPTS_BY_CLASS[class_name])
            active_class = class_name
        frame = read_image(path)
        height, width = frame.shape[:2]
        prediction = model.predict(
            frame, conf=0.02, imgsz=320, max_det=4, agnostic_nms=True, verbose=False
        )[0]
        candidates = []
        for box_tensor, confidence, class_id in zip(
            prediction.boxes.xyxy, prediction.boxes.conf, prediction.boxes.cls
        ):
            box = tuple(int(round(float(value))) for value in box_tensor)
            if valid_box(box, width, height):
                candidates.append((float(confidence), int(class_id), box))

        group = object_id(path)
        split = split_map[(class_name, path.name)]
        row = {
            "source": str(path), "class_name": class_name, "object_id": group,
            "split": split, "status": "rejected", "crop": "", "confidence": "",
            "prompt": "", "box": "",
        }
        if candidates:
            confidence, class_id, box = max(candidates, key=lambda item: item[0])
            crop, padded_box = padded_crop(frame, box)
            destination = OUTPUT / split / class_name / f"{group}__{path.name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_image(destination, crop)

            annotated = frame.copy()
            x1, y1, x2, y2 = padded_box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 0), 3)
            debug_path = OUTPUT / "debug_boxes" / class_name / f"{group}__{path.name}"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            write_image(debug_path, annotated)
            row.update(
                status="accepted", crop=str(destination), confidence=f"{confidence:.6f}",
                prompt=model.names[class_id], box=json.dumps(padded_box),
            )
        rows.append(row)
        if index % 10 == 0 or index == len(sources):
            print(f"진행 {index}/{len(sources)}", flush=True)

    with (OUTPUT / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)

    accepted = [row for row in rows if row["status"] == "accepted"]
    summary = {
        "total": len(rows), "accepted": len(accepted), "rejected": len(rows) - len(accepted),
        "by_split_class": {
            f"{split}/{class_name}": count
            for (split, class_name), count in sorted(
                Counter((row["split"], row["class_name"]) for row in accepted).items()
            )
        },
        "split_strategies": split_strategies,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
