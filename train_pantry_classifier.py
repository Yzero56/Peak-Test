"""pantry_dataset_prepared를 DINOv2 특징으로 바꾸고 재료 분류기를 학습·평가한다."""

from __future__ import annotations

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
DATASET = ROOT / "pantry_dataset_prepared"
MODEL_PATH = ROOT / "pantry_classifier.joblib"
RESULT_PATH = ROOT / "pantry_classifier_evaluation.json"
PREDICTIONS_PATH = ROOT / "pantry_classifier_predictions.csv"
EMBEDDINGS_PATH = ROOT / "pantry_classifier_embeddings.npz"
CLASSES = sorted(p.name for p in (DATASET / "train").iterdir() if p.is_dir())


def load_paths(split: str):
    paths, labels = [], []
    for label in CLASSES:
        folder = DATASET / split / label
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*")):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                paths.append(path); labels.append(label)
    return paths, np.asarray(labels)


def main() -> None:
    print(f"클래스 {len(CLASSES)}개: {CLASSES}", flush=True)
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
            C=c_value, class_weight="balanced", max_iter=3000, random_state=20260827
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
        C=best_c, class_weight="balanced", max_iter=3000, random_state=20260827
    )
    classifier.fit(features[development_indices], labels[development_indices])
    probabilities = classifier.predict_proba(features[test])
    predictions = classifier.classes_[probabilities.argmax(axis=1)]
    confidence = probabilities.max(axis=1)
    test_accuracy = float(accuracy_score(labels[test], predictions))
    report = classification_report(labels[test], predictions, output_dict=True, zero_division=0)
    matrix = confusion_matrix(labels[test], predictions, labels=classifier.classes_).tolist()

    print(f"\n선택된 C={best_c}, 검증 정확도={best_accuracy:.3f}", flush=True)
    print(f"테스트 정확도={test_accuracy:.3f}", flush=True)
    print(classification_report(labels[test], predictions, zero_division=0), flush=True)

    joblib.dump({"classifier": classifier, "classes": list(classifier.classes_)}, MODEL_PATH)

    import csv
    with PREDICTIONS_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "true_label", "predicted_label", "confidence"])
        test_paths = all_paths[test]
        for path, true_label, predicted, conf in zip(test_paths, labels[test], predictions, confidence):
            writer.writerow([str(path), true_label, predicted, f"{conf:.4f}"])

    RESULT_PATH.write_text(
        json.dumps(
            {
                "classes": CLASSES, "tuning": tuning, "best_c": best_c,
                "validation_accuracy": best_accuracy, "test_accuracy": test_accuracy,
                "classification_report": report, "confusion_matrix": matrix,
                "confusion_matrix_labels": list(classifier.classes_),
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n모델 저장: {MODEL_PATH}")
    print(f"평가 저장: {RESULT_PATH}")


if __name__ == "__main__":
    main()
