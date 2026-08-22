"""객체 인식(VLM) 연동 지점.

지금은 mock_detector()가 더미 라벨을 반환한다. 실제 VLM(Claude/OpenAI/Gemini)을
연동할 때는 detect_objects()의 구현부만 교체하면 되고, 호출부(routers/ingest.py)는
바꿀 필요가 없다.
"""

import random
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Detection:
    label: str
    confidence: float


_MOCK_LABELS = [
    "대파", "우유", "애호박", "닭가슴살", "식빵", "시금치", "연어", "플레인요거트",
    "파프리카", "두부", "계란", "당근", "양파", "버터", "방울토마토", "삼겹살",
]


def mock_detector(image_path: Path) -> list[Detection]:
    del image_path  # 목업 단계에서는 이미지 내용을 실제로 분석하지 않음
    count = random.randint(1, 3)
    labels = random.sample(_MOCK_LABELS, count)
    return [Detection(label=label, confidence=round(random.uniform(0.6, 0.98), 2)) for label in labels]


def detect_objects(image_path: Path) -> list[Detection]:
    """현재는 mock_detector 고정. 실제 VLM 연동 시 이 함수 내부만 교체하면 됨."""
    return mock_detector(image_path)
