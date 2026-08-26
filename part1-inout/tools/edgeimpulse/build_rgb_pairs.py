"""
build_rgb_pairs.py — 기존 "좌우로 이어붙인 pair 이미지"들을 R/G/B 채널
인코딩 방식으로 다시 만든다.

배경: EI 모델이 좌우(before/after)를 뒤바꿔도 예측이 거의 안 바뀌는 문제를
발견했다 — 모델이 "두 이미지를 대조"하는 대신 이미지 전체의 우연한 특징(밝기,
분위기)에 반응하고 있었다는 뜻. 원인은 292x219짜리 좌우 합성사진을 96x96으로
squash(뭉개기)하면서 모델이 "왼쪽 vs 오른쪽 대조"를 스스로 학습하기보다 쉬운
지름길을 택했을 가능성이 크다.

고치는 방법: before를 R채널, after를 G채널, 픽셀 차이(diff)를 B채널에 담아
하나의 96x96x3 이미지로 만든다. 이러면 모델이 diff 채널을 무시하고는 분류를
할 수가 없다 — 채널 자체가 "차이"를 명시적으로 담고 있기 때문.

기존 pair 이미지(가운데 6px, RGB(240,60,60) 빨간 구분선으로 나뉜 좌/우 합성)에서
divider를 다시 찾아 좌/우를 분리해낸다 — 재촬영 불필요, 기존 데이터 재사용.

사용법:
    python build_rgb_pairs.py [--out-dir ../../data/rgb_pairs] [--min-diff-pct 0.5]
"""
import argparse
import glob
import os
import re
import sys

import numpy as np
from PIL import Image

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw_captures")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rgb_pairs")

DIVIDER_COLOR = np.array([240, 60, 60], dtype=np.float32)
DIVIDER_TOL = 40  # 색 거리 허용치
MODEL_SIZE = 96


def find_divider(arr: np.ndarray) -> tuple[int, int] | None:
    """arr: (h, w, 3) uint8. 세로로 쭉 이어지는 빨간 구분선의 [start, end) x범위를 찾는다."""
    h, w, _ = arr.shape
    dist = np.linalg.norm(arr.astype(np.float32) - DIVIDER_COLOR, axis=2)  # (h, w)
    is_divider_col = (dist < DIVIDER_TOL).mean(axis=0) > 0.8  # 그 열의 80%+ 픽셀이 divider색
    cols = np.where(is_divider_col)[0]
    if len(cols) == 0:
        return None
    # 가운데 부근에서 연속된 구간 찾기 (가장자리 우연한 매치 배제)
    center = w // 2
    near_center = cols[np.abs(cols - center) < w * 0.3]
    if len(near_center) == 0:
        return None
    start, end = int(near_center.min()), int(near_center.max()) + 1
    return start, end


def split_pair(jpeg_path: str) -> tuple[np.ndarray, np.ndarray] | None:
    """pair 이미지를 (before_rgb, after_rgb) numpy 배열로 분리."""
    img = Image.open(jpeg_path).convert("RGB")
    arr = np.asarray(img)
    div = find_divider(arr)
    if div is None:
        return None
    start, end = div
    before = arr[:, :start]
    after = arr[:, end:]
    if before.shape[1] < 10 or after.shape[1] < 10:
        return None
    return before, after


def encode_rgb(before: np.ndarray, after: np.ndarray) -> tuple[Image.Image, float]:
    """before=R, after=G, diff=B로 인코딩. 밝기 변화(AEC)는 보정 후 diff 계산.
    반환: (인코딩된 이미지, diff_pct) — diff_pct는 필터링용."""
    b_img = Image.fromarray(before).convert("L").resize((MODEL_SIZE, MODEL_SIZE))
    a_img = Image.fromarray(after).convert("L").resize((MODEL_SIZE, MODEL_SIZE))
    b = np.asarray(b_img, dtype=np.float32)
    a = np.asarray(a_img, dtype=np.float32)

    shift = float(a.mean() - b.mean())
    diff = np.abs(b - (a - shift))
    diff_pct = round(float((diff > 30).mean()) * 100, 2)
    diff_u8 = np.clip(diff, 0, 255).astype(np.uint8)

    rgb = np.stack([b.astype(np.uint8), a.astype(np.uint8), diff_u8], axis=2)
    return Image.fromarray(rgb, mode="RGB"), diff_pct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--min-diff-pct", type=float, default=0.5,
                     help="in/out에만 적용 — 이보다 diff%%가 낮으면 변화 없는 실패 캡처로 보고 제외")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # in-pair/out-pair는 hand-free before/after 방식(10자리 타임스탬프)만,
    # hand_only-pair는 그 방식 데이터가 없어서 burst 방식(13자리)을 그대로 쓴다.
    plans = [
        ("in-pair", r"in-pair_(\d{10})_(\d+)\.jpg", True),
        ("out-pair", r"out-pair_(\d{10})_(\d+)\.jpg", True),
        ("hand_only-pair", r"hand_only-pair_(\d{13})_(\d+)\.jpg", False),
    ]

    stats = {}
    for label, pattern, apply_filter in plans:
        rx = re.compile(pattern)
        files = sorted(f for f in os.listdir(RAW_DIR) if rx.match(f))
        kept = skipped_split = skipped_diff = 0
        for fname in files:
            path = os.path.join(RAW_DIR, fname)
            split = split_pair(path)
            if split is None:
                skipped_split += 1
                continue
            before, after = split
            encoded, diff_pct = encode_rgb(before, after)
            if apply_filter and diff_pct < args.min_diff_pct:
                skipped_diff += 1
                continue
            m = rx.match(fname)
            ts, idx = m.group(1), m.group(2)
            # train_pipeline.py의 FNAME_RE는 "<label>_<ts>_<idx3자리>.jpg"에서
            # label을 그대로 뽑아쓰므로, 기존 라벨명(in-pair/out-pair/hand_only-pair)을
            # 그대로 유지한다 — "-rgb" 접미사를 붙이면 새 라벨로 갈라져버린다.
            out_name = f"{label}_{ts}_{idx}.jpg"
            encoded.save(os.path.join(args.out_dir, out_name), format="JPEG", quality=95)
            kept += 1
        stats[label] = (kept, skipped_split, skipped_diff)
        print(f"{label}: kept={kept} skipped(분리실패)={skipped_split} skipped(diff낮음)={skipped_diff}")

    total = sum(s[0] for s in stats.values())
    print(f"\n총 {total}장 -> {args.out_dir}")


if __name__ == "__main__":
    main()
