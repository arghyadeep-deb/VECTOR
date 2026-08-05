# VECTOR Core Intelligence + Orchestration Audit — 2026-08-05

Scope: `core/loop/autonomous_loop.py`, `core/loop/decision_engine.py`,
`core/loop/context_engine.py`, `core/loop/permission_gateway.py`,
`core/brain/goal_system.py`, `core/memory/policy.py`, `core/city/governor.py`,
`core/city/agent_base.py`, `core/city/agent_registry.py`,
`core/city/evolution_engine.py`.

Method: full read of all nine files, cross-referenced against
`.claude/rules/architecture.md`'s ordering rules (hydration-before-LLM,
policy-before/outcome-after, LLM-zero-direct-access), plus one live,
read-only runtime probe (isolated data directory, `VECTOR_TEST_DATA_DIR`
pointed at a scratch folder — the live process on port 8000 and its
encrypted DB were never touched). VECTOR was not restarted or interrupted.

**Overall verdict up front:** this layer is unusually well-audited already —
nearly every file carries dated, specific comments describing a prior
live-caught bug and its fix (KNOWN_ISSUES #1/#16/#22/#25/#27/#35, the
2026-08-04 HP-restore fix, the 2026-08-05 HP-saturation fix, etc.), several
with dedicated regression tests. Most of the failure shapes this audit was
asked to hunt for (silent `except: pass`, hydration-ordering violations,
policy get/update ordering, registry drift) have already been found and
fixed by earlier passes. One severe, previously-undocumented bug was found
in the death→ghost→successor path, confirmed live via probe. Below that,
the layer is genuinely close to production-grade for a single-owner system.

---

## CONFIRMED — Critical

### 1. Agent death/cull permanently downgrades the successor to a capability-less `AgentBase` stub

**Files:** `core/city/agent_registry.py:63-93` (`deregister()`),
`core/city/evolution_engine.py:91-143` (`spawn_successor()`, the dict-based
API `deregister()` actually calls), `core/city/agent_base.py:237-256`
(`die()` → `deregister()`).

**What is wrong:** When a district agent (a real subclass such as
`districts.coding.agent.CodingSwarm`, instantiated at boot by
`ManifestLoader.instantiate_all()` with a real `capabilities` list and a
real overridden `run()`) reaches 0 HP, `AgentBase.die()` calls
`AgentRegistry.deregister(self.id)`. That method does:

```python
blueprint = EvolutionEngine().spawn_successor(ghost_data)   # dict-only, legacy API
successor = AgentBase(str(_uuid.uuid4()), blueprint["name"], agent.district,
                       generation=blueprint["generation"])
successor.health_points = blueprint["starting_hp"]
successor.inherit_ghost(ghost_data)
self.register(successor)
```

and the exception-fallback branch a few lines below does the same with a
bare `AgentBase(...)` call. Neither path re-instantiates the original
subclass. `EvolutionEngine`'s only mechanism for preserving the real class
is `register_constructor()` / `self._agent_constructors` (used by the
separate async `spawn_from_ghost()` API) — but `register_constructor()` is
**never called anywhere in production** (`grep` confirms it only appears in
`evolution_engine.py` itself and three test files), and the real death path
(`AgentRegistry.deregister()`) doesn't call `spawn_from_ghost()` at all — it
calls the legacy dict-only `spawn_successor()`, then hand-builds a bare
`AgentBase`.

**Concrete failure:** the successor keeps the same `name`/`district` and
inherits the ghost's *lessons* (text), but:
- `capabilities` resets to `[]` (`AgentBase.__init__` default) — it can
  never again win `Governor.dispatch()`'s capability-match selection.
- `run()` resets to `AgentBase.run()`, the generic stub:
  `return {"status": "ok", "agent": self.name, "task": task}` — it does
  **no real work** for any task ever dispatched to it, but reports
  `status: "ok"`.

Because `bootstrap_agents()` (which is what actually re-instantiates real
subclasses from `config/agent_manifest.yaml`) runs exactly once, at process
start (`run_vector.py: run_loop()`), this degradation is **permanent for
the remaining uptime of the process** — there is no periodic re-bootstrap
or healing. Given RULE 2 ("the loop never stops") and that `deduct_points`
on task failure/exception is a normal, frequent occurrence (`-30 HP` per
`task_failed_by_governor` / `exception_during_task` in
`governor.dispatch()`), plus the nightly 2AM `cull_bottom()` pass
(`autonomous_loop.py::_reflect_tick`, `evolution_engine.py::cull_bottom()`)
which explicitly `deregister()`s the lowest-HP agents in every district with
>5 agents — every death silently converts a functioning specialist into a
confidently-lying no-op for the rest of the process's life. For a
single-agent district (several exist — e.g. `coding` is fronted by one
`CodingSwarm`), this means the entire district goes fully non-functional
after one death while continuing to report healthy/rising HP
(`elite`/`strong` status) and `"status": "ok"` on every dispatch.

This is exactly the "wrong result returned confidently instead of an honest
failure" failure mode the audit brief called out, and it directly
contradicts the project's own stated Critical Rule #4 ("HP system must be
wired to real task outcomes — fake HP = fake evolution"): after one death,
HP keeps moving but is no longer connected to any real capability at all.

**How verified:** live, read-only runtime probe (script left at
`C:\Users\ARGHYA~1\...\scratchpad\probe_successor_class.py`, isolated to a
scratch `VECTOR_TEST_DATA_DIR` — did not touch the live encrypted DB). The
probe:
1. Ran the real `ManifestLoader().load()` + `instantiate_all()` (170
   manifest entries, 102 instantiated — the rest skipped only because the
   probe's fake DB key couldn't open a fresh encrypted DB in the scratch
   dir, an artifact of isolation, not the bug).
2. Picked a real specialist, `districts.coding.agent.CodingSwarm`
   (`capabilities=['onboarding', 'code_conductor', 'code-intel',
   'database-optimizer', 'db_optimize', 'frontend_developer', 'gui',
   'minimal-change', 'mlops', 'rapid-prototype', 'rapid_prototype']`).
3. Called the real production path: `specialist.deduct_points(10, ...)` →
   `die()` → `AgentRegistry.deregister()`.
4. Inspected the registered successor.

Result (raw output):
```
Picked specialist: districts.coding.agent.CodingSwarm name='CodingSwarm' ...
  run() method: CodingSwarm.run
...
Successors found: 1
  successor type: core.city.agent_base.AgentBase
  successor capabilities: []
  successor run() qualname: AgentBase.run
  successor HP: 600

=== VERDICT ===
Original class:  districts.coding.agent.CodingSwarm
Successor class: core.city.agent_base.AgentBase
Class preserved: False
run() preserved: False
Capabilities preserved: False
```

**Suggested direction (not implemented — audit is read-only):**
`AgentRegistry.deregister()` should look up `type(agent)` (or resolve the
class via the manifest by district+name) and construct the successor with
that class instead of the hardcoded `AgentBase(...)`, then re-apply
`instance.capabilities = [...]` from the manifest entry — mirroring what
`ManifestLoader.instantiate_all()` already does at boot. Alternatively wire
`EvolutionEngine.register_constructor()` for every manifest agent at boot
time and route `deregister()` through `spawn_from_ghost()` instead of the
dict-only `spawn_successor()`.

---

## CONFIRMED — Low / informational

### 2. `EvolutionEngine.cull_bottom()` does redundant double ghost-persistence

**File:** `core/city/evolution_engine.py:263-308` (`cull_bottom()`),
`core/city/agent_registry.py:95-139` (`_persist_ghost()`).

`cull_bottom()` calls `self._record_death(agent)` (writes one
`agent_history` row via `evolution_engine._persist_agent_history()` →
`get_registry()._persist_ghost(ghost_dict)`), then immediately calls
`self._registry.deregister(agent_id)`, which independently rebuilds its own
ghost dict from the *live* agent object and writes `agent_history` again.
Both writes use `INSERT OR REPLACE` keyed on `agent_id`, so this is
idempotent and not a correctness bug — just duplicate work on every cull.
Not worth separate severity; noted for completeness since it sits directly
next to Finding #1's code path.

---

## Modules that are genuinely healthy (no bugs found)

- **`core/loop/context_engine.py`** — `session_hydration_prompt()` is
  real, builds from `get_world_state()` (17 fields across the documented
  domains: time, presence, screen, goals, memory stats, phone, doctrine,
  knowledge-graph facts, person model, available commands), and is called
  from every real LLM-call site checked (`permission_gateway._handle_red_tier`,
  `governor._answer_conversationally`, `governor._llm_classify`). Failure
  paths degrade to a minimal-but-still-present context block rather than
  silently omitting hydration. No bugs found.

- **`core/memory/policy.py`** — `get_score()` / `update_from_outcome()`
  ordering (RULE 7) is correctly followed at every call site checked
  (`decision_engine._score_candidate`, `autonomous_loop._act_on`,
  `autonomous_loop.act` counterfactual-block path). Online averaging math is
  correct and matches its own `__main__` smoke test. No bugs found.

- **`core/loop/decision_engine.py`** — 5-factor formula matches the spec
  weights exactly (`0.30/0.25/0.20/0.15/0.10 - 0.05*cost`), RULE 1
  (context snapshot) and RULE 8 (reasoning-bank injection) both genuinely
  wired before scoring (not decorative), and the module's own docstring is
  honest about a deliberate design choice (context snapshot doesn't feed
  the score formula itself). `record_outcome()`'s neural-training hookup
  is real, not a discard-and-forget stub (an earlier fix, per its own
  comment, closed exactly that gap and fixed a `save_checkpoint()`
  TypeError). No bugs found.

- **`core/loop/permission_gateway.py`** — GREEN/YELLOW/RED/FORBIDDEN gate
  is correctly enforced; the process-wide singleton fix (`__new__`) is
  real and prevents the "different gateway instance never sees the
  approval" class of bug the file itself documents having found before.
  `RED_INTERACTIVE_TOOLS` / `OWNER_APPROVAL_ONLY` / `sanitize_proposed_by`
  are consistent and closed against the specific spoofing vector called
  out in the code comments. `execute_code`'s sandbox path is honestly
  reported as `not_implemented` (a prior fix specifically replaced a
  misleading "sandbox unavailable" message with an accurate one — verified
  by reading the code: `ContainerRunner` really isn't importable that way).
  No bugs found beyond what the file's own comments already flag as
  handled.

- **`core/brain/goal_system.py`** — horizon logic (LONG/MID/SHORT),
  pre-seeded goals, expiry/pruning, and progress tracking all check out.
  `generate_immediate_actions()` maps every goal to a real gateway-known
  action type via `GOAL_ACTION_MAP`. No bugs found.

- **`core/loop/autonomous_loop.py`** — `observe → think → act → reflect`
  is real: each loop has its own `asyncio.timeout`, catches all exceptions,
  and never lets an exception kill the coroutine (matches RULE 2 and the
  code-style resilience convention). RULE 3 (LLM zero direct access) is
  enforced on every `_act_on()` branch checked (VectorCode routing, skills
  routing, hand routing — all pass through `permission_gateway` or
  `governor.dispatch()` before doing anything). RULE 7 outcome wiring
  (`pm.update_from_outcome`) fires on every action branch, including the
  VectorCode fast-path and the counterfactual auto-block path (the file's
  own comment documents a prior live bug where the auto-block path *didn't*
  update policy, causing an infinite re-propose loop — now fixed). No new
  bugs found in the ~2,700 lines read.

- **`core/city/governor.py`** — `dispatch()` correctly gates on rate
  limiting, taint tracking, prompt injection, and council review before
  touching an agent; RULE 9 HP wiring (`award_points`/`deduct_points`) is
  present on every outcome branch. The capability-match-then-HP-fallback
  design (Task A.3) is a documented, deliberate tradeoff, not a bug — but
  it is the exact mechanism that makes Finding #1 dangerous, since a
  capability-less stub still gets selected as the sole `agents` fallback
  and its `"status": "ok"` is returned unmodified for any call that isn't
  explicitly `_llm_classified` (only the LLM-chat path gets a "might not be
  a close match" caveat; the 100+ structured API routes get nothing).

- **`core/city/agent_base.py`** — HP math (`award_points`'s repeat +
  headroom dampening, `deduct_points`'s clamp, `die()`'s ghost
  construction) is correct and matches its own regression test (the
  2026-08-05 saturation-bug fix). `die()` correctly triggers
  `agent_registry.deregister()` — see Finding #1 for what that does next.

---

## Summary table

| # | Severity | File(s) | Status |
|---|----------|---------|--------|
| 1 | **Critical** | `agent_registry.py`, `evolution_engine.py`, `agent_base.py` | CONFIRMED (live probe) |
| 2 | Low | `evolution_engine.py::cull_bottom` | CONFIRMED (redundant, not incorrect) |

No findings in: `context_engine.py`, `policy.py`, `decision_engine.py`,
`permission_gateway.py`, `goal_system.py`. `autonomous_loop.py` and
`governor.py` are clean except as noted where they interact with Finding #1.

## Verdict

This is **not yet production-grade** for the specific reason of Finding #1:
the Darwinian agent-city premise — the project's own headline architectural
claim — silently stops being real for any agent that dies, which is a
routine, expected event (task failures deduct 30 HP; several districts run
one consolidated "Swarm" agent, so one death can zero out an entire
district's real capability while it keeps reporting healthy status). Once
that is fixed, the rest of this layer — hydration ordering, the 5-factor
decision formula, the permission gate, policy learning, and the
observe/think/act/reflect loop itself — is genuinely solid, well-tested,
and already carries the scar tissue of several real prior audits.
