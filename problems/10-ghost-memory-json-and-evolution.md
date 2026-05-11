# Problem 10 — Ghost Memory JSON Serialization + Evolution Not Wired

**Severity: HIGH**
**Status: PARTIALLY FIXED (JSON bug fixed; evolution wiring documented)**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Part A — Ghost Stored as str() Not json.dumps() (FIXED)

### Symptom

`agent_registry._persist_ghost()` serialized `agent.ghost_memory` using
Python's default `str()`:

```python
str(agent.ghost_memory)  # produces {'name': 'Bot', 'lessons': [...]}
```

Python `str()` on a dict produces non-JSON (single quotes, Python repr).
When `get_dead_ghosts()` returns these rows, the `ghost_memory` field is an
unparseable string. Any call to `inherit_ghost(ghost)` that does
`ghost.get("lessons")` on this string returns `None` silently.

### Fix Applied

`core/city/agent_registry.py`:

```python
# _persist_ghost — serialization
import json
json.dumps(agent.ghost_memory)   # valid JSON, deserializable

# get_dead_ghosts — deserialization
"ghost_memory": json.loads(r[5]) if r[5] else {},
```

Also fixed `_persist_ghost` and `get_dead_ghosts` to use
`get_db_connection()` directly (bypasses the now-fixed `self.conn` issue from
Problem 08, but is explicit and safe).

---

## Part B — EvolutionEngine Not Wired (DOCUMENTED)

### Symptom

Agents die (HP → 0), `die()` builds `ghost_memory` in-memory, registry
persists it to `agent_history` — but no successor agent is ever spawned.
The Darwinian evolution cycle is incomplete: death happens, succession doesn't.

### Root Cause

`core/city/evolution_engine.py` has `spawn_successor()` which returns a
blueprint dict. But nothing in the loop calls it. The chain is:

```
agent.die() → ghost built in memory
registry.deregister() → ghost written to agent_history ✅
# MISSING: evolution_engine.spawn_successor(ghost) → new AgentBase registered
```

### Fix Required

Wire into `agent_registry.deregister()`:

```python
def deregister(self, agent_id: str) -> None:
    agent = self._agents.pop(agent_id, None)
    if agent:
        self._persist_ghost(agent)
        # Spawn successor with ghost inheritance
        from core.city.evolution_engine import EvolutionEngine
        from core.city.agent_base import AgentBase
        blueprint = EvolutionEngine().spawn_successor(agent)
        successor = AgentBase(
            agent_id=blueprint["agent_id"],
            name=blueprint["name"],
            district=agent.district,
            generation=blueprint["generation"],
        )
        ghosts = self.get_dead_ghosts(district=agent.district, limit=1)
        if ghosts:
            successor.inherit_ghost(ghosts[0]["ghost_memory"])
        self.register(successor)
        logger.info(f"[VECTOR][agent_registry] successor spawned gen={blueprint['generation']}")
```

### Verification

After fix: kill an agent by deducting HP to 0, confirm:
1. `agent_history` has a row for the dead agent
2. Registry has one fewer agent of the old name
3. Registry has one new agent (same district, gen+1, non-zero starting HP)
4. `successor.lessons` contains inherited lessons from the ghost
