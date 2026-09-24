import sys

__all__ = [
    "AgentRegistry",
    "get_registry",
]

import json
import datetime
import threading

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
        # Death-loop breaker state (see _register_or_quarantine)
        self._death_times: dict[str, list[float]] = {}
        self._quarantine: dict[str, dict] = {}
        self._consecutive_quarantines: dict[str, int] = {}
        self._last_release: dict[str, float] = {}
        logger.info("[VECTOR][agent_registry] initialized")

    def _get_mem(self):
        if self._mem is None:
            from core.memory.episodic import EpisodicMemory
            self._mem = EpisodicMemory()
        return self._mem

    def register(self, agent) -> None:
        """Register a living agent in the city."""
        self._agents[agent.id] = agent
        # Wire EvolutionEngine.register_constructor() into the real
        # register->die->deregister lifecycle (2026-08-05 fix) — it existed
        # but was never called in production. Best-effort / non-fatal: the
        # actual successor-reconstruction in deregister() below uses
        # type(agent) directly (always correct, no lookup-miss risk), this
        # just makes the pre-existing constructor registry genuinely
        # populated for any other consumer of EvolutionEngine.spawn_from_ghost
        # / check_and_evolve (and for tests asserting the wiring is live).
        try:
            from core.city.evolution_engine import get_evolution_engine
            get_evolution_engine().register_constructor(agent.name, type(agent))
        except Exception as e:
            logger.debug(f"[VECTOR][agent_registry] constructor registration skipped for {agent.name}: {e}")
        logger.info(
            f"[VECTOR][agent_registry] +{agent.name} ({agent.district}) "
            f"HP={agent.health_points} gen={agent.generation}"
        )

    def _instantiate_successor(self, agent_class: type, agent, new_id: str, new_gen: int):
        """Build a fresh instance of agent_class, trying the constructor
        shapes actually used across VECTOR's ~130 district agent classes.

        declarative_manifest.ManifestLoader.instantiate_all() always builds
        district agents with `cls()` (zero args) — most subclasses (e.g.
        CodingSwarm, ArchitectBot(ghost=None)) hardcode their own id/name/
        district internally. A smaller set never override __init__ at all
        and need AgentBase's own (agent_id, name, district, generation=)
        signature. Try both; TypeError (signature mismatch) tries the next
        shape. Any OTHER exception is a real bug inside that class's
        __init__ and is left to propagate — masking it as "no constructor
        matched" would hide the actual failure from the loud log in
        deregister()'s except block.
        """
        last_exc: Exception | None = None
        for build in (
            lambda: agent_class(),
            lambda: agent_class(agent_id=new_id, name=agent.name, district=agent.district, generation=new_gen),
            lambda: agent_class(new_id, agent.name, agent.district, new_gen),
        ):
            try:
                return build()
            except TypeError as e:
                last_exc = e
                continue
        raise TypeError(f"no supported constructor shape for {agent_class.__name__}: {last_exc}")

    # ── Death-loop breaker (external review Phase 3 / KNOWN_ISSUES #81) ──────
    # An agent whose every dispatch ends in death (APITester: ~858 deaths/day,
    # one per ~63s) used to be resurrected instantly into the same failure
    # forever. Now the Nth death of the same agent name inside a window
    # parks its successor for an exponentially growing backoff instead of
    # registering it. Configured via CONFIG["agent_death_loop"].

    def _loop_cfg(self) -> dict:
        cfg = CONFIG.get("agent_death_loop", {}) if isinstance(CONFIG, dict) else {}
        return {
            "max_deaths": int(cfg.get("max_deaths", 5)),
            "window": float(cfg.get("window_seconds", 600.0)),
            "base": float(cfg.get("base_backoff_seconds", 300.0)),
            "max": float(cfg.get("max_backoff_seconds", 3600.0)),
        }

    def _record_death(self, name: str) -> None:
        import time
        cfg = self._loop_cfg()
        now = time.time()
        times = [t for t in self._death_times.get(name, []) if now - t < cfg["window"]]
        times.append(now)
        self._death_times[name] = times
        last = self._last_release.get(name)
        if last is not None and now - last > cfg["window"] * 2:
            self._consecutive_quarantines[name] = 0

    def _register_or_quarantine(self, successor, name: str) -> None:
        import time
        cfg = self._loop_cfg()
        if len(self._death_times.get(name, [])) < cfg["max_deaths"]:
            self.register(successor)
            return
        n = self._consecutive_quarantines.get(name, 0) + 1
        self._consecutive_quarantines[name] = n
        backoff = min(cfg["base"] * (2 ** (n - 1)), cfg["max"])
        self._quarantine[successor.id] = {"agent": successor, "until": time.time() + backoff, "name": name}
        self._death_times[name] = []
        logger.critical(
            f"[VECTOR][agent_registry] {name} died {cfg['max_deaths']}x within "
            f"{cfg['window']:.0f}s -- death loop. Successor quarantined for "
            f"{backoff:.0f}s (quarantine #{n}) instead of respawning into the "
            f"same failure. Fix the root cause of the deaths."
        )

    def _release_due_quarantined(self) -> None:
        if not self._quarantine:
            return
        import time
        now = time.time()
        for agent_id in [i for i, q in self._quarantine.items() if q["until"] <= now]:
            entry = self._quarantine.pop(agent_id)
            self._last_release[entry["name"]] = now
            self.register(entry["agent"])
            logger.warning(f"[VECTOR][agent_registry] {entry['name']} released from death-loop quarantine")

    def quarantined(self) -> list[dict]:
        import time
        now = time.time()
        return [
            {"name": q["name"], "agent_id": i, "seconds_remaining": max(0.0, q["until"] - now)}
            for i, q in self._quarantine.items()
        ]

    def deregister(self, agent_id: str) -> None:
        """Remove agent on death. Ghost saved, successor spawned as the SAME
        class as the agent that died (RULE 9 — Darwinism is real, and a
        successor must do REAL WORK, not silently come back as a bare
        AgentBase stub with zero capabilities and a fake 'ok' run() —
        2026-08-05 fix)."""
        agent = self._agents.pop(agent_id, None)
        if not agent:
            return
        self._record_death(agent.name)
        agent_class = type(agent)
        # capabilities are injected by ManifestLoader AFTER construction
        # (declarative_manifest.instantiate_all: `instance.capabilities =
        # list(entry.get("capabilities", []))`) — never set inside a
        # district class's own __init__. So they must be carried through
        # the ghost explicitly, or ANY successor (reconstructed class or
        # the RULE-9 bare-AgentBase fallback) comes back with
        # capabilities=[] and governor.dispatch()'s capability match
        # silently stops routing real work to it.
        agent_capabilities = list(getattr(agent, "capabilities", []))
        ghost_data = {
            "name": agent.name,
            "district": agent.district,
            "generation": agent.generation,
            "final_hp": agent.health_points,
            "ghost_memory": agent.ghost_memory,
            "lessons_learned": getattr(agent, "lessons", []),
            "best_decisions": getattr(agent, "best_decisions", []),
            "personality_traits": getattr(agent, "personality_traits", {}),
            "capabilities": agent_capabilities,
        }
        self._persist_ghost(agent)
        logger.info(
            f"[VECTOR][agent_registry] -{agent.name} died — "
            f"ghost saved gen={agent.generation}"
        )
        try:
            import uuid as _uuid
            from core.city.evolution_engine import get_evolution_engine
            # Must use the singleton — it has constructors registered at boot
            # (line 47). A fresh EvolutionEngine() has zero constructors, so
            # spawn_successor() returns None and we fall through to the bare
            # AgentBase fallback — meaning successors NEVER inherit lessons or
            # capabilities, making Darwinian evolution dead code.
            engine = get_evolution_engine()
            successor_agent = engine.spawn_successor(ghost_data)

            if successor_agent is None:
                raise RuntimeError(
                    f"EvolutionEngine.spawn_successor returned None for "
                    f"{agent.name} — no constructor registered"
                )

            new_id = str(_uuid.uuid4())
            # M1e (2026-09-09): spawn_successor() returns a dict blueprint by
            # design (core/city/evolution_engine.py's own docstring + its
            # __main__ self-test both use dict-key access) -- this call site
            # was the one place still doing attribute access on it, which
            # raised on every real agent death and silently downgraded every
            # successor to a bare, capability-stripped AgentBase stub. No
            # "health_points" key exists in the blueprint; the HP field is
            # named "starting_hp". See
            # VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md.
            successor = self._instantiate_successor(
                agent_class, agent, new_id, successor_agent["generation"]
            )
            successor.generation = successor_agent["generation"]
            successor.district = agent.district
            successor.name = agent.name
            successor.health_points = successor_agent["starting_hp"]
            successor.model = successor._calculate_model()
            successor.capabilities = list(agent_capabilities)
            successor.inherit_ghost(ghost_data)
            self._register_or_quarantine(successor, agent.name)
            logger.info(
                f"[VECTOR][agent_registry] {agent.name} successor spawned as "
                f"{type(successor).__name__} gen={successor.generation} "
                f"HP={successor.health_points} capabilities={len(successor.capabilities)}"
            )
        except Exception as e:
            logger.error(
                f"[VECTOR][agent_registry] {agent.name} successor reconstruction "
                f"FAILED for class {agent_class.__name__}: {e} — downgrading to a "
                f"bare AgentBase so the district stays staffed (RULE 9). This "
                f"agent will do NO REAL WORK (fake 'ok' run(), no capabilities) "
                f"until the process restarts and re-bootstraps it from the "
                f"manifest — fix the constructor mismatch."
            )
            # Fallback: plain gen+1 AgentBase so the district stays staffed (RULE 9)
            try:
                import uuid as _uuid
                from core.city.agent_base import AgentBase
                successor = AgentBase(
                    str(_uuid.uuid4()),
                    agent.name,
                    agent.district,
                    generation=agent.generation + 1,
                )
                successor.capabilities = list(agent_capabilities)
                successor.inherit_ghost(ghost_data)
                self._register_or_quarantine(successor, agent.name)
                logger.info(f"[VECTOR][agent_registry] fallback spawn: {agent.name} gen={successor.generation}")
            except Exception as fe:
                logger.error(f"[VECTOR][agent_registry] fallback spawn also failed: {fe}")

    def _persist_ghost(self, agent) -> None:
        """Save dead agent's history for next-generation inheritance.

        Accepts either a live agent object (attribute access, e.g. from
        deregister()) or a plain ghost dict (e.g. evolution_engine's
        _persist_agent_history, which builds {"agent_id":..., "agent_name":...}
        rather than an AgentBase instance) — both call this method, so both
        shapes must work (2026-07-21: dict callers were crashing here on
        every bulk cull).
        """
        try:
            if isinstance(agent, dict):
                agent_id = agent.get("agent_id") or agent.get("id")
                agent_name = agent.get("agent_name") or agent.get("name")
                district = agent.get("district")
                generation = agent.get("generation")
                final_hp = agent.get("final_hp") or agent.get("health_points")
                ghost_memory = agent.get("ghost_memory")
                caps = agent.get("capabilities")
            else:
                agent_id = agent.id
                agent_name = agent.name
                district = agent.district
                generation = agent.generation
                final_hp = agent.health_points
                ghost_memory = agent.ghost_memory
                caps = getattr(agent, "capabilities", None)

            # Carry capabilities into the persisted ghost row (2026-08-05 fix)
            # so a ghost read back via get_dead_ghosts() — e.g. after a
            # process restart — still yields correct capabilities. die()'s
            # ghost_memory dict (agent_base.py, out of scope here) doesn't
            # include this key, so add it defensively without mutating the
            # caller's own dict. Existing ghost rows without the key are
            # unaffected — callers already do `.get("capabilities", [])`.
            if isinstance(ghost_memory, dict) and caps and "capabilities" not in ghost_memory:
                ghost_memory = {**ghost_memory, "capabilities": list(caps)}

            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            conn.execute(
                "INSERT OR REPLACE INTO agent_history "
                "(agent_id, agent_name, district, generation, final_hp, ghost_memory, died_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    agent_name,
                    district,
                    generation,
                    final_hp,
                    json.dumps(ghost_memory),
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[VECTOR][agent_registry] ghost persist failed: {e}")

    def get(self, agent_id: str):
        self._release_due_quarantined()
        return self._agents.get(agent_id)

    def get_all_agents(self) -> list:
        self._release_due_quarantined()
        return list(self._agents.values())

    def list_alive(self) -> list:
        """Return all agents with HP > 0 (alive). Used by event_fanout_loop."""
        self._release_due_quarantined()
        return [a for a in self._agents.values() if getattr(a, 'health_points', 1) > 0]

    def get_by_district(self, district: str) -> list:
        self._release_due_quarantined()
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
        seen_ids: set[str] = set()
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
            # Guarantee id is always populated
            if not data.get("id"):
                data["id"] = getattr(agent, "id", f"agent-{len(agents)}")
            # Skip duplicates by id (guards against double-bootstrap)
            agent_id = data["id"]
            if agent_id in seen_ids:
                continue
            seen_ids.add(agent_id)
            data["agent_id"] = agent_id
            data["status"] = self._lifecycle_status(agent)
            data["is_alive"] = bool(getattr(agent, "health_points", 0) > 0)
            agents.append(data)
        return agents

    def _lifecycle_status(self, agent) -> str:
        """Return HP-based lifecycle state without calling agent operational APIs."""
        hp = float(getattr(agent, "health_points", 0) or 0)
        if hp >= 800:
            return "elite"
        if hp >= 600:
            return "strong"
        if hp >= 400:
            return "healthy"
        if hp >= 200:
            return "weakened"
        if hp >= 1:
            return "critical"
        return "dead"

    def count_by_district(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self._agents.values():
            counts[a.district] = counts.get(a.district, 0) + 1
        return counts

    def total(self) -> int:
        return len(self._agents)


_registry_singleton: "AgentRegistry | None" = None
_registry_lock = threading.Lock()


def get_registry() -> AgentRegistry:
    """Global singleton — one registry for all of VECTOR City. Thread-safe."""
    global _registry_singleton
    if _registry_singleton is None:
        with _registry_lock:
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

    # After deregister, gen2 successor is spawned → total stays at 3
    successor_agents = [a for a in reg.list_all() if getattr(a.get("generation", 1), "__class__", None) is not None and a.get("generation", 1) >= 2]
    ok = (
        len(all_agents) == 3
        and len(council) == 1
        and reg.total() == 3  # gen2 CodeBot spawned, still 3 alive
        and len(ghosts) >= 1
    )
    print(
        f"✅ agent_registry OK — {len(all_agents)} registered, "
        f"{len(council)} council eligible, 1 death → gen2 spawned, {len(ghosts)} ghost"
        if ok else "❌ FAILED"
    )
