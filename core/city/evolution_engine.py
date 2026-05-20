"""
V.E.C.T.O.R. EvolutionEngine.
Handles agent evolution across generations — dead agents spawn improved successors.

EvolutionEngine manages the lifecycle of agents across generations: spawning new agents
when old ones die (with ghost memory inheritance), culling weak agents, and tracking
evolutionary history.

RULE 9  — Agent Darwinism is real. HP must wire to actual outcomes.
RULE 11 — All evolution via local Ollama only. No Claude API at runtime.
"""
import sys
import json
import uuid
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class EvolutionEngine:
    """
    Evolves agents across generations based on performance data.

    Spawning: when an agent dies (HP=0), spawn a new agent of the same type
              in the same district, inheriting the ghost memory.
    Culling:  periodically identify critically weak agents (HP < 50) and
              offer them a "last chance" before death.
    History:  track all generations in agent_history SQLite table.

    Also exposes the legacy spawn_successor(ghost_dict) API used by
    AgentRegistry.deregister() so that existing callers are not broken.
    """

    # class-level lifetime counters shared across instances
    _total_deaths: int = 0
    _total_spawns: int = 0

    def __init__(self, registry=None, memory=None):
        """
        Parameters
        ----------
        registry : AgentRegistry | None
            Shared city registry.  When None the engine operates in legacy
            (dict-only) mode — spawn_successor() still works.
        memory : EpisodicMemory | None
            Episodic memory store.  Lazily created when first needed if None.
        """
        self._registry = registry
        self._memory = memory

        # maps agent name → its concrete class (for respawning exact type)
        self._agent_constructors: dict[str, type] = {}

        # tracks highest generation seen per "district::name" key
        self._generation_map: dict[str, int] = {}

        # in-process evolution log (also written to episodic_memory)
        self._evolution_log: list[dict] = []

        logger.info("[VECTOR][evolution] EvolutionEngine ready")

    # ── dependency helpers ────────────────────────────────────────────────────

    def _get_memory(self):
        """Return episodic memory, creating it lazily if necessary."""
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    # ── constructor registry ──────────────────────────────────────────────────

    def register_constructor(self, agent_name: str, agent_class: type) -> None:
        """
        Register what class to instantiate when respawning an agent of this type.

        Parameters
        ----------
        agent_name  : str   key that matches AgentBase.name
        agent_class : type  the concrete class (must subclass AgentBase)
        """
        self._agent_constructors[agent_name] = agent_class
        logger.debug(
            f"[VECTOR][evolution] constructor registered: {agent_name} → {agent_class.__name__}"
        )

    # ── legacy dict-based API (called by AgentRegistry.deregister) ────────────

    def spawn_successor(self, dead_agent: dict) -> dict:
        """
        Create an improved successor from a dead agent's ghost dict.

        Kept for backwards-compatibility with AgentRegistry which calls:
            blueprint = EvolutionEngine().spawn_successor(ghost_data)

        Parameters
        ----------
        dead_agent : dict
            Ghost dict with keys: name, generation, lessons_learned,
            best_decisions, personality_traits, died_at

        Returns
        -------
        dict
            Blueprint with keys: name, generation, starting_hp, …
        """
        agent_name = dead_agent.get("name", "Unknown")
        prev_gen = dead_agent.get("generation", 1)
        lessons = dead_agent.get("lessons_learned", [])
        decisions = dead_agent.get("best_decisions", [])
        traits = dead_agent.get("personality_traits", {})

        new_gen = prev_gen + 1

        # track highest generation in the map
        key = agent_name
        if key in self._generation_map:
            self._generation_map[key] = max(self._generation_map[key], new_gen)
        else:
            self._generation_map[key] = new_gen

        successor = {
            "name": agent_name,
            "generation": new_gen,
            "starting_hp": min(500 + (new_gen * 50), 800),
            "lessons_inherited": len(lessons),
            "decisions_inherited": len(decisions),
            "personality_traits": traits,
            "spawned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "death_reason": dead_agent.get("died_at", "unknown"),
        }

        self._evolution_log.append(successor)
        EvolutionEngine._total_deaths += 1
        EvolutionEngine._total_spawns += 1

        logger.info(
            f"[VECTOR][evolution] {agent_name} gen{prev_gen} died → gen{new_gen} spawned "
            f"(HP={successor['starting_hp']}, lessons={len(lessons)})"
        )
        return successor

    # ── class-based async API ─────────────────────────────────────────────────

    async def spawn_from_ghost(self, dead_agent) -> "object | None":
        """
        Called when an AgentBase instance dies (HP=0).

        Creates a new instance of the same class, inherits ghost memory,
        registers it in the city registry, and persists death+birth events.

        Parameters
        ----------
        dead_agent : AgentBase
            The dead agent.  Must have .name, .district, .generation,
            .ghost_memory, .lessons attributes.

        Returns
        -------
        AgentBase | None
            The newly spawned successor, or None if the constructor is unknown.
        """
        agent_name = dead_agent.name
        old_gen = dead_agent.generation
        new_gen = old_gen + 1
        ghost = dead_agent.ghost_memory or {}
        lessons = getattr(dead_agent, "lessons", ghost.get("lessons_learned", []))

        agent_class = self._agent_constructors.get(agent_name)
        if agent_class is None:
            logger.warning(
                f"[VECTOR][evolution] No constructor for '{agent_name}' — cannot spawn successor"
            )
            return None

        # persist the death first
        self._record_death(dead_agent)

        # create successor
        try:
            new_agent = agent_class(
                agent_id=str(uuid.uuid4()),
                name=agent_name,
                district=dead_agent.district,
                generation=new_gen,
            )
        except TypeError:
            # constructor might not accept all kwargs — fall back gracefully
            new_agent = agent_class()
            new_agent.name = agent_name
            new_agent.district = dead_agent.district
            new_agent.generation = new_gen

        new_agent.inherit_ghost(ghost)

        # update generation map
        key = f"{dead_agent.district}::{agent_name}"
        self._generation_map[key] = max(self._generation_map.get(key, 1), new_gen)

        # register in the city registry
        if self._registry is not None:
            self._registry.register(new_agent)

        # update counters and log
        EvolutionEngine._total_deaths += 1
        EvolutionEngine._total_spawns += 1

        entry = {
            "name": agent_name,
            "district": dead_agent.district,
            "generation": new_gen,
            "lessons_inherited": len(lessons),
            "spawned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._evolution_log.append(entry)

        self._record_birth(new_agent)

        logger.info(
            f"[VECTOR][evolution] {agent_name} gen {old_gen} died → "
            f"gen {new_gen} spawned with {len(lessons)} lessons"
        )
        return new_agent

    async def check_and_evolve(self, agents: list) -> dict:
        """
        Scan a list of AgentBase instances, respawn dead ones, flag critical ones.

        Called periodically (e.g. every 30 minutes) from autonomous_loop.

        Parameters
        ----------
        agents : list[AgentBase]

        Returns
        -------
        dict
            {"died": int, "spawned": int, "critical": list[str]}
        """
        died = 0
        spawned = 0
        critical: list[str] = []

        for agent in agents:
            hp = getattr(agent, "health_points", 1)

            if hp == 0:
                died += 1
                new_agent = await self.spawn_from_ghost(agent)
                if new_agent is not None:
                    spawned += 1
            elif 0 < hp < 50:
                critical.append(getattr(agent, "name", "unknown"))
                logger.warning(
                    f"[VECTOR][evolution] CRITICAL — {agent.name} @ {hp} HP "
                    f"(district: {getattr(agent, 'district', '?')})"
                )

        return {"died": died, "spawned": spawned, "critical": critical}

    async def cull_bottom(self, district: str, keep_top: int = 5) -> list[str]:
        """
        If a district has more than keep_top agents, remove the lowest-HP ones.

        Parameters
        ----------
        district  : str
        keep_top  : int   number of agents to retain

        Returns
        -------
        list[str]
            IDs of culled districts.
        """
        if self._registry is None:
            logger.warning("[VECTOR][evolution] cull_bottom: no registry attached")
            return []

        district_agents = self._registry.get_by_district(district)
        if len(district_agents) <= keep_top:
            return []

        # sort ascending by HP so the weakest come first
        sorted_agents = sorted(
            district_agents, key=lambda a: getattr(a, "health_points", 0)
        )
        to_cull = sorted_agents[: len(sorted_agents) - keep_top]
        culled_ids: list[str] = []

        for agent in to_cull:
            agent_id = getattr(agent, "id", None)
            if agent_id is None:
                continue
            self._record_death(agent)
            try:
                self._registry.deregister(agent_id)
            except Exception as e:
                logger.error(
                    f"[VECTOR][evolution] deregister failed for {agent_id}: {e}"
                )
            culled_ids.append(agent_id)

        logger.info(
            f"[VECTOR][evolution] Culled {len(culled_ids)} agents from {district} district"
        )
        return culled_ids

    # ── stats ─────────────────────────────────────────────────────────────────

    def get_evolution_stats(self, agent_name: str | None = None) -> dict:
        """
        Return evolution statistics.

        When agent_name is provided: legacy per-agent view (backwards-compatible).
        When agent_name is None: full system view used by the new async API.
        """
        if agent_name is not None:
            # legacy per-agent view
            generations = [e for e in self._evolution_log if e.get("name") == agent_name]
            return {
                "total_generations": len(generations),
                "current_gen": generations[-1]["generation"] if generations else 1,
                "total_deaths": len(generations),
                "lessons_preserved": sum(
                    e.get("lessons_inherited", 0) for e in generations
                ),
            }

        # full system view
        highest_gen = max(self._generation_map.values(), default=0)

        district_breakdown: dict[str, dict] = {}
        if self._registry is not None:
            for district_name, count in self._registry.count_by_district().items():
                agents = self._registry.get_by_district(district_name)
                hps = [getattr(a, "health_points", 0) for a in agents]
                district_breakdown[district_name] = {
                    "alive": count,
                    "dead": 0,   # dead agents are removed from the live registry
                    "avg_hp": round(sum(hps) / count, 1) if count else 0,
                }

        return {
            "total_deaths": EvolutionEngine._total_deaths,
            "total_spawns": EvolutionEngine._total_spawns,
            "highest_generation": highest_gen,
            "districts": district_breakdown,
        }

    def get_best_practices(self, agent_name: str) -> list[str]:
        """Extract best practices from all generations of an agent."""
        practices = []
        for e in self._evolution_log:
            if e.get("name") == agent_name:
                # Log stores decisions under "decisions_inherited" (check both for compat)
                for d in e.get("decisions_inherited", e.get("decisions", [])):
                    if d.get("reward", 0) > 0.8:
                        practices.append(d.get("description", ""))
        return list(set(p for p in practices if p))

    # ── private helpers ───────────────────────────────────────────────────────

    def _record_death(self, agent) -> None:
        """Store an agent_death event in episodic memory."""
        try:
            mem = self._get_memory()
            content = (
                f"Agent {getattr(agent, 'name', '?')} "
                f"gen {getattr(agent, 'generation', '?')} died at "
                f"{getattr(agent, 'health_points', 0)} HP"
            )
            mem.store(
                event_type="agent_death",
                content=content,
                tags=["evolution", "death", getattr(agent, "district", "unknown")],
                source="evolution_engine",
            )
            self._persist_agent_history(agent)
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _record_death failed: {e}")

    def _record_birth(self, agent) -> None:
        """Store an agent_birth event in episodic memory."""
        try:
            mem = self._get_memory()
            lessons = getattr(agent, "lessons", [])
            content = (
                f"Agent {getattr(agent, 'name', '?')} "
                f"gen {getattr(agent, 'generation', '?')} born with "
                f"{len(lessons)} inherited lessons"
            )
            mem.store(
                event_type="agent_birth",
                content=content,
                tags=["evolution", "birth", getattr(agent, "district", "unknown")],
                source="evolution_engine",
            )
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _record_birth failed: {e}")

    def _persist_agent_history(self, agent) -> None:
        """Delegate to AgentRegistry._persist_ghost to avoid duplicate logic."""
        try:
            from core.city.agent_registry import get_registry
            ghost = {
                "agent_id":    getattr(agent, "id", str(uuid.uuid4())),
                "agent_name":  getattr(agent, "name", "unknown"),
                "district":    getattr(agent, "district", "unknown"),
                "generation":  getattr(agent, "generation", 1),
                "final_hp":    getattr(agent, "health_points", 0),
                "ghost_memory": getattr(agent, "ghost_memory", {}),
            }
            get_registry()._persist_ghost(ghost)
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _persist_agent_history failed: {e}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    sys.stdout.reconfigure(encoding="utf-8")

    from core.city.agent_base import AgentBase
    from core.city.agent_registry import AgentRegistry
    from core.memory.episodic import EpisodicMemory

    async def test():
        mem = EpisodicMemory()
        reg = AgentRegistry()
        engine = EvolutionEngine(reg, mem)

        # define a minimal concrete agent
        class TestAgent(AgentBase):
            def __init__(self, agent_id="test-default", name="TestAgent",
                         district="test", **kwargs):
                super().__init__(
                    agent_id=agent_id, name=name, district=district, **kwargs
                )

        engine.register_constructor("TestAgent", TestAgent)

        # create agent, simulate death, verify respawn
        agent = TestAgent(agent_id="test1", name="TestAgent", district="test")
        reg.register(agent)

        agent.health_points = 0
        agent.ghost_memory = {
            "lessons_learned": ["lesson1"],
            "best_decisions": [],
            "personality_traits": {},
            "generation": 1,
            "died_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        agent.lessons = ["lesson1"]

        new_agent = await engine.spawn_from_ghost(agent)
        assert new_agent is not None, "spawn_from_ghost returned None"
        assert new_agent.generation == 2, f"Expected gen 2, got {new_agent.generation}"
        assert len(new_agent.lessons) == 1, \
            f"Ghost lessons not inherited — got {new_agent.lessons}"

        # check_and_evolve on a second dead agent
        dead2 = TestAgent(agent_id="test2", name="TestAgent", district="test")
        dead2.health_points = 0
        dead2.ghost_memory = {
            "lessons_learned": ["lesson_x"],
            "best_decisions": [],
            "personality_traits": {},
            "generation": 1,
            "died_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        dead2.lessons = ["lesson_x"]
        result = await engine.check_and_evolve([dead2])
        assert result["died"] == 1, f"Expected 1 death, got {result['died']}"
        assert result["spawned"] == 1, f"Expected 1 spawn, got {result['spawned']}"

        # legacy dict API still works
        ghost_dict = {
            "name": "BugHunter",
            "generation": 2,
            "lessons_learned": ["check edge cases", "test boundary"],
            "best_decisions": [],
        }
        blueprint = engine.spawn_successor(ghost_dict)
        assert blueprint["generation"] == 3, "spawn_successor gen calc wrong"
        assert blueprint["name"] == "BugHunter"

        # full-system stats
        stats = engine.get_evolution_stats()
        print(f"Stats: {stats}")

        # per-agent stats (legacy)
        per_agent = engine.get_evolution_stats("BugHunter")
        assert per_agent["total_deaths"] >= 1

        mem.close()
        print("✅ evolution_engine.py OK")

    asyncio.run(test())