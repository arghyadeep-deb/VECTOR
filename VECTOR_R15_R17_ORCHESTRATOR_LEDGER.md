# VECTOR R15→R17 Orchestrator Ledger

**Wave:** Master Cognitive Foundation Wave (R15 Autonomous GREEN→GREEN Switching
→ R16 Epistemic Integration → R17 Plan-Derived Strategy Diversity)
**Starting HEAD:** `589f6039afddf8bb8eb260f11114bd7120893ea8`
**Phase 0 confirmed:** clean tree, single worktree, no stale worktrees, R14
lineage intact, no VECTOR/autonomous-loop process running (two `pythonw`
processes found belong to an unrelated "AI video maker" project; `ollama`
is the idle model server, not an active experiment).

This ledger synthesizes 10 parallel, independent, read-only Wave-1
investigations (R15-A, R15-B, R16-A, R16-B, R17-A, R17-B, G, H, I, J). No
production code was touched during Wave 1.

---

## 1. Current Capability (confirmed by direct source reading, not assumed)

- **Native strategy generation**: real, working (R11/R12). 7 preseeded
  goals, tag→action_type mapping, bounded to 3 candidates/goal.
- **Autonomous, unbiased selection + real execution + real reward +
  persistence**: real, working, proven bias-free (R13/R14).
- **R6 staleness-diversity**: real, working, safety-verified even when it
  surfaces a RED alternative (R14).
- **Epistemic influence on decisions**: **already S5-proven** — a real,
  currently-passing test
  (`tests/integration/test_epistemic_integration.py::
  TestEpistemicEvaluateEndToEnd::test_well_known_domain_wins_over_stale`)
  demonstrates a real winner-flip caused by real epistemic state through
  the real `evaluate()` path. This was NOT previously credited in R14's own
  scorecard — R16-A independently re-ran it and confirmed it passes today.
- **Plan infrastructure**: `Plan`/`PlanStep`/`PlanStore`/`PlanRunner` are
  fully built, persistent (JSON-file-backed with crash recovery), and
  ALREADY unified with `DecisionEngine.evaluate()` (plan-derived candidates
  compete in the same call as goal-derived ones) and with `PolicyMemory`
  (same canonical situation-hash writer). This is dormant, not missing.

## 2. Missing Capability (confirmed gaps, not assumed)

- **GREEN→GREEN autonomous switching**: not yet demonstrated. R14's only
  multi-strategy real goal pattern (`tags=["git","coding"]`) has exactly 2
  GREEN options with a RED one positioned between them in generation
  order — R6 surfaces the RED one, not the second GREEN one. No existing
  real preseeded goal has 2+ GREEN-only options.
- **Epistemic contradiction detection & calibration checking**: confirmed
  absent (S0) in `epistemic_tracker.py`. Evidence provenance is shallow
  (subsystem-name only, not decision_id/candidate_id-correlated).
- **A live, real, non-collision-prone `action_domain` generalization
  boundary**: `action_domain = action_type.split("_")[0]` causes
  unrelated action types to share epistemic dampening today
  (`daily_digest`/`daily_review` → `"daily"`; `check_attendance`/
  `check_calendar`/`check_fatigue` → `"check"`; `search_web`/`search_arxiv`
  → `"search"`). This is a genuine, LIVE, pre-existing defect (not
  hypothetical) that also causes one already-existing test in this
  codebase, `tests/integration/test_epistemic_integration.py::
  test_different_domains_independent`, to fail today.
- **Plan-derived strategy diversity for goals that actually need it**: the
  two Equation goals (VECTOR's only goals with zero real strategies today,
  per R12) CANNOT legitimately gain plan-derived diversity — the rule-based
  decomposer produces one inert `respond` step for their titles (verified
  by hand-tracing the deterministic logic), and the LLM path's invented
  action_types would be blocked as `UNKNOWN` at `PermissionGateway`
  unless someone fabricates a mapping — exactly the fabrication R12
  already refused. The plan MECHANISM works; there is no legitimate real
  content to route through it for the goals that actually need it.

## 3. Evidence

All 10 Wave-1 agent reports (full text preserved in this session's
transcript) are the evidentiary basis for every claim above and every
decision below. Key citations are repeated in the relevant milestone
sections.

## 4. Dependency Graph

```
R15 (GREEN→GREEN switching)
  depends on: nothing new — real, already-trustworthy tag mappings exist
  touches: NO production code (test-only, using the established
  isolated-real-tags methodology R11-R14 already use)

R16 (epistemic integration)
  depends on: nothing from R15
  touches: core/loop/decision_engine.py (ONE small, justified fix —
  action_domain collision) — DecisionEngine is a coupled subsystem, so
  R16's mutation must be serialized against any other agent touching
  decision_engine.py (there are none active)

R17 (plan-derived strategy diversity)
  depends on: nothing from R15/R16 architecturally, but is SERIALIZED
  after R16 since both could theoretically touch decision_engine.py
  (R17 in fact does not need to — see decision below)
  touches: NO production code for its own proof (uses the real
  PlanStore/PlanRunner/AutonomousExecutor APIs directly with a real,
  legitimate PlanStep, exactly analogous to R11-R14's "isolated real
  goal" methodology)
```

**No two milestones require concurrent modification of the same coupled
subsystem** — R16 is the only one with a real production code change, and
it is small, isolated, and executed as a single serialized mutation.

## 5. Proposed Implementation Order

1. **R15** (test-only, no dependencies, fastest to close)
2. **R16** (one small, isolated production fix + tests)
3. **R17** (test-only, uses already-built real plan infrastructure)

## 6. Agents Responsible

Implementation and testing for all three milestones is executed directly
by the orchestrator (this session) rather than further sub-agents, since
each milestone's scope — confirmed by Wave 1 — is now precisely bounded
and does not require additional open-ended investigation. Wave 1's 10
agents remain the investigative record. A FRESH, different set of
read-only auditors will be spawned after implementation for the mandated
final cross-subsystem audit (Section "Final Cross-Subsystem Audit" below,
executed after all three milestones land).

## 7. Risks

- **ArchitectBot.scan_codebase_with_graph() blocks the entire event loop**
  (Agent H, confirmed via `governor.py`'s own KNOWN_ISSUES #0 comment) —
  MITIGATED for this wave by design: R15's flagship scenario
  (`tags=["git","research"]`) never involves `read_code`/`code_task`, so
  this hazard is not exercised. Documented as a pre-existing, out-of-scope
  issue, not fixed here (would be scope creep per the mission's own "do
  not turn this into a general cleanup task" instruction to Agent H).
- **Governor.dispatch() has no PermissionGateway call of its own** (Agent
  I) — a pre-existing, distributed-not-centralized safety pattern. Not
  weakened by this wave; not fixed by this wave (out of scope, flagged for
  a future dedicated hardening task).
- **`_decompose_to_plan()` is fire-and-forget with no timeout** (Agent H)
  — not exercised by R17's design (R17 constructs a real Plan directly via
  `PlanStore`/`PlanRunner`, never calling `add_goal()`/LLM decomposition),
  so this risk is not triggered by this wave.
- **`test_task92_r7_decision_candidate_correlation.py`'s one test missing
  `isolated_vector_db`** (Agent J) — pre-existing, read-only, low-risk.
  Will be fixed as part of this wave's own test-isolation discipline since
  it is now known and trivial to fix, even though it predates this wave.

## 8. Safety Boundaries

Confirmed by Agent I, independently re-verified during implementation:
`PermissionGateway._classify()` is a pure static lookup, never touched by
learned/epistemic/plan state; every real execution path (including the
plan-step path via `AutonomousExecutor`) independently reaches the same
`PermissionGateway.execute()`; no code path lets R15/R16/R17's changes
relax RED/YELLOW/FORBIDDEN authorization.

## 9. Tests Required

Per milestone, following the established R11-R14 rigor: flagship
(bias-free, real production path), causal controls, safety tests,
adversarial review, regression, production-DB-safety watermark
verification (mandatory given the R14 incident).

## 10. Capability Delta for Each Milestone

See each milestone's own report section below (written after
implementation, in `R15_R17_COGNITIVE_FOUNDATION_REPORT.md`).

---

## Milestone Decisions

**R15: REQUIRED, NARROWED.** Repository evidence (R15-A) shows the target
capability is achievable with a **test-only** change — using a real,
already-trustworthy tag pair (`["git","research"]`) with the established
"isolated real goal, real tags, no production mutation" methodology R11-R14
already use. No production code change is needed or justified. Proceeding.

**R16: REQUIRED, NARROWED AND PARTIALLY ALREADY PROVEN.** R16-A found the
target capability (epistemic state changes a real decision) is **already
S5-proven** by an existing, currently-passing test. R16's real remaining
work is: (a) independently re-verify that existing proof is genuine and
robust (not simply trust the agent's claim), (b) fix the one real,
already-failing bug this wave discovered (`action_domain` collision,
`decision_engine.py`) — a small, safety-relevant, justified connective fix,
not a new architecture, (c) add before/after capability evidence and causal
controls distinguishing epistemic influence from PolicyMemory/R6
influence, per the mission's explicit requirement. Proceeding.

**R17: REQUIRED, NARROWED TO THE MECHANISM PROOF, NOT THE EQUATION-GOAL
CONTENT PROBLEM.** R17-A confirms the plan→candidate→execution→learning
pipeline is fully built and wired. R17-B confirms the ONE place that
genuinely needs plan-derived diversity (the Equation goals) cannot get it
without fabrication — R12 already correctly declined that fabrication, and
this wave does not reopen it. R17's legitimate scope is therefore: prove
the ALREADY-BUILT pipeline works end-to-end via a real, non-fabricated
`PlanStep` (real action_type already in the GREEN whitelist, e.g.
`git_status`), constructed directly via the real `PlanStore`/`PlanRunner`
APIs — analogous to how R11-R14 construct a real isolated `GoalSystem`
with real tags rather than running the full seeding pipeline. This proves
"plan steps become real candidates/decisions, not dead metadata" — the
actual R17 target capability — without needing a live LLM call or
fabricated goal semantics. Proceeding on this narrowed, honest basis.

No milestone is eliminated. No milestone is merged. No milestone required
a new prerequisite beyond what's listed above.
