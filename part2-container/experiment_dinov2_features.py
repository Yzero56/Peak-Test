"""DINOv2의 전체 특징과 부분 특징 조합을 비교한다."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import transforms


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "retest_data"
CACHE = ROOT / "dinov2_feature_variants.npz"
OUTPUT = ROOT / "dinov2_feature_experiment.json"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def image_groups():
    groups = {}
    for folder in sorted(path for path in DATA.iterdir() if path.is_dir()):
        paths = sorted(folder.glob("*.jpg"), key=natural_key)
        if paths:
            groups[folder.name.split(" ")[-1]] = paths
    return groups


def unit(values: np.ndarray) -> np.ndarray:
    return values / np.linalg.norm(values, axis=1, keepdims=True)


def extract(groups):
    all_paths = [path for paths in groups.values() for path in paths]
    expected = [str(path.resolve()) for path in all_paths]
    if CACHE.exists():
        cache = np.load(CACHE, allow_pickle=False)
        if cache["paths"].tolist() == expected:
            print("저장된 실험 특징을 재사용합니다.")
            return {name: cache[name] for name in cache.files if name != "paths"}

    print(f"DINOv2 준비 중... (사용 장치: {DEVICE})")
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14")
    model.eval().to(DEVICE)
    preprocess = transforms.Compose([
        transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    collected = {"cls": [], "patch_mean": [], "cls_patch": []}
    batch_size = 16
    for start in range(0, len(all_paths), batch_size):
        batch_paths = all_paths[start:start + batch_size]
        batch = torch.stack([preprocess(Image.open(path).convert("RGB")) for path in batch_paths])
        with torch.no_grad():
            features = model.forward_features(batch.to(DEVICE))
            cls = features["x_norm_clstoken"].cpu().numpy()
            patch_mean = features["x_norm_patchtokens"].mean(dim=1).cpu().numpy()
        collected["cls"].append(cls)
        collected["patch_mean"].append(patch_mean)
        collected["cls_patch"].append(np.concatenate([unit(cls), unit(patch_mean)], axis=1))
        print(f"  {min(start + batch_size, len(all_paths))}/{len(all_paths)}장 완료")
    result = {name: unit(np.concatenate(parts)) for name, parts in collected.items()}
    np.savez_compressed(CACHE, paths=np.array(expected), **result)
    return result


def score(query, references, method):
    similarities = references @ query
    if method == "max":
        return float(similarities.max())
    count = min(3, len(similarities))
    return float(np.sort(similarities)[-count:].mean())


def evaluate(groups, embeddings, reference_count=10, method="top3"):
    labels = list(groups)
    offsets, position = {}, 0
    for label, paths in groups.items():
        offsets[label] = (position, position + len(paths))
        position += len(paths)
    banks = {
        label: embeddings[start:start + reference_count]
        for label, (start, _) in offsets.items()
    }
    same, different = [], []
    identity_correct = total = 0
    for true_label, (start, end) in offsets.items():
        for query in embeddings[start + reference_count:end]:
            scores = {label: score(query, bank, method) for label, bank in banks.items()}
            same.append(scores[true_label])
            different.extend(value for label, value in scores.items() if label != true_label)
            identity_correct += max(scores, key=scores.get) == true_label
            total += 1
    same, different = np.asarray(same), np.asarray(different)
    best = None
    for threshold in np.arange(-0.10, 0.951, 0.001):
        same_accuracy = float(np.mean(same >= threshold))
        different_accuracy = float(np.mean(different < threshold))
        balanced = (same_accuracy + different_accuracy) / 2
        candidate = (balanced, threshold, same_accuracy, different_accuracy)
        if best is None or candidate > best:
            best = candidate
    balanced, threshold, same_accuracy, different_accuracy = best
    return {
        "recommended_threshold": round(float(threshold), 3),
        "balanced_accuracy": round(balanced, 6),
        "same_accuracy": round(same_accuracy, 6),
        "different_accuracy": round(different_accuracy, 6),
        "known_identity_accuracy": round(identity_correct / total, 6),
    }


def main():
    groups = image_groups()
    variants = extract(groups)
    results = {name: evaluate(groups, vectors) for name, vectors in variants.items()}
    best_name = max(results, key=lambda name: results[name]["balanced_accuracy"])
    report = {"results": results, "best_feature": best_name, "best_result": results[best_name]}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n특징 방식별 결과")
    for name, result in results.items():
        print(
            f"  {name:10s}: 균형 정확도 {result['balanced_accuracy'] * 100:.2f}% / "
            f"3종 구분 {result['known_identity_accuracy'] * 100:.2f}% / "
            f"추천 기준 {result['recommended_threshold']:.3f}"
        )
    print(f"\n최고 방식: {best_name}")
    print(f"상세 결과: {OUTPUT.name}")


if __name__ == "__main__":
    main()
