"""
V.E.C.T.O.R. CounterfactualMemory.
Gap 4: Learns from rejected decisions so future proposals avoid known pitfalls.
"""
from pathlib import Path

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from core.runtime_paths import data_path


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity — no ML deps, runs anywhere."""
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class CounterfactualMemory:
    """
    Stores hypothetical scenarios and rejected decisions.
    Gap 4: 'What if I had done X instead of Y?' + 'Why was Y rejected?'
    All data persisted to SQLite for cross-session learning.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = data_path()
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "counterfactual.db")
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info("[VECTOR][counterfactual] CounterfactualMemory initialized")

    def _create_tables(self):
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                original_action TEXT NOT NULL,
                chosen_reason TEXT NOT NULL,
                alternative TEXT NOT NULL,
                alternative_outcome TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                useful INTEGER,
                feedback_reason TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rejections (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                proposal TEXT NOT NULL,
                reason TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                expected_outcome TEXT NOT NULL,
                actual_outcome TEXT NOT NULL,
                delta TEXT NOT NULL DEFAULT '',
                lesson TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scenarios_created ON scenarios(created_at);
            CREATE INDEX IF NOT EXISTS idx_rejections_decision ON rejections(decision_id);
            CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes(decision_id);
        """)
            self._conn.commit()

    # ── Scenario API (original) ─────────────────────────────────────────────

    def record_scenario(
        self,
        original_action: str,
        chosen_reason: str,
        alternative: str,
        alternative_outcome: str,
        context: Optional[dict] = None,
    ) -> dict:
        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        scenario = {
            "id": sid,
            "original_action": original_action,
            "chosen_reason": chosen_reason,
            "alternative": alternative,
            "alternative_outcome": alternative_outcome,
            "context": context or {},
            "created_at": now,
            "useful": None,
        }
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO scenarios (id, original_action, chosen_reason, alternative,
                   alternative_outcome, context, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, original_action, chosen_reason, alternative,
                 alternative_outcome, json.dumps(context or {}), now),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] Failed to persist scenario: {e}")
        logger.info(f"[VECTOR][counterfactual] Scenario recorded: {original_action} vs {alternative}")
        return scenario

    def mark_useful(self, scenario_id: str, useful: bool, reason: str = "") -> bool:
        try:
            with self._lock:
                cur = self._conn.execute(
                    "UPDATE scenarios SET useful=?, feedback_reason=? WHERE id=?",
                    (1 if useful else 0, reason, scenario_id),
                )
                self._conn.commit()
            result = cur.rowcount > 0
            if result:
                logger.info(f"[VECTOR][counterfactual] Scenario {scenario_id} marked useful={useful}")
            return result
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] mark_useful failed: {e}")
            return False

    def get_similar(self, action: str, limit: int = 5) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM scenarios ORDER BY created_at DESC"
                ).fetchall()
            scored = []
            for row in rows:
                sim = _jaccard(action, row["original_action"])
                if sim > 0.1:
                    scored.append((sim, dict(row)))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:limit]]
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_similar failed: {e}")
            return []

    def get_insights(self) -> list[str]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM scenarios WHERE useful=1"
                ).fetchall()
            return [
                f"When considering '{r['original_action']}', alternative '{r['alternative']}' "
                f"was better ({r['feedback_reason'] or ''})"
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_insights failed: {e}")
            return []

    # ── Rejection API (Gap 4 extension) ────────────────────────────────────

    def record_rejection(
        self,
        decision_id: str,
        proposal: str,
        reason: str,
        context: Optional[dict] = None,
    ) -> str:
        rid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO rejections (id, decision_id, proposal, reason, context, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (rid, decision_id, proposal, reason, json.dumps(context or {}), now),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] record_rejection failed: {e}")
        logger.info(f"[VECTOR][counterfactual] Rejection recorded: {decision_id} — {reason[:60]}")
        return rid

    def get_similar_rejections(self, proposal: str, limit: int = 5) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM rejections ORDER BY created_at DESC"
                ).fetchall()
            scored = []
            for row in rows:
                sim = _jaccard(proposal, row["proposal"])
                if sim > 0.15:
                    scored.append((sim, dict(row)))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:limit]]
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_similar_rejections failed: {e}")
            return []

    def should_avoid(self, proposal: str, threshold: float = 0.4) -> tuple[bool, float, str]:
        """
        Returns (should_avoid, confidence, reason).
        True if a similar proposal was previously rejected with high similarity.
        """
        similar = self.get_similar_rejections(proposal, limit=3)
        if not similar:
            return False, 0.0, ""
        best = similar[0]
        sim = _jaccard(proposal, best["proposal"])
        if sim >= threshold:
            return True, round(sim, 3), best["reason"]
        return False, round(sim, 3), ""

    def learn_from_outcome(
        self,
        decision_id: str,
        actual_outcome: str,
        expected_outcome: str,
    ) -> dict:
        oid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        delta = "better" if len(actual_outcome) > len(expected_outcome) else "worse"
        lesson = (
            f"Decision {decision_id}: expected '{expected_outcome[:60]}' "
            f"but got '{actual_outcome[:60]}' ({delta})"
        )
        entry = {
            "id": oid,
            "decision_id": decision_id,
            "expected_outcome": expected_outcome,
            "actual_outcome": actual_outcome,
            "delta": delta,
            "lesson": lesson,
            "created_at": now,
        }
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO outcomes (id, decision_id, expected_outcome, actual_outcome, delta, lesson, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (oid, decision_id, expected_outcome, actual_outcome, delta, lesson, now),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] learn_from_outcome failed: {e}")
        logger.info(f"[VECTOR][counterfactual] Outcome learned: {decision_id} ({delta})")
        return entry

    def get_outcome(self, decision_id: str) -> Optional[dict]:
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT * FROM outcomes WHERE decision_id=? ORDER BY created_at DESC LIMIT 1",
                    (decision_id,),
                ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_outcome failed: {e}")
            return None

    def get_rejection_patterns(self) -> dict:
        try:
            with self._lock:
                total = self._conn.execute("SELECT COUNT(*) FROM rejections").fetchone()[0]
                rows = self._conn.execute(
                    "SELECT reason FROM rejections"
                ).fetchall()
                outcomes_total = self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
                scenarios_total = self._conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
            reason_counts: dict[str, int] = {}
            for row in rows:
                key = row[0][:40] if row[0] else "unknown"
                reason_counts[key] = reason_counts.get(key, 0) + 1
            top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            return {
                "total_rejections": total,
                "total_outcomes_learned": outcomes_total,
                "total_scenarios": scenarios_total,
                "top_rejection_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
            }
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_rejection_patterns failed: {e}")
            return {}

    def get_all_scenarios(self, limit: int = 50) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM scenarios ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][counterfactual] get_all_scenarios failed: {e}")
            return []

    def close(self):
        try:
            with self._lock:
                self._conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    cf = CounterfactualMemory(db_path)

    s = cf.record_scenario(
        "Used linear search", "Simpler code",
        "Used binary search", "10x faster but more complex",
        {"dataset_size": 10000},
    )
    assert "id" in s

    cf.mark_useful(s["id"], True, "Binary search was definitely worth the complexity")
    insights = cf.get_insights()
    assert len(insights) > 0

    rid = cf.record_rejection("dec-001", "Delete all logs", "Too destructive", {"risk": "high"})
    assert isinstance(rid, str)

    similar = cf.get_similar_rejections("delete logs now")
    assert len(similar) > 0

    avoid, conf, reason = cf.should_avoid("delete all the logs")
    assert isinstance(avoid, bool)

    outcome = cf.learn_from_outcome("dec-001", "System crashed", "System stable")
    assert "lesson" in outcome

    patterns = cf.get_rejection_patterns()
    assert "total_rejections" in patterns

    cf.close()
    Path(db_path).unlink(missing_ok=True)
    print("[OK] counterfactual.py")
