"""기존 300장을 YOLO로 자른 뒤 세 용기를 별도 시험 DB에 미리 등록한다."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from container_detector import ContainerDetector, read_image
from container_registry import ContainerDatabase, DinoV2Embedder, normalized, vector_to_blob


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "retest_data"
OUTPUT_DB = ROOT / "known_containers.db"
REPORT = ROOT / "known_containers_report.json"


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def groups():
    result = {}
    for folder in sorted(path for path in DATA.iterdir() if path.is_dir()):
        images = sorted(folder.glob("*.jpg"), key=natural_key)
        if images:
            result[folder.name.split(" ")[-1]] = images
    return result


def insert_known(database, container_id, vectors):
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    representative = normalized(np.mean(vectors, axis=0))
    database.connection.execute(
        """INSERT INTO containers
           (container_id, feature_vector, content, registered_at, last_seen, observation_count)
           VALUES (?, ?, '', ?, ?, ?)""",
        (container_id, vector_to_blob(representative), timestamp, timestamp, len(vectors)),
    )
    database.connection.executemany(
        """INSERT INTO container_features (container_id, feature_vector, captured_at)
           VALUES (?, ?, ?)""",
        [(container_id, vector_to_blob(vector), timestamp) for vector in vectors],
    )
    database.connection.commit()


def main():
    if OUTPUT_DB.exists():
        raise SystemExit(
            f"안전을 위해 기존 DB를 덮어쓰지 않습니다: {OUTPUT_DB}\n"
            "기존 파일을 보존하거나 이름을 바꾼 뒤 다시 실행하세요."
        )
    image_groups = groups()
    print("사전 등록 대상:", ", ".join(f"{name} {len(paths)}장" for name, paths in image_groups.items()))
    detector = ContainerDetector(max_containers=1)
    embedder = DinoV2Embedder()
    database = ContainerDatabase(OUTPUT_DB)
    report = {"database": str(OUTPUT_DB), "containers": {}}

    try:
        for number, (label, paths) in enumerate(image_groups.items(), start=1):
            container_id = f"Container_{number:03d}"
            crops, skipped = [], []
            print(f"\n[{label}] YOLO로 용기 자르는 중...")
            for index, path in enumerate(paths, start=1):
                detections = detector.detect(read_image(path))
                if detections:
                    crop_rgb = cv2.cvtColor(detections[0].crop, cv2.COLOR_BGR2RGB)
                    crops.append(Image.fromarray(crop_rgb))
                else:
                    skipped.append(path.name)
                if index % 20 == 0:
                    print(f"  {index}/{len(paths)}장 완료")
            if not crops:
                raise RuntimeError(f"{label}: YOLO가 용기를 한 장도 찾지 못했습니다.")
            print(f"[{label}] DINOv2 특징 {len(crops)}장 추출 중...")
            vectors = embedder.extract_pil_images(crops)
            insert_known(database, container_id, vectors)
            report["containers"][container_id] = {
                "label_for_test": label,
                "source_images": len(paths),
                "registered_features": len(vectors),
                "yolo_skipped": skipped,
            }
            print(f"[{label}] {container_id}로 특징 {len(vectors)}개 등록 완료")
    finally:
        database.close()

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료 DB: {OUTPUT_DB}")
    print(f"등록 보고서: {REPORT}")


if __name__ == "__main__":
    main()
