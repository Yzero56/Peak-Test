"""YOLO-World로 사진 속 용기 위치를 찾고 용기 부분을 잘라낸다."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLOWorld


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "yolov8m-worldv2.pt"
DEFAULT_CONFIDENCE = 0.02
CONTAINER_PROMPTS = [
    "plastic box",
    "plastic tub",
    "food storage box",
    "food container",
    "bottle",
    "water bottle",
    "plastic bowl",
]


@dataclass
class ContainerDetection:
    box: tuple[int, int, int, int]
    confidence: float
    prompt: str
    crop: np.ndarray


class ContainerDetector:
    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL,
        confidence: float = DEFAULT_CONFIDENCE,
        max_containers: int = 2,
        relative_confidence: float = 0.25,
    ):
        self.confidence = confidence
        self.max_containers = max_containers
        self.relative_confidence = relative_confidence
        self.model = YOLOWorld(str(model_path))
        self.model.set_classes(CONTAINER_PROMPTS)

    def detect(self, image: Path | str | np.ndarray) -> list[ContainerDetection]:
        result = self.model.predict(
            image,
            conf=self.confidence,
            imgsz=320,
            max_det=self.max_containers,
            agnostic_nms=True,
            verbose=False,
        )[0]
        source = result.orig_img
        detections = []
        strongest = float(result.boxes.conf.max()) if len(result.boxes) else 0.0
        for box, confidence, class_id in zip(
            result.boxes.xyxy, result.boxes.conf, result.boxes.cls
        ):
            if float(confidence) < strongest * self.relative_confidence:
                continue
            x1, y1, x2, y2 = (int(round(float(value))) for value in box)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(source.shape[1], x2), min(source.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append(
                ContainerDetection(
                    box=(x1, y1, x2, y2),
                    confidence=float(confidence),
                    prompt=self.model.names[int(class_id)],
                    crop=source[y1:y2, x1:x2].copy(),
                )
            )
        return detections


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"사진을 읽을 수 없습니다: {path}")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    suffix = path.suffix if path.suffix else ".jpg"
    ok, encoded = cv2.imencode(suffix, image)
    if not ok:
        raise ValueError(f"사진을 저장할 수 없습니다: {path}")
    encoded.tofile(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="사진에서 용기를 찾아 잘라냅니다.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "detected_containers")
    parser.add_argument("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    args = parser.parse_args()

    image = read_image(args.image)
    detector = ContainerDetector(confidence=args.confidence)
    detections = detector.detect(image)
    args.output.mkdir(parents=True, exist_ok=True)

    if not detections:
        print("용기를 찾지 못했습니다.")
        raise SystemExit(2)
    for index, detection in enumerate(detections, start=1):
        output_path = args.output / f"container_{index}.jpg"
        write_image(output_path, detection.crop)
        print(
            f"용기 {index}: 확률 {detection.confidence:.3f}, "
            f"위치 {detection.box}, 저장 {output_path}"
        )


if __name__ == "__main__":
    main()
