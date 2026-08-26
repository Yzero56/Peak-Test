"""더 큰 DINOv2 Base 모델이 재식별 정확도를 높이는지 검증한다."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from experiment_dinov2_features import evaluate, image_groups, unit


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "dinov2_vitb14_embeddings.npz"
OUTPUT = ROOT / "dinov2_base_experiment.json"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def main():
    groups = image_groups()
    paths = [path for items in groups.values() for path in items]
    expected = [str(path.resolve()) for path in paths]
    vectors = None
    if CACHE.exists():
        cache = np.load(CACHE, allow_pickle=False)
        if cache["paths"].tolist() == expected:
            vectors = cache["embeddings"]
            print("저장된 DINOv2 Base 특징을 재사용합니다.")
    if vectors is None:
        print(f"DINOv2 Base 준비 중... (사용 장치: {DEVICE})")
        model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14")
        model.eval().to(DEVICE)
        preprocess = transforms.Compose([
            transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        parts = []
        batch_size = 8
        for start in range(0, len(paths), batch_size):
            batch_paths = paths[start:start + batch_size]
            batch = torch.stack([preprocess(Image.open(path).convert("RGB")) for path in batch_paths])
            with torch.no_grad():
                parts.append(model(batch.to(DEVICE)).cpu().numpy())
            print(f"  {min(start + batch_size, len(paths))}/{len(paths)}장 완료")
        vectors = unit(np.concatenate(parts).astype(np.float32))
        np.savez_compressed(CACHE, paths=np.array(expected), embeddings=vectors)

    result = evaluate(groups, unit(vectors))
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nDINOv2 Base 결과")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"상세 결과: {OUTPUT.name}")


if __name__ == "__main__":
    main()
