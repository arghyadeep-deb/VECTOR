"""Trust Ladder — earned autonomy for YELLOW-tier actions.

The permission gateway's tiers are static: an action approved 50 times still
asks on attempt 51. The trust ladder converts owner supervision into growing
independence, per action type:

  - every EXPLICIT owner approval of a YELLOW action extends its streak
  - a streak of ``trust_promotion_streak`` consecutive approvals (default 20)
    with zero bad outcomes promotes the action: it auto-executes from then on
  - any explicit rejection OR failed execution instantly demotes it back to
    owner-gated and resets the streak
  - YELLOW-window timeouts are neutral (missing a phone ping is not a "no")
  - RED and FORBIDDEN actions NEVER participate — owner-gated forever

Persistence: `trust_ladder` table in the main encrypted DB (SQLCipher via
core.memory.episodic.get_db_connection — never plain sqlite3 on that file).
The five sacred memory tables are untouched.

Oversight: /gateway/trust API lists state; demote anytime; the reflect loop
sends a weekly digest of promotions/demotions.
"""

import sys
import datetime
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ladder (
    action_type      TEXT PRIMARY KEY,
    streak           INTEGER NOT NULL DEFAULT 0,
    total_approvals  INTEGER NOT NULL DEFAULT 0,
    total_rejections INTEGER NOT NULL DEFAULT 0,
    bad_outcomes     INTEGER NOT NULL DEFAULT 0,
    auto_execs       INTEGER NOT NULL DEFAULT 0,
    promoted         INTEGER NOT NULL DEFAULT 0,
    promoted_at      TEXT,
    demoted_at       TEXT,
    demote_reason    TEXT,
    last_updated     TEXT
)
"""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class TrustLadder:
    """Per-action-type approval history with promotion/demotion.

    ``conn`` is injectable for tests (in-memory sqlite3); by default the
    main encrypted DB connection is used (SQLCipher discipline).
    """

    def __init__(self, conn=None):
        self._lock = threading.Lock()
        self._conn = conn
        self._ensure_schema()

    # ── infrastructure ────────────────────────────────────────────────────

    def _get_conn(self):
        if self._conn is not None:
            return self._conn
        from core.memory.episodic import get_db_connection
        return get_db_connection()

    def _ensure_schema(self) -> None:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(_SCHEMA)
                conn.commit()
        except Exception as e:
            logger.error(f"[VECTOR][trust] schema init failed: {e}")

    def _threshold(self) -> int:
        try:
            from core.config import CONFIG
            return int(CONFIG["permission"].get("trust_promotion_streak", 20))
        except Exception:
            return 20

    def _upsert(self, action_type: str) -> None:
        # Caller holds the lock.
        self._get_conn().execute(
            "INSERT OR IGNORE INTO trust_ladder (action_type, last_updated) VALUES (?, ?)",
            (action_type, _now()),
        )

    # ── recording ─────────────────────────────────────────────────────────

    def record_approval(self, action_type: str) -> bool:
        """Explicit owner approval. Returns True if this promoted the action."""
        try:
            with self._lock:
                conn = self._get_conn()
                self._upsert(action_type)
                conn.execute(
                    "UPDATE trust_ladder SET streak = streak + 1, "
                    "total_approvals = total_approvals + 1, last_updated = ? "
                    "WHERE action_type = ?",
                    (_now(), action_type),
                )
                row = conn.execute(
                    "SELECT streak, bad_outcomes, promoted FROM trust_ladder WHERE action_type = ?",
                    (action_type,),
                ).fetchone()
                streak, bad, promoted = row[0], row[1], row[2]
                if not promoted and bad == 0 and streak >= self._threshold():
                    conn.execute(
                        "UPDATE trust_ladder SET promoted = 1, promoted_at = ?, "
                        "demote_reason = NULL, last_updated = ? WHERE action_type = ?",
                        (_now(), _now(), action_type),
                    )
                    conn.commit()
                    logger.info(
                        f"[VECTOR][trust] '{action_type}' PROMOTED to auto-execute "
                        f"after {streak} consecutive approvals"
                    )
                    return True
                conn.commit()
                return False
        except Exception as e:
            logger.error(f"[VECTOR][trust] record_approval failed: {e}")
            return False

    def record_rejection(self, action_type: str) -> None:
        """Explicit owner rejection — resets streak, demotes if promoted."""
        try:
            with self._lock:
                conn = self._get_conn()
                self._upsert(action_type)
                conn.execute(
                    "UPDATE trust_ladder SET streak = 0, "
                    "total_rejections = total_rejections + 1, last_updated = ? "
                    "WHERE action_type = ?",
                    (_now(), action_type),
                )
                conn.commit()
            self.demote(action_type, "owner rejected")
        except Exception as e:
            logger.error(f"[VECTOR][trust] record_rejection failed: {e}")

    def record_bad_outcome(self, action_type: str) -> None:
        """Execution failed — resets streak, demotes if promoted."""
        try:
            with self._lock:
                conn = self._get_conn()
                self._upsert(action_type)
                conn.execute(
                    "UPDATE trust_ladder SET streak = 0, "
                    "bad_outcomes = bad_outcomes + 1, last_updated = ? "
                    "WHERE action_type = ?",
                    (_now(), action_type),
                )
                conn.commit()
            self.demote(action_type, "execution failed")
        except Exception as e:
            logger.error(f"[VECTOR][trust] record_bad_outcome failed: {e}")

    def record_auto_exec(self, action_type: str) -> None:
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE trust_ladder SET auto_execs = auto_execs + 1, "
                    "last_updated = ? WHERE action_type = ?",
                    (_now(), action_type),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"[VECTOR][trust] record_auto_exec failed: {e}")

    # ── state ─────────────────────────────────────────────────────────────

    def is_promoted(self, action_type: str) -> bool:
        try:
            with self._lock:
                row = self._get_conn().execute(
                    "SELECT promoted FROM trust_ladder WHERE action_type = ?",
                    (action_type,),
                ).fetchone()
            return bool(row and row[0])
        except Exception as e:
            # Fail closed — no trust DB, no auto-execution.
            logger.debug(f"[VECTOR][trust] is_promoted failed (fail closed): {e}")
            return False

    def promote(self, action_type: str) -> None:
        """Manual owner promotion (HUD/API)."""
        try:
            with self._lock:
                conn = self._get_conn()
                self._upsert(action_type)
                conn.execute(
                    "UPDATE trust_ladder SET promoted = 1, promoted_at = ?, "
                    "demote_reason = NULL, last_updated = ? WHERE action_type = ?",
                    (_now(), _now(), action_type),
                )
                conn.commit()
            logger.info(f"[VECTOR][trust] '{action_type}' manually promoted by owner")
        except Exception as e:
            logger.error(f"[VECTOR][trust] promote failed: {e}")

    def demote(self, action_type: str, reason: str = "manual") -> None:
        try:
            with self._lock:
                conn = self._get_conn()
                cur = conn.execute(
                    "UPDATE trust_ladder SET promoted = 0, streak = 0, demoted_at = ?, "
                    "demote_reason = ?, last_updated = ? WHERE action_type = ? AND promoted = 1",
                    (_now(), reason, _now(), action_type),
                )
                conn.commit()
            if cur.rowcount:
                logger.warning(f"[VECTOR][trust] '{action_type}' DEMOTED — {reason}")
        except Exception as e:
            logger.error(f"[VECTOR][trust] demote failed: {e}")

    def status(self) -> list[dict]:
        """All trust records — for the /gateway/trust API and HUD."""
        try:
            with self._lock:
                rows = self._get_conn().execute(
                    "SELECT action_type, streak, total_approvals, total_rejections, "
                    "bad_outcomes, auto_execs, promoted, promoted_at, demoted_at, "
                    "demote_reason, last_updated FROM trust_ladder "
                    "ORDER BY promoted DESC, streak DESC"
                ).fetchall()
            cols = ["action_type", "streak", "total_approvals", "total_rejections",
                    "bad_outcomes", "auto_execs", "promoted", "promoted_at",
                    "demoted_at", "demote_reason", "last_updated"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as e:
            logger.error(f"[VECTOR][trust] status failed: {e}")
            return []

    def recent_changes(self, days: int = 7) -> dict:
        """Promotions/demotions in the last N days — weekly digest payload."""
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        ).isoformat()
        try:
            with self._lock:
                conn = self._get_conn()
                promoted = conn.execute(
                    "SELECT action_type, promoted_at FROM trust_ladder "
                    "WHERE promoted = 1 AND promoted_at >= ?",
                    (cutoff,),
                ).fetchall()
                demoted = conn.execute(
                    "SELECT action_type, demoted_at, demote_reason FROM trust_ladder "
                    "WHERE promoted = 0 AND demoted_at >= ?",
                    (cutoff,),
                ).fetchall()
                auto = conn.execute(
                    "SELECT COALESCE(SUM(auto_execs), 0) FROM trust_ladder WHERE promoted = 1"
                ).fetchone()
            return {
                "promoted": [{"action_type": r[0], "at": r[1]} for r in promoted],
                "demoted": [{"action_type": r[0], "at": r[1], "reason": r[2]} for r in demoted],
                "total_auto_execs": int(auto[0]) if auto else 0,
            }
        except Exception as e:
            logger.error(f"[VECTOR][trust] recent_changes failed: {e}")
            return {"promoted": [], "demoted": [], "total_auto_execs": 0}


# Module singleton (matches gateway/nudge_engine convention)
_ladder: TrustLadder | None = None


def get_trust_ladder() -> TrustLadder:
    global _ladder
    if _ladder is None:
        _ladder = TrustLadder()
    return _ladder


if __name__ == "__main__":
    # real test, no mocks — in-memory DB exercises the full state machine
    import sqlite3
    t = TrustLadder(conn=sqlite3.connect(":memory:"))
    for _ in range(19):
        assert t.record_approval("send_email") is False
    assert t.is_promoted("send_email") is False
    promoted = t.record_approval("send_email")          # 20th → promote
    assert promoted and t.is_promoted("send_email")
    t.record_bad_outcome("send_email")                   # failure → demote
    assert not t.is_promoted("send_email")
    t.promote("send_email")                              # manual re-promote
    t.record_rejection("send_email")                     # reject → demote
    assert not t.is_promoted("send_email")
    ok = len(t.status()) == 1
    print("✅ trust_ladder.py OK" if ok else "❌ FAILED")
