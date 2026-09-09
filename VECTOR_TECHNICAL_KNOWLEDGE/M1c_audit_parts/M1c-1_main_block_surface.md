# M1c-1 — Self-Test / `__main__` Persistent-Store Surface Audit

Read-only, static analysis only. No file was executed, imported for execution, or run as a
subprocess during this audit. All findings are from direct source reading (Grep/Read) only.

## Scope note (disclosed, not hidden)

The repo has ~1,712 files matching `if __name__ == "__main__":` (a project-wide mandatory
convention per `.claude/rules/code_style.md`: "Every file ends with `if __name__ == '__main__':`
block (real test, no mocks)"). Exhaustively reading every one was not attempted in this pass — that
volume is beyond what a single audit turn can respons­ibly verify. This audit prioritized:

1. Every module that is itself the **definition** of a persistent-store/service class analogous to
   `goal_system.py` (i.e., its own self-test constructs *that very class*, for real) — this is the
   highest-risk category, since it is exactly the shape of both the R11 and M1b incidents.
2. `core/city/governor.py` and `core/loop/decision_engine.py` (orchestration-layer modules whose
   self-tests exercise real cross-subsystem behavior).
3. One district-agent sample (`districts/coding/git_bot.py`) to gauge whether the ~150 district
   agent files (not individually audited here) share the same risk shape.

**Not covered in this pass, and NOT to be assumed safe:** the other ~149 district agent files, most
of `core/api/routers/*`, `core/voice/*`, `core/inference/*`, `core/sensing/*`, `core/video/*`. See
section "Residual scope" at the end.

## Summary table

| File | Constructs persistent store | Isolation mechanism | Guard type | Mutating calls | Other side effects | Classification |
|---|---|---|---|---|---|---|
| `core/brain/goal_system.py` | `GoalSystem()` | Temp `VECTOR_DB_PATH` (as of the uncommitted M1b fix) | Unconditional + hard assert | Yes (`update_goal_progress`, `add_goal`) | none | **VERIFIED-ISOLATED** (after M1b fix; **NOT-ISOLATED before it** — this is the file that caused both real incidents) |
| `core/memory/policy.py` | `PolicyMemory()` | **none** | — | Yes (`update_from_outcome` x3, `record_suppression`) | none | **NOT-ISOLATED** |
| `core/memory/episodic.py` | `EpisodicMemory()` | **none** | — | Yes (`mem.store()` x2 incl. a fabricated "Checked KIIT attendance" episodic row, `mem.remember('owner_name', 'Arghyadeep', ...)` — overwrites the real identity fact with a hardcoded value) | none | **NOT-ISOLATED** — highest severity of the DB-pollution class: this is the foundational module every other store depends on, and its own self-test corrupts a real semantic-memory fact and fabricates a fake episodic event |
| `core/city/agent_registry.py` | `AgentRegistry()` (lazily constructs real `EpisodicMemory()` inside `_get_memory()` on first `deregister()`) | **none** | — | Yes (`register`, `deregister` → real ghost-memory write per file's own docstring) | none | **NOT-ISOLATED** |
| `core/city/evolution_engine.py` | `EpisodicMemory()` directly, plus `AgentRegistry()` | **none** | — | Yes (agent lifecycle + ghost write) | none | **NOT-ISOLATED** |
| `core/loop/autonomous_loop.py` | `AutonomousLoop()` → constructs the ENTIRE stack (GoalSystem, DecisionEngine, PolicyMemory, PermissionGateway, Governor, EpisodicMemory, etc.) | **none** | — | `loop.run_forever()` for 2 real seconds — real observe/think/act/reflect ticks | **HIGHEST SEVERITY FINDING**: a real GREEN-tier candidate could genuinely execute (real district dispatch, real LLM calls, real cost/quota use) within those 2 seconds; RED/YELLOW would at least hit `PermissionGateway`, but nothing stops a GREEN action from completing unattended | **NOT-ISOLATED** |
| `core/city/governor.py` | `get_registry()` (real `AgentRegistry`), `Governor()` | **none** | — | `asyncio.run(gov.dispatch({"type": "code_review", "file": "core/main.py"}))` — a REAL dispatch call | Governor.dispatch() has **no built-in PermissionGateway check** (confirmed architecturally: permission gating happens in `autonomous_loop.py::_act_on()` BEFORE calling `governor.dispatch()` — calling `dispatch()` directly, as this self-test does, bypasses the gate by construction, not by failure). Real `code_review` dispatch likely triggers a real LLM call. | **NOT-ISOLATED**, plus a distinct **permission-bypass-by-construction** finding worth its own flag |
| `core/loop/decision_engine.py` | `DecisionEngine()` (lazy real `_get_policy`/`_get_goals`/`_get_memory`/`_get_epistemic`) | **none** | — | `evaluate()` on 4 hand-built candidates — per R12-G's confirmed finding, `evaluate()` writes one real `EpisodicMemory.store()` row per candidate (4 real rows) | none beyond that | **NOT-ISOLATED**, lower severity (read-mostly, bounded write count) |
| `core/memory/counterfactual.py` | `CounterfactualMemory(db_path)` | Explicit `db_path=` constructor param, real temp file | Explicit, unconditional | Yes, but against the temp file only | none | **VERIFIED-ISOLATED** |
| `core/brain/epistemic_tracker.py` | `EpistemicTracker(db_path=db)` | Explicit `db_path=` constructor param, real temp file, cleaned up after | Explicit, unconditional | Yes, but against the temp file only | none | **VERIFIED-ISOLATED** |
| `core/runtime/plans.py` | `PlanStore(path=tmppath)` | Explicit `path=` constructor param (JSON file, not SQLite), real temp file, cleaned up after | Explicit, unconditional | Yes, but against the temp file only | none | **VERIFIED-ISOLATED** |
| `districts/coding/git_bot.py` (sample) | none (no DB) | n/a | n/a | No mutating calls | `subprocess` git commands (`get_status`, `get_recent_commits`) run for real against **this actual repository** — but both are read-only git operations (no commit/push found) | **NOT-APPLICABLE for persistence; LOW-RISK for subprocess** (read-only) |

## Detail: the absence-guard anti-pattern (the exact M1b mechanism)

Only **one** occurrence of the specific `if X not in os.environ` / `if not X` absence-guard
anti-pattern that caused the M1b incident was found in this pass: the **pre-fix** version of
`core/brain/goal_system.py`'s `__main__` block (already corrected in the uncommitted working tree,
per the M1b milestone). No other file audited in this pass used an absence-guard for
`VECTOR_DB_PATH` or an equivalent env var inside a `__main__` block — the other core files audited
either use **no isolation at all** (`policy.py`, `episodic.py`, `agent_registry.py`,
`evolution_engine.py`, `autonomous_loop.py`, `governor.py`, `decision_engine.py`) or use the
**correct** explicit-constructor-parameter pattern (`counterfactual.py`, `epistemic_tracker.py`,
`plans.py`). This means the *specific* dotenv-precedence bug is not (as far as this pass found)
duplicated elsewhere — but a **different, arguably worse** pattern is widespread: simply not
attempting isolation at all, relying entirely on nobody running these files directly outside of a
controlled context.

## Ranked by likelihood of accidental direct execution during normal development

1. `core/loop/autonomous_loop.py` — **CRITICAL**. A developer debugging the main loop is the single
   most plausible person to run `python core/loop/autonomous_loop.py` directly. Highest consequence
   (real 2-second production run of the entire cognitive stack).
2. `core/city/governor.py` — **HIGH**. Real dispatch bypassing the permission gate by construction,
   likely real LLM cost.
3. `core/memory/episodic.py` — **HIGH**. Foundational module, real identity-fact overwrite +
   fabricated episodic row every run.
4. `core/memory/policy.py` — **MEDIUM**. Bounded blast radius (unique-keyed rows) but still real
   production DB writes with zero isolation.
5. `core/city/agent_registry.py` / `evolution_engine.py` — **MEDIUM**. Real ghost-memory writes,
   also triggers the R12-E-confirmed successor-spawn crash every run.
6. `core/loop/decision_engine.py` — **LOW-MEDIUM**. Bounded (4 rows), mostly read-only against real
   policy/goal state.

## Residual scope (not audited in this pass)

- ~149 other `districts/*.py` agent files — only 1 sampled. The sample was low-risk (read-only git
  subprocess calls), but this is a single data point, not a proof the class is safe.
- `core/api/routers/*`, `core/voice/*`, `core/inference/*`, `core/sensing/*`, `core/video/*`,
  `core/security/*`, `core/engine/*` — not audited.
- Whether `core/memory/reasoning_memory.py`, `core/memory/causal_graph.py`,
  `core/brain/person_model.py`, `core/city/meta_cognition.py`, `core/city/agent_base.py` follow the
  same NOT-ISOLATED pattern was not checked in this pass (time-boxed) — these are exactly the shape
  of module most likely to share the risk (each defines a persistent-store class analogous to
  `goal_system.py`) and should be the FIRST thing checked in any follow-up pass, before assuming
  they are fine.
