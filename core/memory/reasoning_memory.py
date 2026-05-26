import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class ReasoningMemory:
    """
    RULE 8 — Every thought-action-outcome stored. inject_past_reasoning() used before
    similar decisions. High-reward chains (>0.7) tagged is_training_data=1 → custom LLM data.
    """

    def __init__(self):
        self._mem = None
        logger.info("[VECTOR][reasoning_memory] initialized")

    def _get_mem(self):
        if self._mem is None:
            from core.memory.episodic import EpisodicMemory
            self._mem = EpisodicMemory()
        return self._mem

    def store_chain(
        self,
        situation: str,
        goal_ids: list[str],
        steps: list[str],
        action: str,
        outcome: str,
        reward: float,
    ) -> str:
        """
        Store a reasoning chain. Chains with reward > 0.7 become training data.
        Returns chain_id.
        """
        chain_id = self._get_mem().store_chain(
            situation=situation,
            goal_ids=goal_ids,
            steps=steps,
            action=action,
            outcome=outcome,
            reward=reward,
        )
        flag = "🎓 training" if reward > 0.7 else ""
        logger.debug(
            f"[VECTOR][reasoning_memory] stored chain {chain_id[:8] if chain_id else '?'} "
            f"reward={reward:.2f} {flag}"
        )
        return chain_id

    def inject_past_reasoning(self, situation: str, limit: int = 3) -> str:
        """
        RULE 8 — Retrieve past chains similar to current situation.
        Returns formatted string ready to inject into LLM context before a decision.
        """
        try:
            conn = self._get_mem().conn
            rows = conn.execute(
                "SELECT situation, steps, action_taken, outcome, reward FROM reasoning_chains "
                "WHERE situation LIKE ? ORDER BY reward DESC LIMIT ?",
                (f"%{situation[:30]}%", limit),
            ).fetchall()

            if not rows:
                return ""

            lines = ["[PAST REASONING — similar situations]"]
            for r in rows:
                steps_list = json.loads(r[1]) if r[1] else []
                steps_str = " → ".join(steps_list[:3]) if steps_list else "—"
                lines.append(
                    f"• Situation: {r[0][:80]}\n"
                    f"  Steps: {steps_str}\n"
                    f"  Action: {r[2]} | Outcome: {r[3]} | Reward: {r[4]:.2f}"
                )
            lines.append("[END PAST REASONING]")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[VECTOR][reasoning_memory] inject failed: {e}")
            return ""

    def get_training_data(self, limit: int = 100) -> list[dict]:
        """
        Return chains tagged is_training_data=1 (reward > 0.7).
        These are the dataset for the custom Chairman LLM.
        """
        return self._get_mem().get_training_data(limit=limit)

    def get_recent(self, limit: int = 20, situation: str = "") -> list[dict]:
        """D2 — Return the most recent reasoning chains for the decision trace panel."""
        try:
            conn = self._get_mem().conn
            if situation:
                rows = conn.execute(
                    "SELECT id, situation, steps, action_taken, outcome, reward, created_at "
                    "FROM reasoning_chains WHERE situation LIKE ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (f"%{situation[:50]}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, situation, steps, action_taken, outcome, reward, created_at "
                    "FROM reasoning_chains ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            result = []
            for r in rows:
                steps_list = json.loads(r[2]) if r[2] else []
                result.append({
                    "id": r[0],
                    "situation": r[1],
                    "steps": steps_list,
                    "action_taken": r[3],
                    "outcome": r[4],
                    "reward": float(r[5]) if r[5] is not None else 0.0,
                    "created_at": r[6],
                })
            return result
        except Exception as e:
            logger.error(f"[VECTOR][reasoning_memory] get_recent failed: {e}")
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._get_mem().conn
            total = conn.execute("SELECT COUNT(*) FROM reasoning_chains").fetchone()[0]
            training = conn.execute(
                "SELECT COUNT(*) FROM reasoning_chains WHERE is_training_data=1"
            ).fetchone()[0]
            avg_row = conn.execute("SELECT AVG(reward) FROM reasoning_chains").fetchone()[0]
            avg_reward = float(avg_row) if avg_row else 0.0
            return {
                "total_chains": total,
                "training_data": training,
                "avg_reward": round(avg_reward, 3),
            }
        except Exception as e:
            logger.error(f"[VECTOR][reasoning_memory] get_stats failed: {e}")
            return {"total_chains": 0, "training_data": 0, "avg_reward": 0.0}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    rm = ReasoningMemory()

    chain_id = rm.store_chain(
        situation="User asked to check KIIT attendance",
        goal_ids=["g_kiit_attendance"],
        steps=["classify_intent", "route_to_time_calendar", "scrape_kiit_portal"],
        action="check_attendance",
        outcome="Found 3 upcoming classes, attendance at 78%",
        reward=0.85,
    )
    rm.store_chain(
        situation="User asked for weather",
        goal_ids=[],
        steps=["classify_intent", "call_weather_api"],
        action="check_weather",
        outcome="Returned weather data",
        reward=0.5,
    )

    past = rm.inject_past_reasoning("KIIT attendance")
    stats = rm.get_stats()

    ok = (
        chain_id is not None
        and stats["total_chains"] >= 2
        and stats["training_data"] >= 1
        and "PAST REASONING" in past
    )
    print(
        f"✅ reasoning_memory OK — chains={stats['total_chains']}, "
        f"training={stats['training_data']}, avg={stats['avg_reward']}"
        if ok else "❌ FAILED"
    )
