"""2차 프로토타입용 다중 시점(갤러리) 용기 데이터베이스."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_V2 = ROOT / "containers_v2_improved.db"
DEFAULT_LOG_V2 = ROOT / "recognition_log_v2_improved.csv"
# 1차 데이터의 같은 용기 평균(0.5378)과 다른 용기 평균(0.3332)을 참고한 절충값.
DEFAULT_THRESHOLD_V2 = 0.52


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def normalized(vector: np.ndarray) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32).reshape(-1)
    length = float(np.linalg.norm(value))
    if length == 0:
        raise ValueError("길이가 0인 특징 벡터는 저장할 수 없습니다.")
    return value / length


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(normalized(a), normalized(b)))


def vector_to_blob(vector: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, normalized(vector), allow_pickle=False)
    return buffer.getvalue()


def blob_to_vector(blob: bytes) -> np.ndarray:
    return np.load(io.BytesIO(blob), allow_pickle=False)


def select_representative_vectors(
    vectors: list[np.ndarray], duplicate_threshold: float = 0.98, maximum: int = 15
) -> list[np.ndarray]:
    """거의 같은 모습을 버리고 입력 순서대로 대표 특징을 남긴다."""
    selected: list[np.ndarray] = []
    for vector in vectors:
        vector = normalized(vector)
        if selected and max(cosine_similarity(vector, old) for old in selected) >= duplicate_threshold:
            continue
        selected.append(vector)
        if len(selected) >= maximum:
            break
    return selected


class ContainerDatabaseV2:
    def __init__(self, db_path: Path | str = DEFAULT_DB_V2):
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS containers (
                container_id TEXT PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                registered_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS container_vectors (
                vector_id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id TEXT NOT NULL,
                feature_vector BLOB NOT NULL,
                captured_at TEXT NOT NULL,
                FOREIGN KEY(container_id) REFERENCES containers(container_id) ON DELETE CASCADE
            )"""
        )
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(container_vectors)")
        }
        if "color_vector" not in columns:
            self.connection.execute("ALTER TABLE container_vectors ADD COLUMN color_vector BLOB")
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_container_vectors_id ON container_vectors(container_id)"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _next_id(self) -> str:
        rows = self.connection.execute("SELECT container_id FROM containers").fetchall()
        numbers = []
        for row in rows:
            try:
                numbers.append(int(row["container_id"].rsplit("_", 1)[1]))
            except (ValueError, IndexError):
                pass
        return f"Container_{max(numbers, default=0) + 1:03d}"

    def register_gallery(
        self, vectors: list[np.ndarray], color_vectors: list[np.ndarray], content: str = ""
    ) -> dict:
        if not vectors or len(vectors) != len(color_vectors):
            raise ValueError("등록할 대표 모습이 없습니다.")
        container_id = self._next_id()
        captured_at = now_text()
        self.connection.execute(
            "INSERT INTO containers(container_id,content,registered_at,last_seen) VALUES(?,?,?,?)",
            (container_id, content, captured_at, captured_at),
        )
        self.connection.executemany(
            """INSERT INTO container_vectors
               (container_id,feature_vector,captured_at,color_vector) VALUES(?,?,?,?)""",
            [(container_id, vector_to_blob(vector), captured_at, vector_to_blob(color))
             for vector, color in zip(vectors, color_vectors)],
        )
        self.connection.commit()
        return {"status": "registered", "container_id": container_id,
                "similarity": None, "vector_count": len(vectors), "content": content}

    def recognize(
        self, vector: np.ndarray, color_vector: np.ndarray,
        threshold: float = DEFAULT_THRESHOLD_V2,
        update_last_seen: bool = True,
    ) -> dict:
        vector = normalized(vector)
        color_vector = normalized(color_vector)
        rows = self.connection.execute(
            """SELECT container_id, feature_vector, color_vector FROM container_vectors
               WHERE color_vector IS NOT NULL ORDER BY container_id, vector_id"""
        ).fetchall()
        best_id = None
        best_similarity = -1.0
        best_dino = -1.0
        best_color = -1.0
        scores_by_container: dict[str, list[tuple[float, float, float]]] = {}
        for row in rows:
            dino_similarity = cosine_similarity(vector, blob_to_vector(row["feature_vector"]))
            color_similarity = cosine_similarity(color_vector, blob_to_vector(row["color_vector"]))
            # 많은 등록 사진 중 외형과 색상이 함께 가까운 사례를 찾는다.
            similarity = 0.50 * dino_similarity + 0.50 * color_similarity
            scores_by_container.setdefault(row["container_id"], []).append(
                (similarity, dino_similarity, color_similarity)
            )
        for container_id, scores in scores_by_container.items():
            top = sorted(scores, reverse=True)[:3]
            similarity = float(np.mean([item[0] for item in top]))
            dino_similarity = float(np.mean([item[1] for item in top]))
            color_similarity = float(np.mean([item[2] for item in top]))
            if similarity > best_similarity:
                best_id, best_similarity = container_id, similarity
                best_dino, best_color = dino_similarity, color_similarity
        if best_id is None or best_similarity < threshold:
            return {"status": "unknown", "container_id": None,
                    "similarity": None if best_id is None else best_similarity,
                    "dino_similarity": None if best_id is None else best_dino,
                    "color_similarity": None if best_id is None else best_color, "content": ""}
        seen_at = now_text()
        if update_last_seen:
            self.connection.execute(
                "UPDATE containers SET last_seen=? WHERE container_id=?", (seen_at, best_id)
            )
            self.connection.commit()
        content = self.connection.execute(
            "SELECT content FROM containers WHERE container_id=?", (best_id,)
        ).fetchone()[0]
        return {"status": "matched", "container_id": best_id,
                "similarity": best_similarity, "dino_similarity": best_dino,
                "color_similarity": best_color, "content": content}

    def list_containers(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT c.container_id,c.content,c.registered_at,c.last_seen,
                      COUNT(v.vector_id) AS vector_count
               FROM containers c LEFT JOIN container_vectors v
               ON c.container_id=v.container_id
               GROUP BY c.container_id ORDER BY c.container_id"""
        ).fetchall()
        return [dict(row) for row in rows]


def append_log(log_path: Path | str, *, event: str, container_id: str | None,
               similarity: float | None, detection_confidence: float | None,
               detail: str = "") -> None:
    path = Path(log_path)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(["timestamp", "event", "container_id", "similarity",
                             "detection_confidence", "detail"])
        writer.writerow([now_text(), event, container_id or "",
                         "" if similarity is None else f"{similarity:.6f}",
                         "" if detection_confidence is None else f"{detection_confidence:.6f}", detail])
