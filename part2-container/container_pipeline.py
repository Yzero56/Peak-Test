"""사진 → YOLO 위치 탐지 → DINOv2 재식별 → SQLite 저장 통합 프로그램."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
from PIL import Image

from container_detector import ContainerDetector, read_image, write_image
from container_registry import (
    DEFAULT_DB,
    DEFAULT_THRESHOLD,
    ContainerDatabase,
    DinoV2Embedder,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent


def analyze_image(
    image_path: Path,
    database: ContainerDatabase,
    detector: ContainerDetector,
    embedder: DinoV2Embedder,
    identity_threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[dict], object]:
    frame = read_image(image_path)
    return analyze_frame(frame, database, detector, embedder, identity_threshold)


def analyze_frame(
    frame,
    database: ContainerDatabase,
    detector: ContainerDetector,
    embedder: DinoV2Embedder,
    identity_threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[dict], object]:
    detections = detector.detect(frame)
    if not detections:
        return [], frame

    pil_crops = [
        Image.fromarray(cv2.cvtColor(detection.crop, cv2.COLOR_BGR2RGB))
        for detection in detections
    ]
    vectors = embedder.extract_pil_images(pil_crops)
    results = []
    annotated = frame.copy()
    for detection, vector in zip(detections, vectors):
        identity = database.recognize_or_register(vector, threshold=identity_threshold)
        item = {
            "status": identity["status"],
            "container_id": identity["container_id"],
            "identity_similarity": identity["similarity"],
            "content": identity["content"],
            "detection_confidence": detection.confidence,
            "detection_prompt": detection.prompt,
            "box": list(detection.box),
        }
        results.append(item)

        x1, y1, x2, y2 = detection.box
        color = (0, 200, 0) if identity["status"] == "matched" else (0, 165, 255)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        text = f"{identity['container_id']} {detection.confidence:.2f}"
        text_y = max(18, y1 - 7)
        cv2.putText(
            annotated, text, (x1, text_y), cv2.FONT_HERSHEY_SIMPLEX,
            0.5, color, 2, cv2.LINE_AA,
        )
    return results, annotated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="사진에서 용기를 찾아 신규 등록하거나 기존 용기로 재식별합니다."
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=ROOT / "pipeline_result.jpg")
    parser.add_argument("--identity-threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    print("YOLO 용기 탐지 모델 준비 중...")
    detector = ContainerDetector()
    embedder = DinoV2Embedder()
    database = ContainerDatabase(args.db)
    try:
        results, annotated = analyze_image(
            args.image, database, detector, embedder, args.identity_threshold
        )
    finally:
        database.close()

    if not results:
        print("용기를 찾지 못했습니다.")
        raise SystemExit(2)
    write_image(args.output, annotated)
    for item in results:
        if item["status"] == "registered":
            print(f"새 용기 등록: {item['container_id']}")
        else:
            print(
                f"기존 용기 인식: {item['container_id']} "
                f"(유사도 {item['identity_similarity']:.4f})"
            )
        print(f"  탐지 확률: {item['detection_confidence']:.4f}")
        print(f"  내용물: {item['content'] or '아직 입력하지 않음'}")
    print(f"결과 이미지: {args.output}")
    print("결과 JSON:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
