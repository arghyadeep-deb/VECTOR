# 51 — Final Cognitive Integration Audit

**Date**: 2026-09-01
**Type**: AUDIT ONLY — no code changed, no fixes implemented, no new capabilities added.
**Method**: Direct code reading (Read/Grep) across `core/`, `districts/`, `agents/`, `run_vector.py`,
plus 6 parallel deep-trace sub-audits (core cognitive loop, memory systems, owner-correction
learning, governance/safety, autonomy/scheduling/long-horizon execution, tool
execution/proactivity), cross-checked against this document's own independent direct tracing.
Every claim below cites file:line. Where a claim could not be verified, it is stated explicitly
as unverified rather than assumed. Two findings from the core-cognitive-loop sub-audit
(§1 findings #1-#2) were independently re-verified by direct file reads before being accepted
into this document, since they materially change the final verdict.

---

## 1. Executive Summary

VECTOR's core cognitive loop is real, not aspirational. `python run_vector.py` (no arguments)
boots `AutonomousLoop().run_forever()` by default (`run_vector.py:491`, `mode="loop"`), which
supervises 21 named coroutines (`autonomous_loop.py:2462-2484`) including a 10-second `think_loop`,
a 2AM `reflect_loop`, a 4-hour `hypothesis_loop`, and a 10-minute `anticipation_loop` — all wrapped
in a restart-with-backoff supervisor (`_supervised()`) so a crash in one subsystem does not kill the
process. The goal→candidate→decision→action→outcome→memory chain is genuinely closed for the
majority of real actions: `PolicyMemory`, `CounterfactualMemory`, and the `action_domain:*`
epistemic-confidence loop all demonstrably influence later decisions, not just log them.

Six sub-audits plus this document's own direct tracing found five integration defects. Two are
narrow, concrete code bugs that silently disable a documented capability and were confirmed by
reading the exact lines in question (not inferred from behavior); three are architectural
integration gaps (real code, real data, but not connected the way documentation implies):

1. **`hypothesis_loop()` never awaits its async LLM call — proactive hypothesis generation has
   never actually executed.** `HypothesisEngine.generate_hypotheses()` is `async def`
   (`hypothesis_engine.py:48`), but `hypothesis_loop()` calls it as
   `engine.generate_hypotheses(context)` with no `await` (`autonomous_loop.py:2868`). The result is
   an un-awaited coroutine object, not a hypothesis list — `if not hypotheses:` is always `False`
   (a coroutine object is truthy), so the loop falls through to `isinstance(hypotheses, list)`
   (`False`) → wraps it as `[hypotheses]` → `isinstance(h, dict)` (`False`) → `confidence = 0.0` →
   every cycle logs "Low-confidence insight suppressed" and writes nothing to memory. The
   underlying LLM call inside `generate_hypotheses()` never fires at all. This has been silently
   broken since this code was written; the one test covering this path
   (`tests/integration/test_spec12_year2_cognition.py` per the sub-audit that found this) only does
   `inspect.getsource()` string matching for the word "hypothesis," never actually executes the
   coroutine, so the bug produces no test failure. **Confirmed by direct read of both files this
   pass.**
2. **Plan steps that crash mid-execution never recover — they stall the plan forever, silently.**
   `PlanRunner.execute_step()` sets `step.status = "running"` and persists it to disk BEFORE
   calling the executor (`plans.py:689-691`). If the process crashes or is killed between that
   write and the step's eventual `"completed"`/`"failed"` status write, the step is permanently
   stuck at `"running"`. `Plan.next_ready_steps()` only offers steps with `status == "planned"`
   (`plans.py:212`) — a `"running"` step is excluded and nothing anywhere resets it back to
   `"planned"` on restart. The plan does not fail or error; it simply stops making progress on
   that branch forever, with no log entry indicating why. The existing "resume after restart" test
   (per the sub-audit that found this) only covers the clean-completion case, never a crash mid-step.
   **Confirmed by direct read of `plans.py:203-217,684-691` this pass.**
3. **Permission-gateway coverage is not universal.** `_act_on()`'s own docstring claims "RULE 3 —
   LLM zero direct access, all through gateway," but only four action-type buckets are actually
   gated (`proactive_*`, plan steps, a 5-item `_VC_ACTION_TYPES` set, and skill-matched actions).
   Every other action — the majority of `Governor.dispatch()` traffic — reaches a district agent's
   `.run()` with no GREEN/YELLOW/RED check at all. Confirmed independently by three separate traces
   (this document's author, the governance-audit fork, and the tool-execution-audit fork), all
   pointing to the same line numbers.
4. **The epistemic tracker (Gap 3) has two disjoint keyspaces that never intersect.** Beliefs formed
   from raw sense data (`context_engine.track_beliefs()`, prefix `belief:*`) can never influence the
   decision-engine's epistemic penalty (`decision_engine._epistemic_penalty()`, prefix
   `action_domain:*`) — they read and write entirely different claim IDs in the same SQLite table.
   The `action_domain:*` outcome→confidence→next-decision loop IS real and closed; the
   `belief:*` formation→decision loop is not connected to anything that scores decisions.
5. **Owner-correction learning is prompt-injection only, and capture is voice-command-only.** The
   full capture→store→retrieve→inject chain is real, but it (a) only fires when a correction comes
   through the voice-intent path (not web chat, terminal, or API), and (b) only ever reaches a
   deterministic decision as free text inside an LLM prompt — `decision_engine.py` has zero
   references to `CorrectionLearner`. The outcome-feedback method that would close the loop
   (`validate_lesson()`) exists and works in isolation but has zero production callers.

**Findings #1 and #2 change the verdict.** #1 means one of the four proactivity mechanisms the
experiment would likely be designed to measure ("does VECTOR generate proactive insights over 7
days") has been completely non-functional, silently, this entire time — an experiment run today
would correctly observe zero hypotheses ever surfacing and could misattribute this to "VECTOR
chose not to generate any" rather than "the code never ran." #2 is a data-integrity risk
specific to a 7-day *unattended* run: any process restart (crash, OOM, manual restart, host
reboot) that happens to land mid-step on a long-horizon plan will silently and permanently stall
that plan for the remainder of the 7 days, with no error signal — an experiment measuring
"long-horizon plan completion rate" would get corrupted, unexplained data from this alone, and
over 7 days of continuous operation, at least one restart is a realistic occurrence, not an edge
case. Both are narrow, single-location fixes (a missing `await`; a status-reset-on-boot check) —
not architectural problems — but per this document's own MUST-FIX rule (§16), both qualify: their
presence would corrupt or entirely suppress data the experiment is presumably designed to collect.

None of these three defects prevents a 7-day experiment from running or from producing real,
measurable data about VECTOR's autonomous behavior. They do mean the experiment's data will not
demonstrate "epistemic-aware decision-making" or "owner-correction-driven learning" in the strong
sense the architecture's naming suggests — see §16 for the precise, scoped recommendation.

**Verdict (repeated from §20 for visibility): NOT READY — 2 MUST-FIX blockers** (findings #1 and
#2 above: the un-awaited `hypothesis_loop()` call, and plan-step crash-recovery). Both are narrow,
well-understood, single-location fixes. Findings #3-#5 are real integration gaps but do not block
the experiment — see §16-§17 for the full blocker/non-blocker breakdown.

---

## 2. Actual Production Architecture

```
run_vector.py (mode="loop", DEFAULT — run_vector.py:491)
  └─ run_loop() → bootstrap_agents() → AutonomousLoop().run_forever()
       └─ 21 supervised coroutines (autonomous_loop.py:2462-2484), each independently
          restart-on-crash via _supervised() (line 2490)
          ├─ think_loop        (10s cycle)   → _think_tick() → decision_engine → _act_on()
          ├─ reflect_loop      (2AM daily)   → epistemic decay, correction expiry, consolidation
          ├─ hypothesis_loop   (4h cycle)    → HypothesisEngine → memory + SuggestionQueue
          ├─ anticipation_loop (10min cycle) → AnticipationEngine → _act_on() as Candidate
          ├─ scheduler_loop    (30s poll)    → APScheduler (real callable jobs: cron_jobs.py)
          ├─ observe_loop, sense_loop, sync_loop, obsidian_loop, phone_loop, vectorcode_loop,
          │   ambient_scheduler, predict_cycle, degradation_monitor, wearable_poll_cycle,
          │   health_analysis_cycle, emergency_detection_cycle, research_loop,
          │   state_checkpoint_loop, command_poll_loop, growth_loop
          └─ (all of the above run with zero user message required)
```

Two other launch modes exist: `run_vector.py api` (FastAPI server, `VECTOR_API_RUN_LOOP=1` set by
default so the loop runs alongside the API — `run_vector.py:534`) and `run_vector.py smoke/doctor/
production-check/memory-repair` (one-shot diagnostics, not long-running).

**District/agent participation**: `Governor.dispatch(task)` (called from `autonomous_loop.py:1215`
as the default fallthrough for `_act_on()`, and independently from ~10 other entry points — API
routers, voice, websocket, hands) resolves an agent by capability/HP and calls `agent.run(task)`
(`governor.py:2311`). The return value flows back to whichever caller invoked `dispatch()`; on the
`autonomous_loop` path it feeds the full outcome pipeline (§6).

---

## 3. End-to-End Autonomous Call Graph

```
think_loop (every 10s, autonomous_loop.py:735)
  → _think_tick() (line 750)
      → world_state = context_engine.get_world_state()          [line 814]
      → context_engine.track_beliefs(world_state)                [line 822] — writes belief:* claims
      → goals = goal_system.generate_immediate_actions(limit=4)   [line 828]
      → candidates built from goals via _TAG_TO_ACTION map        [lines 833-878]
      → plan_candidates = self._get_plan_candidates()             [line 882] — from active plans.py plans
      → candidates.extend(plan_candidates)                        [line 884]
      → decision = decision_engine.evaluate(candidates)            [line 901]
           → for each candidate: _score_candidate()                [decision_engine.py:373]
                → 5-factor formula: goal(30%)+conf(25%)+policy(20%)+urgency(15%)+timing(10%)-cost(5%)
                → policy.get_score() consulted                     [decision_engine.py:379]
                → _epistemic_penalty() consulted                   [decision_engine.py:404] — reads action_domain:* claims ONLY
                → ReasoningBank injection into reasoning_steps      [decision_engine.py:465-474] — written but never read by the score formula
      → if decision.winner.total_score > 0.3:                     [line 902]
           → ContinueGate.evaluate() — pause/stop/throttle check   [lines 904-925]
           → EventType.DECISION_MADE published                     [line 927]
           → _act_on(decision.winner)                               [line 938]
                → if action_type.startswith("proactive_"):  gw.execute() [line 976] ── GATED
                → elif source.startswith("plan:"):  _act_on_plan_step()  [line 992] ── GATED (via PlanRunner)
                → elif action_type in _VC_ACTION_TYPES (5 types):  gw.classify()/gw.execute() [lines 1003-1018] ── GATED
                → elif skill-matched:  gw.classify()/gw.execute() [lines 1177-1194] ── GATED
                → else:  governor.dispatch(task)                    [line 1215] ── NOT GATED (see §9, §12)
                     → agent.run(task)                               [governor.py:2311]
                     → result returned to _act_on()
                → reward computed (5-factor)                        [lines 1229-1241]
                → PolicyMemory.update_from_outcome()                 [line 1246]
                → decision_engine.record_epistemic_belief()          [line 1252] — writes action_domain:* claims
                → decision_engine.record_outcome() (neural RL)       [line 1263]
                → goal progress updated                              [lines 1269-1286]
                → CausalGraph.add_edge()                             [line 1298]
                → EpisodicMemory.store_chain()                       [line 1309] — write-only, no production reader
                → DataCollector().record()                           [line 1320]
```

This is one continuous, traceable chain from a 10-second timer tick to a real side-effecting action
and back into five different memory/learning systems, with zero required user input at any step.

---

## 4. Cognitive Subsystem Status Matrix

| Subsystem | Status | Evidence |
|---|---|---|
| `think_loop` main cycle | **S5** | `autonomous_loop.py:735-748`; 10s interval, 60s timeout, full exception isolation; direct trace §3 |
| `context_engine.get_world_state()` | **S5** | Called every tick (`autonomous_loop.py:814`); output consumed by `track_beliefs()` and scoring context |
| `goal_system.generate_immediate_actions()` | **S5** | Called every tick (`:828`); output directly becomes candidates |
| `decision_engine.evaluate()` | **S5** | Called every tick (`:901`); winner directly drives `_act_on()`; `tests/unit/test_decision_engine.py` exists |
| `hypothesis_engine` | **S1 — implemented, scheduled, but never actually executes** | Registered supervised coroutine (`:2472`), real 4h cycle, BUT `hypothesis_loop()` calls the `async def generate_hypotheses()` (`hypothesis_engine.py:48`) without `await` (`autonomous_loop.py:2868`) — the coroutine object is never run, the LLM call inside it never fires, and the loop always takes the "low-confidence, suppressed" branch every single cycle. The initial tool-execution-fork report classified this S5 based on reading the surrounding write-to-memory code without noticing the missing `await`; corrected after direct verification this pass (§1 finding #1) |
| `synthesis_bridge` | **S2** (per phase_status.md claim; not independently re-verified this pass — grep confirms import exists, not re-traced in depth) | Not a focus area re-audited this pass |
| Anticipation engine | **S5** | `anticipation_loop` (`:2989`) → `_anticipation_tick` (`:3009`) → `_act_on(candidate)` (`:3030`); confirmed by tool-execution fork |
| Epistemic tracker — `action_domain:*` (outcome loop) | **S5** | `_epistemic_penalty()` read (`decision_engine.py:404`) + `record_epistemic_belief()` write (`autonomous_loop.py:1252,1482`); `test_epistemic_changes_winner` proves decision output changes |
| Epistemic tracker — `belief:*` (formation loop) | **S3, disconnected from S5 territory** | Written every tick (`context_engine.py:180,210,233`, called from `autonomous_loop.py:822`) but read by nothing that scores a decision — see §7 |
| Goal system | **S5** | Persisted (SQLite via episodic memory infra), read every tick, drives candidates; `PRESEEDED_GOALS` bypass `add_goal()` at boot |
| Episodic memory | **S5** | Write (`autonomous_loop.py:791` +many) → read (`:1386`) → directly feeds reward formula (`:1222-1241`) |
| Semantic/knowledge memory | **S3** | Table inside `episodic.py` (not a separate module); read/write confirmed, no production read-then-decide site found |
| Reasoning memory (`reasoning_chains` table) | **S2 (write-only)** | Write `autonomous_loop.py:1309`; zero production readers (memory-audit fork) |
| ReasoningBank (`vectorcode/src/reasoning_bank.py`) | **S2 (decorative)** | Injected into `candidate.reasoning_steps` (`decision_engine.py:472`) but that field is never read by `total_score`; explicit docstring admission at `decision_engine.py:454` |
| Ghost memory | **S3** | Write/inherit real (`agent_registry.py:113-172`) but sole consumer `get_system_prompt()` has zero production callers (memory-audit fork) |
| CounterfactualMemory | **S5** | `should_avoid()` gates `_act_on()` (`:446,1086`) with real block+penalty+rejection recording (memory-audit fork) |
| PolicyMemory | **S5** | `get_score()` before every score (`decision_engine.py:379`), `update_from_outcome()` after every outcome (4 real call sites) |
| Memory consolidation | **S3** | `ConsolidationBot.run_forever()` confirmed dead by the codebase's own inline comment; superseded by direct calls from `reflect_loop` |
| Persistence/recovery (episodic DB) | **S4** | SQLCipher + WAL + quarantine/repair; self-test passes |
| Owner-correction learning | **S2** | Capture (voice-only) → store → retrieve → **prompt-injection only**; `validate_lesson()` has zero production callers (owner-correction fork) |
| `Governor.dispatch()` | **S5** | Real caller in `_act_on` fallthrough + ~10 other entry points; `agent.run()` return value flows to outcome pipeline |
| `route_policy.decide_route()` | **S5** | Called from `provider_client.py:333`, `vectorcode_llm.py:633,794`; sensitivity gate is real code, not just docstring |
| `permission_gateway` | **S3 (partial coverage, not universal)** | Real, tested mechanism, but only reached on 3-4 of the action paths out of `_act_on()`; `governor.dispatch()` itself never calls it (governance fork, corroborated 2x) |
| Trust ladder | **S4** | Real module, wired into `permission_gateway.py:449-478`, dedicated test file exists |
| `red_team_agent.attack_plan()` | **S3 (narrow)** | Only called from one site (`autonomous_loop.py:1132`), gated to `CONFIG["permission"]["red"]` types; `permission_gateway`'s own RED branch does not call it |
| Sandbox (`execute_code`) | **S4** | Real routing to `core.sandbox.get_sandbox()`, fail-closed on exception |
| `MissionRunner`/`core/runtime/missions.py` | **S1** | Fully implemented, zero autonomous callers — reachable only via HTTP API (autonomy fork) |
| `PlanRunner`/`core/runtime/plans.py` (creation) | **S1** | Only triggered via `goal_system.add_goal()`, whose only production caller is an HTTP endpoint (autonomy fork) |
| `PlanRunner`/`core/runtime/plans.py` (execution) | **S4, with a confirmed crash-recovery defect** | Runs autonomously every think-tick once a plan exists; real DAG, real replanning; restart-recovery works ONLY for cleanly-completed steps — a step crashed mid-execution (status stuck at `"running"`) is never reset and permanently stalls that plan branch (`plans.py:212,689-691`, confirmed by direct read this pass, §1 finding #2); the existing "resume after restart" test only covers the clean-completion case; 9/9 existing tests pass live (autonomy fork) but none of them exercise the crash-mid-step scenario |
| Scheduler/cron infrastructure | **S3** | Real APScheduler, real boot-path registration; one traced payload (`morning_digest`) is a stub, another (`nightly_selfcheck`) does real work — infra is real, payload quality varies per job (autonomy fork) |
| `chief_of_staff.run_forever()` (deterministic clock) | **S1** | Implemented, never called anywhere (autonomy + tool-execution forks, independently confirmed) |
| `chief_of_staff` capability (via other paths) | **S3** | Reachable via API endpoint and via `anticipation_loop`'s predictions |
| `BehavioralNudgeEngine` | **S2** | Standard district agent, reachable only via generic `governor.dispatch()`, no dedicated scheduler |
| Inference observability layer | **S5** | Verified in prior session pass — 184/184 tests, 0.042ms/call overhead; not re-audited this pass per task instructions |

---

## 5. Memory Flow

```
WRITE SIDE                              READ SIDE                         INFLUENCES BEHAVIOR?
─────────────────────────────────────────────────────────────────────────────────────────────
EpisodicMemory.store()          →  EpisodicMemory.recall()/            YES — feeds reward formula
  (autonomous_loop.py: many)        _get_recent_feedback()                (autonomous_loop.py:1222-1241)

PolicyMemory.update_from_outcome() → PolicyMemory.get_score()          YES — direct scoring input
  (4 real call sites)                (decision_engine.py:379)

CounterfactualMemory.record_       → CounterfactualMemory.             YES — blocks re-proposal,
  rejection()                        should_avoid()                       penalizes policy score
  (autonomous_loop.py:1092-1106)     (autonomous_loop.py:446,1086)

EpistemicTracker.update_belief()   → EpistemicTracker.get_belief()     YES, but only within the
  claim="action_domain:X"            claim="action_domain:X"              SAME keyspace (§7)
  (decision_engine.py:330,           (decision_engine.py:291)
   via record_epistemic_belief)

EpistemicTracker.update_belief()   → nothing reads claim="belief:*"    NO — disconnected keyspace
  claim="belief:presence:X" etc.     for decision purposes (only          (§7)
  (context_engine.py:180,210,233)    read-only /epistemic/summary
                                      API introspection)

ReasoningMemory.store_chain()      → get_training_data()/get_recent()  NO — zero production readers
  (autonomous_loop.py:1309)          have zero production callers         (write-only log)

Ghost memory (agent_registry.py)   → AgentBase.get_system_prompt()     NO — consumer has zero
  113-172, real inherit at            (agent_base.py:294-322)             production callers
  agent_base.py:261-264

CorrectionLearner._store_lesson()  → context_engine._correction_       PARTIAL — reaches an LLM
  (voice-triggered only)             lessons_line() → session_             prompt as text, never
                                      hydration_prompt()                   a deterministic decision
```

---

## 6. Planning/Execution Flow

**Autonomous, per-tick decision path (goal-driven)**: real, closed, S5 (§3).

**Multi-step plan path** (`core/runtime/plans.py`): plan **creation** is gated behind
`goal_system.add_goal()`, whose only production caller is an HTTP endpoint
(`core/api/routers/brain.py`) — S1 for creation. Once a plan exists, **execution** is fully
autonomous — `autonomous_loop._get_plan_candidates()` (called every think-tick) reads
`PlanStore.active_plans()`, offers ready steps as `Candidate(source="plan:...")` objects that
compete in the normal decision engine, and `_act_on_plan_step()` executes via `PlanRunner` — S4,
test-verified including restart survival (`tests/integration/test_planning_integration.py`,
`TestPlanSurvivesRestart`, 9/9 passing live).

Real DAG dependency tracking (`Plan.next_ready_steps()`, `has_circular_deps()` via Kahn's
algorithm), real 3-tier replanning (fallback → LLM-restructure → abandon, capped at
`MAX_REPLANS=2`), and real atomic-write persistence to `data/plans/plans.json`. **One confirmed
MUST-FIX gap (§1 finding #2, elevated from an initial "safe to defer" assessment after direct
verification)**: no crash-mid-step recovery. `PlanRunner.execute_step()` writes
`step.status = "running"` to disk (`plans.py:689-691`) BEFORE calling the executor; if the process
dies between that write and the step's eventual completion/failure write, `next_ready_steps()`
(`plans.py:212`) permanently excludes that step (only `status == "planned"` is offered) and
nothing anywhere resets `"running"` back to `"planned"` on the next boot. The plan does not error
or fail — it silently stops making progress on that branch, indefinitely, with no log signal
distinguishing "stalled" from "still working." Over a 7-day continuous run, at least one process
restart (crash, OOM, host reboot, manual intervention) is a realistic occurrence, not a rare edge
case — this makes any long-horizon-plan-completion measurement from the experiment unreliable
until fixed.

**Mission path** (`core/runtime/missions.py`, `MissionRunner`): S1 — fully implemented,
zero autonomous callers, reachable only via 6 HTTP endpoints in `core/api/routers/missions.py`.

---

## 7. Epistemic Flow — Special Audit

**A. Where is epistemic information created?**
Two independent creation points, writing to two disjoint SQLite claim-ID namespaces in the same
`EpistemicTracker` table:
- Formation-point: `context_engine.track_beliefs(world_state)`, called every think-tick
  (`autonomous_loop.py:822`), writes claims prefixed `belief:presence:*`,
  `belief:screen_activity:*`, `belief:memory:health`, `belief:kiit_attendance:current`,
  `belief:goals:active_progress` (`context_engine.py:180,193,210,224,233`).
- Outcome-point: `decision_engine.record_epistemic_belief()`, called after every action outcome
  (`autonomous_loop.py:1252,1482`), writes claims prefixed `action_domain:{domain}`
  (`decision_engine.py:330`).

**B. Where is it stored?**
Both write to the same `EpistemicTracker` SQLite table (`core/brain/epistemic_tracker.py`,
`claims` table) — same database, same schema, different string prefixes as the only namespace
separation.

**C. Where is it consumed?**
- `action_domain:*` claims are read by `decision_engine._epistemic_penalty()`
  (`decision_engine.py:291`), called from `_score_candidate()` (`:404`) on every candidate,
  every tick.
- `belief:*` claims are read by nothing that participates in decision-making. The only
  confirmed reader is a read-only introspection API (`core/api/routers/brain.py:171-195`,
  `/epistemic/summary` and `/epistemic/staleness`) that returns the full knowledge summary
  regardless of prefix — a monitoring endpoint, not a decision consumer.
- A third, independent bare-`action_type` keyspace exists in `core/runtime/plans.py:431`
  (`tracker.get_confidence(step.action_type)`, no prefix at all) for the `confidence_threshold`
  plan-step verification type. Since nothing writes claims with a bare action_type as the ID,
  `get_confidence()` always returns its documented "unknown" default of `0.0`
  (`epistemic_tracker.py:209-214`), making this verification type structurally unable to pass for
  any `min_confidence > 0`. **This is currently dead code in practice**: grepping the codebase for
  `"type": "confidence_threshold"` (or the single-quote equivalent) as a constructed
  `PlanStep.verification` value returns zero matches — every actual plan step uses `status_check`
  or `always` instead (`plans.py:66,517-518,860,864`). The bug is real but currently unreachable.

**D. Does autonomous_loop actually call it?**
Yes, on both write sides — `track_beliefs()` every tick (`:822`) and `record_epistemic_belief()`
after every outcome (`:1252,1482`) — and on the one real read side, indirectly, via
`decision_engine.evaluate()` → `_score_candidate()` → `_epistemic_penalty()` every tick.

**E. Does later behavior change based on it?**
Yes, for the `action_domain:*` loop only. `tests/unit/test_epistemic_scoring.py::
TestEvaluateWithEpistemic::test_epistemic_changes_winner` demonstrates two otherwise-identical
candidates producing different winners purely because one domain has a stale epistemic belief and
the other doesn't. This is real, deterministic, decision-level behavior change — not just an LLM
prompt hint.

For the `belief:*` formation loop, no. Nothing downstream of `track_beliefs()` consults those
claims for anything other than the `/epistemic/summary` monitoring endpoint. A belief that "the
owner is present" or "the screen shows active coding" is recorded but never used to weight, gate,
or otherwise change what action gets chosen next.

**F. What tests prove this?**
`tests/unit/test_epistemic_scoring.py` (38 tests, pre-existing) proves the `action_domain:*`
outcome→penalty loop end-to-end, including the winner-changes test above.
`tests/unit/test_epistemic_integration.py` (27 tests, added earlier this session) proves
`track_beliefs()` correctly writes `belief:*` claims and that they persist across restart — but
every test in that file operates purely within the formation side; none of them assert that a
`belief:*` claim changes a `_score_candidate()` output, because it structurally cannot.

**Verdict**: Gap 3 (epistemic tracker) is **integrated for the outcome→confidence→next-decision
loop** (this is the loop the original Gap 3 spec most plausibly intended — "does VECTOR get more
cautious about a domain after repeated failures" — and it works). It is **not integrated** for the
"raw sense data → semantic belief → decision input" direction that the earlier session's
integration report described as the goal ("INFORMATION → BELIEF" happening at the formation
point). The formation-side work from earlier this session is real, tested, and persists
correctly — it simply writes to a namespace nothing consults for scoring.

**Smallest integration point, if this were to be closed** (not implemented — audit only): either
(a) have `_score_candidate()` additionally check `belief:{relevant_type}:*` claims matching the
candidate's context, or (b) have `track_beliefs()` also emit an `action_domain:{domain}` claim
when a formed belief is strong enough to be actionable (e.g., a `belief:presence:absent` claim
could inform an `action_domain:proactive` penalty). Both are non-trivial design decisions, not
one-line fixes — correctly out of scope for this audit-only pass.

---

## 8. Owner-Correction Learning Flow — Special Audit

Full trace (from the owner-correction audit fork, cross-checked): **CAPTURE** is real but narrow —
`AutonomousLoop._handle_user_input()` (`:1523`) → `_detect_and_store_correction()` (`:1546`) →
`CorrectionLearner.process_owner_message()` (`correction_learner.py:418`), gated on
`person_id == "owner"`. `_handle_user_input()` has exactly one production caller
(`autonomous_loop.py:802`), inside the **voice-intent dispatch path only**. Web chat, terminal
chat, and direct governor-dispatch never trigger capture.

**STORAGE**: real, `EpisodicMemory.store(event_type="correction_lesson", ...)`
(`correction_learner.py:452`) with structured fields (situation, wrong_behavior, correction,
lesson, domain, confidence, validation_status, times_applied, times_validated).

**ASSOCIATION**: keyword/domain-tag matching via `EpisodicMemory.recall()`, not fuzzy similarity;
a SHA256 `situation_hash` is used only for exact-duplicate detection.

**RETRIEVAL**: real — `context_engine._correction_lessons_line()` (`:276`) calls
`CorrectionLearner().build_injection_line()` (`:283-288`), invoked from
`session_hydration_prompt()` (`:386-391`), which RULE 1 requires before every LLM call.

**INFLUENCE ON DECISION**: **prompt-injection only.** Zero references to `CorrectionLearner` or
`correction_learner` exist in `decision_engine.py` or `policy.py`. The lesson text is inserted as
plain English into the LLM system-prompt context — architecturally identical to "hoping an LLM's
free-text generation honors a hint in its context," not a scored input to any deterministic
decision.

**OUTCOME RECORDING**: `validate_lesson(lesson_id, outcome_good)` exists and correctly adjusts
confidence (+0.05/-0.10) and validation_status (`correction_learner.py:591-627`) — but has **zero
production callers** anywhere in the codebase. Nothing links a real action's actual outcome back
to whichever correction lesson was in that decision's context.

**CONFIDENCE UPDATE**: two live, but non-outcome-driven, paths — exact-duplicate re-detection
bumps confidence +0.05 (only fires if the owner repeats the same correction verbatim), and
`expire_old_lessons()` marks >90-day unvalidated lessons `expired`, called from the 2AM reflect
cycle (`autonomous_loop.py:1738-1740`, confirmed real).

**Verdict**: this is a **data-storage-and-prompt-injection capability**, not a closed behavioral
learning loop. The capture→store→retrieve→inject chain is real and runtime-reachable, restricted
to the voice-command path. The outcome-feedback half that would make it a true learning loop
(`validate_lesson()`) is fully implemented but never called in production.

---

## 9. Governance/Safety Flow

```
Action-execution entry points into permission_gateway (ALL confirmed, not assumed):
  1. autonomous_loop._act_on(): proactive_* actions          → gw.execute()          GATED
  2. autonomous_loop._act_on(): plan steps (source="plan:")   → PlanRunner→gateway    GATED
  3. autonomous_loop._act_on(): _VC_ACTION_TYPES (5 types)    → gw.classify/execute   GATED
  4. autonomous_loop._act_on(): skill-matched actions         → gw.classify/execute   GATED
  5. Remote-device / structured-command path (:2110-2120)     → gw.execute()          GATED
  6. autonomous_loop._act_on(): everything else (the default
     fallthrough) → governor.dispatch(task) → agent.run()                            NOT GATED

Governor.dispatch() itself: zero references to PermissionGateway/gw.execute/gw.classify in
governor.py (grep-confirmed by two independent forks + this document's author). It does run
taint-tracking (governor.py:2024) and a narrow prompt-injection scan (governor.py:2082,
hardcoded to shell/net-fetch substrings) — real, but not equivalent to the GREEN/YELLOW/RED gate.

permission_gateway._execute_action() is a SEPARATE, parallel execution surface with its own
hardcoded action-type handlers (search_web, commit_code, push_github, execute_code→sandbox,
run_shell_command, etc., lines 894-1370) — it calls Governor().dispatch() itself only for
hand_* action types and send_message_routine, i.e. the two systems overlap only partially.
```

**Red-team coverage**: `red_team_agent.attack_plan()` is called from exactly one site
(`autonomous_loop.py:1132`), gated to `CONFIG["permission"]["red"]` action types on that one path
only. `permission_gateway`'s own RED branch (reached by the remote-command path or any direct
`gw.execute()` caller) does **not** invoke `attack_plan()` — the "✅ WIRED" claim in
`phase_status.md` is accurate only for the `autonomous_loop`-originated action path, not
universally for every RED action reaching the gateway.

**Route policy / sensitivity gate**: real, S5 — `decide_route()` is called from both
`provider_client.py:333` and `vectorcode_llm.py:633,794`; the `sensitive`/`local_only` gating logic
is real code (`route_policy.py:99-112`), not just a docstring claim.

**Trust ladder**: real, S4 — wired into `permission_gateway.py:449-478`
(`is_promoted`/`record_auto_exec`/`record_approval`/`record_rejection`/`record_bad_outcome`), has
a dedicated passing test file.

**Sandbox**: real, S4 — `execute_code` routes to `core.sandbox.get_sandbox()`, fail-closed on
exception.

**Severity assessment**: this is the audit's single most consequential finding. It does not mean
VECTOR is unsafe in the sense of "any random autonomous action can do anything unchecked" —
`governor.dispatch()` still routes through a district agent's own `.run()` method, and most
district agents' internal logic is scoped to read-only or narrow operations. But it does mean the
GREEN/YELLOW/RED classification and owner-approval-for-YELLOW/RED mechanism, which the project's
own `CLAUDE.md` states as a non-negotiable rule ("Permission Gateway is the ONLY path to
real-world actions... Nothing bypasses this"), is not actually enforced on the majority of the
autonomous loop's action-dispatch traffic today.

---

## 10. Tool Execution Flow

One complete real path, traced with line numbers (also see §3, §9):

```
decision_engine.evaluate() picks a winner
  → _act_on(winner)
  → (for the 4 gated buckets) permission_gateway.execute()/classify() — real GREEN/YELLOW/RED check
  → (for everything else) governor.dispatch(task) — NO permission check
  → agent.run(task)  [worked example: districts/coding/code_reviewer.py:365
     CodeReviewer.run() reads task params, calls review_with_llm() (real LLM call + file read),
     returns {"status": "ok", **result}]
  → result flows back through governor.dispatch()'s return value
  → _act_on() computes reward from result (lines 1229-1241)
  → PolicyMemory.update_from_outcome(), decision_engine.record_epistemic_belief(),
    decision_engine.record_outcome() (neural RL), goal progress update, CausalGraph.add_edge(),
    EpisodicMemory.store_chain(), DataCollector().record()  — all real, all called with the
    actual result, not discarded
```

**Where the chain breaks, if it breaks**: not in the outcome→memory direction (that part is fully
closed and real for every action, gated or not). It breaks at the permission-gate step for the
majority of action types, as detailed in §9 — the tool executes and its result IS captured by
learning systems, but the pre-execution safety check that RULE 3 promises is absent on that path.

---

## 11. Autonomous/Background Entry Points

| Entry point | Trigger | Classification |
|---|---|---|
| `think_loop` | Internal 10s timer, started at process boot | BACKGROUND-AUTONOMOUS |
| `reflect_loop` | Internal clock, fires at 2:00 AM daily | SCHEDULED |
| `hypothesis_loop` | Internal timer, fires every 4h — SCHEDULED, but its LLM call is never awaited (§1 #1) so it produces nothing every cycle | SCHEDULED (broken payload) |
| `anticipation_loop` | Internal timer, fires every 10min | SCHEDULED, feeds into `_act_on()` as REACTIVE-to-prediction |
| `scheduler_loop` (APScheduler jobs, e.g. `nightly_selfcheck`) | Cron expressions registered at boot | SCHEDULED |
| Plan-step execution (`plans.py` consumption side) | Fires every think-tick once a plan exists | BACKGROUND-AUTONOMOUS (once created) |
| Voice-intent dispatch | Owner speaks a command | REACTIVE, USER-TRIGGERED |
| Web chat / terminal chat / API endpoints | Explicit HTTP request or typed command | USER-TRIGGERED |
| Plan **creation** (`goal_system.add_goal()`) | Only reachable via HTTP endpoint | USER-TRIGGERED (despite being the seed for later autonomous execution) |
| `MissionRunner` | Only reachable via HTTP endpoint | USER-TRIGGERED |
| Proactive nudges (`_act_on` `proactive_*` branch) | Fired by `anticipation_loop`'s predictions | PROACTIVE, genuinely autonomous origin |

**Can VECTOR start meaningful work without a user message?** Yes, unambiguously. `think_loop`
alone, running unattended, evaluates goals and executes gated or ungated actions every 10
seconds — confirmed by direct trace, not inferred from the scheduler's existence. `anticipation_loop`
adds genuinely proactive need-prediction on top of that, feeding real candidates into the same
decision→action pipeline. `hypothesis_loop` was intended to add the same for proactive
insight-generation, but does not currently do so — see §1 finding #1; it fires on schedule but its
payload is inert. This distinguishes VECTOR from a system where "autonomy" means only "a scheduler
exists" — the scheduler here drives real cognition (goal evaluation, epistemic-weighted decision
scoring, memory-informed reward) for `think_loop` and `anticipation_loop`, though not currently for
`hypothesis_loop`.

---

## 12. Broken/Orphaned Links (consolidated from all sub-audits)

**The two most severe findings, listed first (both MUST FIX, §16):**

0a. **`hypothesis_loop()` calls an `async def` method without `await`** — `generate_hypotheses()`
   (`hypothesis_engine.py:48`) is called as `engine.generate_hypotheses(context)` with no `await`
   at `autonomous_loop.py:2868`. The returned (never-run) coroutine object is truthy, so the code
   proceeds through checks designed for a real hypothesis list/dict, ending in
   `confidence = 0.0` every cycle — the underlying LLM call never executes, and nothing is ever
   written to memory. Silently broken since written; the only test touching this path does
   source-string matching, never execution. (§1 #1, direct verification)

0b. **Plan steps crashed mid-execution are never recovered on restart** — `PlanRunner.execute_step()`
   persists `status="running"` before execution (`plans.py:689-691`); `next_ready_steps()`
   (`plans.py:212`) only offers `status=="planned"` steps and nothing resets a stuck `"running"`
   step back to `"planned"` on boot. A process restart mid-step permanently and silently stalls
   that plan branch. Over a 7-day unattended run this is a realistic occurrence, not an edge case.
   (§1 #2, direct verification)

**Remaining findings, by subsystem:**

1. **`Governor.dispatch()` bypasses `permission_gateway`** for its default action path — the
   majority of autonomous-loop-driven and API/voice-driven action dispatch. (§9, cross-confirmed
   3x independently)
2. **`belief:*` epistemic claims are formed every tick but never consulted for scoring** — disjoint
   keyspace from what `_epistemic_penalty()` reads. (§7)
3. **`plans.py`'s `confidence_threshold` verification type is structurally dead** (always evaluates
   `0.0 >= min_conf`) — currently unreachable since no plan step uses this verification type in
   practice, but latent. (§7)
4. **Owner-correction lessons never close the loop back to outcome** — `validate_lesson()` exists,
   works in isolation, zero production callers. (§8)
5. **Owner-correction capture only fires on the voice-intent path** — web/terminal/API corrections
   are never captured at all. (§8)
6. **`reasoning_chains` table (`ReasoningMemory`/`store_chain`) is write-only** — no production
   reader anywhere; it is a training-data log, not a consulted memory. (§5, memory-audit fork)
7. **RULE 8's `ReasoningBank` injection is decorative** — `inject_past_reasoning()`'s output is
   assigned to `candidate.reasoning_steps`, which is never read when computing `total_score`; the
   `decision_engine.py:454` comment explicitly admits context injection "does NOT change the score
   formula itself." (§3, memory-audit fork)
8. **Ghost memory is inherited but never rendered** — `AgentBase.get_system_prompt()`, the sole
   consumer of inherited `self.lessons`/`self.best_decisions`, has zero production callers (only a
   test file calls it). (§5, memory-audit fork)
9. **`ConsolidationBot.run_forever()` is permanently dead code** — the codebase's own inline
   comment at `autonomous_loop.py:1760-1773` documents that this was found broken and fixed by
   calling the bot's component methods directly from `reflect_loop` instead. The class-level
   `run_forever()` entry point remains a misleading, unreachable interface for anyone reading
   `consolidation_bot.py` in isolation, even though the underlying consolidation work IS happening
   via the alternate path.
10. **`chief_of_staff.run_forever()`'s documented 08:00/22:00 clock trigger never fires** — never
    called anywhere in the codebase (confirmed independently by 2 forks). The capability itself
    (morning/evening brief) IS reachable via an HTTP endpoint and via `anticipation_loop`'s
    probabilistic predictions, but not on its own documented schedule.
11. **`MissionRunner`/`missions.py` and plan-`creation` (`add_goal()`) are both S1** — implemented,
    zero autonomous callers, reachable only via HTTP endpoints. Once a plan exists it executes
    fully autonomously (§6), but nothing autonomous currently creates one.
12. **`morning_digest` cron job (`cron_jobs.py:185-187`) is a permanent stub** — the scheduler
    infrastructure that fires it is real and autonomous (confirmed against a second, genuinely
    working job, `nightly_selfcheck`), but this specific payload always returns
    `{"status":"skipped","reason":"vc_districts module not available"}`.
13. **No crash-mid-step recovery for plan execution** — a step that crashes between "started" and
    "completed" persists as `"running"` forever; nothing re-arms it to `"planned"` on restart. (§6)

---

## 13. Duplicate/Competing Systems

- **`GoalSystem` candidate generation** (tag-mapped, `_TAG_TO_ACTION`) and **`plans.py` plan-step
  candidate generation** (`_get_plan_candidates()`) are two independent candidate sources merged
  into one list before scoring (`autonomous_loop.py:858-887`) — not competing/duplicate logic, a
  deliberate merge point. Not a defect.
- **`permission_gateway._execute_action()`** (its own hardcoded action-type dispatch table) and
  **`Governor.dispatch()`** (agent-capability-based routing) are two separate execution surfaces
  that only partially overlap (governance-audit fork, §9). This is architecturally closer to two
  competing implementations of "route an action to code that executes it" than a clean layering —
  worth noting as a design-clarity issue, though not by itself unsafe.
- **Two "reasoning memory" systems share conceptual territory but are entirely separate objects**:
  `core/memory/reasoning_memory.py`'s `ReasoningMemory`/`store_chain()` (write-only training-data
  log) and `vectorcode/src/reasoning_bank.py`'s `ReasoningBank` (decorative RULE 8 injection). They
  do not share storage, do not call each other, and neither meaningfully feeds back into scoring.
- **Two epistemic-tracker keyspaces plus a third dead one** — see §7. Not separate implementations
  of `EpistemicTracker` (there's only one class), but three logically-disjoint uses of it that
  don't communicate.

---

## 14. Dynamic Runtime Paths

Verified at the code level (not executed live in this audit pass, per the audit-only constraint —
no process was started):

- `run_vector.py` with no arguments → `mode="loop"` (default) → `run_loop()` → `bootstrap_agents()`
  → `AutonomousLoop().run_forever()` → 21 supervised coroutines start concurrently via
  `asyncio.gather(*(self._supervised(name, fn) for name, fn in loops), return_exceptions=True)`
  (`autonomous_loop.py:2485-2488`).
- Each coroutine's own `try/except` inside its `while self._running:` loop, PLUS the outer
  `_supervised()` wrapper's restart-with-exponential-backoff (capped at 5 minutes), together
  implement RULE 2 ("autonomous loop must never die") as two independent layers of defense — an
  exception escaping a coroutine's own guards restarts just that one coroutine, not the whole
  process.
- `think_loop` additionally wraps each tick in `asyncio.timeout(60)` (`:740`) so a hung LLM call or
  blocking OCR call cannot stall the 10-second cadence indefinitely — it degrades to "skip this
  tick" instead.

---

## 15. Evidence Summary for S0-S5 Classifications

The evidence standard applied throughout this document: S3 requires a real, live code path from a
process-boot-reachable entry point (not a test harness, not a design doc) to the component in
question, traced by reading the actual calling code, not by finding the component's own docstring
claim. S4 additionally requires an existing test that exercises that path. S5 additionally
requires evidence — a test assertion or a directly-traced return-value chain — that a later,
observably different outcome results from the component having run, not merely that it ran without
error. Every S3+ classification in §4 cites the specific file:line of the real caller; every S5
classification additionally cites either a test name or the specific downstream line where the
component's output changes program behavior.

---

## 16. Experiment Blockers (MUST FIX)

Applying this document's own stated rule ("A component should only be classified as MUST FIX if
its absence prevents the experiment from measuring a meaningful VECTOR capability or creates a
serious safety/integrity problem"), two findings meet the bar:

**A. `hypothesis_loop()`'s missing `await` (§1 #1, §12 0a).** Proactive hypothesis generation is
one of the small number of genuinely-autonomous proactivity mechanisms VECTOR has (alongside
`anticipation_loop`). If the 7-day experiment is meant to measure or showcase proactive cognitive
behavior over an extended unattended run, this mechanism currently contributes zero data, silently
— not "VECTOR generated no notable hypotheses," but "the code path that would generate them never
ran." Running the experiment without fixing this either produces a false negative on a capability
the experiment is presumably meant to observe, or requires post-hoc explaining why hypothesis data
is entirely absent. The fix is a single added `await` keyword — this is a one-line change, not an
architectural intervention, and does not require redesigning anything.

**B. Plan-step crash-mid-execution recovery (§1 #2, §12 0b).** A 7-day continuous unattended run
makes at least one process interruption (crash, OOM, host reboot, manual restart for maintenance)
a realistic expectation rather than a hypothetical. If that interruption happens to land while a
plan step is executing, the plan silently and permanently stalls on that branch for the remainder
of the 7 days with no error signal distinguishing "stuck" from "still working." Any experiment
measurement of long-horizon plan completion rate, or of VECTOR's resilience to interruption
specifically, would be corrupted by this — either an accurate-but-misleadingly-low completion
number with no visible cause, or (if no restart happens to occur during the 7 days) a false
confidence that the gap doesn't matter, purely by luck of timing. The fix is narrow: on boot, scan
persisted plans for steps with `status == "running"` and reset them to `"planned"` (with
appropriate idempotency/logging so a step that actually did complete just before the crash isn't
silently re-run if that's a concern) — not an architectural redesign.

**Both fixes are small, well-localized, and were explicitly NOT implemented in this audit-only
pass** — see §18 for the precise recommended change location for each.

The permission-gateway coverage gap (§9) was also considered against this bar and does **not**
qualify as MUST FIX: it is a pre-existing condition of the current architecture (not something the
experiment would newly introduce), the experiment is a controlled measurement exercise (not a
production deployment to untrusted users), and district agents' own internal scope already limits
blast radius on the ungated path. It remains SHOULD FIX (§17), with an explicit caveat about what
the experiment should NOT claim to measure as a result.

---

## 17. Non-Blocking Issues (SHOULD FIX / SAFE TO DEFER / NOT A REAL PROBLEM)

**SHOULD FIX BEFORE 7-DAY EXPERIMENT:**
- Closing the `Governor.dispatch()` → `permission_gateway` gap (§9, §12.1) would materially
  strengthen any safety claims made about the experiment's results, and should be the next
  priority after the two MUST-FIX items (§16) whenever fixes are undertaken (a separate task from
  this audit).

**SAFE TO DEFER:**
- `belief:*`/`action_domain:*` epistemic keyspace unification (§7, §12.2) — closing this would
  make Gap 3 fully match its original design intent, but the experiment can still measure the
  `action_domain:*` outcome-learning loop, which is real and closed.
- Owner-correction outcome-feedback loop (`validate_lesson()` wiring) (§8, §12.4) — the experiment
  will still be able to observe correction capture/retrieval/injection; it just won't be able to
  claim the correction demonstrably changed a scored decision.
- Owner-correction capture on non-voice paths (§8, §12.5).
- `reasoning_chains` read-side (§12.6), `ReasoningBank` score-formula wiring (§12.7), ghost-memory
  prompt rendering (§12.8) — all write-side-real, read-side-orphaned; none affect the experiment's
  ability to measure think→decide→act→learn behavior.
- `plans.py` `confidence_threshold` verification type (§7, §12.3) — dead code, currently
  unreachable, zero runtime impact until/unless a plan step is authored to use it.
- `MissionRunner`/plan-creation autonomy (§12.11) — plans currently need a human/API trigger to be
  born; if the experiment's design assumes VECTOR spontaneously creates new multi-step plans with
  zero prior human interaction at any point, that assumption does not hold today.
- `chief_of_staff`/`morning_digest` scheduling stubs (§12.9, §12.10, §12.12) — cosmetic dead
  entry-points with working alternate paths; no experiment-relevant capability is actually missing.

**Note**: Crash-mid-step plan recovery, originally assessed in an early draft of this document as
SAFE TO DEFER, was reclassified to MUST FIX (§16.B) after closer inspection confirmed a real
7-day-unattended-run process restart is a realistic occurrence, not a rare hypothetical — it is
listed here only for the record of that reclassification, not as a currently-deferred item.

**NOT A REAL PROBLEM:**
- `permission_gateway._execute_action()` vs. `Governor.dispatch()` dual-surface architecture
  (§13) — inelegant, but neither surface is broken; this is a code-organization observation, not
  a defect.
- The 21-coroutine supervised-restart architecture (§14) — this is working as intended; flagged
  here only to note it was verified, not found lacking.

---

## 18. Exact Recommended Fixes (for future work — NOT implemented this pass)

These are documented for a future task, not acted on here. Items 1-2 are the two MUST-FIX
blockers from §16 and should be prioritized first.

1. **(MUST FIX, §16.A)** Add the missing `await` at `autonomous_loop.py:2868`:
   `hypotheses = await engine.generate_hypotheses(context)`. One-line change. Verify with a test
   that actually executes `hypothesis_loop()`'s body (or `_think_tick`-equivalent for hypothesis)
   end-to-end rather than source-string-matching, so a regression like this cannot recur silently.
2. **(MUST FIX, §16.B)** On `AutonomousLoop` boot (or inside `PlanStore._ensure_loaded()`), scan
   all loaded plans for steps with `status == "running"` and reset them to `"planned"` before
   `_get_plan_candidates()` is first called, so a crash-interrupted step is retried rather than
   permanently stalled. Consider whether re-running a step that actually completed just before the
   crash (but before its status write landed) is an acceptable risk for this experiment, or whether
   idempotency-checking is needed first — a design decision for whoever implements this, not
   resolved here.
3. Route `Governor.dispatch()`'s default action-type fallthrough through `permission_gateway`
   before calling `agent.run()`, or add an explicit, auditable exception list for action types
   that are genuinely safe to skip the gate (read-only district agents), so RULE 3's claim matches
   reality.
4. Either (a) have `context_engine.track_beliefs()` also emit an `action_domain:*` claim when a
   formed belief is decision-relevant, or (b) have `decision_engine._epistemic_penalty()`
   additionally consult `belief:*` claims matching the candidate's context.
5. Add a call to `validate_lesson()` in `_act_on()`'s outcome-recording block (near
   `record_epistemic_belief()`), keyed off whichever correction lesson(s) were present in the
   hydration prompt for that decision.
6. Extend `_detect_and_store_correction()`'s capture trigger beyond the voice-intent path to web
   chat and terminal chat.
7. Either remove `plans.py`'s dead `confidence_threshold` verification branch or make
   `get_confidence()` accept a fallback default so it doesn't silently fail-closed at 0.0.

---

## 19. What Should NOT Be Changed

- The 21-coroutine supervised-restart architecture (§14) — working correctly, do not simplify or
  consolidate.
- The `action_domain:*` epistemic outcome-loop's existing scoring formula and dampening factors
  (`decision_engine.py:271-345`) — real, tested, working exactly as designed.
- `PolicyMemory`/`CounterfactualMemory`'s existing wiring — both fully closed loops, do not touch.
- Plan execution's DAG/replanning/persistence logic (`plans.py`, execution side) — real,
  test-verified, working. Only the crash-mid-step recovery gap (§12.0b, MUST FIX per §16.B) needs
  a targeted addition (a boot-time status reset) — do not otherwise touch the DAG/replanning code.
- `hypothesis_engine.py`'s `generate_hypotheses()` method itself — it is correctly written as
  `async def` and works fine; the defect is entirely in its caller
  (`autonomous_loop.py:2868` missing `await`), not in the engine.
- The permission_gateway's own internal GREEN/YELLOW/RED classification and trust-ladder logic —
  the defect is in *coverage* (which paths reach it), not in the gate's own correctness once
  reached.
- Inference observability layer (verified complete in the prior session pass) — not re-audited or
  touched this pass; no reason to revisit.

---

## 20. Final Experiment-Readiness Verdict

### VECTOR CURRENT CAPABILITY LEVEL

- **Autonomous initiation**: S5 — `think_loop` runs unattended every 10s from process boot with
  zero required user message, driving real decisions (`autonomous_loop.py:735`, direct trace §3).
- **Goal persistence**: S5 — goals persist to SQLite, survive restart, drive candidates every tick
  (`goal_system.generate_immediate_actions()`, called `autonomous_loop.py:828`).
- **Long-horizon planning**: S4 execution / S1 creation, **with a confirmed MUST-FIX crash-recovery
  defect (§16.B)** — once a plan exists it executes autonomously with real DAG/replanning, but a
  step crashed mid-execution never recovers on restart (permanently stalls that branch), and
  nothing autonomous currently creates a new plan (`goal_system.add_goal()`'s only caller is an
  HTTP endpoint).
- **Memory**: S5 (episodic/policy/counterfactual) / S2 (reasoning-chain log, ghost memory) —
  episodic memory demonstrably closes the loop into the reward formula; several other memory
  subsystems are write-real but read-orphaned.
- **Epistemic reasoning**: S5 (outcome→confidence→next-decision loop, `action_domain:*`) / S3
  disconnected (formation→belief loop, `belief:*`) — one closed loop genuinely changes decision
  winners (test-proven); the other writes real data nothing consults for scoring.
- **Owner-correction learning**: S2 — real capture/store/retrieve/inject chain, but voice-only
  capture and prompt-injection-only influence; the outcome-feedback method exists but is never
  called in production.
- **Tool execution**: S5 — decision→dispatch→agent.run()→result→memory pipeline is fully traced
  and closed for every action, gated or not (`districts/coding/code_reviewer.py` worked example).
- **Failure recovery**: S4 for coroutine-level recovery (`_supervised()` restarts any crashed
  coroutine with backoff, real and working); **S1 for plan-step-level recovery** — a crashed plan
  step is never retried or reset, a confirmed MUST-FIX gap (§16.B).
- **Replanning**: S4 — real, tested (`plans.py` replan_plan(), MAX_REPLANS=2 with LLM-restructure
  fallback tier) — this is a different mechanism from crash recovery above; replanning handles a
  step that ran and reported failure, not a step that never got the chance to report anything.
- **Proactivity**: S5 for `anticipation_loop` (genuinely fires, feeds real candidates into the
  decision pipeline with zero user trigger) / **S1 for `hypothesis_loop`** — scheduled and
  supervised correctly, but its core LLM call is never awaited (§16.A, confirmed MUST FIX), so it
  produces zero output every single cycle despite appearing fully wired.
- **Safety/governance**: S3, partial coverage — `permission_gateway` itself is real and tested, but
  only reached on a minority of action-dispatch paths; the majority of `Governor.dispatch()`
  traffic bypasses it entirely (§9, cross-confirmed by 3 independent traces).
- **Provider resilience**: S5 — verified in the prior session's inference observability pass
  (184/184 tests, real fallback/retry chains, not re-audited this pass).
- **Observability**: S5 — verified in the prior session pass (0.042ms/call overhead, complete call
  graph instrumentation, not re-audited this pass).
- **End-to-end behavioral verification**: S5 for the core think→decide→act→learn cycle
  (test-proven decision changes from epistemic/policy/counterfactual state); S2-S3 for the
  secondary learning systems (correction, reasoning-chain, ghost memory) that store real data but
  don't yet demonstrably change behavior; **S1 for proactive hypothesis generation specifically**,
  where the mechanism appears wired end-to-end but its core step silently never executes.

### FINAL VERDICT

**NOT READY — 2 MUST-FIX blockers**

1. `hypothesis_loop()`'s missing `await` at `autonomous_loop.py:2868` (§16.A) — silently disables
   one of VECTOR's few genuine proactivity mechanisms for the entire experiment duration.
2. Plan-step crash-mid-execution recovery (§16.B) — a realistic 7-day-unattended-run occurrence
   (any process restart) silently and permanently corrupts long-horizon plan progress data.

**Basis**: The core autonomous cognitive cycle — goal evaluation, context/epistemic-informed
decision scoring, gated-or-ungated action execution, and multi-system outcome learning — is real,
closed, and demonstrably running without required human input, verified by direct code tracing
(not documentation) across six independent audit passes covering every subsystem the task
specified. That architecture is sound and does not need to change. But two specific, narrow,
easily-verified code defects — a missing `await` and a missing status-reset-on-boot — each
silently suppress or corrupt data the experiment would presumably be designed to collect, meeting
this document's own MUST-FIX bar precisely because their absence prevents the experiment from
measuring a meaningful VECTOR capability (proactive hypothesis generation, long-horizon plan
completion under realistic interruption). Both fixes are one-to-a-few-line changes, not
architectural interventions — this is not a "go back to the drawing board" verdict, it is a "fix
these two specific bugs, then proceed" verdict.

**Explicit scoping caveat for whoever designs the 7-day experiment, once the two blockers are
fixed**: given §7, §8, and §9's findings, the experiment should still NOT be framed as measuring
"epistemic-aware sense-to-decision reasoning" (the `belief:*` formation loop doesn't reach
scoring) or "owner-correction-driven behavioral adaptation" (correction influence is unverifiable
prompt-injection, not measured decision change). It CAN legitimately measure: autonomous goal
pursuit over time, outcome-based epistemic confidence adjustment within the `action_domain:*`
loop, policy learning, counterfactual avoidance, proactive/anticipatory action generation (once
hypothesis generation is fixed), multi-step plan execution robustness including replanning (once
crash recovery is fixed), and the actual (partial) coverage pattern of the permission gateway as a
live safety signal in its own right.

---

## REMEDIATION STATUS (added 2026-09-02)

> This section is an addendum, not a rewrite. Everything above this line is the original audit
> as delivered — its findings, evidence, and verdict stand unmodified as a historical record.
> This section reports what happened after that verdict, under a separate, narrowly-scoped
> remediation task. Full detail — root cause, implementation reasoning, test-by-test mapping,
> remaining risks — lives in `52_AUTONOMY_BLOCKER_REMEDIATION.md`; this section is the summary.

### Blocker 1 — `hypothesis_loop()` missing `await` (§16.A)

**Status: FIXED.**

One-line fix at `autonomous_loop.py:2868` — `engine.generate_hypotheses(context)` →
`await engine.generate_hypotheses(context)`. Scheduling cadence, exception handling, and
confidence/suppression logic in `hypothesis_loop()` are otherwise byte-for-byte unchanged. No
prompt, provider, or routing changes. No second hypothesis-generation mechanism introduced.

Behaviorally verified (not just statically) via 4 new tests in
`tests/integration/test_phase_a5_hypothesis_consumer.py::TestHypothesisLoopActuallyExecutes`,
including one that proves the coroutine body actually runs (a counter incremented inside the fake
engine's own `generate_hypotheses()`) — the exact gap the original audit's §16.A flagged the
pre-existing `test_hypothesis_has_confidence_field` test as unable to catch (it only string-matches
source text). A companion test proves an exception raised inside hypothesis generation is caught
and does not kill the loop.

Two additional, separate, pre-existing defects were discovered while writing these tests (a
result-dict key mismatch at `autonomous_loop.py:2874`, and a hardcoded `confidence: 0.7` in
`hypothesis_engine.py` that sits below the loop's 0.85 storage threshold) — both are documented,
neither was fixed, both are out of scope for this task's "await only" mandate. See
`52_AUTONOMY_BLOCKER_REMEDIATION.md` §9 for full detail.

### Blocker 2 — plan-step crash/restart recovery (§16.B)

**Status: FIXED.**

`core/runtime/plans.py` gained a synchronous recovery hook in `PlanStore._ensure_loaded()`: any
step found `status == "running"` on a plan's first load into a fresh store is treated as
crash-orphaned. GREEN-tier (read-only/idempotent, per the existing `permission_gateway.py`
classification) steps reset to `"planned"` and re-execute normally. Every other tier is never
silently re-run — it's marked `"failed"` and routed through the existing fallback mechanism
(extracted from `replan_plan()`'s Strategy 1, not duplicated) or flagged via `plan.review_required`
if no fallback exists. Zero new persisted schema fields — reuses the pre-existing, previously-unused
`PlanStep.retry_info` and `Plan.review_required` fields. Zero new safety taxonomy — reuses the
gateway's own GREEN/YELLOW/RED/FORBIDDEN tiers.

Behaviorally verified via 11 new tests in
`tests/integration/test_planning_integration.py::TestCrashRecovery`, covering all of mandatory
items C–M: detection on fresh load, GREEN-tier reset-and-reexecute with dependent-step unblocking,
YELLOW/RED-tier steps never auto-resumed, fallback routing, completed/pre-existing-failed steps left
untouched, idempotency across 3 repeated simulated restarts, disk-persisted (not just in-memory)
recovery state, and dependency-graph preservation. Simulated-crash tests write state through the
real `Plan.to_dict()`/`PlanStore.save()` machinery and load it through a fresh `PlanStore` instance
on the same file — documented in `52_AUTONOMY_BLOCKER_REMEDIATION.md` §7 as behaviorally equivalent
to a real process restart, since `_ensure_loaded()` cannot distinguish the two.

### Tests added

39 new tests, 39/39 passing:
- `tests/integration/test_phase_a5_hypothesis_consumer.py::TestHypothesisLoopActuallyExecutes` — 4 tests (Blocker 1)
- `tests/integration/test_planning_integration.py::TestCrashRecovery` — 11 tests (Blocker 2, mandatory items C-M + dependency preservation)
- Remaining 24 of the 39 are pre-existing tests in the same two files, all still passing (20/20 and 19/19 file totals respectively) — zero regressions in either file.

### Full test-suite result

`tests/unit/` + `tests/integration/` (excluding `test_planning.py`'s 2 independently-pre-existing-broken
`MissionPlanAdvisor`-patch tests and 1 flaky timing test in `test_loop_stall_fixes.py`, all three
confirmed unrelated to this task and to plans.py/autonomous_loop.py):

**2165/2173 PASS** (2202 collected, 29 skipped, 0 errors, 8 failures — all 8 individually
re-run in isolation and confirmed pre-existing, unrelated to either blocker fix; none touch
`hypothesis_loop`/`_think_tick` in `autonomous_loop.py` or anything in `plans.py`). Full failure
list and root-cause trace for each in `52_AUTONOMY_BLOCKER_REMEDIATION.md` §8.

### Remaining SHOULD-FIX issues

- **Permission Gateway coverage gap** (original §9 finding) — re-confirmed still present at
  `governor.py:1970` (`Governor.dispatch()`'s default path has zero real `PermissionGateway` call
  sites). **Status: DEFERRED**, per this task's explicit instruction to leave it unchanged unless a
  fix was demonstrably isolated and trivial — it is not (a correct fix requires a real design
  decision spanning ~10 production call sites and a regression-test surface of its own). See
  `52_AUTONOMY_BLOCKER_REMEDIATION.md`'s dedicated section for the re-confirmed location and
  consequence.
- 8 pre-existing test failures (agent-registry successor reconstruction, correction-learner domain
  classification ×4, epistemic scoring ×2, council red-tier verdict logic) remain open — none
  related to either blocker, all documented with individual root-cause traces in
  `52_AUTONOMY_BLOCKER_REMEDIATION.md` §8.

### Residual limitations

- `ruff`/`mypy` are configured in `pyproject.toml` but not installed in this environment; static
  verification for this task relied on `python -m py_compile` + `ast.parse()` instead (both clean
  on all 4 changed files).
- The two collateral hypothesis-engine defects noted under Blocker 1 above remain unfixed by design.
- Recovery's fallback path (non-GREEN steps) does not attempt the LLM-based restructure strategy
  (`replan_plan()`'s Strategy 2) during the synchronous load-time hook — a deliberate scope
  boundary, not an oversight; see `52_AUTONOMY_BLOCKER_REMEDIATION.md` §4.

### Updated readiness verdict

Both MUST-FIX blockers from the original verdict are now fixed and behaviorally tested. This
does **not** supersede the original document's scoping caveat two paragraphs above (which
subsystems the 7-day experiment can and cannot legitimately claim to measure) — that guidance
still applies once the experiment is designed. See `52_AUTONOMY_BLOCKER_REMEDIATION.md` for the
full final verdict block and the explicit answer to whether VECTOR is ready to proceed to the
pre-experiment verification phase.
