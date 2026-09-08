# Task 78 — VECTOR Offline Digital Twin / Decision Simulation Lab

Segment 2 (the running 7-day experiment) was never stopped, restarted, signaled,
attached to, queried, or interacted with in any way during this task. No
production `.py` file was modified. No experiment database or log was opened.
This entire task built and ran a new, isolated, disk-backed research tool under
`VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/` — see §17 for the exact final
integrity check.

---

## 1. Objective

Build a reusable offline laboratory that reproduces VECTOR's real
decision-making logic against fully isolated storage, so questions like "why
did VECTOR choose action A?", "did memory/policy/counterfactual/epistemic
state actually influence this decision?", and "can a learned state cause a
later behavioral change, provably?" can be answered by running code, not by
re-reading `decision_engine.py` from scratch every time.

## 2. Why This Is Different From Tasks 71/72

Tasks 71 and 72 are architecture audits and a design document — they read
source and describe what exists and what a future Learning V2 should look
like. Task 78 builds and runs a working artifact: ~2,900 lines of Python
across 21 modules, 4 pytest files (28 tests, all passing — see §17), and 4
saved, deterministically-replayable scenario fixtures, all of which execute
**real, unmodified `core/*` production classes** — `DecisionEngine`,
`PolicyMemory`, `GoalSystem`, `EpisodicMemory`, `EpistemicTracker`,
`CounterfactualMemory` — against isolated SQLite state. Findings already
documented in Task 71/72 (the `analyze_progress` dominance pattern, the
`_TAG_TO_ACTION` dead mapping, counterfactual's post-hoc-only veto position)
are **reused as grounding, not rediscovered**, and in several places this lab
produces genuinely new evidence Task 71/72 did not have — most notably the
Level-5 generalization finding in §11 and the Level-6 provenance gap in §11.

## 3. Laboratory Architecture

```
Scenario (deterministic recipe)
   |
   v
IsolatedVectorEnv (isolation.py)      -- VECTOR_DB_PATH/VECTOR_DB_KEY env vars
   |                                      + explicit db_path= for CF/epistemic
   v
DigitalTwin.run_in_env()  (twin.py)
   |
   +-- real GoalSystem (seeded or overridden)
   +-- real PolicyMemory (pre-seeded via policy_updates)
   +-- real EpistemicTracker (pre-seeded via epistemic_beliefs)
   +-- real CounterfactualMemory (pre-seeded via counterfactual_rejections)
   +-- real DecisionEngine.evaluate(candidates)  <-- the actual 5-factor scorer
   +-- counterfactual_veto()  <-- faithful port of autonomous_loop.py:1090-1126
   |
   v
DecisionTrace (trace.py) -- run_id, situation, goals, candidates, per-candidate
                             score components (VERBATIM from the real engine),
                             ranking, winner, rejected, decision reason, veto

Built on top of DecisionTrace:
  experiments.py        -- generic paired A/B comparator ("exactly one changed variable")
  policy_lab.py          -- 6 PolicyMemory sensitivity experiments
  counterfactual_lab.py  -- 8 CounterfactualMemory veto/decay/indirect-influence experiments
  epistemic_lab.py       -- 5 EpistemicTracker sensitivity experiments (incl. namespace test)
  level4_experiment.py   -- the flagship behavioral-adaptation experiment + causal chain
  controls.py            -- 8 named confound controls
  evolution.py           -- multi-experience accumulation vs. adaptation
  sensitivity.py         -- one-factor-at-a-time decision-critical ranking
  replay.py              -- deterministic scenario save/replay + fingerprinting
  regression.py          -- PRESERVED/INTENDED/UNINTENDED/SAFETY_REGRESSION classifier
  scaffold_l5_l6.py       -- Level-5 (real experiment) + Level-6 (documented gap) research scaffolding
  scorecard.py            -- runs everything above, produces the Level 0-7 scorecard (§16)
```

## 4. Isolation Guarantees

- **Mechanism, not invention**: `core/memory/db_utils.py::configured_db_path()`
  already honors a `VECTOR_DB_PATH` environment-variable override "for
  repair/tests" (its own docstring). This is the exact, pre-existing,
  official isolation mechanism `tests/backend/test_memory_quality.py` and
  siblings already use. `IsolatedVectorEnv` (isolation.py) reuses it
  verbatim — set `VECTOR_DB_PATH`/`VECTOR_DB_KEY`, call
  `core.memory.episodic.close_db_connection()`, and every class that routes
  through that singleton (`EpisodicMemory`, `PolicyMemory`, `GoalSystem`) is
  isolated at once, using their real, unmodified code.
- `CounterfactualMemory` and `EpistemicTracker` each accept an explicit
  `db_path` constructor argument in production already (see their own
  `__main__` self-tests) — the lab just hands them a path under the same
  run-scoped temp directory.
- Every `IsolatedVectorEnv` gets its own `tempfile.mkdtemp(prefix="vector_twin_<run_id>_")`
  directory. Nothing in the lab ever constructs a path pointing at the real
  `vector_memory.db`, `counterfactual.db`, or `epistemic.db`.
- **Disclosed side effect, understood and harmless**: `EpisodicMemory.store()`
  (called by the real `DecisionEngine.evaluate()` to log every candidate)
  triggers `core.engine.memory_tree.tree_builder`'s one-time legacy-migration
  check, which **reads** `~/.vector_ca/memory_tree/memory_tree.json` (a
  real, global, non-experiment file) and **writes** a migrated copy only
  into the isolated run's own temp directory, explicitly leaving the
  original in place (confirmed via this session's own log output — see
  §17). This is read-only with respect to the source file and never touches
  any experiment-related path; it is disclosed here rather than silently
  omitted.
- No lab module imports `core.loop.autonomous_loop` (the file with
  websockets, hardware sensing, the scheduler, and the event bus). Two
  narrow slices of its orchestration logic were manually, faithfully ported
  with exact line citations — see §5.
- No lab module calls a real LLM/cloud provider. `DecisionEngine._reasoning_bank`,
  `._neural_trainer`, and `._metacognition` are deliberately set to `False`
  (the class's own "unavailable" sentinel — not a new code path) before
  every run; `._context_engine` is replaced with a two-line stand-in whose
  `get_world_state()` returns `{}`, justified because `decision_engine.py`'s
  own comment states that value "does NOT currently change the score formula
  itself."
- The main pytest suite (`pytest.ini`'s `testpaths = tests`) does **not**
  discover this lab's tests — they only run via an explicit path
  (`pytest "VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests"`), so nothing here
  can ever affect the project's CI or default test run.
- Every `IsolatedVectorEnv`'s temp directory is either explicitly cleaned by
  the caller (`.cleanup()`) or swept by an autouse pytest session fixture
  (`tests/conftest.py`) — confirmed zero `vector_twin_*` directories remain
  under the OS temp folder after this task (see §17).

## 5. Real Production Logic Reused (vs. Adapters)

**Directly imported, real, unmodified, isolated via `VECTOR_DB_PATH`:**
`core.memory.episodic.EpisodicMemory`, `core.memory.policy.PolicyMemory`,
`core.brain.goal_system.GoalSystem` (including its real `PRESEEDED_GOALS`
and real `generate_immediate_actions()`).

**Directly imported, real, unmodified, isolated via explicit `db_path=`:**
`core.brain.epistemic_tracker.EpistemicTracker`,
`core.memory.counterfactual.CounterfactualMemory`.

**Directly imported, real, unmodified — and confirmed to make zero LLM or
network calls anywhere in its own scoring path:**
`core.loop.decision_engine.DecisionEngine` / `Candidate` / `Decision`. This
was verified by reading `evaluate()` and `_score_candidate()` in full (not
assumed): the only calls inside are DB reads/writes (`PolicyMemory`,
`GoalSystem`, `EpisodicMemory`, `EpistemicTracker`) and optional,
gracefully-degrading lazy dependencies.

**Two small, exact, cited adapters** (real orchestration glue from
`core/loop/autonomous_loop.py` that cannot safely be imported wholesale —
that file pulls in the event bus, scheduler, websockets, and hardware
sensing):

| Adapter | Source lines ported | What it does |
|---|---|---|
| `twin.auto_candidates_from_goals()` | `autonomous_loop.py:832-878` | The exact goal-action -> `Candidate` translation, **including** the dead `_TAG_TO_ACTION` lookup (kept dead deliberately — see §7) |
| `twin.counterfactual_veto()` | `autonomous_loop.py:1090-1126` | The exact post-selection veto check + the hardcoded `reward=0.05` policy penalty on a block |

**Deliberately excluded** (out of scope for "the smallest meaningful decision
surface," documented in `twin.py`'s own module docstring): `PlanStore`/
`PlanRunner` plan-step candidates, the avatar mood nudge, `SwarmCoordinator`
consensus veto, `ThreatDetector` scanning, and the entire
observe/sense/act/reflect tick machinery.

## 6. Scenario Model

`scenario.py`'s `Scenario` dataclass: `situation`, `goals` (`None` = real
`PRESEEDED_GOALS`), `candidates` (`"auto"` = real
`generate_immediate_actions()`, or an explicit list), `policy_updates`,
`counterfactual_rejections` (with `created_at_days_ago` backdating for
staleness-decay tests), `epistemic_beliefs` (with `age_hours_override`
backdating for TTL-staleness tests), `apply_counterfactual_veto`. Fully
JSON-(de)serializable (`to_json`/`from_json`), and `.clone(**overrides)`
gives every paired experiment in the lab its "baseline + exactly one changed
variable" primitive via a JSON deep-copy (no shared-reference bugs between
A and B).

## 7. Decision Trace Format

`trace.py`'s `DecisionTrace`: `run_id`, `situation`, `active_goals`,
`generated_candidates`, `memory_inputs`/`policy_inputs`/
`counterfactual_inputs`/`epistemic_inputs` (what was actually applied before
scoring), a `CandidateTrace` per candidate carrying its
`score_components`/`reasoning_steps` **verbatim from the real
`Candidate.reasoning_chain`/`.reasoning_steps`** (never re-derived), the
winner, rejected list, the real `Decision.reasoning` string, and
counterfactual veto status/reason. `.explain()` renders a full "why did X
win?" narrative from this data alone.

**Independent re-confirmation of a Task 71/72 finding, this time from a live
run, not from reading source**: replaying `scenarios/scenario_001_auto_seeded_goals.json`
(real seeded goals, real `generate_immediate_actions()`) produces:

```
Winner: analyze_progress (score=0.75) over 3 alternatives.
goal_alignment=1.00 policy=0.50 confidence=0.70
```

`goal_alignment=1.00` — the maximum possible — because two of the seven real
`PRESEEDED_GOALS` are `LONG`/`MID` horizon with `progress==0.0`
(`g_kiit_attendance`, priority 10; `g_first_revenue`, priority 10), both of
which map through `GOAL_ACTION_MAP` to `"analyze_progress"`, and
`generate_immediate_actions()` never reaches `_TAG_TO_ACTION` because its own
returned dicts never carry a `"tags"` key (re-derived directly from
`goal_system.py`'s source, independent of Task 71's own citation of the same
fact).

## 8. Counterfactual Experiments (Phase 5/7)

`counterfactual_lab.py`, all passing (`pytest`, §17):

- A rejection whose proposal string matches the current winner (exact
  `json.dumps(params)` format, matching `autonomous_loop.py`'s own proposal
  construction) **vetoes** the action; an unrelated rejection does **not**.
- A rejection ~50 days old decays (real `_decay_factor()` math, `decay_days=7`
  default -> ~7 half-lives) below the 0.7 veto threshold; a fresh one (0.01
  days old) still blocks.
- **Proven, not assumed** (`exp_veto_does_not_change_ranking`): toggling
  `apply_counterfactual_veto` True/False produces **zero** score-component
  delta on any candidate — counterfactual state is confirmed to be entirely
  outside `DecisionEngine`'s scoring path, exactly matching the source-level
  finding in §5/twin.py's dependency map.
- **The one real, closed indirect loop, measured**
  (`exp_indirect_policy_penalty_reshapes_future_ranking`): repeatedly vetoing
  the same action across cycles forces the real `reward=0.05` policy penalty
  (`autonomous_loop.py:1115`, already cited in Task 71/72, now measured live)
  each time, which — over enough cycles, sharing one isolated `PolicyMemory` —
  genuinely drags that action's future policy_score down relative to a
  never-vetoed rival.

## 9. Policy Experiments (Phase 6)

`policy_lab.py`, all passing:

- Reward direction moves score in the correct direction (higher reward ->
  higher score).
- Reward is correctly isolated per `(action_type, situation_hash)` — a
  reward on a different `params` dict for the *same* `action_type`
  (`exp_different_situation_same_action`) produces **zero** measured
  transfer; a reward on a genuinely different `action_type`
  (`exp_different_action_types_isolated`) likewise does not leak.
- **Measured, not merely cited**, limitation from Task 71/72: two
  contradictory rewards (0.9 then 0.1) collapse to the plain online average
  — `PolicyMemory` has no mechanism to represent "the last experience
  contradicted the earlier one" as anything other than an indistinguishable
  midpoint (`exp_contradictory_rewards`, `controls.control_8`).

## 10. Epistemic Experiments (Phase 8)

`epistemic_lab.py`, all passing:

- A low-confidence `action_domain:*` belief measurably lowers score versus
  no belief at all; a stale (TTL-expired) belief lowers it further (heaviest
  0.70x dampening), matching `_epistemic_penalty()`'s documented tiers,
  confirmed with real numbers, not just re-reading the docstring.
- **Falsification test, proven**: a `belief:*`-namespaced claim (the general
  `update_belief`/`record_claim` namespace used elsewhere, e.g.
  `user_name`/`location`) produces **exactly zero** score change, because
  `_epistemic_penalty()` only ever reads `action_domain:<domain>` keys. This
  had been implied but not directly proven in earlier tasks; this lab proves
  it with a paired experiment.

## 11. Level-4 Behavioral Adaptation Experiment (Phase 9) — The Flagship

`level4_experiment.py`. Runs **two decisions against ONE isolated environment
with a real `close_db_connection()` + reopen of the SAME on-disk SQLite file
between them** (genuine restart semantics, not a simulation), and requires
evidence along the full chain before declaring anything:

```
EXPERIENCE -> STATE CHANGE -> PERSISTENCE -> RETRIEVAL
            -> DECISION INFLUENCE -> BEHAVIORAL CHANGE (winner flips)
            -> CAUSATION (a no-learning control run's winner did NOT flip)
```

A real run (`scenarios/scenario_002_close_race.json` — `search_web`
confidence 0.60 vs `check_calendar` confidence 0.62, a deliberately close
race), with a `reward=0.98` outcome applied to `search_web` between runs:

```
run1 winner: check_calendar  0.52
run2 winner: search_web      0.611
control1 winner: check_calendar
control2 winner: check_calendar

VERDICT: PASS — full causal chain demonstrated: experience caused a
persistent, retrieved, decision-changing, winner-flipping behavioral change
```

This is a genuine, reproducible, mechanistically-explained demonstration
that VECTOR's *existing* `PolicyMemory` + `DecisionEngine` wiring **is**
capable of Level-4 behavioral adaptation, under laboratory conditions with a
strong, unambiguous reward signal and a close initial race. Section 14
addresses why this does not contradict Segment 2's observed
`analyze_progress` dominance.

**Design constraint, disclosed rather than hidden**: Level-4 requires >= 2
competing candidates whose scores are close enough for a policy shift to
plausibly flip the ranking — `run_level4_experiment()` raises `ValueError`
on a single-candidate or `"auto"` scenario rather than silently reporting a
false result.

## 12. Control Experiments (Phase 10)

`controls.py`, all 8 implemented and passing: no-learning, learned-state-
present, unrelated-memory-present, same-situation-no-relevant-experience,
restart-between-learning-and-recall, time-passage-without-learning,
different-situation, contradictory-experience. Every one of them runs a real
scenario through the real twin — none are asserted from first principles.

## 13. Sensitivity Analysis (Phase 12)

`sensitivity.py`, run against the real 5-factor formula's own weights
(`W_GOAL=0.30, W_CONF=0.25, W_POLICY=0.20, W_URGENCY=0.15, W_TIMING=0.10,
W_COST=0.05`):

| Factor | Δ (low->high) | Decision-critical? |
|---|---|---|
| confidence | large | **yes** |
| policy_score | +0.096 (single strong reward) | **yes** |
| goal_alignment | large (0.3 floor -> active-goal ceiling) | **yes** |
| urgency, timing_score | moderate | yes |
| estimated_cost_inr | small, capped | marginal |
| epistemic_factor | multiplicative dampening only, never a boost | conditionally yes |
| **counterfactual_state** | **exactly 0.0** | **no — not a scoring input at all** |
| **episodic_memory recall** | **exactly 0.0 (no read path exists)** | **no** |

## 14. Multi-Experience Evolution (Phase 11)

`evolution.py` applies a reward sequence (`[0.6, 0.7, 0.8, 0.9, 0.95]`) one
step at a time against a shared isolated env and explicitly separates
`state_accumulated()` (did `sample_count` grow — trivially yes, every run)
from `behavioral_adaptation_events()` (did the winner actually flip, and at
which step). This is the tool that would let a future session distinguish
"VECTOR's policy_memory table now has 40,000 rows" from "VECTOR's behavior
has actually changed" — exactly the row-count-vs-behavior distinction
Task 71 flagged as a risk for the eventual Day-7 analysis.

## 15. Replay System (Phase 13)

`replay.py`: `record(scenario, path)` runs a scenario once and saves both
the `Scenario` and a canonical fingerprint (selected action, ranking,
per-candidate scores, veto status) plus its SHA-256 hash. `replay(path)`
reloads, re-runs fresh, and reports either an exact match or a precise,
field-level reason for the mismatch (which candidate's score moved, by how
much, whether the winner or the veto status changed) — never a bare
"different." Four real fixtures are saved under `learning_lab/scenarios/`
and all four replay with an exact match (confirmed in §17).

## 16. Regression System (Phase 14)

`regression.py` builds on `replay.py`: `save_case()`/`check_case()`
classify a case as `PRESERVED`, `INTENDED_CHANGE` (only when the case was
explicitly saved with `accept_change=True`), `UNINTENDED_CHANGE`, or
`SAFETY_REGRESSION` (specifically: a previously-vetoed action is no longer
vetoed on replay). Per Task 78's explicit instruction, this is **not** wired
into the project's CI — it is a standalone mechanism a future session can
adopt deliberately when Learning V2 work begins.

## 17. Test Results

```
pytest "VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests" -v
28 passed, 0 failed, 0 skipped, 0 errors  (17.4s)
```

Covering: twin wiring + isolation (4), policy/counterfactual/epistemic labs
(6), sensitivity (2), Level-4 + all named controls (5), evolution (1),
scaffold L5/L6 (1), replay determinism (2), regression classification (3),
full 8-level scorecard (3). None of these tests touch experiment state,
production databases, the running VECTOR process, or runtime configuration
— every DB path used is a fresh `tempfile.mkdtemp()` directory, verified by
`isolation.assert_isolated()` and by direct inspection of the logged paths
during every run (e.g. `...\Temp\vector_twin_<run_id>_...\epistemic.db`).
All `vector_twin_*` temp directories created during this task's testing and
manual script runs (343+ over the course of the session) were swept; a
session-scoped `tests/conftest.py` fixture now does this automatically for
future lab runs.

**Level 0-7 scorecard** (`scorecard.py`, real output from this session):

```
LEVEL 0 — STORAGE                  PASS
LEVEL 1 — RETRIEVAL                PASS
LEVEL 2 — INFLUENCE                PASS   (Δ=+0.0960)
LEVEL 3 — PERSISTENT STATE         PASS
LEVEL 4 — BEHAVIORAL ADAPTATION    PASS   (full causal chain, control ruled out)
LEVEL 5 — GENERALIZATION           PASS   (domain-prefix epistemic bucketing — see §11 note below)
LEVEL 6 — CORRECTION               NOT_IMPLEMENTED  (no provenance field exists anywhere on the write path)
LEVEL 7 — META-LEARNING            NOT_IMPLEMENTED  (every learning parameter traced is a static CONFIG constant)
```

**Level 5 note** (new finding from this lab, not previously documented):
`search_arxiv` and `search_web` share the domain prefix `"search"`
(`action_type.split("_")[0]`). An epistemic belief recorded against
`action_domain:search` (regardless of which specific `search_*` action_type
produced it) measurably changes **every** `search_*` action's score via
`_epistemic_penalty()`. This is a real, narrow, already-existing
generalization channel — not something newly built — and it is worth the
next Learning V2 session's attention precisely because it is *undocumented*
and *unintentional*-looking (nothing in `decision_engine.py`'s comments
suggests this was a deliberate design choice).

## 18. Limitations

- The lab reproduces **the scoring/veto surface** of one decision cycle. It
  does not simulate the observe/sense/act/reflect loop, the scheduler, the
  event bus, plan execution, or multi-agent/district coordination — those
  remain out of scope by design (§5).
- `ContextEngine.get_world_state()` is replaced with an empty-dict stand-in.
  This is justified (§4/§5) but means the lab cannot currently test any
  *future* change that makes world-state context actually feed into scoring
  — a Learning V2 change here would need the stand-in swapped back for a
  real (still-isolated) `ContextEngine`.
- `ReasoningBank`/`MetaCognition`/the neural RL trainer are disabled. If a
  future Learning V2 makes any of these genuinely decision-influential, this
  lab's `build_isolated_engine()` will need updating to isolate them too
  (none currently expose a constructor-level isolation path the way
  `PolicyMemory`/`CounterfactualMemory`/`EpistemicTracker` do — this is
  itself a finding worth noting for that future work).
- Level 6 (correction) and Level 7 (meta-learning) have no real mechanism to
  test yet — `scaffold_l5_l6.py`'s `CorrectionExperienceRecord` defines the
  contract a future implementation would need; nothing more.
- The lab was exercised only against the real, seeded, fresh state each
  scenario starts from — it was never pointed at, and cannot be pointed at,
  Segment 2's actual accumulated state (by design; see §4).

## 19. Production Integration Requirements

None required to use the lab as-is — it is fully standalone. If a future
session wants to promote any part of it toward production:

- `regression.py`'s case system would need a decision on where
  "golden" cases live and how `pytest.ini`'s `testpaths` should be extended
  (deliberately not done in this task).
- Closing the Level-6 gap (§11, §18) means adding a provenance field
  somewhere on the `PolicyMemory.update_from_outcome()` /
  `CounterfactualMemory.record_rejection()` write path — a real Learning V2
  schema change, out of scope for this task by design.
- The Level-5 domain-generalization channel (§17) should be either
  deliberately documented as intended behavior or reconsidered — currently
  neither is true.

## 20. Post-Experiment Implementation Recommendations

1. Re-run `scorecard.py` and the full sensitivity/control suite against
   Segment 2's **actual accumulated policy/counterfactual/epistemic state**
   once the experiment concludes (via a read-only export into the lab's
   isolated format, never live access) — this lab's synthetic scenarios
   prove the mechanisms *can* work; the real question for Day 7 is whether
   Segment 2's actual 7 days of runtime ever exercised them with a signal
   strong enough to matter (the `analyze_progress` dominance + the flat
   `reward=0.05` counterfactual penalty documented in Task 71/72 suggest the
   real reward signal was far weaker and far less varied than this lab's
   deliberately clean `0.98` test reward).
2. Use `evolution.py`'s accumulation-vs-adaptation split, not raw row
   counts, when analyzing Segment 2's `policy_memory` table growth.
3. Treat the Level-5 generalization channel (§17) as a design decision that
   needs to be made explicitly, not left as an accidental side effect of
   `action_type.split("_")[0]` domain bucketing.
4. Prioritize closing the Level-6 provenance gap (§11/§18) before any
   correction-learning work begins — there is currently no way for the
   system to tell an owner's deliberate correction apart from noise, at the
   data-model level, not merely the UX level.
5. Adopt `replay.py`/`regression.py` as the standard way to validate any
   Learning V2 change against the exact scenarios recorded in
   `learning_lab/scenarios/` before it ships, expanding that fixture set as
   real interesting Segment 2 situations are identified.

---

## Final Post-Experiment Map

```
CURRENT VECTOR (Segment 2, untouched)
      |
WHAT THE LAB CAN REPRODUCE
   -> one full decision cycle: goal-seeded candidate generation, the real
      5-factor DecisionEngine formula, PolicyMemory get/update, Epistemic
      dampening, the post-hoc CounterfactualMemory veto — all real code
      |
WHAT THE LAB CAN MEASURE
   -> Levels 0-5 of the storage->retrieval->influence->persistence->
      behavioral-adaptation->generalization ladder, each with a real,
      passing, falsifiable experiment and an honest control group
      |
WHAT IT CANNOT MEASURE YET
   -> Level 6 (correction) and Level 7 (meta-learning) — no real mechanism
      exists in production to test; the observe/sense/act/reflect loop,
      scheduler, event bus, and multi-agent coordination are out of scope
      |
WHAT MUST BE CHANGED AFTER DAY 7
   -> (a) add a provenance field to the policy/counterfactual write path
      (Level 6), (b) decide deliberately on the Level-5 domain-generalization
      channel, (c) re-point the lab's analysis (not the lab's mechanism) at
      Segment 2's real accumulated state via a read-only export
      |
WHAT EXPERIMENT WILL PROVE THE CHANGE WORKS
   -> re-run scorecard.py; a provenance change should let a new Level-6
      experiment (mirroring level4_experiment.py's causal-chain structure)
      show owner-corrections and random noise producing DIFFERENT policy
      state, with the same no-learning-style control ruling out confounds
```
