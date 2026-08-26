"""
evaluate.py — collect.py로 실제 냉장고에서 모은 라벨링된 사진들로 Wa 브랜치
용기 종류 분류기(category_classifier.joblib)의 정확도를 재검증한다.

collect.py와 분리한 이유: YOLO-World/DINOv2 모델을 불러오는 게 무겁고(수 GB
다운로드 포함 가능), 촬영은 여러 번 나눠 할 수 있지만 평가는 다 모은 다음
한 번에 돌리는 게 자연스러워서.

탐지 로직은 origin/Wa:browser_category_realtime.py의 CategoryRealtimeService와
동일하게 맞췄다 — 학습 데이터를 만들 때 쓴 클래스별 프롬프트(정답을 미리 아는
상태)가 아니라, 실제 판정처럼 전체 프롬프트를 한 번에 주고 탐지한다. 그래야
"실전에서 몇 % 맞히는지"에 가까운 수치가 나온다.

실행 (사진을 다 모은 뒤, 인터넷 되는 상태에서 — DINOv2/YOLO-World 최초 1회
다운로드 필요):
  ./.venv/bin/python tools/category_eval/evaluate.py

결과: docs/CATEGORY_FRIDGE_REPORT.md, docs/category_fridge_confusion_matrix.png,
data/category_eval_captures/predictions.csv
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import cv2
import joblib
import numpy as np
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dinov2_embedder import DinoV2Embedder  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "category_eval_captures"
MODEL_PATH = Path(__file__).resolve().parent / "category_classifier.joblib"
WEIGHTS_DIR = ROOT / "weights"
YOLO_WEIGHTS = WEIGHTS_DIR / "yolov8m-worldv2.pt"
DOCS_DIR = ROOT / "docs"
KOREAN_LABELS = {"drink_container": "텀블러", "food_container": "반찬 용기", "water_bottle": "생수병"}
CLASSES = ["drink_container", "food_container", "water_bottle"]

# origin/Wa:browser_category_realtime.py와 동일 — 실제 실시간 판정에서 쓰는
# "정답을 모르는 채로" 탐지하는 통합 프롬프트 목록.
PROMPTS = [
    "food storage container", "plastic food container", "lunch box", "plastic box",
    "tumbler", "travel mug", "coffee mug", "drinking cup", "water bottle",
]


def valid_detection(frame, box) -> bool:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    if bw <= 0 or bh <= 0:
        return False
    area = bw * bh / float(width * height)
    return 0.015 <= area <= 0.85 and bw / width < 0.97 and bh / height < 0.97


def detect_crop(model, frame):
    result = model.predict(frame, conf=0.02, imgsz=320, max_det=4, agnostic_nms=True, verbose=False)[0]
    candidates = []
    for box, confidence in zip(result.boxes.xyxy, result.boxes.conf):
        coords = tuple(int(round(float(v))) for v in box)
        if valid_detection(frame, coords):
            candidates.append((coords, float(confidence)))
    if not candidates:
        return None, None
    box, confidence = max(candidates, key=lambda item: item[1])
    x1, y1, x2, y2 = box
    return frame[y1:y2, x1:x2].copy(), confidence


def main() -> None:
    if not MODEL_PATH.exists():
        sys.exit(f"분류기 모델이 없습니다: {MODEL_PATH}")

    samples = []  # (path, true_label)
    for label in CLASSES:
        for path in sorted((DATA_DIR / label).glob("*.jpg")):
            samples.append((path, label))
    if not samples:
        sys.exit(
            f"{DATA_DIR}에 시험 사진이 없습니다. 먼저 collect.py로 실제 냉장고에서 "
            "라벨링된 사진을 모으세요."
        )
    print(f"시험 사진 {len(samples)}장 ({dict(Counter(label for _, label in samples))})")

    print("YOLO-World 모델 준비 중...")
    from ultralytics import YOLOWorld

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    detector = YOLOWorld(str(YOLO_WEIGHTS))
    detector.set_classes(PROMPTS)

    embedder = DinoV2Embedder()
    bundle = joblib.load(MODEL_PATH)
    classifier = bundle["classifier"]

    rows = []
    true_labels, predicted_labels = [], []
    missed = 0
    for path, true_label in samples:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"  [건너뜀] 읽기 실패: {path}")
            continue
        crop, detection_confidence = detect_crop(detector, frame)
        if crop is None:
            missed += 1
            rows.append([str(path), true_label, "미탐지", "", ""])
            print(f"  [미탐지] {path.name} (정답: {KOREAN_LABELS[true_label]})")
            continue
        pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        vector = embedder.extract_pil_images([pil])[0]
        probabilities = classifier.predict_proba([vector])[0]
        index = int(probabilities.argmax())
        predicted_label = str(classifier.classes_[index])
        confidence = float(probabilities[index])
        true_labels.append(true_label)
        predicted_labels.append(predicted_label)
        mark = "O" if predicted_label == true_label else "X"
        print(
            f"  [{mark}] {path.name}: 정답 {KOREAN_LABELS[true_label]} -> "
            f"예측 {KOREAN_LABELS[predicted_label]} ({confidence:.1%}, YOLO {detection_confidence:.2f})"
        )
        rows.append([str(path), true_label, predicted_label, f"{confidence:.4f}", f"{detection_confidence:.4f}"])

    predictions_path = DATA_DIR / "predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "true_label", "predicted_label", "confidence", "detection_confidence"])
        writer.writerows(rows)

    total = len(samples)
    detected = len(true_labels)
    accuracy_over_detected = (
        sum(t == p for t, p in zip(true_labels, predicted_labels)) / detected if detected else 0.0
    )
    accuracy_overall = sum(t == p for t, p in zip(true_labels, predicted_labels)) / total if total else 0.0

    print(f"\n총 {total}장 중 탐지 {detected}장, 미탐지 {missed}장")
    print(f"탐지된 사진 기준 정확도: {accuracy_over_detected:.1%}")
    print(f"전체(미탐지=오답 처리) 기준 정확도: {accuracy_overall:.1%}")

    report_lines = [
        "# 용기 종류 분류(Wa) 실제 냉장고 재검증",
        "",
        f"학습 때와 다른 실제 냉장고 카메라(문틀에 마운트된 XIAO ESP32S3+OV3660,",
        f"webcam_ap_capture.ino) 앞에서 새로 찍은 사진 {total}장으로 재검증.",
        "",
        "## 결과",
        "",
        f"- 탐지 {detected}장 / 미탐지(YOLO-World가 물체를 못 찾음) {missed}장",
        f"- **탐지된 사진 기준 정확도: {accuracy_over_detected:.1%}** ({sum(t==p for t,p in zip(true_labels,predicted_labels))}/{detected})",
        f"- 전체(미탐지를 오답으로 계산) 기준 정확도: {accuracy_overall:.1%}",
        "",
    ]
    if detected:
        cr = classification_report(true_labels, predicted_labels, labels=CLASSES, zero_division=0, output_dict=True)
        report_lines.append("| 클래스 | 재현율 | 정밀도 |")
        report_lines.append("|---|---|---|")
        for cls in CLASSES:
            stats = cr.get(cls, {})
            support = int(stats.get("support", 0))
            if support == 0:
                continue
            report_lines.append(
                f"| {KOREAN_LABELS[cls]} | {stats.get('recall',0):.1%} | {stats.get('precision',0):.1%} |"
            )
        report_lines.append("")
        report_lines.append("Confusion matrix: `category_fridge_confusion_matrix.png` 참고.")

        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        matrix = confusion_matrix(true_labels, predicted_labels, labels=CLASSES)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        # 기본 폰트(DejaVu Sans)는 한글이 없어서 라벨이 네모(tofu)로 깨진다 — macOS 기본 탑재
        # AppleGothic으로 바꿔서 텀블러/반찬 용기/생수병 라벨이 정상적으로 나오게 함.
        plt.rcParams["font.family"] = "AppleGothic"
        plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=(5, 4.5))
        im = ax.imshow(matrix, cmap="Blues")
        ko_labels = [KOREAN_LABELS[c] for c in CLASSES]
        ax.set_xticks(range(len(CLASSES)), labels=ko_labels)
        ax.set_yticks(range(len(CLASSES)), labels=ko_labels)
        ax.set_xlabel("예측"); ax.set_ylabel("정답")
        ax.set_title("용기 종류 분류 — 실제 냉장고 재검증")
        for i in range(len(CLASSES)):
            for j in range(len(CLASSES)):
                ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                        color="white" if matrix[i, j] > matrix.max() / 2 else "black")
        fig.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        fig.savefig(DOCS_DIR / "category_fridge_confusion_matrix.png", dpi=150)
        print(f"\n저장됨: {DOCS_DIR / 'category_fridge_confusion_matrix.png'}")
    else:
        report_lines.append("(탐지된 사진이 없어 confusion matrix를 만들지 못함)")

    report_path = DOCS_DIR / "CATEGORY_FRIDGE_REPORT.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"저장됨: {report_path}")
    print(f"저장됨: {predictions_path}")


if __name__ == "__main__":
    main()
