"""수집한 사진 전체로 용기 재식별 임계값을 검증한다."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

from container_registry import DinoV2Embedder, normalized


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "retest_data"
DEFAULT_CACHE = ROOT / "dinov2_validation_embeddings.npz"
DEFAULT_JSON = ROOT / "reidentification_validation.json"
DEFAULT_CSV = ROOT / "reidentification_validation.csv"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_groups(data_dir: Path) -> dict[str, list[Path]]:
    groups = {}
    for folder in sorted(path for path in data_dir.iterdir() if path.is_dir()):
        label = folder.name.split(" ")[-1]
        images = sorted(
            path for path in folder.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES
        )
        if images:
            groups[label] = images
    if len(groups) < 2:
        raise ValueError("서로 다른 용기 사진 폴더가 최소 2개 필요합니다.")
    return groups


def load_or_extract(groups: dict[str, list[Path]], cache_path: Path, rebuild: bool):
    expected_paths = [str(path.resolve()) for paths in groups.values() for path in paths]
    if cache_path.exists() and not rebuild:
        cached = np.load(cache_path, allow_pickle=False)
        cached_paths = cached["paths"].tolist()
        if cached_paths == expected_paths:
            print(f"저장된 디지털 지문을 재사용합니다: {cache_path.name}")
            return cached["embeddings"]
        print("사진 목록이 달라 디지털 지문을 다시 만듭니다.")

    embedder = DinoV2Embedder()
    vectors = []
    total = len(expected_paths)
    done = 0
    for label, paths in groups.items():
        print(f"[{label}] 사진 {len(paths)}장 처리 중...")
        group_vectors = embedder.extract_many(paths)
        vectors.extend(group_vectors)
        done += len(paths)
        print(f"  전체 {done}/{total}장 완료")
    embeddings = np.stack(vectors).astype(np.float32)
    np.savez_compressed(cache_path, paths=np.array(expected_paths), embeddings=embeddings)
    print(f"디지털 지문 저장 완료: {cache_path.name}")
    return embeddings


def pair_scores(groups: dict[str, list[Path]], embeddings: np.ndarray):
    labels = []
    for label, paths in groups.items():
        labels.extend([label] * len(paths))
    matrix = embeddings @ embeddings.T
    same, different = [], []
    for i, j in combinations(range(len(labels)), 2):
        (same if labels[i] == labels[j] else different).append(float(matrix[i, j]))
    return np.asarray(same), np.asarray(different)


def measurements(same: np.ndarray, different: np.ndarray, threshold: float) -> dict:
    same_correct = float(np.mean(same >= threshold))
    different_correct = float(np.mean(different < threshold))
    return {
        "threshold": round(float(threshold), 4),
        "same_container_accuracy": round(same_correct, 6),
        "different_container_accuracy": round(different_correct, 6),
        "balanced_accuracy": round((same_correct + different_correct) / 2, 6),
        "same_container_missed": int(np.sum(same < threshold)),
        "different_container_confused": int(np.sum(different >= threshold)),
    }


def choose_threshold(same: np.ndarray, different: np.ndarray) -> dict:
    candidates = np.arange(0.20, 0.801, 0.001)
    results = [measurements(same, different, value) for value in candidates]
    return max(results, key=lambda item: (item["balanced_accuracy"], item["threshold"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="용기 사진 전체로 재식별 정확도를 측정합니다.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--threshold", type=float, default=0.44)
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args()

    groups = find_groups(args.data)
    print("검사 대상:", ", ".join(f"{name} {len(paths)}장" for name, paths in groups.items()))
    embeddings = load_or_extract(groups, DEFAULT_CACHE, args.rebuild_cache)
    embeddings = np.stack([normalized(vector) for vector in embeddings])
    same, different = pair_scores(groups, embeddings)

    current = measurements(same, different, args.threshold)
    recommended = choose_threshold(same, different)
    report = {
        "containers": {name: len(paths) for name, paths in groups.items()},
        "same_pairs": len(same),
        "different_pairs": len(different),
        "same_similarity": {
            "mean": round(float(same.mean()), 6),
            "min": round(float(same.min()), 6),
            "max": round(float(same.max()), 6),
        },
        "different_similarity": {
            "mean": round(float(different.mean()), 6),
            "min": round(float(different.min()), 6),
            "max": round(float(different.max()), 6),
        },
        "current_threshold_result": current,
        "recommended_threshold_result": recommended,
        "warning": "용기 3개로 얻은 임시 결과이며, 용기가 늘면 다시 검증해야 합니다.",
    }
    DEFAULT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with DEFAULT_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["구분", "사진쌍 수", "평균", "최솟값", "최댓값"])
        writer.writerow(["같은 용기", len(same), same.mean(), same.min(), same.max()])
        writer.writerow(["다른 용기", len(different), different.mean(), different.min(), different.max()])

    print("\n현재 기준값 검사")
    print(f"  기준값: {current['threshold']:.3f}")
    print(f"  같은 용기 정답률: {current['same_container_accuracy'] * 100:.2f}%")
    print(f"  다른 용기 정답률: {current['different_container_accuracy'] * 100:.2f}%")
    print(f"  균형 정확도: {current['balanced_accuracy'] * 100:.2f}%")
    print("\n데이터상 추천 기준값")
    print(f"  기준값: {recommended['threshold']:.3f}")
    print(f"  균형 정확도: {recommended['balanced_accuracy'] * 100:.2f}%")
    print(f"\n상세 결과 저장: {DEFAULT_JSON.name}, {DEFAULT_CSV.name}")
    print("주의: 현재 용기 3개만 사용한 임시 결과입니다. 용기가 늘면 다시 검사해야 합니다.")


if __name__ == "__main__":
    main()
