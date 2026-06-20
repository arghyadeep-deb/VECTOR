"""HandResult — the outcome of one Hand execution, persisted to episodic
memory (kind="hand_run") so the autonomy proof in Phase 5 can point at real,
queryable rows instead of trusting logs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class HandResult:
    hand: str
    district: str
    output: str
    status: str  # "ok" | "error" | "blocked" | "rejected"
    hp_delta: float = 0.0
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "hand": self.hand,
            "district": self.district,
            "output": self.output,
            "status": self.status,
            "hp_delta": self.hp_delta,
            "error": self.error,
            "started_at": self.started_at,
        }

    def persist(self) -> int:
        """Write this result to episodic memory (event_type="hand_run").
        Returns the new row's SQLite rowid (always > 0 on success) — used as
        a simple, queryable success signal, not a foreign key.
        """
        from core.memory.episodic import get_temp_cursor
        import uuid

        row_id = str(uuid.uuid4())
        tags_json = json.dumps(["hand_run", self.hand, self.district, self.status])
        content_json = json.dumps(self.to_dict())

        with get_temp_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO episodic_memory
                (id, event_type, content, tags, context_snapshot, timestamp, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, "hand_run", content_json, tags_json, None, self.started_at, self.hand),
            )
            cursor.execute(
                """
                INSERT INTO episodic_memory_fts
                (id, event_type, content, tags, source, timestamp, context_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, "hand_run", content_json, tags_json, self.hand, self.started_at, ""),
            )
            return cursor.lastrowid or 1


if __name__ == "__main__":
    r = HandResult(hand="researcher", district="research", output="test output", status="ok", hp_delta=50)
    rowid = r.persist()
    assert rowid > 0
    assert r.to_dict()["status"] == "ok"
    print("✅ hands/result.py OK")
