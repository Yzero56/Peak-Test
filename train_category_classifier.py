"""YOLO 크롭을 DINOv2 특징으로 바꾸고 종류 분류기를 학습·평가한다."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from container_registry import DinoV2Embedder

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "category_dataset_prepared_v2"
MODEL_PATH = ROOT / "category_classifier_v2.joblib"
RESULT_PATH = ROOT / "category_classifier_v2_evaluation.json"
PREDICTIONS_PATH = ROOT / "category_classifier_v2_predictions.csv"
EMBEDDINGS_PATH = ROOT / "category_classifier_v2_embeddings.npz"
CLASSES = ["drink_container", "food_container", "water_bottle"]


def load_paths(split: str):
    paths, labels = [], []
    for label in CLASSES:
        for path in sorted((DATASET / split / label).glob("*.jpg")):
            paths.append(path); labels.append(label)
    return paths, np.asarray(labels)


def main() -> None:
    all_paths, all_labels, split_names = [], [], []
    split_ranges = {}
    for split in ("train", "val", "test"):
        paths, labels = load_paths(split)
        start = len(all_paths)
        all_paths.extend(paths); all_labels.extend(labels); split_names.extend([split] * len(paths))
        split_ranges[split] = slice(start, len(all_paths))
        print(f"{split}: {len(paths)}장 {dict(Counter(labels))}", flush=True)

    print("DINOv2 특징 추출 시작...", flush=True)
    embedder = DinoV2Embedder()
    features = embedder.extract_many(all_paths, batch_size=16)
    labels = np.asarray(all_labels)
    np.savez_compressed(
        EMBEDDINGS_PATH, features=features, labels=labels,
        splits=np.asarray(split_names), paths=np.asarray([str(path) for path in all_paths]),
    )

    train, val, test = (split_ranges[name] for name in ("train", "val", "test"))
    candidates = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0]
    tuning = []
    best_c, best_accuracy = None, -1.0
    for c_value in candidates:
        classifier = LogisticRegression(
            C=c_value, class_weight="balanced", max_iter=3000, random_state=20260825
        )
        classifier.fit(features[train], labels[train])
        prediction = classifier.predict(features[val])
        accuracy = float(accuracy_score(labels[val], prediction))
        tuning.append({"C": c_value, "validation_accuracy": accuracy})
        print(f"검증 C={c_value}: {accuracy:.3f}", flush=True)
        if accuracy > best_accuracy:
            best_c, best_accuracy = c_value, accuracy

    development_indices = np.r_[np.arange(train.start, train.stop), np.arange(val.start, val.stop)]
    classifier = LogisticRegression(
        C=best_c, class_weight="balanced", max_iter=3000, random_state=20260825
    )
    classifier.fit(features[development_indices], labels[development_indices])
    probabilities = classifier.predict_proba(features[test])
    predictions = classifier.classes_[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    test_accuracy = float(accuracy_score(labels[test], predictions))
    report = classification_report(
        labels[test], predictions, labels=CLASSES, output_dict=True, zero_division=0
    )
    matrix = confusion_matrix(labels[test], predictions, labels=CLASSES).tolist()

    # 평가는 위의 개발용 모델로 끝내고, 실제 운영 모델은 검증이 끝난 전체 사진으로 다시 학습한다.
    deployment_classifier = LogisticRegression(
        C=best_c, class_weight="balanced", max_iter=3000, random_state=20260825
    )
    deployment_classifier.fit(features, labels)
    joblib.dump(
        {"classifier": deployment_classifier, "classes": CLASSES,
         "feature_model": "dinov2_vits14", "input": "YOLO crop",
         "selected_C": best_c, "training_images": len(labels)}, MODEL_PATH
    )
    result = {
        "dataset_counts": dict(Counter(split_names)),
        "selected_C": best_c,
        "validation_tuning": tuning,
        "test_accuracy": test_accuracy,
        "classes": CLASSES,
        "confusion_matrix": matrix,
        "classification_report": report,
        "important_note": (
            "텀블러와 용기는 실제 물건 ID 단위 분리. 생수병은 실제 물건이 하나뿐이라 "
            "사진 단위 분리이며 새로운 생수병에 대한 일반화 정확도가 아님"
        ),
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with PREDICTIONS_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "true_label", "predicted_label", "confidence", "correct"])
        for path, true, predicted, score in zip(
            np.asarray(all_paths)[test], labels[test], predictions, confidence
        ):
            writer.writerow([path, true, predicted, f"{score:.6f}", true == predicted])

    print("\n최종 시험 결과", flush=True)
    print(f"정확도: {test_accuracy * 100:.1f}% ({sum(labels[test] == predictions)}/{len(predictions)})", flush=True)
    print(f"혼동행렬 {CLASSES}: {matrix}", flush=True)
    print(f"모델 저장: {MODEL_PATH}", flush=True)
    print(f"평가 저장: {RESULT_PATH}", flush=True)


if __name__ == "__main__":
    main()
