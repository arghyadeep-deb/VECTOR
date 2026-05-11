import sys
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class PolicyMemory:
    """
    RULE 7 — Policy wired BOTH directions. Either alone = not learning.
    get_score()           BEFORE every decision.
    update_from_outcome() AFTER every action.

    Online averaging: new_avg = (old_avg * n + reward) / (n + 1)
    """

    DEFAULT_SCORE = 0.5

    def __init__(self):
        self._mem = None
        logger.info("[VECTOR][policy] initialized")

    def _get_mem(self):
        if self._mem is None:
            from core.memory.episodic import EpisodicMemory
            self._mem = EpisodicMemory()
        return self._mem

    @staticmethod
    def make_situation_hash(context: dict | str) -> str:
        """12-char deterministic hash of situation context for policy lookup."""
        if isinstance(context, dict):
            key = json.dumps(context, sort_keys=True, default=str)
        else:
            key = str(context)
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def get_score(self, action_type: str, situation_hash: str) -> float:
        """
        RULE 7 — Call BEFORE every decision.
        Returns avg reward [0.0-1.0] for this (action, situation) pair.
        Returns DEFAULT_SCORE if no data yet.
        """
        try:
            conn = self._get_mem().conn
            row = conn.execute(
                "SELECT avg_reward, sample_count FROM policy_memory "
                "WHERE action_type=? AND situation_hash=?",
                (action_type, situation_hash),
            ).fetchone()
            if row:
                avg_reward, count = row
                logger.debug(
                    f"[VECTOR][policy] {action_type}/{situation_hash[:6]} "
                    f"→ {avg_reward:.3f} ({count} samples)"
                )
                return float(avg_reward)
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_score failed: {e}")
        return self.DEFAULT_SCORE

    def update_from_outcome(
        self, action_type: str, situation_hash: str, reward: float
    ) -> None:
        """
        RULE 7 — Call AFTER every action with the real outcome reward.
        reward: 0.0 = complete failure → 1.0 = excellent.
        """
        reward = max(0.0, min(1.0, reward))
        try:
            conn = self._get_mem().conn
            row = conn.execute(
                "SELECT avg_reward, sample_count FROM policy_memory "
                "WHERE action_type=? AND situation_hash=?",
                (action_type, situation_hash),
            ).fetchone()

            if row:
                old_avg, n = row
                new_avg = (old_avg * n + reward) / (n + 1)
                conn.execute(
                    "UPDATE policy_memory SET avg_reward=?, sample_count=?, "
                    "last_updated=datetime('now') "
                    "WHERE action_type=? AND situation_hash=?",
                    (new_avg, n + 1, action_type, situation_hash),
                )
            else:
                conn.execute(
                    "INSERT INTO policy_memory "
                    "(action_type, situation_hash, avg_reward, sample_count, last_updated) "
                    "VALUES (?, ?, ?, 1, datetime('now'))",
                    (action_type, situation_hash, reward),
                )
            conn.commit()
            logger.debug(f"[VECTOR][policy] updated {action_type} reward={reward:.3f}")
        except Exception as e:
            logger.error(f"[VECTOR][policy] update_from_outcome failed: {e}")

    def get_top_actions(self, limit: int = 10) -> list[dict]:
        """Top-performing action types with ≥3 samples, by avg reward."""
        try:
            rows = self._get_mem().conn.execute(
                "SELECT action_type, avg_reward, sample_count FROM policy_memory "
                "WHERE sample_count >= 3 ORDER BY avg_reward DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"action": r[0], "avg_reward": round(r[1], 3), "samples": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_top_actions failed: {e}")
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._get_mem().conn
            total = conn.execute("SELECT COUNT(*) FROM policy_memory").fetchone()[0]
            avg = conn.execute("SELECT AVG(avg_reward) FROM policy_memory").fetchone()[0] or 0.0
            return {"total_entries": total, "overall_avg_reward": round(float(avg), 3)}
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_stats failed: {e}")
            return {"total_entries": 0, "overall_avg_reward": 0.0}


if __name__ == "__main__":
    import uuid
    sys.stdout.reconfigure(encoding="utf-8")

    pm = PolicyMemory()
    # Use unique key per run so fresh DB state is guaranteed
    run_id = uuid.uuid4().hex[:8]
    h = pm.make_situation_hash({"task": "smoke_test", "run": run_id})

    score_before = pm.get_score("smoke_web_test", h)  # fresh key → must be default

    pm.update_from_outcome("smoke_web_test", h, 0.9)
    pm.update_from_outcome("smoke_web_test", h, 0.7)
    pm.update_from_outcome("smoke_web_test", h, 0.8)

    score_after = pm.get_score("smoke_web_test", h)
    stats = pm.get_stats()

    ok = (
        score_before == PolicyMemory.DEFAULT_SCORE
        and score_after > score_before
        and stats["total_entries"] >= 1
    )
    print(
        f"✅ policy OK — default={score_before}, after 3 updates={score_after:.3f}, "
        f"entries={stats['total_entries']}"
        if ok else "❌ FAILED"
    )
