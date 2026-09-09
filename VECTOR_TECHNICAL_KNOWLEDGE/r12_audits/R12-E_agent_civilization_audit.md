# R12-E — Agent Civilization Audit

## Objective
Read-only audit of `core/city/{agent_base,governor,agent_registry,evolution_engine}.py`
at HEAD `81b53b1175aede4ed05d1b9d086af91dda64c8a6`. Determine what part of the
"Darwinian agent civilization" (HP, death, succession, evolution) is genuinely
behaviorally real vs decorative bookkeeping. No production code modified; one
existing test was *run* (not edited) as evidence.

## Method
Direct source read of all four files, grep for `health_points`/`can_vote_in_council`
usage across the repo, then ran the pre-existing regression test
`tests/unit/test_agent_registry_successor_class.py` (already in the suite, written
for the 2026-08-05 "successor comes back as a bare stub" fix) to check whether its
own claimed fix is currently live.

## Findings

### 1. HP → model tier: REAL (`agent_base.py:82-94,181-183`)
`award_points()`/`deduct_points()` both call `self._calculate_model()` after every
change; HP bands (800/600/400/200/1) map to `CONFIG['models']['cloud_coder'
/'cloud_orchestrator'/'focus'/'reasoning'/'ambient']`. This is a real, unconditional
side effect of every HP change — not test-only.

### 2. HP → dispatch selection: REAL, but often a no-op tiebreak
`governor.py:2294,2301,2315` (`agent = max(capable/agents, key=lambda a: a.health_points)`)
and `governor.py:2184` (council pre-agent selection) genuinely use HP to pick which
agent handles a task. This is real code, not vestigial. However its practical effect
depends on district agent-count: most districts have exactly one agent per declared
capability, so the `max()` over a 1-element list is a no-op. Genuine HP-driven
routing only manifests where a district has ≥2 agents sharing a capability (e.g.
`coding` — 24 agents loaded via `CodingSwarm._load_agents()`, confirmed live in the
test run below). Not measured in this audit: how often that condition actually
occurs during a real dispatch in production traffic.

### 3. `can_vote_in_council()` (700 HP gate): wired, reachable
`agent_registry.get_council_eligible()` filters on it and is consumed by
`governor.py`'s council-convene path. Real gate, not orphaned — confirmed by
grep (files list includes `districts/governance/llm_council.py`,
`core/city/governor.py`). Not independently re-verified end-to-end in this pass
(R12-I's safety trace or a dedicated council test would be the authoritative check).

### 4. Ghost memory + lesson inheritance: REAL when the successor path succeeds
`die()` → `agent_registry.deregister()` → ghost dict persisted to `agent_history`
SQLite table (`_persist_ghost()`) → `inherit_ghost()` copies lessons/best_decisions/
personality_traits onto the new instance → `get_system_prompt()` folds them into the
successor's own system prompt (`agent_base.py:294-322`). This chain is genuinely
wired end-to-end **when `_instantiate_successor()` succeeds**. See Finding 5 for why
it currently does not.

### 5. **P0/P1 DEFECT (confirmed live, not hypothetical): successor reconstruction is currently broken for every real district-agent class — every death silently downgrades to a bare, capability-stripped `AgentBase` stub.**

`agent_registry.py:126-138`:
```python
engine = get_evolution_engine()
successor_agent = engine.spawn_successor(ghost_data)   # returns a plain dict
...
successor = self._instantiate_successor(
    agent_class, agent, new_id, successor_agent.generation   # <- dict.generation
)
successor.generation = successor_agent.generation              # <- dict.generation
...
successor.health_points = successor_agent.health_points        # <- dict.health_points
```
`EvolutionEngine.spawn_successor()` (`evolution_engine.py:97-149`) returns a plain
`dict` with keys `name`/`generation`/`starting_hp`/... — it has no `.generation` or
`.health_points` *attributes*. Every call to `successor_agent.generation` raises
`AttributeError: 'dict' object has no attribute 'generation'`, which is caught by
the surrounding `except Exception` and silently downgrades the successor to a bare
`AgentBase(..., generation=agent.generation + 1)` (the fallback branch,
`agent_registry.py:161-176`) — logged as an `ERROR` (loud, not silent-silent), but
this is now the **only** path any real successor ever takes.

**Live confirmation** (this session, `pytest tests/unit/test_agent_registry_successor_class.py -v`):
```
test_dying_coding_swarm_respawns_as_coding_swarm_with_capabilities  FAILED
...
ERROR | core.city.agent_registry:deregister:153 - [VECTOR][agent_registry]
CodingSwarm successor reconstruction FAILED for class CodingSwarm:
'dict' object has no attribute 'generation' — downgrading to a bare AgentBase
so the district stays staffed (RULE 9). This agent will do NO REAL WORK
(fake 'ok' run(), no capabilities) until the process restarts...
```
1 failed / 2 passed. The other two tests pass *because* they only assert the
fallback-path behavior (bare `AgentBase`, capabilities preserved, lessons
preserved) — they do not require the real-class path to work, so they mask the
regression rather than catch it. Only the one test asserting `type(successor) is
CodingSwarm` (the actual intended fix from the 2026-08-05 commit referenced in this
file's own docstring) fails.

**Blast radius**: `cull_bottom()` (`evolution_engine.py:298-319`, wired live into
`autonomous_loop.py:1926` on the 2AM reflect tick) also calls
`self._registry.deregister(agent_id)` for every culled agent — same broken path.
So both organic death (HP→0) and scheduled culling currently downgrade every real
district-agent subclass (CodingSwarm's 24 sub-agents, ArchitectBot, BugHunter, all
~133 agent classes) to a generic `AgentBase` with a fake `run()` returning
`{"status": "ok", ...}` and (until manifest re-injection on next process restart)
zero capabilities — meaning `governor.dispatch()`'s capability-match routing stops
sending real work to any agent that has ever died or been culled, for the remainder
of that process's lifetime.

**Root cause**: a type mismatch introduced when the class-based reconstruction
logic (`_instantiate_successor`, `agent_class(...)`) was added on top of the
pre-existing dict-returning `spawn_successor()` API (kept, per its own docstring,
"for backwards-compatibility with AgentRegistry"). The async, attribute-based
`spawn_from_ghost()` (`evolution_engine.py:153-231`) does NOT have this bug — it is
never called from `agent_registry.py` though; only the legacy dict-returning
`spawn_successor()` is.

**Not a new finding invented for this report** — it is fully explained by, and
directly contradicts, the very docstring at `agent_registry.py:83-88` ("Ghost
saved, successor spawned as the SAME class as the agent that died ... a successor
must do REAL WORK, not silently come back as a bare AgentBase stub") and the class
docstring's claim "RULE 9 — Agent Darwinism is real." That claim is currently false
for the reconstruction step specifically (ghost/lesson inheritance and district
re-staffing both remain real; class/capability fidelity does not).

### 6. Generation number / starting-HP bonus: real in the dict path, moot in practice
`spawn_successor()`'s `starting_hp = min(500 + gen*50, 800)` never reaches a live
agent today, because `successor.health_points = successor_agent.health_points`
throws before it would be applied — the bare-`AgentBase` fallback always starts a
fresh gen+1 agent at the constructor default of 500 HP
(`agent_registry.py:165-170`, `agent_base.py:42`), same as gen 1. So today, in
practice, **a new generation gets zero starting-HP advantage** despite the intended
design — generation number increments and lessons carry over, but the "improved
successor" HP head-start does not.

### 7. Stale references / dead code
No dangling imports of removed modules found in these four files. One naming
mismatch worth noting for R12-J: `evolution_engine.py` has two independent
successor-spawn code paths (`spawn_successor` dict-based/legacy vs
`spawn_from_ghost` async/class-based) that appear to have diverged — only the
broken one is actually reachable from production. This is a coupling/duplication
smell, not just the P1 bug itself: fixing the bug requires deciding which path is
canonical rather than patching the symptom.

## Real vs Decorative Table

| Mechanism | Status | Evidence |
|---|---|---|
| HP → model tier | REAL | agent_base.py:82-94, unconditional on every award/deduct |
| HP → dispatch tiebreak among multi-agent districts | REAL (conditionally impactful) | governor.py:2294/2301/2315/2184 |
| HP → council eligibility gate (700) | REAL, wired | agent_registry.get_council_eligible(), consumed by governor.py |
| Death detection (HP=0 → die()) | REAL | agent_base.py:213-214 |
| Ghost persistence (SQLite `agent_history`) | REAL | agent_registry.py:178-234, _persist_ghost() |
| Lesson/decision/trait inheritance onto successor | REAL, but only reaches a bare AgentBase today | inherit_ghost() + get_system_prompt() |
| **Successor is the SAME class as predecessor** | **BROKEN — currently always fails, silently downgrades** | confirmed by live test run, §5 |
| Successor capability list preserved | REAL (survives even the broken path) | agent_registry.py:171 |
| Successor starting-HP bonus by generation | DEAD in practice (throws before applied) | §6 |
| cull_bottom() (bottom-HP pruning, reflect tick) | REAL, wired, but inherits the same successor bug | autonomous_loop.py:1926, evolution_engine.py:298-319 |
| EvolutionEngine.check_and_evolve()/spawn_from_ghost() (async, correct-typed path) | Implemented, NOT reachable from the real death path | evolution_engine.py:153-231; agent_registry.py never calls it |

## Current Capability Level
- HP bookkeeping and its immediate consequences (model tier, dispatch tiebreak,
  council gate): **L2-L3** (real influence on real decisions).
- "Darwinian evolution" (successor genuinely inherits both behavior AND lessons):
  **L0-L1 in current production reality** — the behavioral half (class/capability
  fidelity) is broken; only the memory half (lessons/traits) survives.

## What's Broken vs Working
**Working**: HP tracking, HP-gated model/dispatch/council effects, death detection,
ghost persistence, lesson/trait inheritance data, cull_bottom scheduling.
**Broken**: successor class reconstruction (`agent_registry.py:126-138` × the dict
return type of `evolution_engine.spawn_successor()`) — currently 100% failure rate
for any class beyond bare `AgentBase`, confirmed by a live pre-existing test run,
not conjecture.

## Recommended Next Milestone
This is a **genuine, currently-live defect**, not a "build more" suggestion: fix the
type mismatch between `agent_registry.deregister()`'s attribute access and
`evolution_engine.spawn_successor()`'s dict return (either make `spawn_successor()`
return an object with attributes, or change `agent_registry.py` to use `[...]`
subscript access, or switch `agent_registry.py` to call the already-correct
`spawn_from_ghost()` instead of the legacy dict API — a deliberate architectural
choice for the orchestrator/mutation-owner, not this audit, to make). The one
regression test that already exists
(`test_dying_coding_swarm_respawns_as_coding_swarm_with_capabilities`) is sufficient
to verify the fix — it currently fails and should be the acceptance gate.

## Open Questions
- How often, in real production dispatch traffic, does a district actually have
  ≥2 agents sharing one capability (making HP-based selection non-trivial rather
  than a 1-element no-op)? Not measured here.
- Whether `spawn_from_ghost()` (the correct-typed async path) was ever the intended
  production path and `agent_registry.deregister()` simply never got updated to call
  it, vs. the two paths being independently maintained by design — needs an
  orchestrator/history judgment call, not visible from source alone.
- Whether this bug has been live since the 2026-08-05 fix's commit (i.e., the fix
  was never actually verified against CI) or was introduced by a later change —
  worth checking git blame/history if a full defect timeline is needed.
