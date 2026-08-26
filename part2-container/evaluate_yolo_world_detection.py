"""사전학습 YOLO-World가 기존 용기 300장의 위치를 찾는지 검사한다."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLOWorld


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "retest_data"
OUTPUT = ROOT / "yolo_world_evaluation"
MODEL = ROOT / "yolov8m-worldv2.pt"
PROMPTS = [
    "plastic box",
    "plastic tub",
    "food storage box",
    "food container",
    "bottle",
    "water bottle",
    "plastic bowl",
]
THRESHOLDS = [0.01, 0.02, 0.03, 0.05, 0.10, 0.25]


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def collect_images():
    groups = {}
    for folder in sorted(path for path in DATA.iterdir() if path.is_dir()):
        paths = sorted(folder.glob("*.jpg"), key=natural_key)
        if paths:
            groups[folder.name.split(" ")[-1]] = paths
    return groups


def save_annotated(result, output_path: Path):
    image = result.plot()
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if ok:
        encoded.tofile(output_path)


def main():
    OUTPUT.mkdir(exist_ok=True)
    sample_dir = OUTPUT / "samples"
    sample_dir.mkdir(exist_ok=True)
    groups = collect_images()
    model = YOLOWorld(MODEL)
    model.set_classes(PROMPTS)
    rows = []
    label_counts = defaultdict(int)
    total = sum(len(paths) for paths in groups.values())
    completed = 0

    for label, paths in groups.items():
        print(f"[{label}] {len(paths)}장 검사 중...")
        results = model.predict(
            [str(path) for path in paths], conf=0.01, imgsz=320,
            batch=16, verbose=False,
        )
        for index, (path, result) in enumerate(zip(paths, results), start=1):
            if len(result.boxes):
                best_index = int(result.boxes.conf.argmax())
                confidence = float(result.boxes.conf[best_index])
                class_id = int(result.boxes.cls[best_index])
                box = result.boxes.xyxy[best_index].cpu().tolist()
                width, height = result.orig_shape[1], result.orig_shape[0]
                area_ratio = ((box[2] - box[0]) * (box[3] - box[1])) / (width * height)
                predicted_name = model.names[class_id]
                label_counts[(label, predicted_name)] += 1
            else:
                confidence, predicted_name, area_ratio = 0.0, "없음", 0.0
                box = [0.0, 0.0, 0.0, 0.0]
            rows.append({
                "실제_폴더": label,
                "파일": str(path.relative_to(ROOT)),
                "최고_후보": predicted_name,
                "확률": confidence,
                "상자_화면비율": area_ratio,
                "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3],
            })
            if index in {1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100}:
                save_annotated(result, sample_dir / f"{label}_{index:03d}.jpg")
        completed += len(paths)
        print(f"  전체 {completed}/{total}장 완료")

    csv_path = OUTPUT / "detections.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = {"model": MODEL.name, "prompts": PROMPTS, "total_images": total, "groups": {}}
    for label in groups:
        group_rows = [row for row in rows if row["실제_폴더"] == label]
        summary["groups"][label] = {
            "images": len(group_rows),
            "detection_rate_by_threshold": {
                str(value): round(sum(row["확률"] >= value for row in group_rows) / len(group_rows), 4)
                for value in THRESHOLDS
            },
            "mean_best_confidence": round(float(np.mean([row["확률"] for row in group_rows])), 4),
            "median_box_screen_ratio": round(float(np.median([row["상자_화면비율"] for row in group_rows])), 4),
            "predicted_prompt_counts": {
                prompt: label_counts[(label, prompt)] for prompt in PROMPTS if label_counts[(label, prompt)]
            },
        }
    summary["overall_detection_rate_by_threshold"] = {
        str(value): round(sum(row["확률"] >= value for row in rows) / len(rows), 4)
        for value in THRESHOLDS
    }
    json_path = OUTPUT / "summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n기준값별 전체 탐지율")
    for threshold, rate in summary["overall_detection_rate_by_threshold"].items():
        print(f"  {float(threshold):.2f}: {rate * 100:.1f}%")
    print(f"\n결과: {json_path}")
    print(f"표본 이미지: {sample_dir}")


if __name__ == "__main__":
    main()
