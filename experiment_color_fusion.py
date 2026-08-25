"""DINOv2 모양 특징과 공간별 HSV 색상 특징을 결합해 검증한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

from experiment_dinov2_features import evaluate, image_groups, unit


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DINO_CACHE = ROOT / "dinov2_feature_variants.npz"
OUTPUT = ROOT / "color_fusion_experiment.json"


def spatial_hsv(path: Path) -> np.ndarray:
    # cv2.imread는 Windows 한글 경로를 읽지 못하므로 바이트로 읽어 디코딩한다.
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"사진을 읽을 수 없습니다: {path}")
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    height, width = hsv.shape[:2]
    features = []
    # 전체 색상과 2x2 위치별 색상을 함께 기억한다.
    regions = [hsv]
    for y in range(2):
        for x in range(2):
            regions.append(hsv[y * height // 2:(y + 1) * height // 2,
                               x * width // 2:(x + 1) * width // 2])
    for region in regions:
        histogram = cv2.calcHist([region], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256])
        features.append(histogram.reshape(-1))
    vector = np.concatenate(features).astype(np.float32)
    length = np.linalg.norm(vector)
    return vector / length


def main():
    groups = image_groups()
    all_paths = [path for paths in groups.values() for path in paths]
    cache = np.load(DINO_CACHE, allow_pickle=False)
    if cache["paths"].tolist() != [str(path.resolve()) for path in all_paths]:
        raise SystemExit("DINOv2 캐시의 사진 순서가 다릅니다. 특징 실험을 다시 실행하세요.")
    dino = unit(cache["cls"].astype(np.float32))
    print("사진의 색상 특징 계산 중...")
    color = unit(np.stack([spatial_hsv(path) for path in all_paths]))

    results = {}
    results["color_only"] = evaluate(groups, color)
    for dino_weight in np.arange(0.1, 1.0, 0.1):
        combined = np.concatenate(
            [np.sqrt(dino_weight) * dino, np.sqrt(1 - dino_weight) * color], axis=1
        )
        name = f"dino_{dino_weight:.1f}_color_{1-dino_weight:.1f}"
        results[name] = evaluate(groups, combined)
    best_name = max(results, key=lambda name: results[name]["balanced_accuracy"])
    report = {"results": results, "best_method": best_name, "best_result": results[best_name]}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n색상 결합 결과")
    for name, result in results.items():
        print(
            f"  {name:25s}: 균형 정확도 {result['balanced_accuracy'] * 100:5.2f}% / "
            f"3종 구분 {result['known_identity_accuracy'] * 100:5.2f}%"
        )
    print(f"\n최고 방식: {best_name}")
    print(json.dumps(results[best_name], ensure_ascii=False, indent=2))
    print(f"상세 결과: {OUTPUT.name}")


if __name__ == "__main__":
    main()
