"""
dinov2_embedder.py — Wa 브랜치 origin/Wa:container_registry.py의 DinoV2Embedder를
그대로 옮겨온 것. 재검증 평가(evaluate.py)가 학습 때와 동일한 특징 추출 방식을
쓰도록 이 파일 하나로 분리했다 (원본은 SQLite 등록 로직까지 같이 있어서 무겁다).
"""
from __future__ import annotations

import numpy as np


def normalized(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(vector))
    if length == 0:
        raise ValueError("길이가 0인 특징 벡터는 저장할 수 없습니다.")
    return vector / length


class DinoV2Embedder:
    """DINOv2 모델은 실제로 특징을 뽑을 때만 불러온다(torch.hub, 최초 1회 인터넷 필요)."""

    def __init__(self):
        import torch
        from torchvision import transforms

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"DINOv2 모델 준비 중... (사용 장치: {self.device})")
        self.model = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14")
        self.model.eval().to(self.device)
        self.preprocess = transforms.Compose(
            [
                transforms.Resize(256, interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def extract_pil_images(self, images, batch_size: int = 16) -> np.ndarray:
        images = [image.convert("RGB") for image in images]
        if not images:
            return np.empty((0, 384), dtype=np.float32)
        vectors = []
        for start in range(0, len(images), batch_size):
            batch_images = images[start : start + batch_size]
            batch = self.torch.stack([self.preprocess(image) for image in batch_images])
            with self.torch.no_grad():
                output = self.model(batch.to(self.device)).cpu().numpy()
            vectors.extend(normalized(vector) for vector in output)
        return np.stack(vectors)
