"""주방 재료 인식 결과를 용기 단위로 묶어 SQLite에 신규 등록/갱신하는 간단한 DB."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).with_name("pantry_registry.db")

# 라벨 -> 어느 용기에 담기는지 (발표 시연용 고정 매핑)
CONTAINER_BY_LABEL = {
    "당근": "A용기",
    "대파": "A용기",
    "양파": "A용기",
    "김치": "김치용기",
}


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PantryRegistry:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pantry_items (
                container_name TEXT NOT NULL,
                item_label TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                seen_count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (container_name, item_label)
            )
            """
        )
        self.connection.commit()

    def observe(self, item_label: str) -> dict:
        """이 라벨을 방금 인식했다고 알려주면, 처음이면 신규 등록하고 아니면 last_seen만 갱신한다."""
        container_name = CONTAINER_BY_LABEL.get(item_label, "미분류용기")
        row = self.connection.execute(
            "SELECT * FROM pantry_items WHERE container_name = ? AND item_label = ?",
            (container_name, item_label),
        ).fetchone()
        stamp = now_text()
        if row is None:
            self.connection.execute(
                """INSERT INTO pantry_items
                   (container_name, item_label, registered_at, last_seen, seen_count)
                   VALUES (?, ?, ?, ?, 1)""",
                (container_name, item_label, stamp, stamp),
            )
            self.connection.commit()
            return {"status": "registered", "container_name": container_name,
                    "item_label": item_label, "seen_count": 1}
        self.connection.execute(
            """UPDATE pantry_items SET last_seen = ?, seen_count = seen_count + 1
               WHERE container_name = ? AND item_label = ?""",
            (stamp, container_name, item_label),
        )
        self.connection.commit()
        return {"status": "known", "container_name": container_name,
                "item_label": item_label, "seen_count": row["seen_count"] + 1}

    def snapshot(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM pantry_items ORDER BY container_name, item_label"
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()
