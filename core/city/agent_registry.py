import sys
import json
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class AgentRegistry:
    """
    Central register of all living VECTOR City agents.
    RULE 9 — Agent Darwinism is real. HP system wires to actual outcomes.
    Death → ghost memory preserved in agent_history table.
    """

    def __init__(self):
        self._agents: dict[str, object] = {}
        self._mem = None
        logger.info("[VECTOR][agent_registry] initialized")

    def _get_mem(self):
        if self._mem is None:
            from core.memory.episodic import EpisodicMemory
            self._mem = EpisodicMemory()
        return self._mem

    def register(self, agent) -> None:
        """Register a living agent in the city."""
        self._agents[agent.id] = agent
        logger.info(
            f"[VECTOR][agent_registry] +{agent.name} ({agent.district}) "
            f"HP={agent.health_points} gen={agent.generation}"
        )

    def deregister(self, agent_id: str) -> None:
        """Remove agent on death. Ghost memory saved to agent_history."""
        agent = self._agents.pop(agent_id, None)
        if agent:
            self._persist_ghost(agent)
            logger.info(
                f"[VECTOR][agent_registry] -{agent.name} died — "
                f"ghost saved gen={agent.generation}"
            )

    def _persist_ghost(self, agent) -> None:
        """Save dead agent's history for next-generation inheritance."""
        try:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            conn.execute(
                "INSERT OR REPLACE INTO agent_history "
                "(agent_id, agent_name, district, generation, final_hp, ghost_memory, died_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    agent.id,
                    agent.name,
                    agent.district,
                    agent.generation,
                    agent.health_points,
                    json.dumps(agent.ghost_memory),
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[VECTOR][agent_registry] ghost persist failed: {e}")

    def get(self, agent_id: str):
        return self._agents.get(agent_id)

    def get_by_district(self, district: str) -> list:
        return [a for a in self._agents.values() if a.district == district]

    def get_council_eligible(self) -> list:
        """Agents with HP >= 700 who can vote in council."""
        return [a for a in self._agents.values() if a.can_vote_in_council()]

    def get_elite(self, min_hp: int = 800) -> list:
        return [a for a in self._agents.values() if a.health_points >= min_hp]

    def get_dead_ghosts(self, district: str | None = None, limit: int = 10) -> list[dict]:
        """Ghost memories of dead agents for next-gen inheritance."""
        try:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            if district:
                rows = conn.execute(
                    "SELECT agent_id, agent_name, district, generation, final_hp, ghost_memory "
                    "FROM agent_history WHERE district=? ORDER BY died_at DESC LIMIT ?",
                    (district, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT agent_id, agent_name, district, generation, final_hp, ghost_memory "
                    "FROM agent_history ORDER BY died_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {
                    "id": r[0], "name": r[1], "district": r[2],
                    "generation": r[3], "final_hp": r[4],
                    "ghost_memory": json.loads(r[5]) if r[5] else {},
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"[VECTOR][agent_registry] get_dead_ghosts failed: {e}")
            return []

    def list_all(self) -> list[dict]:
        agents = []
        for agent in self._agents.values():
            if hasattr(agent, "to_dict"):
                data = agent.to_dict()
            else:
                data = {
                    "id": getattr(agent, "id", ""),
                    "name": getattr(agent, "name", "unknown"),
                    "district": getattr(agent, "district", "unknown"),
                    "generation": getattr(agent, "generation", 1),
                    "health_points": getattr(agent, "health_points", 0),
                }
            data["agent_id"] = data.get("id", "")
            data["status"] = agent.get_status() if hasattr(agent, "get_status") else "unknown"
            data["is_alive"] = bool(getattr(agent, "is_alive", False))
            agents.append(data)
        return agents

    def count_by_district(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._agents.values():
            counts[a.district] = counts.get(a.district, 0) + 1
        return counts

    def total(self) -> int:
        return len(self._agents)


_registry_singleton: "AgentRegistry | None" = None


def get_registry() -> AgentRegistry:
    """Global singleton — one registry for all of VECTOR City."""
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = AgentRegistry()
    return _registry_singleton


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from core.city.agent_base import AgentBase

    reg = AgentRegistry()

    a1 = AgentBase("reg_test_001", "CodeBot", "coding")
    a2 = AgentBase("reg_test_002", "ResearchBot", "research")
    a3 = AgentBase("reg_test_003", "CouncilBot", "governance")
    a3.health_points = 750

    reg.register(a1)
    reg.register(a2)
    reg.register(a3)

    all_agents = reg.list_all()
    council = reg.get_council_eligible()
    counts = reg.count_by_district()

    reg.deregister("reg_test_001")
    ghosts = reg.get_dead_ghosts(district="coding")

    ok = (
        len(all_agents) == 3
        and len(council) == 1
        and reg.total() == 2
        and len(ghosts) >= 1
    )
    print(
        f"✅ agent_registry OK — {len(all_agents)} registered, "
        f"{len(council)} council eligible, 1 death → {len(ghosts)} ghost"
        if ok else "❌ FAILED"
    )
