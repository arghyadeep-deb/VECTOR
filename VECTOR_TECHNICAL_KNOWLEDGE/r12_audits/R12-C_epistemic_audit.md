# R12-C — Epistemic Audit

**HEAD audited:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6`
**Type:** Read-only. No production code or DB touched.

## Objective

Determine whether `EpistemicTracker` beliefs currently exert real influence on production
decisions (RUNTIME_REACHABLE), or remain orphaned as prior audits (`72_LEARNING_ARCHITECTURE_V2.md`,
`51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md`, `85_COGNITIVE_FOUNDATION_REMEDIATION_PLAN.md`) found. A
stale `phase_status.md` note in this session's own context claims `epistemic_tracker` is "ORPHANED
... NOT called from autonomous_loop" as of a 2026-08-13 audit — this claim was independently
re-verified against current source and found **partially false**: it was fixed for one of the two
belief namespaces, not both.

## Method

Direct source read of `core/brain/epistemic_tracker.py`, then repo-wide grep for every call site of
`EpistemicTracker`/`get_belief`/`update_belief`/`_get_epistemic`/`action_domain` outside `tests/` and
`learning_lab/`, then read of each call site in `core/loop/decision_engine.py`,
`core/loop/autonomous_loop.py`, and `core/loop/context_engine.py` to confirm each is on a real,
unconditional execution path (not a mock-only or test-only path).

## Findings

**Two structurally separate belief-writer pathways exist, sharing one SQLite `claims` table
(`core/brain/epistemic_tracker.py:47-57`), distinguished only by key-prefix convention — never by
schema:**

### Pathway 1 — `action_domain:*` (fully closed loop, RUNTIME_REACHABLE)

- **Write (after outcome):** `core/loop/autonomous_loop.py:1349` — inside the real winner-outcome
  handling block, immediately after `PolicyMemory.update_from_outcome()` (`:1343`), using the SAME
  real `reward` computed at `:1330-1336` from `user_feedback`/`goal_progress`/`not_overridden`/
  `not_corrected`/`completed`. Calls `DecisionEngine.record_epistemic_belief(action_type,
  outcome_status, reward)` (`decision_engine.py:438-469`), which writes claim_id
  `f"action_domain:{action_type.split('_')[0]}"` via `epistemic.merge_belief()`. A second call site
  exists at `autonomous_loop.py:1611` (a second outcome-handling branch). Not gated behind any test
  flag — real production execution path.
- **Read (before scoring):** `core/loop/decision_engine.py:497` `_score_candidate()` calls
  `self._epistemic_penalty(candidate)` at `:532` **unconditionally for every candidate**, which is
  itself called unconditionally from `evaluate()` at `:686` for every candidate in every real
  decision. `_epistemic_penalty()` (`:395-436`) reads claim_id `f"action_domain:{domain}"`
  (`:414-416`) and returns a `[0.70, 1.0]` multiplier applied directly to the candidate's total score
  (`total *= epistemic_factor`, `:533`). Gated only by `CONFIG.get("epistemic_scoring", True)`
  (`:409`) — confirmed **no such key exists in `core/config.py`**, so this defaults to `True` (ON) in
  production today.
- **Decay:** `core/loop/autonomous_loop.py:1859`, inside `_reflect_tick()` (2AM reflection), calls
  `DecisionEngine.decay_epistemic()` → `epistemic.decay_all()`.

This pathway is genuinely closed: real reward → real belief write → real belief read → real score
multiplier on the very next `evaluate()` call for any candidate in that same domain. **This
contradicts the stale note; it was fixed** (matches this session's own R9 report, which is
consistent with what the source now shows).

### Pathway 2 — `belief:*` (write-only, confirmed orphaned)

- **Write (every think-tick):** `core/loop/context_engine.py::track_beliefs()` (`:154-239`), called
  unconditionally from `core/loop/autonomous_loop.py:888` inside `_think_tick()` after
  `get_world_state()`. Writes five distinct claim families every tick when the source data is
  present: `belief:presence:{present|absent}` (`:180`, from face detector), `belief:kiit_attendance:
  current` (`:193`, from KIIT scraper), `belief:screen_activity:{activity}` (`:210`, from screen
  observer), `belief:goals:active_progress` (`:221`, from GoalSystem), `belief:memory:health`
  (`:233`, from episodic stats).
- **Read:** grepped the entire `core/` tree for any `get_belief`/`get_confidence` call using a
  `belief:*`-prefixed key, or any other consumer of `track_beliefs()`'s return value beyond the
  `updated: list[str]` used only for a debug log line (`autonomous_loop.py:890`). **Zero matches.**
  The only other consumer of `EpistemicTracker` state anywhere in production is
  `core/api/routers/brain.py:178`, which calls `get_knowledge_summary()` — an aggregate stat
  (counts/avg confidence) for an API endpoint, not a per-key lookup, and not read by
  `DecisionEngine`. This exact finding is already independently documented in
  `72_LEARNING_ARCHITECTURE_V2.md:290` ("write-only, no confirmed consumer"),
  `51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md:64/739`, and `85_COGNITIVE_FOUNDATION_REMEDIATION_PLAN.md:492`
  — my independent re-read of current source confirms these are still accurate at this HEAD; nothing
  in the R6-R11 work this session touched this pathway.

**Namespace question:** `action_domain:*` and `belief:*` are not merged — they physically share one
table but never collide in practice because of the prefix convention (enforced by discipline, not by
a schema constraint — a future writer using a bare, unprefixed key could theoretically collide with
either).

## Reader/writer map

| Namespace | Writer(s) | Real production call site | Reader(s) | Real production call site |
|---|---|---|---|---|
| `action_domain:*` | `DecisionEngine.record_epistemic_belief()` | `autonomous_loop.py:1349`, `:1611` (after every real action outcome) | `DecisionEngine._epistemic_penalty()` | `decision_engine.py:411-416`, called from `_score_candidate()` (`:532`) ← `evaluate()` (`:686`), every real decision |
| `belief:*` | `ContextEngine.track_beliefs()` | `autonomous_loop.py:888`, every `_think_tick()` | *(none found)* | — |

## Current capability level

- `action_domain:*` pathway: **L3** (behaviorally connected — belief state demonstrably changes a
  real score on the next real decision in the same domain). Not yet independently proven at L4
  (persistent-adaptation-changes-a-winner) specifically *through this mechanism* in this audit — R9's
  own report should be consulted for whether that was separately demonstrated; this audit only
  confirms the wiring is real and unconditional, not that a specific behavioral test exists proving a
  winner flip caused solely by epistemic dampening.
- `belief:*` pathway: **L1** (retrieval works — `get_belief()`/`get_knowledge_summary()` return real
  persisted values) but **L0 for decision influence** — nothing reads it for scoring, so it cannot be
  L2 or above for that purpose.

## IMPLEMENTED vs INTEGRATED vs RUNTIME_REACHABLE vs TEST_VERIFIED vs BEHAVIORALLY_VERIFIED

| Pathway | IMPLEMENTED | INTEGRATED | RUNTIME_REACHABLE | TEST_VERIFIED | BEHAVIORALLY_VERIFIED |
|---|---|---|---|---|---|
| `action_domain:*` (dampening) | yes | yes | **yes** — confirmed unconditional in real `evaluate()`/`_act_on()` paths | yes (`tests/test_r9_epistemic_prerequisites.py` et al.) | not independently re-verified in this audit (out of scope — this was a read-only source audit, not a re-run of R9's behavioral tests) |
| `belief:*` (context beliefs) | yes | **no** (writer exists, no reader) | write path yes; read-for-decision path **no** | yes, write-side only (`tests/unit/test_epistemic_integration.py`) | N/A — nothing to behaviorally verify since it influences nothing |

## What's broken vs working

**Working:** the epistemic *dampening* loop (`action_domain:*`) is real, wired both ways,
unconditional, and defaults ON. This is the part of "epistemic prerequisites" that R9 evidently
fixed, and it remains intact and untouched by R11's work this session.

**Not broken, but genuinely incomplete:** the *semantic* belief loop (`belief:presence`,
`belief:kiit_attendance`, `belief:screen_activity`, `belief:goals`, `belief:memory`) is real,
persisted, and queryable via the API — but it is pure telemetry today. It was clearly designed with
future decision-relevance in mind (the five categories map naturally onto plausible future decision
factors — e.g. "don't propose an attendance-related action if KIIT data isn't fresh," "dampen
screen-activity-dependent actions when presence is stale") but nothing currently reads it. This is
not a regression and not a safety issue — it is inert, unused capacity.

## Recommended next milestone (only if genuinely justified)

**Not recommending immediate integration of the `belief:*` pathway** — per this mission's own rule
("do not recommend integration just for its own sake"), and per the Understanding Engine phase's own
sequencing (R16 Epistemic Integration explicitly comes after reward/outcome contracts are stable,
which is downstream of R13-R15 in this program). If/when R16 is reached, the smallest safe
integration would be: pick ONE well-scoped read site (e.g., dampen `search_web`/`check_attendance`
candidates when `belief:kiit_attendance:current` is stale or absent) rather than a broad merge of the
two namespaces — merging them outright would risk exactly the kind of accidental cross-contamination
this mission's safety rules warn against (R16: "Do not merge action_domain and belief namespaces
merely for convenience").

## Open questions

1. Was a behavioral test ever written that specifically isolates the `action_domain:*` dampening
   effect as the SOLE cause of a winner flip (independent of PolicyMemory)? Not found in this audit's
   scope — worth checking `tests/test_r9_epistemic_prerequisites.py` directly if R14/R16 need this as
   a dependency.
2. The five `belief:*` categories were clearly designed with specific future consumers in mind
   (attendance-gating, presence-gating). Was there ever a companion design doc specifying which
   candidate types each belief was meant to gate? Worth checking `docs/design/multi_step_planning.md`
   and `docs/epistemic_tracker_integration_report.md` (both appeared in the grep) before designing
   R16's integration.
3. `merge_belief()`'s Bayesian-ish update (`0.7*old + 0.3*new`) and `get_belief()`'s TTL-based hard
   cutoff (`stale=True, current_confidence=0.0` past TTL) both apply identically to both namespaces —
   worth confirming in R16 whether the same decay/staleness parameters are actually appropriate for
   semantic beliefs (e.g., "owner is present") as for outcome-confidence beliefs (e.g., "coding
   actions tend to succeed"), since they are semantically very different kinds of claims sharing one
   mechanism.
