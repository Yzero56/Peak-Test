"""사진으로 냉장고 용기를 자동 등록하고 다시 식별하는 프로그램."""

from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_DB = Path(__file__).with_name("containers.db")
DEFAULT_THRESHOLD = 0.44


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def vector_to_blob(vector: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(vector, dtype=np.float32), allow_pickle=False)
    return buffer.getvalue()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.load(io.BytesIO(blob), allow_pickle=False)


def normalized(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(vector))
    if length == 0:
        raise ValueError("길이가 0인 특징 벡터는 저장할 수 없습니다.")
    return vector / length


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(normalized(a), normalized(b)))


class ContainerDatabase:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS containers (
                container_id TEXT PRIMARY KEY,
                feature_vector BLOB NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                registered_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                observation_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS container_features (
                feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id TEXT NOT NULL,
                feature_vector BLOB NOT NULL,
                captured_at TEXT NOT NULL,
                FOREIGN KEY(container_id) REFERENCES containers(container_id)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_features_container ON container_features(container_id)"
        )
        # 이전 버전 DB도 기존 대표 특징을 첫 번째 관찰 기록으로 자동 이전한다.
        self.connection.execute(
            """INSERT INTO container_features (container_id, feature_vector, captured_at)
               SELECT c.container_id, c.feature_vector, c.registered_at
               FROM containers c
               WHERE NOT EXISTS (
                   SELECT 1 FROM container_features f WHERE f.container_id = c.container_id
               )"""
        )
        self.connection.commit()

    def _similarity_to_container(self, container_id: str, vector: np.ndarray) -> float:
        rows = self.connection.execute(
            "SELECT feature_vector FROM container_features WHERE container_id = ?",
            (container_id,),
        ).fetchall()
        scores = sorted(
            (cosine_similarity(vector, blob_to_vector(row["feature_vector"])) for row in rows),
            reverse=True,
        )
        # 관찰 기록이 많아져도 가장 가까운 3개만 평균내어 비교한다.
        return float(np.mean(scores[:3]))

    def _next_id(self) -> str:
        rows = self.connection.execute("SELECT container_id FROM containers").fetchall()
        numbers = []
        for row in rows:
            try:
                numbers.append(int(row["container_id"].split("_")[-1]))
            except ValueError:
                continue
        return f"Container_{max(numbers, default=0) + 1:03d}"

    def recognize_or_register(
        self,
        vector: np.ndarray,
        threshold: float = DEFAULT_THRESHOLD,
        content: str = "",
    ) -> dict:
        vector = normalized(vector)
        rows = self.connection.execute("SELECT * FROM containers").fetchall()

        best_row = None
        best_similarity = -1.0
        for row in rows:
            similarity = self._similarity_to_container(row["container_id"], vector)
            if similarity > best_similarity:
                best_row, best_similarity = row, similarity

        seen_at = now_text()
        if best_row is not None and best_similarity >= threshold:
            count = best_row["observation_count"]
            old_vector = blob_to_vector(best_row["feature_vector"])
            updated_vector = normalized((old_vector * count + vector) / (count + 1))
            self.connection.execute(
                """UPDATE containers
                   SET feature_vector = ?, last_seen = ?, observation_count = ?
                   WHERE container_id = ?""",
                (vector_to_blob(updated_vector), seen_at, count + 1, best_row["container_id"]),
            )
            self.connection.execute(
                """INSERT INTO container_features
                   (container_id, feature_vector, captured_at) VALUES (?, ?, ?)""",
                (best_row["container_id"], vector_to_blob(vector), seen_at),
            )
            self.connection.commit()
            return {
                "status": "matched",
                "container_id": best_row["container_id"],
                "similarity": best_similarity,
                "content": best_row["content"],
            }

        container_id = self._next_id()
        self.connection.execute(
            """INSERT INTO containers
               (container_id, feature_vector, content, registered_at, last_seen)
               VALUES (?, ?, ?, ?, ?)""",
            (container_id, vector_to_blob(vector), content, seen_at, seen_at),
        )
        self.connection.execute(
            """INSERT INTO container_features
               (container_id, feature_vector, captured_at) VALUES (?, ?, ?)""",
            (container_id, vector_to_blob(vector), seen_at),
        )
        self.connection.commit()
        return {
            "status": "registered",
            "container_id": container_id,
            "similarity": None if best_row is None else best_similarity,
            "content": content,
        }

    def list_containers(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT container_id, content, registered_at, last_seen, observation_count
               FROM containers ORDER BY container_id"""
        ).fetchall()

    def update_content(self, container_id: str, content: str) -> bool:
        cursor = self.connection.execute(
            "UPDATE containers SET content = ? WHERE container_id = ?",
            (content, container_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0


class DinoV2Embedder:
    """DINOv2 모델은 사진 인식 명령을 실행할 때만 불러온다."""

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
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
                ),
            ]
        )

    def extract(self, image_path: Path | str) -> np.ndarray:
        return self.extract_many([image_path])[0]

    def extract_many(self, image_paths, batch_size: int = 16) -> np.ndarray:
        from PIL import Image

        image_paths = [Path(path) for path in image_paths]
        missing = next((path for path in image_paths if not path.is_file()), None)
        if missing is not None:
            raise FileNotFoundError(f"사진을 찾을 수 없습니다: {missing}")
        images = [Image.open(path).convert("RGB") for path in image_paths]
        return self.extract_pil_images(images, batch_size=batch_size)

    def extract_pil_images(self, images, batch_size: int = 16) -> np.ndarray:
        images = [image.convert("RGB") for image in images]
        if not images:
            return np.empty((0, 384), dtype=np.float32)
        vectors = []
        for start in range(0, len(images), batch_size):
            batch_images = images[start : start + batch_size]
            batch = self.torch.stack(
                [self.preprocess(image) for image in batch_images]
            )
            with self.torch.no_grad():
                output = self.model(batch.to(self.device)).cpu().numpy()
            vectors.extend(normalized(vector) for vector in output)
        return np.stack(vectors)


def print_result(result: dict, threshold: float) -> None:
    if result["status"] == "registered":
        print(f"\n새 용기로 등록했습니다: {result['container_id']}")
        if result["similarity"] is not None:
            print(f"가장 가까운 기존 용기와의 유사도: {result['similarity']:.4f}")
    else:
        print(f"\n기존 용기로 인식했습니다: {result['container_id']}")
        print(f"유사도: {result['similarity']:.4f} (기준: {threshold:.2f})")
    print(f"내용물: {result['content'] or '아직 입력하지 않음'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="사진의 디지털 지문을 비교해 냉장고 용기를 등록/재식별합니다."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="DB 파일 경로")
    subparsers = parser.add_subparsers(dest="command", required=True)

    recognize = subparsers.add_parser("recognize", help="사진으로 용기 등록 또는 재식별")
    recognize.add_argument("image", type=Path, help="용기 사진 경로")
    recognize.add_argument("--content", default="", help="신규 용기의 내용물")
    recognize.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)

    subparsers.add_parser("list", help="등록된 용기 목록 보기")

    update = subparsers.add_parser("set-content", help="용기의 내용물 수정")
    update.add_argument("container_id")
    update.add_argument("content")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database = ContainerDatabase(args.db)
    try:
        if args.command == "recognize":
            vector = DinoV2Embedder().extract(args.image)
            result = database.recognize_or_register(
                vector, threshold=args.threshold, content=args.content
            )
            print_result(result, args.threshold)
        elif args.command == "list":
            rows = database.list_containers()
            if not rows:
                print("아직 등록된 용기가 없습니다.")
            for row in rows:
                print(
                    f"{row['container_id']} | 내용물: {row['content'] or '미입력'} | "
                    f"본 횟수: {row['observation_count']} | 마지막 확인: {row['last_seen']}"
                )
        elif args.command == "set-content":
            if database.update_content(args.container_id, args.content):
                print(f"{args.container_id}의 내용물을 '{args.content}'(으)로 저장했습니다.")
            else:
                raise SystemExit(f"등록되지 않은 ID입니다: {args.container_id}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
