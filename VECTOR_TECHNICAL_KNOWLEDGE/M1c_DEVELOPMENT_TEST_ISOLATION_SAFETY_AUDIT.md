# M1c — Development / Test Isolation Safety Audit

Read-only audit. No production code, goal data, or database was modified as part of this milestone.
No self-test, module, or subprocess was executed against the real environment. Four parallel
read-only sub-audits (static analysis only) plus direct orchestrator work (incident recurrence
analysis, and a read-only provenance check for the five `progress=0.076` goals). Full sub-reports:
`VECTOR_TECHNICAL_KNOWLEDGE/M1c_audit_parts/M1c-{1,2,3,4}_*.md`.

**Starting HEAD verified before this audit:** `b156a4792` (branch `production-hardening-complete`,
single worktree, no staleness). Two files remain uncommitted from M1b at the time of this audit —
`core/brain/goal_system.py` (the M1b fix itself) and `COGNITIVE_EVOLUTION_ORCHESTRATOR.md` — neither
was touched further during this audit.

---

## A. Executive verdict

**YELLOW.**

Not RED: the specific mechanism that caused both real incidents (R11 and M1b) is now understood
precisely and is confirmed **isolated to the one file already fixed** — no other file in the repo
uses the dangerous absence-guarded (`if "VECTOR_DB_PATH" not in os.environ`) override pattern.

Not GREEN: this audit found the *same underlying class of hazard* — a development-time self-test or
verification command touching real, consequential state with no isolation at all, not even a broken
one — in **multiple other files**, none of which had been identified before this audit. Several are
more severe than the goal-store issue (real writes into `reasoning_chains`, one of the five
never-touch memory tables; a real `AutonomousLoop.run_forever()` invocation that could execute a
real GREEN action; an ungated MCP tool server). The isolation boundary is real in places and
provably absent in others — it has never been applied consistently, and no single mechanism or
fixture enforces it repo-wide.

**Determination (section K) follows from this: do not resume R17 yet — not because R17's own target
file is unsafe (it is already correctly isolated), but because this audit's own P0 findings
constitute unresolved risk in the surrounding development environment that a reasonable safety
posture should close first, per the owner's own explicit standard for this milestone.**

---

## B. Incident recurrence risk

**R11 incident** (disclosed in `R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md`): running
`python core/brain/goal_system.py` directly, with no awareness that its `__main__` self-test calls
`update_goal_progress()` and `add_goal()` for real, mutated the real production goal store. No
isolation attempt existed at all at that time.

**M1b incident** (this session, disclosed in `COGNITIVE_EVOLUTION_ORCHESTRATOR.md`): a *first* fix
attempt added an isolation guard, but the guard was conditional
(`if "VECTOR_DB_PATH" not in os.environ:`) and the condition was always false in practice, because
`core.config`'s dotenv load (triggered by an earlier import in the same file) had already set that
env var from `.env`'s real value. The guard looked correct, was even run once and appeared to work
("✅ goal_system OK"), but silently deferred to the real store. Caught only because the orchestrator
independently re-read production state afterward rather than trusting the self-test's own success
output.

**Common root cause:** in both cases, a person (or agent) reasonably believed a specific piece of
code was "just a test" or "already fixed," and that belief was not independently verified against
the actual resolved state before the code was run for real. In M1b specifically, the deeper
mechanism was: **an isolation guard's own correctness depended on import-order/environment-timing
knowledge that was not verified before the guard was trusted.**

**What mitigation exists now:** `core/brain/goal_system.py`'s `__main__` block now overrides
`VECTOR_DB_PATH` **unconditionally** (no guard) and asserts `configured_db_path()` resolves to the
override before constructing `GoalSystem()` — refusing to proceed rather than silently falling
through. This closes the *exact* mechanism for *this one file*.

**What remains vulnerable (this is the core deliverable of this audit):** the same underlying
pattern — a `__main__` self-test or verification command touching real state, with no isolation, or
an isolation mechanism whose correctness was never independently verified — exists in multiple other
files never previously audited. See sections C–H. **The M1b-specific dotenv-precedence bug is
confirmed NOT repeated elsewhere (M1c-2)** — but "no isolation attempt at all" (the R11-style
hazard) is confirmed present in several other files, which is arguably a **more directly dangerous**
state than a broken guard, since there is no mechanism at all to reason about, verify, or trust.

**Is current mitigation sufficient?** No — it is sufficient only for the one file it was applied to.
It establishes a correct *pattern* (unconditional override + hard assert) that should be replicated,
but nothing enforces that replication repo-wide.

---

## C. Complete self-test / `__main__` inventory (M1c-1)

Full detail: `M1c_audit_parts/M1c-1_main_block_surface.md`. The repo has ~1712 files with a
`if __name__ == "__main__":` block (a mandated project convention — not itself a defect). This
sub-audit prioritized the ~11 files most likely to construct a persistent store or application
service, rather than attempting exhaustive coverage of all 1712 (explicitly disclosed as a scope
limit, not claimed as complete).

| File | Constructs persistent store | Isolation | Guard type | Mutating calls | Other side effects | Classification |
|---|---|---|---|---|---|---|
| `core/brain/goal_system.py` | Yes (GoalSystem) | Yes | **Unconditional + hard assert (fixed in M1b)** | Yes | — | VERIFIED-ISOLATED |
| `core/memory/policy.py` | Yes (PolicyMemory) | None found | none | Yes | — | **NOT-ISOLATED** |
| `core/memory/episodic.py` | Yes (EpisodicMemory) | None found | none | Yes (`remember`, inserts) | writes into `reasoning_chains` | **NOT-ISOLATED** |
| `core/city/agent_registry.py` | Yes | None found | none | Yes | — | **NOT-ISOLATED** |
| `core/city/evolution_engine.py` | Yes | None found | none | Yes | — | **NOT-ISOLATED** |
| `core/loop/autonomous_loop.py` | Yes (full stack) | None found | none | Yes | **real `run_forever()` for 2s — a real GREEN action could execute** | **NOT-ISOLATED, HIGHEST RISK** |
| `core/city/governor.py` | Indirect (dispatches real tasks) | None found | none | Yes (`dispatch()`) | **bypasses PermissionGateway by construction** (gate lives in `autonomous_loop._act_on()`, not `Governor`) | **NOT-ISOLATED** |
| `core/loop/decision_engine.py` | Indirect (reads/writes policy via real engine) | None found | none | Yes | — | **NOT-ISOLATED** |
| `core/memory/counterfactual.py` | Yes | Yes | explicit `db_path=` kwarg | — | — | VERIFIED-ISOLATED |
| `core/brain/epistemic_tracker.py` | Yes | Yes | explicit `db_path=` kwarg | — | — | VERIFIED-ISOLATED |
| `core/runtime/plans.py` | Yes (PlanStore) | Yes | explicit temp-path pattern | — | — | VERIFIED-ISOLATED (**directly relevant to R17 — already safe**) |

**Only 1 file uses the exact M1b absence-guard anti-pattern — the already-fixed `goal_system.py`.**
7 of 11 audited files are NOT-ISOLATED outright (never attempted isolation at all).

**Explicit residual scope, not claimed complete:** ~5 more core modules and ~149 district agent
files were not individually checked in this pass. This audit deliberately prioritized breadth
across core persistence over exhaustive per-district coverage; district agents are a plausible
location for the same pattern and were not ruled out.

---

## D. Environment / dotenv isolation map (M1c-2)

Full detail: `M1c_audit_parts/M1c-2_env_dotenv_map.md`.

- `core/__init__.py:33-38` calls `load_dotenv()` (default `override=False`) on **any** `import core`
  or `import core.<anything>`. `.env:11` sets `VECTOR_DB_PATH=vector_memory.db` — the real
  production path. This is the exact mechanism that made M1b's conditional guard useless.
- `configured_db_path()` (`core/memory/db_utils.py`) reads the env var **fresh at every call**, not
  cached — meaning an **unconditional** override always works regardless of when it's set, but a
  **conditional** ("if not already set") guard never can, because dotenv has always already set it
  by the time any file-level code runs.
- **Confirmed: no other file in the repo uses the absence-guarded write pattern.** Every other
  `VECTOR_DB_PATH` writer (`test_e1_persistent_learning.py`, `test_r10_decision_provenance.py`,
  `test_r11_learning_integration.py`, `test_task89c_goal_progress.py`,
  `core/benchmark/isolation.py`) writes unconditionally.
- **New finding — `VECTOR_DB_KEY` caching (not previously documented):** `_get_db_key()`
  (`core/memory/episodic.py:93-133`) resolves and caches the encryption key **process-wide, once,
  permanently** — unlike the path resolver. If a test that expects an isolated key runs in a process
  where an earlier test already opened a connection with a different key, the isolation for the KEY
  (not the path) silently fails to apply. Every affected test file is self-documented as "must run
  standalone" — as long as that convention holds, this doesn't manifest. If violated, the realistic
  failure mode is a loud key-mismatch crash, not a silent write to the real DB — bounded severity,
  but undocumented until now.
- 4 writer sites were flagged by the sub-audit as "not individually re-verified line-by-line" —
  listed in the sub-report for a future pass, not confirmed unsafe.

---

## E. Persistent-state construction map (M1c-3)

Full detail: `M1c_audit_parts/M1c-3_constructors_and_fixtures.md`.

| Class | Zero-arg default | Isolation mechanism | Reads `VECTOR_DB_PATH`? |
|---|---|---|---|
| `GoalSystem()` | **Real production DB** | env-var only | Yes |
| `PolicyMemory()` | **Real production DB** (per-method reads) | env-var only | Yes |
| `EpisodicMemory()` | **Real production DB**, process-wide singleton connection | env-var only, cached on first call | Yes |
| `EpistemicTracker()` | **Real `data/epistemic.db`** | **explicit `db_path=` kwarg — does NOT read `VECTOR_DB_PATH` at all** | **No** |
| `CounterfactualMemory()` | **Real `data/counterfactual.db`** | **explicit `db_path=` kwarg — does NOT read `VECTOR_DB_PATH` at all** | **No** |
| `get_plan_store()` | **Real production plan store** | none — unoverridable module-level singleton | No override path found |

**This is the single most consequential new finding of this audit.** This entire session's
established isolation convention — set `VECTOR_DB_PATH` before any `core.*` import — has **never
isolated `EpistemicTracker` or `CounterfactualMemory`**, because those two classes use a completely
different mechanism that the env var doesn't reach. Any test or script that constructs either of
those for real (not mocked, no explicit `db_path=` passed) while relying only on `VECTOR_DB_PATH`
isolation would silently read/write the real `data/epistemic.db` / `data/counterfactual.db`, with
no error and no indication.

**Cross-check against this session's own R11 test suite:** `test_r11_learning_integration.py`'s
`DecisionEngine` fixture explicitly mocks `_get_epistemic` (`MagicMock()`, `get_belief.return_value
= None`) — so that specific file is NOT exposed to this gap; epistemic was never constructed for
real there. This audit did not re-verify every other R6–R11 test file for the same mocking
discipline — flagged as an open question, not resolved.

**Fixture inventory:** no global/session-scoped fixture isolates all tests automatically; isolation
remains entirely per-file discipline, as R12-H already found for the 3 files fixed in M1. Beyond
those 3, this audit found **10 more test files** constructing `GoalSystem()`/`PolicyMemory()`/
`EpisodicMemory()` for real with no `VECTOR_DB_PATH` and no mocking:
- **2 inspected in depth: a deliberate, pre-existing "uuid-unique keys, no isolation" design** —
  real writes to the real `policy_memory` table, made collision-safe by unique keys rather than by
  isolation, permanent test-noise growth by design. One of these two also runs a real schema
  `ALTER TABLE` against the live production connection **on purpose**. This is a known, intentional
  pattern from an earlier task, not a newly discovered accident — but it is a different isolation
  philosophy than everywhere else in the codebase, and worth the owner knowing it exists.
- **The other 8 are UNKNOWN** — not individually verified safe or unsafe in this pass.

---

## F. Test-fixture isolation assessment

Covered above (E) — no separate global fixture exists. `pytest.ini`'s `testpaths` excludes
`VECTOR_TECHNICAL_KNOWLEDGE/learning_lab` (must be run via explicit path), which itself has a
session-scoped `conftest.py` that auto-cleans `vector_twin_*` temp dirs but does not, by itself,
prevent a test file from choosing not to isolate.

---

## G. Development verification hazard inventory (M1c-4, Part 1)

Full detail: `M1c_audit_parts/M1c-4_dev_verification_and_side_effects.md`.

- Multiple prior session reports document agents using `python core/<module>.py` as a "quick sanity
  check" pattern — exactly the habit that produced both real incidents. No single file catalogs
  which of these are safe; safety was assessed ad hoc, per-file, each time.
- **`89D_POLICY_REWARD_IDENTITY.md`** documents a **third, structurally separate hazard class**:
  running a module as a bare relative-path script can, on this machine, silently resolve `import
  core.*` against a *different installed copy* of the codebase than the current worktree —
  producing misleading verification results **independent of database safety entirely**. This means
  even a correctly-isolated self-test's reported success is not proof it exercised the code you
  think it did, unless the import resolution itself is also verified.

---

## H. Consequential side-effect surface (M1c-4, Part 2)

- **`core/mcp_server.py`**: a prior dedicated red-team task (Task 60) already found this exposes
  14+ tools — including `db_quarantine` and browser/email actions — with **no PermissionGateway
  enforcement and a fail-open security wrapper**. Not reachable from the autonomous loop, but
  running `python core/mcp_server.py` directly (a natural "does this file still work" check) would
  serve real, ungated, potentially destructive capabilities to whatever client connects. This was
  previously accepted as "out of scope for the autonomous-experiment gate" — but is squarely
  in-scope for this audit's question ("can development/verification reach a consequential side
  effect"), and was never remediated.
- **`core/loop/autonomous_loop.py`**'s self-test (already listed in C) is the highest-risk finding
  in this entire audit: 2 real seconds of a genuinely running cognitive loop, unisolated, capable of
  real district dispatch and real LLM calls if a GREEN candidate happened to win.
- **`core/memory/episodic.py`**'s self-test writes fabricated content directly into
  `reasoning_chains` — one of the five memory tables `.claude/rules/memory.md` explicitly documents
  as becoming **real LLM training data**, and marks "never touch" alongside the other 4 sacred
  tables. This is a rule-level violation of the project's own documented memory discipline, not
  merely a data-hygiene nuisance.
- No subprocess/network/device-control/financial/communications-sending hazard was found reachable
  from a `__main__` or test-file path in the portion of the surface actually checked (scope caveat
  from C applies here too — not exhaustively checked across all districts).

---

## I. The five `progress=0.076` goals

**READ-ONLY. No mutation performed. Provenance established for 4 of 5; not re-investigated further
per instruction.**

`VECTOR_TECHNICAL_KNOWLEDGE/61_EXPERIMENT_BASELINE.md:78-86` shows an identical documented snapshot
from the stopped 7-day autonomous experiment:

```
MID    First ₹1 of product revenue... progress=0.076
MID    Complete Karpathy playlist...  progress=0.076
LONG   Equation portfolio...          progress=0.076
LONG   KIIT placement preparation...  progress=0.076
```

This matches `g_first_revenue`, `g_karpathy_30`, `g_equation_portfolio`, `g_placement_prep` exactly.
**Classification: KNOWN — provenance established, pre-existing documented experiment data, not
caused by this session.**

**One discrepancy flagged, not resolved:** that same baseline document shows `g_kiit_attendance` at
`progress=0.0`, while the current real store (as last observed, read-only, during M1b's damage
verification) shows it at `0.076` too — a fifth goal matching the same numeric pattern but not
matching this specific baseline snapshot. **Classification: UNKNOWN** — could be a later experiment
checkpoint not yet found, could be something else. Not investigated further; no mutation performed;
flagged for the owner.

---

## J. Required remediation, ranked

**P0 — must fix before any further autonomous mutation of production-adjacent code:**
1. `core/loop/autonomous_loop.py`'s self-test — real, unisolated `run_forever()` capable of a real
   GREEN action executing. Highest-risk finding in this audit.
2. `core/memory/episodic.py`'s self-test — real writes into `reasoning_chains` (a documented
   never-touch table) and overwrites the real `owner_name` fact, with literally no isolation
   attempt (not even a broken one).
3. `EpistemicTracker`/`CounterfactualMemory`'s isolation gap — `VECTOR_DB_PATH` does not reach
   them at all. At minimum, every test file relying on `VECTOR_DB_PATH` isolation needs to be
   confirmed to also mock or explicitly `db_path=`-isolate these two stores wherever they might be
   constructed for real (R11's own test does mock `_get_epistemic` — other files not yet verified).
4. `core/mcp_server.py`'s ungated tool exposure on direct execution (pre-existing Task 60 finding,
   never remediated) — a developer running this file directly serves real, ungated, potentially
   destructive tools.

**P1 — should fix:**
5. `core/memory/policy.py`, `core/city/agent_registry.py`, `core/city/evolution_engine.py`,
   `core/loop/decision_engine.py` self-tests — NOT-ISOLATED, same class of hazard as the above,
   lower individually-assessed severity but unverified blast radius.
6. `core/city/governor.py`'s self-test bypassing PermissionGateway by construction — not itself a
   bug (the gate correctly lives elsewhere), but a documentation gap that invites someone to test
   Governor "in isolation" and wrongly conclude the gate was exercised.
7. The 8 UNKNOWN test files found beyond the 3 already fixed in M1 (section E) — need individual
   verification, not assumed safe or unsafe.
8. `VECTOR_DB_KEY` process-wide caching (section D) — document the "must run standalone" convention
   more visibly, or consider a per-process reset hook for isolated test runs.

**P2 — later hardening:**
9. A repo-wide enforced isolation mechanism (e.g. a `conftest.py`-level guard, or a lint/CI check
   that flags any `__main__` block constructing a known persistent-store class without an adjacent
   isolation call) — would prevent this entire class of incident structurally rather than
   file-by-file. Explicitly a P2, not P0/P1: this is new architecture, and per this milestone's own
   scope ("not to redesign VECTOR"), building it is a decision for the owner, not something to do
   automatically here.
10. The `89D_POLICY_REWARD_IDENTITY.md`-documented import-resolution hazard (running a script by
    relative path can resolve `core.*` against a different installed copy) — worth a documented
    "always verify sys.path[0]/`core.__file__`" convention for any future direct-execution
    verification.
11. The `g_kiit_attendance` 0.076-vs-0.0 discrepancy (section I) — worth the owner's own review,
    not an automated fix.

---

## K. Explicit determination

**Do not resume R17 mutation yet. Remediation required first — specifically the P0 items in
section J.**

Reasoning: R17's own target file (`core/runtime/plans.py`) is independently confirmed
VERIFIED-ISOLATED already (section C) — R17 itself is not the source of risk. But this audit was
explicitly commissioned because two real incidents proved the development environment's isolation
discipline could not be assumed trustworthy, and this audit's own findings confirm that distrust
was warranted: multiple other files carry the same or worse hazard, undiscovered until now. Resuming
autonomous mutation work while P0 items remain open would mean the *next* verification step in R17
(or any milestone) could just as easily trip one of these newly-found hazards (most plausibly: a
future verification step that touches `EpistemicTracker`/`CounterfactualMemory` without realizing
`VECTOR_DB_PATH` doesn't isolate them, or a habitual `python core/<module>.py` check landing on one
of the 7 NOT-ISOLATED files found in section C).

This is a recommendation, not a self-executed decision — per this milestone's explicit instruction,
no remediation has been performed, and none will be until the owner reviews these findings and
decides how to proceed.
