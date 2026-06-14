import sys
import json

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

    @staticmethod
    def _time_column(conn) -> str:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reasoning_chains)").fetchall()}
        if "created_at" in columns:
            return "created_at"
        return "timestamp"

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

    @staticmethod
    def _row_to_chain(row) -> dict:
        steps = json.loads(row[2]) if row[2] else []
        goal_ids = json.loads(row[7]) if len(row) > 7 and row[7] else []
        return {
            "id": row[0],
            "situation": row[1],
            "steps": steps,
            "action_taken": row[3],
            "outcome": row[4],
            "reward": float(row[5]) if row[5] is not None else 0.0,
            "created_at": row[6],
            "goal_ids": goal_ids,
        }

    def search_chains(self, query: str, limit: int = 5, min_reward: float | None = None) -> list[dict]:
        """Retrieve reasoning chains related to a query.

        Searches situation, action, and outcome text so recall still works when
        the current prompt does not share the exact situation prefix.
        """
        query = (query or "").strip()
        if limit <= 0:
            return []
        try:
            conn = self._get_mem().conn
            time_column = self._time_column(conn)
            params: list[object] = []
            where = []
            if query:
                like = f"%{query}%"
                where.append("(situation LIKE ? OR action_taken LIKE ? OR outcome LIKE ?)")
                params.extend([like, like, like])
            if min_reward is not None:
                where.append("reward >= ?")
                params.append(float(min_reward))
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            params.append(limit)
            rows = conn.execute(
                f"""SELECT chain_id, situation, steps, action_taken, outcome, reward, {time_column}, goal_ids
                    FROM reasoning_chains
                    {where_sql}
                    ORDER BY reward DESC, {time_column} DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
            return [self._row_to_chain(row) for row in rows]
        except Exception as e:
            logger.error(f"[VECTOR][reasoning_memory] search_chains failed: {e}")
            return []

    def retrieve_similar(self, situation: str, limit: int = 3) -> list[dict]:
        """Compatibility helper for callers that need structured recall."""
        return self.search_chains(situation, limit=limit)

    def inject_past_reasoning(self, situation: str, limit: int = 3) -> str:
        """
        RULE 8 — Retrieve past chains similar to current situation.
        Returns formatted string ready to inject into LLM context before a decision.
        """
        try:
            chains = self.retrieve_similar(situation, limit=limit)
            if not chains:
                return ""

            lines = ["[PAST REASONING — similar situations]"]
            for chain in chains:
                steps_list = chain.get("steps") or []
                steps_str = " → ".join(steps_list[:3]) if steps_list else "—"
                lines.append(
                    f"• Situation: {chain.get('situation', '')[:80]}\n"
                    f"  Steps: {steps_str}\n"
                    f"  Action: {chain.get('action_taken')} | "
                    f"Outcome: {chain.get('outcome')} | "
                    f"Reward: {chain.get('reward', 0.0):.2f}"
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
            time_column = self._time_column(conn)
            if situation:
                rows = conn.execute(
                    f"SELECT chain_id, situation, steps, action_taken, outcome, reward, {time_column} "
                    "FROM reasoning_chains WHERE situation LIKE ? "
                    f"ORDER BY {time_column} DESC LIMIT ?",
                    (f"%{situation[:50]}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT chain_id, situation, steps, action_taken, outcome, reward, {time_column} "
                    f"FROM reasoning_chains ORDER BY {time_column} DESC LIMIT ?",
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
