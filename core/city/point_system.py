# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by the HP system in core/city/agent_base.py. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""
V.E.C.T.O.R. PointSystem.
HP point system for agent health and evolution tracking.
"""
from collections import deque
from loguru import logger
from core.config import CONFIG

# Cap the in-memory HP event log so a long-running process cannot grow it
# without bound. Summaries/leaderboards operate on the recent window.
_MAX_POINT_LOGS = 5000


class PointSystem:
    """
    Centralized HP point management for all districts.
    Tracks how agents earn/deduct points across sessions.
    """

    POINT_RULES = {
        "successful_action": 10,
        "learning_moment": 25,
        "good_decision": 50,
        "council_contribution": 30,
        "missed_deadline": -30,
        "bad_decision": -20,
        "failed_action": -15,
        "security_threat": -25,
        "death": -500,
    }

    def __init__(self):
        self._logs: deque[dict] = deque(maxlen=_MAX_POINT_LOGS)
        logger.info("[VECTOR][point_system] PointSystem initialized")

    def apply(self, agent_name: str, action: str, amount: int | None = None) -> dict:
        """Apply a named action to an agent's HP."""
        if amount is None:
            amount = self.POINT_RULES.get(action, 0)
        result = {
            "agent": agent_name,
            "action": action,
            "amount": amount,
            "timestamp": None,
        }
        self._logs.append(result)
        logger.info(f"[VECTOR][point_system] {agent_name}: {action} ({amount:+d} HP)")
        return result

    def get_summary(self, agent_name: str) -> dict:
        """Get point summary for an agent."""
        agent_logs = [l for l in self._logs if l["agent"] == agent_name]
        total = sum(l["amount"] for l in agent_logs)
        return {
            "agent": agent_name,
            "total_adjustments": len(agent_logs),
            "net_points": total,
            "events": agent_logs[-10:],
        }

    def leaderboard(self) -> list[dict]:
        """Rank agents by net points."""
        agents = set(l["agent"] for l in self._logs)
        scores = []
        for agent in agents:
            net = sum(l["amount"] for l in self._logs if l["agent"] == agent)
            events = sum(1 for l in self._logs if l["agent"] == agent)
            scores.append({"agent": agent, "net_points": net, "events": events})
        return sorted(scores, key=lambda x: x["net_points"], reverse=True)


if __name__ == "__main__":
    ps = PointSystem()
    ps.apply("BugHunter", "good_decision", 50)
    ps.apply("BugHunter", "successful_action", 10)
    print(ps.leaderboard())