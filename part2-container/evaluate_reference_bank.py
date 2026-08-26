"""처음 본 순간 자동 촬영한 여러 프레임을 보관하는 방식의 효과를 검증한다."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "dinov2_validation_embeddings.npz"
OUTPUT = ROOT / "reference_bank_evaluation.json"


def natural_key(path: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path)]


def load_groups():
    if not CACHE.exists():
        raise SystemExit("먼저 python validate_reidentification.py 를 실행해야 합니다.")
    cached = np.load(CACHE, allow_pickle=False)
    paths = cached["paths"].tolist()
    embeddings = cached["embeddings"].astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    grouped = {}
    for path, vector in zip(paths, embeddings):
        folder = Path(path).parent.name
        label = folder.split(" ")[-1]
        grouped.setdefault(label, []).append((path, vector))
    for label in grouped:
        grouped[label].sort(key=lambda item: natural_key(item[0]))
    return grouped


def bank_score(query: np.ndarray, references: np.ndarray, method: str) -> float:
    scores = references @ query
    if method == "max":
        return float(scores.max())
    if method == "mean":
        centroid = references.mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        return float(centroid @ query)
    count = min(3, len(scores))
    return float(np.sort(scores)[-count:].mean())


def measure(grouped, reference_count: int, method: str):
    labels = sorted(grouped)
    banks = {
        label: np.stack([vector for _, vector in grouped[label][:reference_count]])
        for label in labels
    }
    same_scores, different_scores = [], []
    identity_correct = 0
    query_count = 0
    for true_label in labels:
        for _, query in grouped[true_label][reference_count:]:
            scores = {label: bank_score(query, bank, method) for label, bank in banks.items()}
            same_scores.append(scores[true_label])
            different_scores.extend(score for label, score in scores.items() if label != true_label)
            identity_correct += max(scores, key=scores.get) == true_label
            query_count += 1

    same = np.asarray(same_scores)
    different = np.asarray(different_scores)
    candidates = np.arange(0.20, 0.901, 0.001)
    best = None
    for threshold in candidates:
        same_accuracy = float(np.mean(same >= threshold))
        different_accuracy = float(np.mean(different < threshold))
        balanced = (same_accuracy + different_accuracy) / 2
        candidate = (balanced, threshold, same_accuracy, different_accuracy)
        if best is None or candidate > best:
            best = candidate
    balanced, threshold, same_accuracy, different_accuracy = best
    at_044_same = float(np.mean(same >= 0.44))
    at_044_different = float(np.mean(different < 0.44))
    return {
        "automatic_initial_frames": reference_count,
        "comparison_method": method,
        "test_images": query_count,
        "known_identity_accuracy": round(identity_correct / query_count, 6),
        "threshold_0.44_balanced_accuracy": round((at_044_same + at_044_different) / 2, 6),
        "recommended_threshold": round(float(threshold), 3),
        "recommended_balanced_accuracy": round(balanced, 6),
        "same_container_accuracy": round(same_accuracy, 6),
        "different_container_accuracy": round(different_accuracy, 6),
    }


def main():
    grouped = load_groups()
    results = []
    for reference_count in (1, 3, 5, 10):
        for method in ("max", "top3", "mean"):
            results.append(measure(grouped, reference_count, method))
    best = max(results, key=lambda item: item["recommended_balanced_accuracy"])
    report = {
        "meaning": "새 용기 최초 감지 때 사용자가 아닌 카메라가 연속 프레임을 자동 저장하는 방식",
        "results": results,
        "best_result": best,
        "limitation": "현재 3개 용기의 기존 촬영 데이터로 한 검증이며 실제 냉장고에서 다시 확인해야 함",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("자동 참고사진 저장 방식 비교")
    for item in results:
        print(
            f"  {item['automatic_initial_frames']:2d}프레임 / {item['comparison_method']:4s} | "
            f"추천 기준 {item['recommended_threshold']:.3f} | "
            f"균형 정확도 {item['recommended_balanced_accuracy'] * 100:5.2f}% | "
            f"등록된 3종 구분 {item['known_identity_accuracy'] * 100:5.2f}%"
        )
    print("\n가장 좋은 결과")
    print(json.dumps(best, ensure_ascii=False, indent=2))
    print(f"\n상세 결과: {OUTPUT.name}")


if __name__ == "__main__":
    main()
