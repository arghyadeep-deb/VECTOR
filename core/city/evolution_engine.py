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
import threading


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

    def get_constructor(self, agent_name: str) -> type | None:
        """Return the class registered for agent_name via register_constructor(),
        or None if nothing is registered for that name."""
        return self._agent_constructors.get(agent_name)

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
        try:
            from core.city import experience
            if experience.fair_cull_enabled():
                # Rank alone is not a reason to die: an agent that was never given work sits at the bottom of a district through no
                # fault of its own (owner rule 2026-09-26: idle agents are safe). Only an agent that is genuinely failing -- critical
                # HP AND a record of its own mistakes -- can be culled.
                to_cull = [a for a in to_cull
                           if getattr(a, "health_points", 0) < 200
                           and experience.own_fault_failures(experience.lineage_key(a)) >= 3]
        except Exception as e:
            # A broken/unavailable experience ledger cannot prove that a low-ranked agent is at fault. Fail safe: postpone this
            # cull pass instead of silently reverting to the legacy rank-only policy and killing healthy or idle agents.
            logger.warning("[VECTOR][evolution] fair-cull check failed; skipping cull pass: {}", e)
            to_cull = []
        culled_ids: list[str] = []

        for agent in to_cull:
            agent_id = getattr(agent, "id", None)
            if agent_id is None:
                continue
            # Log the death event only here — deregister() below
            # unconditionally persists its own ghost row from the live
            # agent object (AgentRegistry.deregister() -> _persist_ghost()),
            # so calling the full _record_death() (which also persists a
            # ghost) would just write the same agent_history row twice.
            # If deregister() somehow doesn't run (agent_id lookup miss,
            # etc.) the ghost is simply not persisted for this cull pass —
            # same as the pre-existing behavior when deregister() itself
            # fails, since its ghost write happens before its risky
            # successor-spawn logic and does not raise.
            self._log_death_event(agent)
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
        """Extract best practices from all generations of an agent.

        Queries agent_history for the ghost_memory JSON which stores
        best_decisions from each generation. The in-memory _evolution_log
        only stores a count (lessons_inherited), not the actual decisions —
        so we must go to the database.
        """
        practices = []
        try:
            from core.memory.episodic import get_db_connection, close_db_connection
            conn = get_db_connection()
            try:
                rows = conn.execute(
                    "SELECT ghost_memory FROM agent_history WHERE agent_name = ?",
                    (agent_name,)
                ).fetchall()
                for (ghost_json,) in rows:
                    if not ghost_json:
                        continue
                    import json as _json
                    ghost = _json.loads(ghost_json)
                    for d in ghost.get("best_decisions", []):
                        if d.get("reward", 0) > 0.6:
                            desc = d.get("decision", d.get("description", ""))
                            if desc:
                                practices.append(str(desc))
            finally:
                close_db_connection(conn)
        except Exception as e:
            logger.warning("[VECTOR][evolution] get_best_practices query failed for {}: {}", agent_name, e)
        return list(set(practices))

    # ── private helpers ───────────────────────────────────────────────────────

    def _record_death(self, agent) -> None:
        """Store an agent_death event in episodic memory AND persist the
        ghost row (agent_history).

        Callers that will immediately follow up with
        AgentRegistry.deregister() (which unconditionally persists its own
        ghost row from the live agent object — see
        AgentRegistry.deregister()/_persist_ghost()) should call
        _log_death_event() instead of this method, to avoid writing the
        same agent_history row twice. See cull_bottom() below — its
        double-write was harmless (INSERT OR REPLACE is idempotent, and
        deregister()'s object-shaped ghost always lands last) but redundant.
        spawn_from_ghost()/check_and_evolve() do NOT call deregister(), so
        they still need the full _record_death() (event + ghost persist).
        """
        try:
            self._log_death_event(agent)
            self._persist_agent_history(agent)
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _record_death failed: {e}")

    def _log_death_event(self, agent) -> None:
        """Store just the agent_death episodic event — no ghost persist.

        Split out of _record_death() so cull_bottom() can log the death
        event without also writing a redundant agent_history row that
        deregister() is about to write anyway.
        """
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
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _log_death_event failed: {e}")

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
                # 2026-08-05 fix — see AgentRegistry.deregister()/_persist_ghost:
                # capabilities live outside ghost_memory and must be carried
                # explicitly so a ghost read back later still has them.
                "capabilities": list(getattr(agent, "capabilities", [])),
            }
            get_registry()._persist_ghost(ghost)
        except Exception as e:
            logger.error(f"[VECTOR][evolution] _persist_agent_history failed: {e}")


# ── singleton ─────────────────────────────────────────────────────────────────
# Session-lifetime EvolutionEngine so register_constructor()'s
# agent_name → class map (populated by AgentRegistry.register(), 2026-08-05
# fix) actually persists across calls — EvolutionEngine() on its own
# creates a fresh instance with an empty map every time, which is why the
# constructor registry was previously dead in production.

_evolution_engine_singleton: "EvolutionEngine | None" = None
_evolution_engine_lock = threading.Lock()


def get_evolution_engine() -> "EvolutionEngine":
    """Global singleton EvolutionEngine — mirrors agent_registry.get_registry()."""
    global _evolution_engine_singleton
    if _evolution_engine_singleton is None:
        with _evolution_engine_lock:
            if _evolution_engine_singleton is None:
                _evolution_engine_singleton = EvolutionEngine()
    return _evolution_engine_singleton


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
