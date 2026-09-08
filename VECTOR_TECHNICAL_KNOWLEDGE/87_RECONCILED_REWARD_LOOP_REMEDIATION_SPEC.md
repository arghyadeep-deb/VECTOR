# Task 87 — Reconciled Reward-Loop Remediation Specification

**Mode: read-only.** No production source, config, `.env`, database, log, or runtime state was
modified. No process was started, stopped, signaled, or interacted with. No package was
installed. No fix was implemented. One file created: this document. All database access used
`mode=ro` SQLCipher connections via the project's own `_get_db_key()`, per the pattern
established in Tasks 79/81/83/85.

**Method.** Task 84, 85, and 86 are treated as evidence, not conclusions. Every claim load-bearing
enough to appear in the final implementation spec (§28) was checked against current source this
session. Where I re-derived a fact from source or a read-only query myself, it is marked
**[V]** (verified this session). Where I rely on a prior task's own verification without
re-deriving it (because re-deriving it would cost effort without changing any conclusion), it is
marked **[T84]**/**[T85]**/**[T86]**. Where something could not be checked in this environment, it
is marked **UNVERIFIED**, not assumed. Task 86 could not open `vector_memory.db` (no SQLCipher
binding in its environment) and explicitly flagged Task 85's live-goal-table read as unverified
by it. **I have SQLCipher access and used it this session** — this document is the first of the
three to independently confirm, from the live goal table itself, the mechanism Task 86 derived
from source alone. That confirmation, plus one finding not present in either Task 85 or Task 86
(§9.4 — the surviving goal's immunity to its own staleness rule is a missing-field accident, not
a guarantee), are this document's own contribution beyond reconciling the other two.

---

## 1. Executive summary

Task 85 correctly found and precisely specified a real defect (the PolicyMemory key mismatch) and
proposed a well-disciplined, minimal-footprint plan built on it. Task 86, attacking that plan,
found a **second, larger, already-closed loop that Task 85 never examined**: `goal.progress` is
written as `round(0.10 × reward, 3)` on every successful action and read every scoring cycle at
1.5× the weight of the policy term Task 85 was optimizing. This loop is negative and has an
absorbing state — a goal that is successfully acted on enough times auto-completes and is
permanently removed from candidate generation, whether or not the goal was actually achieved.
**This session independently re-derived and confirmed that exact mechanism from current source**
(§6, §9) and additionally confirmed, from the live goal table Task 86 could not read, that it has
already consumed one goal (`g_daily_commit`, a daily-habit goal, now permanently `completed`) and
that the sole surviving candidate-generating goal (`g_kiit_attendance`) owes its survival to two
independent accidents — it is the only goal the counterfactual veto has never let execute, **and**
it is the only goal with no `created_at`/`last_updated` timestamp, which happens to make it immune
to an unrelated 90-day staleness-expiry rule that would otherwise be deleting it too (§9.4, new
this session).

Independently re-verified this session and found accurate in every particular checked: the
`_multi_backend_fallback()` timeout-parameter-accepted-and-discarded bug (§5), the
`PolicyMemory.make_situation_hash()` pre-existing canonical function (§11), `code_task`'s RED-tier
membership (§12/§18), and `TrustLadder`'s `trust_promotion_streak=20` default (§18).

**Reconciled verdict: Task 86's corrected ordering is right, and this document adopts it, with one
addition (the timestamp-immunity finding) and one refinement (an explicit accounting of what R0–R10
produces on the L0–L5 ladder, kept separate from any claim about understanding).** The immediate,
honestly-scoped target is a **closed, honest, measurable reward-adaptation loop** — not a cognitive
foundation, not understanding, not counterfactual reasoning. That renaming, which Task 86 proposed
in its closing section, is adopted here in this document's own title.

---

## 2. Current architecture reconstruction (Section 1 of the task)

Reconstructed and independently re-verified this session for every row marked **[V]**; carried
from Task 84/85/86 without re-derivation, but not contradicted by anything found this session,
for rows marked **[T84/85/86]**.

| # | Item | Classification | Evidence |
|---|---|---|---|
| 1 | `autonomous_loop.py` — 21 supervised coroutines, `_supervised()` restart-on-exception | **D/E** (runtime reachable, restart behavior test-adjacent via 107h zero-crash observation) | **[T84]** |
| 2 | `observe_loop` | **D**, degraded — `_tick_count` collapse ~1,000× | **[T84/86]** |
| 3 | `think_loop` → `_think_tick()` | **D** | **[T84]**, structure re-read this session, unchanged |
| 4 | Candidate generation (`generate_immediate_actions`) | **C** connected, **degenerate** output | **[V]** re-read `goal_system.py:212-242` this session |
| 5 | `DecisionEngine.evaluate()` / `_score_candidate()` | **D** — 5-factor linear form, no LLM | **[T85/86]**, weights re-confirmed structurally consistent with cited call sites |
| 6 | `GoalSystem` | **C**, and the site of the pathological loop | **[V]** full re-read this session, §6 |
| 7 | `PolicyMemory` | **C**, mis-keyed for 3 of ≥8 writers | **[V]** `policy.py` read, §11 |
| 8 | `CounterfactualMemory` | **C**, one-directional veto only | **[T84/85/86]**, not re-queried (DB state unchanged since Task 83/85) |
| 9 | `EpistemicTracker` | **C** mechanism, **B** signal (starved) | **[T84]** |
| 10 | `PermissionGateway` | **F** — behaviorally verified safe across 107h+ live operation, adversarially tested in Tasks 53/57/58/59/60 | **[T84]** |
| 11 | `Governor` | **D** — routes 43,312 dispatches, no gateway calls | **[T82/83/84]**, this conversation's own prior direct source read |
| 12 | Event bus (`core/event_bus/wiring.py`) | **C**, district-keyed, two closed cycles | **[T82/84]**, this conversation's own prior direct source read |
| 13 | Fanout (`_fanout_handler`, `_tracked_task`) | **D**, unbounded fire-and-forget | **[T84]** |
| 14 | `AgentBase.vchat()` | **D** — synchronous `ollama_safe.chat()` call from async code | **[V]** re-read `agent_base.py:325-341` this session |
| 15 | `Governor._llm_classify()` | **D** — same synchronous call pattern | **[V]** re-read `governor.py:1653-1675` this session |
| 16 | `ollama_safe.chat()` | **D/E** — the semaphore path is bounded and correct | **[V]** re-read `ollama_safe.py:184-320`, this conversation's own prior session |
| 17 | `_multi_backend_fallback()` | **B implemented but broken** — `timeout` param accepted, never referenced, no circuit breaker on any of 3 engine calls | **[V]** full function body read this session, `ollama_safe.py:659-726`; grep for `timeout` inside the function returns zero matches |
| 18 | `hypothesis_loop` | **B** — pipeline logic correct (three historical defects fixed), no timeout on its LLM call, one call in 107h hung ~69.9h | **[T84]** |
| 19 | Anticipation | **F** — deterministic, behaviorally verified, its one "change" was a clock artifact | **[T84]** |
| 20 | Plan execution (`plans.py`) | **E** — DAG, crash recovery, tested; creation is **B** (`add_goal()`'s only caller is an HTTP router) | **[T84]** |
| 21 | Reward calculation (5-factor, `autonomous_loop.py:1244-1258`) | **D** — real, reads owner feedback; unreachable on the dominant (vetoed) path | **[V]** re-read this session, §6 |
| 22 | Goal-progress update (`autonomous_loop.py:1283-1298`) | **C, and pathological** | **[V]** full re-read this session, §6 — the central new finding |
| 23 | PolicyMemory writers (5 in `autonomous_loop.py`/`hands/runner.py` + `PolicyMemory.make_situation_hash` + `commands.py`'s own + 2 `router.py` call sites) | **C for 3 of ≥8 implementations; disconnected for the rest** | **[V]** grep across all four files this session, §11 |
| 24 | PolicyMemory reader (`decision_engine.py:268/379`) | **D** | **[V]** re-confirmed this session |
| 25 | `TrustLadder` | **C** — real streak/promotion machinery, `trust_promotion_streak=20` default | **[V]** `core/loop/trust_ladder.py` read this session, §18 |
| 26 | `AgentRegistry` | **D** | **[T82/83/84]** |
| 27 | Successor spawning (`spawn_successor`/`deregister`) | **B** — fired exactly once in the 107h window observed, correct fallback taken | **[T82/83/84]**, this conversation's own prior direct source+live-log read |
| 28 | `APITester` | **D**, stale-reference mechanism untraced | **[T83/84/86]** |
| 29 | `ScriptGenerator` | **D**, task-type-blind hardcoded default | **[T82/84]** |
| 30 | `causal_graph.CausalGraph` | **C** — written on every real-outcome cycle, never audited as a reader | **[V]** re-read `autonomous_loop.py:1309-1319` this session, confirmed inside the same reward block as §6 |
| 31 | `CorrectionLearner.validate_lesson()` | **B** — correct, test-covered, **zero production callers** | **[V]** repo-wide grep this session: callers exist only in `tests/unit/` and `tests/integration/` |
| 32 | `ReasoningMemory`/`ReasoningBank` | **B** (SQL table: HTTP-endpoint-only reader) / **A→dead** (file bank: injected into a field `total_score` never reads) | **[T84]** |

**No row above claims "learning" from a write alone.** Every **C**/**D** row is qualified by
whether its value can change a future score, per this task's own instruction.

---

## 3. Task 85 vs Task 86 reconciliation table (Section 2 of the task)

Resolved against current source this session, not merely summarized.

| Task 85 claim | Task 86 challenge | Current-source verdict | Evidence | Implementation consequence |
|---|---|---|---|---|
| **A. PolicyMemory is the central learning mechanism / the only place a persisted value changes a future decision** | `goal_alignment` (weight 0.30) also does, via `progress`, and more destructively | **Task 86 correct.** `_increment = round(0.10 * reward, 3)`; `progress = min(1.0, progress + _increment)`, gated on `winner.goal_ids and completed >= 1.0` | **[V]** `autonomous_loop.py:1283-1298`, read in full this session | Goal-progress repair (R3) must precede or accompany, not follow, any PolicyMemory work |
| **B. `goal.progress` semantics** | It is a cumulative reward counter, not an achievement measure | **Task 86 correct**, confirmed by the writer formula itself and by `update_goal_progress()`'s auto-`completed` at `>=1.0` with no reactivation path | **[V]** `goal_system.py:244-258`, re-read this session | Must decouple before any candidate-eligibility rule is built on `progress` |
| **C. Candidate diversity — tags/staleness fix is safe and "zero-cost"** | The composition of both halves autonomously generates `code_task`, which is **RED** | **Task 86 correct.** `code_task` confirmed in the RED list at `config.py:258`, annotated "code write + execute paths" | **[V]** re-read `config.py:230-265` this session | R6 must ship staleness-only first; tag routing requires a GREEN-only allowlist, never shipped bare |
| **D. Hypothesis-loop timeout is the right P0** | Wrong layer; `_multi_backend_fallback` is the actual unbounded primitive; P0 destroys the diagnostic | **Task 86 correct**, and stronger than stated: the discarded-`timeout` bug is a clean, unambiguous, single-function defect, not an inference | **[V]** full function read this session, zero `timeout` references inside `_multi_backend_fallback` | R1 targets the fallback function, not `hypothesis_loop`; the diagnostic (R0) runs before any runtime fix ships |
| **E. `_multi_backend_fallback` timeout not used** | (Task 86's own finding) | **Confirmed independently, in full, this session** | **[V]** | Highest-confidence runtime finding in this document — see §5 |
| **F. Event fanout ranked #8/#9 (low priority)** | It is the load generator for the runtime problem and the noise floor for every measurement; should be #2 | **Task 86 correct.** The causal chain `_fanout_handler → governor.dispatch → route_task → _llm_classify → ollama_safe.chat (sync) → (on failure) _multi_backend_fallback (unbounded)` is real and every link is independently verified in this conversation's own Task 82-85 source reads plus this session's re-check of the two synchronous call sites | **[V]**/**[T82-85]** | R2 (fanout cooldown) moves to position 2, immediately after R1 |
| **G. PolicyMemory key canonicalization — one new module** | `PolicyMemory.make_situation_hash()` already exists, already canonical-shaped, already used by 2 other call sites; a new module is unnecessary | **Task 86 correct.** Confirmed `policy.py:24` (`@staticmethod make_situation_hash`), and confirmed **[V]** this session that `core/memory/router.py:180` and `:316` already call `self._mem.policy.make_situation_hash(...)` | **[V]** grep + read this session | R5 reuses `PolicyMemory.make_situation_hash`; no new module created (satisfies the task's Rule 10) |
| **H. Veto reward (0.05) contamination** | Canonicalizing the key before separating the veto write from the reward channel merges a control-flow constant into the reward mean | **Task 86 correct**, and the arithmetic is unavoidable: `update_from_outcome` is a plain cumulative mean (`policy.py`, confirmed no decay term in the update signature checked against `decision_engine.py`'s reader — see §11), so any merge is permanent until manually corrected | **[V]**/**[T86]** | R4 (separate the channel) must ship **before** R5 (canonicalize), reversing Task 85's order |
| **I. Experience table is necessary** | The necessary primitive is an id, not a table; existing rows (episodic `decision_candidate`, `gateway_audit`, `governor_dispatch`) already carry most of what's needed | **Task 86 correct on the minimal case.** `Decision.all_candidates` already exists (`decision_engine.py:41/537`) **[V]**, confirming candidates-with-identity is achievable without a new persistent structure | **[V]** | R7 stamps a `decision_id` into existing rows; no new table (satisfies Rule 9) |
| **J. decision_id** | Necessary; `candidate_id` also needed for losers/vetoed candidates to be referenceable | **Both needed, source supports it.** `all_candidates` already holds every candidate object in a tick; stamping identity onto them at construction is additive, not a new store | **[V]** | §16 |
| **K. Counterfactual — bounded reasoning design** | Cannot learn without the untaken branch's outcome; naming is wrong; real learning requires bounded GREEN-only exploration, not proposed by Task 85 | **Task 86 correct on both counts.** `should_avoid()` confirmed post-selection-only (no `CounterfactualMemory` reference found in `decision_engine.py` this session's grep) | **[V]** | §17 renames the near-term capability "decision provenance"; exploration deferred with explicit prerequisites |
| **L. Bounded exploration** | Not proposed by Task 85 at all; is the only honest route to a real untaken-outcome | **Task 86's addition, not a disagreement with Task 85 — a gap.** Confirmed no exploration mechanism exists anywhere in `decision_engine.py`/`autonomous_loop.py` per this session's targeted greps | **[V]** absence confirmed | Specified as a future prerequisite list only (§17), explicitly not implemented per Rule 13 |
| **M. Connecting `belief:*` into scoring** | Dangerous now: beliefs are self-contradictory today, would suppress the only 34 real actions, inverts `_epistemic_penalty()`'s "don't penalize ignorance" design | **Task 86 correct**, and this document does not revisit the underlying contradiction (`presence:absent` + `screen_activity:active_coding` simultaneously) since it was already DB-verified in this conversation's own prior Task-84-era read and the DB state is unchanged | **[T84 §4.3, V-DB in this conversation's own prior turn]** | Rule 14 (do not connect belief:* to scoring) is honored; R9 specifies only prerequisites |
| **N. Belief contradiction detection** | Needed as a precondition, not a companion, to any belief→scoring work | **Agreed**, no new evidence needed — this is a design conclusion following directly from M | — | §15 |
| **O. HP shaping fix timing** | Should not ship during the same window as the learning measurement — confounds attribution of any observed behavior change | **Task 86 correct**, and Rule 15 (do not modify HP shaping) makes this moot for this task regardless | **[T85/86]**, not re-derived — Rule 15 forecloses the question | Frozen, per instruction |
| **P. Successor bug fix timing/target** | The registry-level dict/attribute bug fired once in 107h; the *live* defect is an untraced stale reference; fixing the registry bug alone would create false confidence | **Task 86 correct**, and independently reconfirmed in this conversation's own Task 83 work (exactly one `[VECTOR][agent_registry]` successor-reconstruction line in the entire 107h boot log, followed by 5,558 more "DIED" events with zero further registry engagement) | **[T83, this conversation's own prior direct log analysis]** | Rule 16 (do not fix successor lifecycle yet) honored; §19 gives the trace-first plan |
| **Q. APITester stale reference** | Untraced; must be traced before any lifecycle fix | Confirmed still untraced by any of Tasks 83-86 | **[T83-86]** | §19 produces a hypothesis tree, not a fix |
| **R. ReasoningBank** | Should be deleted outright — costs a read+write per cycle for zero effect | **Task 86 correct and this is the clearest deletion candidate in the whole reconciliation** — `total_score` never reads the field it's injected into, per both Task 84's and this conversation's own review | **[T84/86]** | §20 marks it DEPRECATE, not FREEZE — the one exception to "be conservative" |
| **S. CorrectionLearner** | `validate_lesson()` should be wired — cheapest real capability gain available | **Confirmed independently this session**: zero production callers, only test callers, function itself unchanged and correct | **[V]** repo-wide grep this session | §14 specifies the wiring design, not implemented (per Rule 3 of the top-level rules — no implementation) |
| **T. Understanding architecture scope** | Task 85's roadmap does not create a foundation for situational understanding; the decision layer is model-free (six scalars, fixed weights, no LLM in scoring) | **Confirmed.** `_score_candidate()`'s five weighted terms plus the epistemic clamp are the entire scoring function; no call to any LLM-classification or embedding function appears in `decision_engine.py`'s scoring path per source structure already read in this conversation and re-confirmed by this session's re-reads of the surrounding call sites | **[T86]**, structurally consistent with everything re-verified this session | §22 keeps Understanding as an explicitly separate, frozen programme |
| **U. Situation representation** | `sha256(action_type + params)` is an identifier, not a representation; supports equality only | **Confirmed** — `params` for the dominant unstarter candidate is `{"goal_id":..., "title": f"Start: {goal['title']}"}` **[V]** re-confirmed this session against `goal_system.py:233-240`'s dict literal | **[V]** | R5's defining-field allowlist (§11) is the only "representation" work done in R0-R10, and it is explicitly key hygiene, not understanding |
| **V. Generalization** | Requires a situation representation that doesn't exist; a hash-bucket `situation_class` is architecture substituting for a model | **Agreed** — no counter-evidence found; embeddings vs. hand-rolled buckets is a model-capability question, not resolved here | — | §21 places `situation_class` explicitly in "architecture where model capability may be the better tool", deferred past R0-R10 |
| **W. TrustLadder** | Working policy learning could accelerate YELLOW→autonomous promotion; unmentioned anywhere in Tasks 51-85 | **Confirmed this session, independently, from source.** `trust_promotion_streak` defaults to 20 (`trust_ladder.py:85`); promotion requires `bad_outcomes == 0 and streak >= threshold` (`:115`); streak resets on any explicit rejection or execution failure (`:140,:157`) | **[V]** full file structure read this session | §18 — new required control, not implemented, specified only |

---

## 4. Evidence classification summary (Section 2 continued)

Of the 23 disagreement items (A–W), **19 resolve in Task 86's favor**, **2 are agreements/gap-fills
with no disagreement to resolve** (L, N), and **2 are pure verification passes with no live
contest** (S, on which both prior tasks agree; T/U/V, on which both prior tasks essentially agree
once T84's own framing is taken into account). **Zero items resolve in Task 85's favor against a
specific Task 86 challenge.** This is not a comment on Task 85's overall quality — its evidence
hygiene, its refusal to fabricate counterfactual outcomes, its `reward: null` idea, and its freeze
list are all independently sound and are carried forward unchanged into this document (§26, §32).
It is a comment on the value of adversarial review applied to a plan that had not yet examined the
`goal.progress` writer path at all.

---

## 5. Runtime starvation analysis (Section 3 of the task)

**Independently re-verified this session, in full, not accepted on citation.**

### 5.1 What is proven

- `_OLLAMA_SYNC_SEMAPHORE.acquire(timeout=CONFIG.get("ollama_semaphore_timeout_sec", 60.0))`, with a
  `finally: _OLLAMA_SYNC_SEMAPHORE.release()` — **PROVEN bounded and safe** (this conversation's own
  prior direct read, re-confirmed structurally consistent this session).
- `_multi_backend_fallback(model, messages, timeout, *, caller_id)` — **PROVEN** the `timeout`
  parameter is accepted and never used. Read the entire 68-line function body this session
  (`ollama_safe.py:659-726`). All three engine calls (`LiteLLMEngine.generate`,
  `AppleFMEngine.generate`, `GemmaCppEngine.generate`) pass only `model=`/`max_tokens=2048`. No
  `timeout=` argument anywhere. No `_wrap_with_circuit_breaker` call anywhere in this function
  (contrast with the main Ollama path, which does wrap its call). **This is the cleanest, most
  unambiguous defect in this entire reconciliation** — a grep for the literal string `timeout`
  inside the function body returns zero matches.
- `Governor._llm_classify()` (`governor.py:1653-1675`, re-read this session) and `AgentBase.vchat()`
  (`agent_base.py:325-341`, re-read this session) both call `ollama_safe.chat` (a plain, synchronous
  `def`) directly from `async def` functions, with no `asyncio.to_thread` wrapper. **PROVEN.**
- Only 3 of 21 coroutines (`observe`, `think`, `reflect`) have any `asyncio.timeout` **[T86, not
  re-counted line-by-line this session, but consistent with every coroutine name list already
  independently confirmed in this conversation's own Task 84 read]**.
- A `hypothesis_engine` inference call recorded a `latency_ms` of 251,520,681 ms (69.9 hours) with
  `status=error` **[T84, DB-sourced, not re-queried this session — no reason to expect the historic
  telemetry row has changed]**.

### 5.2 What is not proven

- **Whether the 69.9h hang specifically passed through `_multi_backend_fallback`.** The telemetry
  row records the outer call's latency, not which internal branch was in flight for how long.
  `_multi_backend_fallback` is reachable on Ollama-daemon-unavailable *or* on a 60s semaphore
  timeout; it is the only unbounded primitive found in the whole call chain, which makes it the
  best explanation available, but "best available" is not "the same as observed."
- **Whether it is sufficient, alone, to explain the ~1,000× observe/think cadence collapse.** The
  fanout-load chain (§ below) is a necessary co-factor: `_multi_backend_fallback` only blocks a
  *caller*; something has to be calling it at high frequency and on the event-loop thread for its
  blocking to matter at the scale observed. That caller is `_llm_classify`/`vchat`, and *those* are
  reached at dispatch-path volume (43,312/107h) via the fanout chain.

### 5.3 Classification

| Candidate mechanism | Classification | Basis |
|---|---|---|
| `_multi_backend_fallback` ignores its own `timeout`; unbounded, no breaker | **PROVEN present as a defect.** Whether it is *the* cause of the specific 69.9h hang: **LIKELY** | Full function read, zero-match grep this session |
| Synchronous `ollama_safe.chat()` on the event-loop thread via `_llm_classify`/`vchat` | **PROVEN present as a defect.** Contribution to the *measured* ~1,000× slowdown magnitude: **PLAUSIBLE, unproven** | Both call sites re-read this session |
| `_OLLAMA_SYNC_SEMAPHORE` unbounded block | **DISPROVEN** | Bounded acquire + guaranteed release, re-confirmed structurally sound |
| Unbounded fanout task growth (`_tracked_task`) exhausting the event-loop ready queue | **PLAUSIBLE, unproven** | Structure confirmed (§ below); causal link to the exact magnitude not measured |
| 18-of-21 missing coroutine timeouts | **PROVEN present as a systemic gap; a symptom of the primitive above, not an independent cause** | Consistent with prior task counts |
| `hypothesis_loop`'s own missing timeout | **PROVEN present; LOW causal importance** — one caller of the shared unbounded primitive, output has zero autonomous consumers (`suggestion_queue.db`, last row predates Segment 2) | **[T84]** |

**No claim here converts "probably" into "confirmed."** The unbounded primitive is a proven defect
independent of whether it explains the exact 69.9-hour figure; that distinction is preserved
throughout the rest of this document.

---

## 6. R0 — diagnostic (Section 3/6 of the task)

**Design only. Not implemented. Must run, and produce a result, before R1 ships.**

**Objective:** name the starvation mechanism, or bound how much of it remains unexplained, without
altering behavior and without destroying the one loud anomaly signal (the 69.9h latency row) that
exists.

**Instrumentation points, in order of preference:**

1. **Zero-code-change pass first.** Enable the already-shipped, opt-in
   `VECTOR_THREAD_DUMP_SEC` (`core/loop/thread_dump.py`) on a **disposable clone**, run it for a
   window long enough to observe at least one dispatch-heavy period, and read
   `data/logs/thread_dumps.log`. If the main thread is repeatedly captured inside an
   `ollama.Client`/`httpx`/`LiteLLMEngine`/`AppleFMEngine`/`GemmaCppEngine` frame, that is direct,
   sampling-based evidence of in-thread blocking, with zero new code.
2. **If (1) is inconclusive: a two-line, revert-safe monotonic-drift probe** around
   `observe_loop`'s and `think_loop`'s own `await asyncio.sleep(...)` calls:
   ```
   _t0 = time.monotonic()
   await asyncio.sleep(interval)
   drift_ms = (time.monotonic() - _t0 - interval) * 1000
   if drift_ms > SOME_THRESHOLD: logger.warning(f"[VECTOR][diag] sleep drift {drift_ms}ms on {loop_name}")
   ```
   This is deterministic (not sampling), distinguishes "blocked in-thread" from "queued behind
   `to_thread`" without `PYTHONASYNCIODEBUG`, and is two lines per coroutine, trivially removable.
3. **Snapshot an immutable baseline first.** Before either instrument runs, copy (not touch) the
   current `goals_v1` JSON blob, the `policy_memory` table, `epistemic.db`, and `counterfactual.db`
   to a read-only scratch location. This gives every later experiment (§23) a fixed comparison
   point and satisfies §27's "historical preservation" requirement for the diagnostic phase itself.

**What the diagnostic must NOT do:**
- Must not run against the live Segment-2-successor process — disposable clone only.
- Must not add a timeout to `_multi_backend_fallback` or any coroutine as part of "diagnosing" —
  that is R1, a separate, later step, and doing it early would remove the very anomaly being
  diagnosed (Task 86's point, independently endorsed here: bounding the caller before naming the
  cause converts a screaming signal into routine-looking noise).
- Must not be left running in production indefinitely — both instruments are diagnostic-only and
  should be disabled once R0's acceptance criteria are met.

**Acceptance criteria (exact, per the task's requirement):**
- **Pass condition:** at least one of the two instruments produces a specific, named call frame or
  a specific, timestamped drift event that can be correlated against `inference_calls.timestamp`
  for the historic 69.9h row (or a fresh reproduction of a multi-minute+ stall on the clone).
- **Fail condition:** neither instrument produces any anomaly across a run at least as long as the
  gap between Segment 2's burst and sparse phases (~64 minutes, per this conversation's own prior
  Task 83/84 measurement) — in which case R1 should still ship (it is a proven defect regardless,
  §5.1), but the causal claim linking it to the specific ~1,000× magnitude must remain **LIKELY**,
  not be upgraded to **PROVEN**, in any future report.

---

## 7. R1 — runtime remediation (Section 4 of the task)

**Design only. No code changes below.**

Answering the task's 15 numbered questions directly, from source:

1. **Can the existing `timeout` parameter be safely propagated?** Yes — it is already threaded
   into `_multi_backend_fallback`'s signature and simply needs to reach the three `.generate(...)`
   calls, e.g. `engine.generate(fallback_messages, model=..., max_tokens=2048, timeout=timeout)`,
   **if and only if each engine's `generate()` accepts a `timeout` kwarg** — **UNVERIFIED this
   session**: `LiteLLMEngine`, `AppleFMEngine`, `GemmaCppEngine` live in `vectorcode/src/vc_engine/`
   and were not read this session. This must be checked before implementation; if one engine's
   `generate()` does not accept `timeout`, wrapping the call site (item 4 below) is required for
   that engine specifically.
2. **Do all three engines support timeout?** **UNVERIFIED** — flagged as the first thing the
   implementation task must check, not assumed.
3. **Is wrapping the entire chain sufficient, or is a hard deadline required?** A hard deadline is
   safer and simpler than three per-engine timeouts: wrap the whole three-engine sequence in one
   `concurrent.futures.ThreadPoolExecutor(...).submit(...).result(timeout=timeout)` (since
   `_multi_backend_fallback` itself is a synchronous function, not a coroutine — it cannot use
   `asyncio.wait_for` directly without already being on a thread). This bounds total fallback time
   regardless of which engine is slow, and is a single change point rather than three.
4. **Do synchronous calls need to move to a worker thread?** They are already synchronous
   (`ollama_safe.chat`, and by extension `_multi_backend_fallback`, are plain `def`s). The question
   that matters is whether **the callers** (`Governor._llm_classify`, `AgentBase.vchat`) should move
   to `asyncio.to_thread(...)`. **Recommendation: yes, at the caller, as a second, separable step**
   — this does not require touching `ollama_safe.py` itself and directly addresses item 14/15/16
   below (event-loop-thread occupancy) independently of the timeout fix.
5. **Would moving to a worker thread create a new problem?** Yes, one to name explicitly:
   `asyncio.to_thread` uses a bounded default executor (`ThreadPoolExecutor`, default
   `min(32, os.cpu_count()+4)` workers); if dispatch volume (43,312/107h, ~1 every 9s) saturates
   that pool with slow fallback calls, callers would queue *behind the pool* instead of blocking the
   event loop directly — better (the loop stays responsive) but not free (new callers wait). This
   is why R2 (reduce fanout volume) must land at the same time or before this specific sub-change,
   not after.
6. **Does cancellation actually stop the underlying operation?** **UNVERIFIED and likely NO** for
   the three fallback engines without reading their implementations — a `ThreadPoolExecutor.submit`
   with a `.result(timeout=...)` does **not** cancel the underlying thread if it's still running a
   blocking call; it only stops *waiting* for it. This must be stated as a known limitation, not
   silently assumed away: **the fix bounds the caller's wait, not the callee's execution.** A truly
   hung `GemmaCppEngine` subprocess would keep running in the background even after the caller times
   out. This is acceptable for the immediate goal (unblock the event loop / unblock `hypothesis_loop`)
   but must be documented as a residual leak, not solved.
7. **What happens if one backend ignores cancellation?** Per (6): it keeps running, consuming a
   thread-pool slot until it finishes or the process exits. Over many repeated timeouts this could
   exhaust the pool — a monitoring/alerting gap to flag, not fix, in this spec.
8. **Does circuit breaker state remain coherent?** The Ollama path already has its own breaker
   (`_wrap_with_circuit_breaker("ollama", _call)`); `_multi_backend_fallback` currently has none.
   Adding a bound does not by itself add a breaker — **recommend also wrapping the three-engine
   sequence in the same `_wrap_with_circuit_breaker` pattern already used for Ollama**, so a
   consistently-failing fallback backend stops being retried every call, independent of the timeout
   fix. This is additive, not required for R1's minimum bound, and should be scoped as a follow-on
   if it adds meaningful risk to bundle into one change.
9. **Does fallback order remain unchanged?** Yes — the fix only bounds each attempt's duration; it
   does not reorder LiteLLM → AppleFM → GemmaCpp.
10. **Does provider selection change?** No — same three engines, same order, same trigger condition
    (Ollama unavailable or semaphore-timeout).
11. **Does latency telemetry remain honest?** Yes, and it improves: currently, a hung fallback call
    would (per the 69.9h precedent) report an enormous, honest-but-useless latency; after the fix,
    `_record_observability`'s latency figure reflects the actual bound, and a new `status=timeout`
    (distinct from `status=error`) should be recorded so the alerting logic in
    `InferenceObservability.alert_check()` can distinguish "the fallback timed out" from "the
    fallback errored" — a one-value schema addition to an already-existing observability call,
    not a new subsystem.
12. **Does the fix affect ordinary user-triggered calls?** Any call path that reaches
    `ollama_safe.chat()` when Ollama itself is down would now get a bounded response instead of an
    unbounded hang — this is a strict improvement for user-triggered calls (they currently share
    the exact same unbounded risk), not a behavior change specific to autonomous callers.
13. **Does it affect autonomous calls?** Same answer — the function is shared; there is no
    autonomous-vs-user branch inside `_multi_backend_fallback`.
14. **Does it affect district fanout?** Yes, and this is the point: `Governor._llm_classify()` sits
    directly in the `route_task()` path used by dispatch, so bounding the fallback bounds the worst
    case for every one of the 43,312/107h dispatches, not just `hypothesis_loop`'s ~26 calls.

**Files/functions:** `core/inference/ollama_safe.py` (`_multi_backend_fallback`, and optionally the
two synchronous call sites in `core/city/governor.py` and `core/city/agent_base.py` as a second,
separable sub-change).

**Invariants that MUST remain unchanged:** fallback engine order; the "never raises, returns `""`
on total failure" contract (`chat()`'s existing failure contract, explicitly cited in the current
source's own comment); the Ollama-path semaphore/circuit-breaker behavior (untouched by this
change); `caller_id`-based observability tagging.

**Tests required:** a unit test that mocks all three fallback engines to block past the configured
timeout and asserts `_multi_backend_fallback` returns within a bounded wall-clock window; a
regression test asserting fallback order and return value are unchanged when an engine succeeds
quickly; a test asserting `_record_observability` records a distinguishable `status` for a
timed-out fallback vs. a clean failure.

**Behavioral proof required:** re-run R0's thread-dump diagnostic on the clone after the fix and
confirm no main-thread frame is captured inside a fallback engine call beyond the configured bound.

**Rollback:** revert the one function; no persisted state changes; the pre-fix behavior (unbounded,
but never previously observed to fail except once in the historic record) resumes exactly.

---

## 8. R2 — fanout remediation (Section 5 of the task)

**Design only.**

**Verified this session (consistent with this conversation's own prior direct reads of
`core/event_bus/wiring.py`, `governor.py`, and `autonomous_loop.py` in Tasks 82-85, not
re-derived line-by-line again here since the files have not changed):** `PUBLISH_EVENTS` is keyed
by district only, discarding `task_type`; `EVENT_TRIGGER_MAP` maps each event to a fixed
downstream list; `_fanout_handler` creates each downstream dispatch via `_tracked_task()`, an
unbounded fire-and-forget set with no semaphore, depth cap, dedup, or cycle detection; two closed
cycles exist (marketing/data_analytics/strategy/content, and content/marketing/qa); `strategy` has
zero registered agents and receives 4,655/107h dispatches that all log `"no agents in strategy"`
before falling through.

**Design R2:**

- **Edge identity:** `(source_event_type, target_district, target_task_type)` — the finest key
  that distinguishes every distinct downstream trigger in `EVENT_TRIGGER_MAP` without requiring any
  change to the map's own structure.
- **Cooldown key:** identical to edge identity above — one TTL entry per edge, not per dispatched
  task instance (so 5,582 identical `qa::review_content` dispatches collapse to one cooldown
  bucket, not 5,582).
- **TTL semantics:** a simple in-process (not persisted — no new table) `dict[edge_id, float]`
  mapping edge → last-fired monotonic timestamp; an edge is eligible to fire again only if
  `now - last_fired > cooldown_seconds`. Default cooldown should be derived from observed dispatch
  cadence (currently ~9s system-wide) times a safety factor — e.g. start conservative (60-300s) and
  measure, rather than guessing a final value in this spec.
- **First-event behavior:** an edge with no prior entry fires immediately (cold start is not
  penalized).
- **Duplicate behavior:** a duplicate event for an edge still in cooldown is dropped silently
  (logged at DEBUG, not WARNING, to avoid trading dispatch spam for log spam) — not queued, not
  retried.
- **Failure behavior:** if the downstream `governor.dispatch()` call itself fails or returns
  `no_agents`, **the cooldown timer still starts at fire-time, not at success-time** — this is
  the conservative, monotonically-load-reducing choice (a failing edge should not be retried
  faster than a succeeding one; retrying faster would increase pressure on exactly the paths
  already failing, e.g. the unstaffed `strategy` district).
- **Restart behavior:** the cooldown dict is in-process and resets on restart — acceptable, because
  its purpose is load-shaping within a boot, not cross-boot memory; explicitly not persisted, per
  the instruction to avoid new persistent structures where an in-process bound suffices.
- **Memory bounds:** the dict has at most `len(EVENT_TRIGGER_MAP)`'s total edge count entries —
  a small, fixed, compile-time-bounded number, not unbounded growth.
- **Cleanup:** none required beyond the fixed-size dict above; no periodic sweep needed since the
  key space does not grow.
- **Concurrency behavior:** the dict is read/written from the same asyncio task context
  (`_fanout_handler`'s own coroutine); if fanout ever becomes multi-worker, a lock would be needed —
  out of scope for the current single-loop architecture.
- **Cooldown applies before dispatch** (a gate on whether to call `governor.dispatch()` at all),
  not after — this is what actually reduces load, rather than merely suppressing a downstream
  side-effect after the expensive call already happened.
- **Nested fanout counts:** a dispatch that itself publishes a new event and re-triggers the fanout
  handler is subject to the *same* per-edge cooldown as any other trigger of that edge — no special
  case is needed because the edge identity (source event + target) is the same regardless of
  whether the *source* event was itself fanout-triggered or user/plan-triggered.

**`strategy` edge:** retire it explicitly (remove the `ANALYTICS_READY → strategy::review_analytics_insights`
entry from `EVENT_TRIGGER_MAP`) rather than "staff" it with a placeholder agent — staffing it with
an agent whose only job is to satisfy an unread dispatch would just relocate the waste, and no
task in this series has identified any actual work `strategy` should be doing. If the owner later
wants a real `strategy` district, that is a separate, deliberate addition, not a byproduct of
removing a no-op edge.

**Explicitly deferred, not implemented, not designed further here (per the task's own instruction
and Task 86's argument):** re-keying `PUBLISH_EVENTS`/`EVENT_TRIGGER_MAP` by `(district, task_type)`
instead of district alone. This is architecturally correct in principle but changes *which*
downstream tasks fire — a behavior change, not a load-shaping change — and should wait until after
R2's cooldown establishes a lower, cleaner measurement baseline. Source analysis this session found
no safety or correctness reason (only a cognitive-noise reason) to do it now, so per the task's
explicit instruction ("do NOT re-key... unless source analysis proves it is required for
safety/correctness"), it stays deferred.

**Safety check (required by the task):** R2 strictly removes dispatch opportunities; it creates no
new action type, no new district, no new capability, and no new reachable permission tier. It is
monotonically load-reducing by construction (a cooldown can only suppress a fire that would
otherwise have happened, never add one).

---

## 9. R3 — goal-progress remediation (Section 6/7 of the task) — the central finding

### 9.1 Independent trace, this session, of every write and read of `progress`

**Writers found:**
1. `autonomous_loop.py:1283-1298` — the reward-derived increment, re-read in full this session:
   ```python
   if winner.goal_ids and completed >= 1.0:
       gs = self._get_goals()
       _increment = round(0.10 * reward, 3)
       for _gid in winner.goal_ids:
           _goal = next((g for g in gs.get_active_goals() if g["id"] == _gid), None)
           if _goal is not None:
               _new_progress = min(1.0, _goal.get("progress", 0.0) + _increment)
               gs.update_goal_progress(_gid, _new_progress, note=f"+{_increment} from {winner.action_type} (reward={reward:.2f})")
   ```
2. `autonomous_loop.py:~1515-1520` — the equivalent for plan-step outcomes **[T85/86, not
   re-read line-for-line this session but structurally consistent with the reward-writer pattern
   confirmed above and unchanged in this session's own broader read of the surrounding function]**.
3. `goal_system.update_goal_progress()` itself — the sole mutator; called only from the two sites
   above plus any HTTP router path (`core/api/routers/brain.py`, per Task 84's citation, not
   re-checked this session since it is out of the autonomous-loop path and does not change this
   finding).

**Readers found:**
1. `get_active_goals()` (`goal_system.py:200-206`, re-read this session) — filters
   `status == "active"`, no reactivation path anywhere in the file.
2. `_score_goal_alignment()` (decision_engine.py, per **[T85/86]**, structurally consistent with
   the `progress_gap = 1.0 - progress` formula both prior tasks independently cite) — reads
   `progress` on every scoring cycle, weight 0.30, the single largest weight in the 5-factor score.
3. `generate_immediate_actions()` (`goal_system.py:212-242`, re-read in full this session) — the
   exact-equality check `goal.get("progress", 0) == 0.0` gates the MID/LONG unstarter branch.
4. `_prune_expired()` (`goal_system.py:151-198`, read in full this session, **new to this
   document**) — a goal is auto-expired if `(now - last_updated_or_created_at).days > _STALE_DAYS[horizon]`
   **and** `progress == 0.0`. `_STALE_DAYS = {"SHORT": 7, "MID": 30, "LONG": 90}` (confirmed this
   session).

### 9.2 What "progress" semantically means, resolved

**Confirmed, from the writer formula alone, with no ambiguity: `progress` is a cumulative reward
counter, not a measure of goal achievement.** It increments only on `completed >= 1.0` (execution
succeeded) and only by an amount proportional to the 5-factor `reward` value computed for that
specific action — a value that already includes real owner feedback, but which measures "was this
action good", not "how much closer is this goal to done." Two different actions on two unrelated
goals with the same reward advance their respective goals by the same increment, regardless of
how large or well-defined either goal actually is.

### 9.3 Does completion criteria exist? Are goals recurring? — traced, not assumed

- **No goal in `PRESEEDED_GOALS` (`goal_system.py:25-88`, read in full this session) carries any
  explicit completion-criterion field** — no `target_value`, no `done_when`, no `recurring` flag.
  Completion is implicit and solely driven by `progress >= 1.0`.
- **No recurring-goal semantics exist anywhere in `goal_system.py`.** `g_daily_commit` — titled
  "Commit code every single day — no exceptions", a goal whose subject is inherently repeating —
  has no field distinguishing it from a one-shot goal.
- **Completion is irreversible.** `update_goal_progress()` sets `status="completed"` at
  `progress >= 1.0` (re-confirmed this session, `goal_system.py:244-258`); `get_active_goals()`
  filters to `status=="active"`; no function anywhere in the file sets a goal's status back to
  `"active"` from `"completed"`.

### 9.4 Independent confirmation from the live goal table — the finding this document adds

**Read this session, via read-only SQLCipher query against `semantic_memory.goals_v1`** (Task 86
could not perform this read in its environment and explicitly flagged Task 85's own read of it as
unverified by Task 86):

| goal_id | horizon | progress | status | created_at | last_updated |
|---|---|---|---|---|---|
| `g_kiit_attendance` | LONG | **0.0** | active | **None** | **None** |
| `g_karpathy_30` | MID | 0.076 | active | None | 2026-06-23T21:29:09Z |
| `g_vector_phase1` | MID | 0.25 | active | None | None |
| `g_placement_prep` | LONG | 0.076 | active | None | 2026-06-23T21:32:14Z |
| `g_daily_commit` | SHORT | 1.0 | **completed** | None | 2026-06-23T21:27:48Z |
| `g_first_revenue` | MID | 0.076 | active | None | 2026-07-10T22:17:53Z |
| `g_equation_portfolio` | LONG | 0.076 | active | None | 2026-07-10T22:18:24Z |

This **independently confirms Task 86's source-derived mechanism against the live data**: six of
seven `PRESEEDED_GOALS` (re-confirmed this session, `goal_system.py:25-88`) start at exactly
`progress: 0.0`; five have since moved off zero (four to 0.076, one — the daily-commit habit goal —
all the way to 1.0 and permanent `completed`); exactly one (`g_kiit_attendance`) remains at exactly
0.0, and it is the sole surviving source of a candidate in `generate_immediate_actions()`'s
MID/LONG-unstarter branch — fully consistent with the closed, self-reinforcing loop Task 86
described (veto blocks execution → no reward → no progress increment → stays at 0.0 → stays
eligible → re-proposed → vetoed again).

**New finding, not present in Task 85 or Task 86:** `g_kiit_attendance` is the **only** goal in the
table with `created_at=None` **and** `last_updated=None` — both fields entirely absent. Tracing
`_prune_expired()`'s exact logic (`last = goal.get("last_updated") or goal.get("created_at"); if
last: ...`) shows that **a goal with neither field is silently exempt from the 90-day
staleness-expiry check that would otherwise apply to a LONG-horizon goal frozen at `progress==0.0`
for this long.** Every other zero-touched-progress goal in the system has *some* timestamp and
would eventually be evaluated by this rule; `g_kiit_attendance`'s survival as VECTOR's sole
remaining decision candidate is therefore contingent on an unrelated missing-field accident, not
on any deliberate protection. **If this goal ever acquires a timestamp** (e.g., a future code
change that backfills `created_at` on load, or any code path that touches
`last_updated` without going through the reward-gated increment above), it would become eligible
for expiry on the very next `_prune_expired()` call, and — because its `progress` can structurally
never move off `0.0` under the current veto — `generate_immediate_actions()` would then return an
empty list every cycle, and `_think_tick()` would return immediately with zero downstream activity
at all. **This must be treated as a live risk to be preserved-around, not fixed-around, during R3**
— the repair in §9.5 must not incidentally give this goal a timestamp before the eligibility rule
itself is repaired, or it could silently disappear before R3 even ships.

### 9.5 Is this pathological? — confirmed, not assumed

**Yes.** It is a negative-feedback loop (success → higher `progress` → lower `goal_alignment` for
that goal specifically → that goal's own candidates score lower going forward) with an absorbing
state (`completed`, irreversible). It has already consumed one goal in its entirety
(`g_daily_commit`) and — per §9.4 — the system's current one-candidate state is not evidence the
loop has "settled"; it is evidence the loop is still running and has simply reached the point where
only the one goal the veto protects from ever executing remains untouched by it.

**Task 85's own P2 (replace the exact-equality staleness check with a graded threshold) would make
this worse, not better**, exactly as Task 86 argued: admitting more goals into rotation under the
current mechanism means more goals get executed, accumulate `0.10 × reward` per success, and
eventually auto-complete — permanently shrinking the active goal set further, not diversifying it
sustainably.

### 9.6 Designed repair (R3) — evaluating the five options from the task

- **Option A (keep `progress`, stop modifying it from generic reward):** the smallest change, but
  leaves `progress` frozen at its current (mostly-noninformative, `0.076`-clustered) values forever,
  with no path to it ever meaning anything again without a separate mechanism.
- **Option B (explicit reward accumulator separate from progress):** correct in spirit — cleanly
  separates "was this goal-linked action rewarded" from "is this goal done" — but by itself does
  not solve the missing-completion-criteria problem; a goal could still never be marked done by any
  mechanism, or the new accumulator could just become a second copy of the same pathology under a
  different name if anything is later built to auto-complete off of it.
- **Option C (explicit completion criteria):** the structurally correct long-term fix, but requires
  defining, per-goal, what "done" means — `g_kiit_attendance`'s "maintain above 75%" is not a
  progress-toward-completion measure at all (a maintenance goal has no natural 100%), which argues
  completion criteria cannot be applied uniformly without first classifying goal *shapes*
  (one-shot vs. maintenance vs. recurring) — a larger design question than this task should resolve
  unilaterally.
- **Option D (recurring goal semantics):** necessary specifically for `g_daily_commit`-shaped goals,
  insufficient alone for `g_kiit_attendance`-shaped ones (a maintenance goal, not a recurring
  daily-reset one).
- **Option E (combination) — chosen, minimum coherent version:**
  1. **Decouple `progress` from the reward formula immediately.** Remove the
     `_increment = round(0.10 * reward, 3)` write entirely from the two writer sites. This alone
     stops the bleeding — no further code needs to change for `progress` to stop being corrupted
     further. **This is Option A, applied as the immediate, zero-ambiguity first step, because it
     requires no new semantics to be invented and has the smallest possible blast radius.**
  2. **Stop auto-`completed` for any goal that has no explicit completion criterion.** Since no
     current goal has one (§9.3), this means: **for the existing seed goals, `update_goal_progress()`
     should no longer transition `status` to `"completed"` automatically at `progress >= 1.0`
     unless the goal record carries an explicit `completion_criterion` field.** This is a
     conditional change to existing logic, not new semantics — goals without a criterion simply
     stop auto-completing; nothing about them becomes recurring or reactivated.
  3. **Add an optional `recurring: bool` field, defaulting to absent/false, and set it `True`
     specifically for goals whose title/shape is a habit** (the obvious, minimal case being
     `g_daily_commit`). A `recurring=True` goal's `progress` resets to `0.0` on a fixed cadence
     (e.g., daily, matching its SHORT horizon) rather than accumulating toward a one-time
     completion — this is the smallest field that stops a habit goal from being permanently
     deleted by success, without inventing a general goal-taxonomy system.
  4. **Do not touch `GOAL_ACTION_MAP`** (per Rule 11) and **do not fabricate progress** for any
     goal — no goal's `progress` value is backfilled, estimated, or reinterpreted; only the write
     path changes, going forward.

### 9.7 Migration and historical-data treatment (explicit, per the task's requirement)

- **Existing progress values are preserved, frozen, as-is.** No recalibration, no backfill, no
  reinterpretation of the current `0.0` / `0.076` / `0.25` / `1.0` values — they remain exactly
  what they are, a historical record of what happened under the old (now-understood-to-be-flawed)
  semantics.
- **`g_daily_commit`'s `completed` status is NOT automatically reversed.** Per Rule 5 ("do not
  automatically reactivate completed goals"), this goal stays completed unless the project owner
  makes an explicit, separate decision to recreate or reactivate it as a `recurring` goal. This
  document does not make that call.
- **No migration script is required for the R3 repair itself** — removing a write and adding a
  conditional guard around another write requires no data transformation, only a code change.
- **A backup/snapshot of `goals_v1` immediately before R3 ships is required** (the same immutable
  baseline R0 already establishes, §6, satisfies this — no separate step needed if R0 has already
  run).
- **The 29,164-sample policy bucket and the 30,504-row counterfactual history are untouched by R3**
  — neither table is written or read by any code path this fix changes.

---

## 10. R4 — suppression/reward separation (Section 9 of the task)

**Design only.**

**Traced this session (structurally consistent with this conversation's own prior direct read of
the exact line):** the counterfactual veto path writes `update_from_outcome(winner.action_type,
_sit_hash, reward=0.05)` — a **hardcoded literal**, not derived from any property of the vetoed
action, at the moment `should_avoid()` blocks execution, **before** any real outcome exists.

**What 0.05 semantically represents:** not a reward — a **control-flow artifact** recording "this
proposal was suppressed", assigned an arbitrary small-but-nonzero constant presumably so the action
isn't scored as an outright failure (which might have used `0.0`) but also isn't rewarded. It
represents **avoidance/suppression information**, not an outcome measurement, and it should never
have been written through the same channel as the real 5-factor outcome reward.

**Should it affect PolicyMemory's `avg_reward` at all?** No — under R5's canonicalization, any
action type that is sometimes vetoed and sometimes executed would have its `avg_reward` become an
arithmetic mean of a control-flow constant and a real outcome measurement, with no way to
distinguish them (`update_from_outcome`'s cumulative-mean formula has no channel/tag argument).
Since the veto fires far more often than execution for any contested action (100% of the time for
`analyze_progress`, per every measurement in Tasks 79-85), the constant would dominate and suppress
the very reward signal R5 exists to reconnect.

**Design R4:**
- **Reward channel = actual outcome reward only.** The 5-factor writer (`:1263`), the VectorCode
  writer (`:1046`), and the plan-step writer (`:1493`) all continue writing to `policy_memory`
  exactly as they do today (modulo R5's key fix).
- **Suppression channel = separate.** The veto-penalty write moves to a distinct destination —
  the simplest option, and the one requiring no new table (per the spirit of Rules 7/9 even though
  they technically apply to different subsystems), is a **new column on the existing
  `policy_memory` row** (e.g., `veto_count INTEGER DEFAULT 0`, incremented instead of blended into
  `avg_reward`) or, if a schema change to `policy_memory` is undesirable, a **separate small table
  keyed by the same canonical hash** recording suppression counts only, never touching `avg_reward`.
  Both options are schema-additive, not destructive, and both preserve `CounterfactualMemory`'s own
  existing `rejections` table completely unchanged (the veto is still recorded there, in full,
  exactly as today — R4 only stops it from *also* being blended into the reward mean).
- **Historical interpretation of the dominant 29,164-sample bucket:** since this bucket is now
  understood to be **100% suppression-channel writes** (every one of the 1,198 decision cycles this
  conversation's own Task 83 measured produced a veto, and this has been the case since at least
  2026-06-18 per Task 84's lifetime `CounterfactualMemory` read), it should be **frozen and
  relabeled, not migrated** — it becomes historical evidence of "this action was suppressed 29,164
  times", which is itself a legitimate and interesting fact, not evidence about the action's
  outcome quality (which was never actually measured, because it never ran).

### 10.1 Exact tests required (per the task's explicit list)

- **Veto does not become reward:** a test that fires `should_avoid() == True` for a candidate and
  asserts `policy_memory.avg_reward` for that candidate's canonical key is **unchanged** (or that a
  separate suppression-count field increments while the reward field does not).
- **Actual outcome reward does become reward:** a test that runs a real (mocked-outcome) execution
  through the 5-factor writer and asserts `policy_memory.avg_reward` moves by exactly the amount
  the existing cumulative-mean formula predicts.
- **Veto remains observable:** a test asserting `CounterfactualMemory.rejections` still receives a
  row on every veto, unchanged from current behavior.
- **Policy retrieval remains deterministic:** given a fixed sequence of writes, `get_score()` for a
  given key returns the same value on repeated calls with no writes in between.
- **Old history is preserved:** a test (against a copy of the historical bucket, not the live table)
  asserting the existing 29,164-sample row's `avg_reward`/`sample_count` are byte-identical before
  and after the R4 code change ships (since R4 does not touch existing rows, only future writes).

---

## 11. R5 — PolicyMemory canonicalization (Section 8/10 of the task)

**Design only.**

### 11.1 Complete key matrix (verified this session, all eight implementations)

| # | Location | Formula | Reads/writes reader's current key? |
|---|---|---|---|
| **Reader** | `decision_engine.py:268` → `get_score()` `:379` | `f"{action_type}:{sorted(params.items())}"` | — |
| 1 | `autonomous_loop.py:1112` (veto penalty) | `f"{action_type}:{sorted(params.items())}"` | YES |
| 2 | `autonomous_loop.py:1046` (VectorCode reward) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | NO |
| 3 | `autonomous_loop.py:1263` (5-factor reward) | same `json.dumps` form | NO |
| 4 | `autonomous_loop.py:1493` (plan-step reward) | `f"plan_step:{action_type}:{json.dumps(...)}"` | NO (prefix too) |
| 5 | `hands/runner.py:145` | `sha256(f"hand:{name}")` | NO — no params at all |
| 6 | `core/memory/policy.py:24` `PolicyMemory.make_situation_hash()` **[V, confirmed this session]** | `json.dumps(context, sort_keys=True, default=str)`-based, `@staticmethod` | Not directly compared (different call convention — takes a dict/str `context`, not `action_type`+`params` separately), but same underlying serialization family as #2/#3/#4 |
| 7 | `core/memory/router.py:180,316` **[V, confirmed this session]** | calls `self._mem.policy.make_situation_hash(...)` — i.e., defers to #6 | inherits #6's non-match with the reader |
| 8 | `core/api/routers/commands.py:44` **[V, confirmed this session]** | its own private `_make_situation_hash(params)` | independent third implementation, not compared to the reader in this session (out of the autonomous-loop path; an HTTP-triggered path) |

**Eight implementations, confirmed, not five.** Task 86's correction of Task 85's count is
verified accurate.

### 11.2 Answering the task's eleven questions

1. **Which key function should be canonical?** `PolicyMemory.make_situation_hash()` — it already
   exists, is already co-located with the table it keys, is already used by two other call sites
   (`router.py`), and its underlying serialization (`json.dumps(..., sort_keys=True, default=str)`)
   already matches the *intent* of writers #2/#3/#4 (which independently reimplemented the same
   idea). **This satisfies Rule 10** (do not create a new PolicyKey module unless the existing
   function is proven unable to become canonical) — nothing found this session proves it cannot;
   it needs a calling-convention wrapper (to accept `action_type` + `params` the way the reader and
   `autonomous_loop`'s writers do) and the two design additions below, not a replacement.
2. **Can it become the sole canonical function?** Yes, with two additions (below) — no evidence
   found that its current `json.dumps`-based approach is unsound; its problem today is that it is
   simply not called by the reader or by writers #1-#5.
3. **What should happen to old rows?** Left exactly as-is, un-migrated, un-deleted — a new
   `v2:`-prefixed key scheme (below) means old rows are naturally never looked up by new code,
   without needing to be touched at all.
4. **Should a version prefix be introduced?** Yes — `v2:` (or similar), prepended to every new
   canonical key, so that a future serialization change can never silently re-merge with this one
   or with the pre-fix rows.
5. **Which params define the situation?** A declared, explicit allowlist per action_type family —
   at minimum `action_type` and `goal_id` (or the equivalent stable identifier for non-goal-sourced
   candidates); explicitly **not** `title` (free text).
6. **Which params are display-only?** `title` — confirmed this session by re-reading
   `goal_system.py:233-240`'s candidate-param construction (`{"goal_id": ..., "title": f"Start:
   {goal['title']}"}`) — `title` is a human-readable label with no bearing on what the action
   actually is.
7. **Should free-text titles be excluded?** Yes, unconditionally — a goal-title edit must never
   silently orphan learned history, per Task 86's correctly-identified failure mode.
8. **Should `source` be part of identity?** Yes, and this is where R4/R5 interact with the
   plan-step case: `source="think_loop"` vs. `source="plan:<id>"` vs. a Hands-originated action are
   plausibly different *policy domains* even for the same `action_type` — collapsing them without
   evidence they are the same domain would be exactly the "silently merge semantically different
   situations" failure Rule 10's spirit (and the task's explicit Section 10 instruction) warns
   against. **Recommendation: keep `source`'s coarse category (goal / plan / hand / vectorcode) as
   part of the key**, not the literal plan-instance id (which would fragment identical logical
   actions across different plan runs).
9. **Should plan-step identity remain distinct?** Yes — do not normalize away the `plan_step:`
   prefix into the same bucket as goal-originated candidates of the same `action_type`, per (8).
10. **What collisions could occur?** Two different goals with the same `action_type` and no other
    defining param (rare, but possible for generic actions like `research_topic`) would
    legitimately share a key under an allowlist that excludes `goal_id` — but the allowlist above
    *includes* `goal_id`, so this collision is avoided by design, at the cost of never generalizing
    across goals (an explicit, intentional limitation, not an oversight — generalization is
    deferred, §21).
11. **What should happen across schema versions?** The `v2:` prefix answers this — a future `v3:`
    would coexist with `v2:` rows exactly as `v2:` coexists with the un-prefixed historical rows,
    with no migration required at any step.

### 11.3 Exact examples (per the task's requirement)

- **Same situation → same key:** two `analyze_progress` proposals for `g_kiit_attendance`,
  differing only in the exact wording appended after "Start: " if the goal's title were edited
  between them — **under the old key, different; under the new allowlisted key, same** (since
  `title` is excluded).
- **Different situation → different key:** `research_topic` for `g_placement_prep` vs.
  `research_topic` for `g_first_revenue` — different `goal_id`, different key, correctly kept
  separate.
- **Renamed display field → same key:** editing a goal's `title` string must not change its policy
  key (this is the concrete regression test for item 7 above).
- **Different source → potentially different key:** `code_task` proposed by the goal system
  (`source="think_loop"`) vs. `code_task` executed as a plan step (`source="plan:<id>"`) — kept
  separate per (8)/(9), pending evidence they are the same policy domain, which this session did
  not find.

### 11.4 Ordering relative to R4 (explicit resolution of the task's Rule stated in Section 8)

Per the task's own instruction ("do NOT canonicalize the key until the suppression-vs-reward
contamination question is resolved") and the reconciliation in §3 row H: **R4 ships before R5.**
This document's implementation order (§25) reflects this.

---

## 12. R6 — candidate diversity (Section 11 of the task)

**Design only.**

### 12.1 Verification of Task 85/86's claims, this session

- **How many goals exist:** 7 (§9.4's table), all re-confirmed this session directly from
  `semantic_memory.goals_v1`.
- **What their progress values mean:** cumulative reward, not achievement (§9.2) — confirmed.
- **Which are active:** 6 of 7 (`g_daily_commit` is `completed`).
- **Which are recurring:** none — no `recurring` field exists anywhere in current source (§9.3).
- **Which have tags:** all 7 (`PRESEEDED_GOALS`, re-read in full this session, every entry carries
  a non-empty `tags` list).
- **Which tags map to RED/YELLOW/GREEN via `_TAG_TO_ACTION`:** traced this session —
  `_TAG_TO_ACTION` (`autonomous_loop.py:833-856`) maps `coding`/`build`/`debug`/`fix`/`implement`/
  `write_code`/`refactor` → `code_task`, confirmed **RED** (`config.py:258`, re-read this session).
  `git` → `git_status`, `kiit`/`attendance` → `check_attendance`, `research`/`ml`/`karpathy`/
  `learning` → `search_arxiv`/`daily_digest`, `finance` → `monthly_report`, `health` →
  `check_fatigue`, `placement`/`interview`/`dsa` → `search_web`, `memory` → `consolidate`,
  `reflection` → `daily_review`, `code_review` → `code_review_vc` — **tier of each of these was
  not individually re-checked against `config.py` this session beyond `code_task`**, and should be
  re-verified as part of implementing the GREEN-only allowlist below, not assumed safe by category.
- **Whether candidate generation can ever produce multiple action types:** yes, structurally, if
  both the SHORT branch and the MID/LONG-unstarter branch are simultaneously populated — but
  currently only the latter ever is (§9.4), and even then only ever produces one candidate.
- **Whether it consumes world state/beliefs/time/context:** confirmed **no** — `generate_immediate_actions(self, limit: int = 5)` (re-read this session, full signature) takes no
  argument but `limit`. It reads only `self._goals` (the persisted goal list). No world-state,
  belief, or time input reaches it at any point.

### 12.2 Design R6 — sequenced exactly per the task's preferred order

1. **Repair goal progress first (R3).** Non-negotiable prerequisite — building eligibility logic
   on a field that means "recently rewarded" rather than "needs attention" would systematically
   surface the wrong goals (Task 86's point, confirmed structurally sound and not contradicted by
   anything found this session).
2. **Introduce safe staleness/eligibility only after (1), and only as a graded replacement for the
   exact-`0.0` check** — e.g., `progress < some_low_threshold` combined with a genuine time-based
   "hasn't been advanced in N days" signal, now meaningful once `progress` no longer silently
   resets via reward accumulation. This is the only new logic this section proposes, and it does
   not touch `GOAL_ACTION_MAP`.
3. **Retain `GOAL_ACTION_MAP` exactly as-is** (per Rule 11) — every newly-eligible goal still maps
   through the existing, gateway-safe `SHORT→research_topic`/`MID,LONG→analyze_progress` scheme.
   This alone produces **more candidates of the existing two action types**, which is sufficient to
   satisfy the "≥2 legitimate competing candidates" objective **without any tag propagation at
   all** — e.g., once `g_karpathy_30` and `g_placement_prep` (both currently at 0.076, both
   currently ineligible) become eligible under a graded threshold, `generate_immediate_actions()`
   could return multiple `analyze_progress` candidates (different `goal_id`s) in the same tick,
   which is real competition once R5's key allowlist (§11) makes their `policy` terms distinguishable by
   `goal_id`.
4. **Measure candidate diversity** (via E6, §23) before proceeding further.
5. **Only later, as an explicitly separate, reviewed change, consider GREEN-only tag routing** —
   and per the task's explicit requirement, **it must include a GREEN-only construction-time
   allowlist**: filter `_TAG_TO_ACTION`'s resolved `action_type` against the GREEN tier list at the
   moment the candidate dict is built, falling back to `GOAL_ACTION_MAP`'s existing mapping if the
   tag-resolved type is not GREEN. Concretely: `g_vector_phase1`'s tags `["vector","coding","build"]`
   would resolve `"coding"` → `"code_task"` (RED) — the allowlist check would reject this and fall
   back to `GOAL_ACTION_MAP["MID"] = "analyze_progress"`, exactly preserving today's safe behavior
   for that specific goal while still allowing GREEN-mapped tags (e.g., a hypothetical `git`→
   `git_status`, if `git_status` is confirmed GREEN — **UNVERIFIED this session, must be checked
   before implementation**) to pass through.

### 12.3 Explicit composed test (per the task's requirement)

**Staleness eligibility and tag propagation must be tested together, not independently**, per the
task's explicit instruction — this session's own source read confirms exactly why: `g_vector_phase1`
sits at `progress=0.25`, ineligible under today's exact-equality rule; only the staleness change
admits it, and only the tag change re-types it to `code_task`. Neither change alone produces the
RED-tier escalation Task 86 found; **the composed test must construct the state where both changes
are active simultaneously and assert the GREEN-only allowlist still prevents `code_task` from ever
reaching a constructed `Candidate` object** — a test of the composition, not of either half in
isolation.

---

## 13. R7 — decision identity (Section 12 of the task)

**Design only. No new table — per Rule 9, and per this session's own confirmation that a new
table is not proven necessary.**

### 13.1 Why a new Experience table is not adopted

Confirmed this session: `Decision.all_candidates: list[Candidate]` already exists
(`decision_engine.py:41`, populated at `:537`) — every candidate considered in a tick, winners and
losers alike, is already held in one Python-level structure at decision time. Combined with the
already-existing per-cycle episodic writes (`decision_candidate` rows from `DecisionEngine`,
`governor_dispatch` rows from `Governor`, `gateway_audit` rows from `PermissionGateway`), the
missing primitive is **an id that survives from candidate to outcome**, not a new table to hold
them in.

### 13.2 Design

- **`decision_id`** — a ULID (monotonic, sortable), minted once per `_think_tick()` invocation that
  produces at least one candidate. Carried as a field on every `Candidate` object constructed in
  that tick (winners and losers alike — resolving the task's explicit requirement that losers be
  identifiable).
- **`candidate_id`** — a ULID minted per individual `Candidate` within that tick, distinct from
  `decision_id`. **Both are required**, per the task's own framing: `decision_id` answers "which
  think-tick was this", `candidate_id` answers "which specific candidate within it" — needed
  separately because a single tick can and (after R6) should produce multiple candidates, each of
  which has its own eventual disposition.
- **Disposition, per candidate, using values already implied by existing code paths** (not
  invented): `proposed` (default) → `vetoed` (counterfactual block) → `gated_denied` (Permission
  Gateway rejection) → `dispatched` (reached `governor.dispatch()`) → `executed` (agent ran) →
  `failed` (exception/error status) → `abandoned` (no outcome ever recorded — a timeout/never-
  resolved case).
- **Stamping, not a new table:** `decision_id`/`candidate_id`/`disposition` are added as fields
  inside the existing `context`/`params` JSON blob already written on the `decision_candidate`
  episodic row (no schema change to `episodic_memory` required, since `context_snapshot` is
  already a JSON column), and the same `decision_id` is passed through to the `gateway_audit` row
  (which already has room for it via its own JSON-capable fields, **UNVERIFIED — the exact
  `gateway_audit` schema was read in a prior session as `seq, ts, action_type, level, approved,
  executed, proposed_by, reason` with no JSON column; adding `decision_id` here would require
  either a new nullable column or folding it into `reason` — this is a real open schema question,
  not resolved by this document, and must be decided during implementation, not assumed**) and into
  `policy_memory`'s update call (as an optional parameter to `update_from_outcome`, logged
  alongside the reward write, not necessarily as a new persisted column if a log-line correlation
  is sufficient for the first version).
- **Losers, vetoed, denied, executed, failed, retries, plan steps, async outcomes, partial success,
  abandoned actions** — represented via the `disposition` enum above (covering the synchronous
  cases) plus, for retries specifically, a `parent_candidate_id` field (null except on a retry,
  pointing at the original `candidate_id`) — this is the one place this design adds a relation
  beyond a flat stamp, because retries genuinely need to reference their predecessor and no
  existing structure does this today. Asynchronous outcomes (e.g., a `ScriptGenerator` output whose
  real value is only knowable later, §14) are represented by leaving `disposition="executed"` with
  a null final reward until a later process resolves it — explicitly **not** solved by this
  document (§14 addresses why not).

### 13.3 Minimum viable version, if full stamping is judged too large for one implementation step

If even this reduced design is judged too large for a single bounded implementation task (§26),
the absolute minimum is: mint `decision_id` per tick, log it once in the existing
`Winner:`-line log statement, and stamp it into the `decision_candidate` episodic row's existing
JSON context field only. This alone makes E2 (§23) answerable via a log/DB join, with zero schema
changes anywhere, at the cost of not yet covering gateway/policy correlation — an acceptable first
increment, explicitly smaller than the full design above.

---

## 14. R8 — self-correction (Section 16 of the task)

**Design only. Not implemented.**

**Traced this session:** `CorrectionLearner.validate_lesson(self, lesson_id: str, outcome_good:
bool) -> None` (`correction_learner.py:591`) exists, is well-formed (confirmed via its own unit
tests, which exercise both the `outcome_good=True` confidence-increase path and the
`outcome_good=False` confidence-decrease path), and has **zero production callers** — confirmed by
a repo-wide grep this session returning matches only in `tests/unit/test_correction_learner.py`
and `tests/integration/test_correction_integration.py`.

**Why it has zero callers:** no code path in `autonomous_loop.py`, `governor.py`, or any district
agent calls it after an action's outcome is known. The capture/store/inject side of
`CorrectionLearner` (an owner correction becomes a lesson, and the lesson is later injected into a
prompt) is real and wired; the *feedback* side (did following that lesson actually help) was built
and tested but never connected to the outcome-attribution machinery that would need to call it.

**Is wiring it safe?** Yes, with the exact prerequisite ordering below — it consumes an
`outcome_good: bool`, which requires the caller to already know whether an action succeeded, which
already exists at the point the 5-factor reward is computed (`autonomous_loop.py:~1240`). Wiring
this is strictly additive (a new call at an existing, already-safe point) and does not touch
`PermissionGateway`, `Governor`, or any action-reachability path.

**Specification (design only):**
- **Input contract:** `lesson_id` (must reference a lesson previously injected into the prompt that
  led to this action — requires that the injection path already tags which lesson(s) were active,
  which was not verified this session and must be checked before implementation), `outcome_good`
  (derived from the same `completed`/`reward` values already computed in the 5-factor block).
- **Trigger:** immediately after the 5-factor reward is computed, on the executed (non-vetoed)
  path only — the same gate that already exists for the goal-progress write (§9) and the
  `record_epistemic_belief` call, so this is a fourth call added to an already-established
  "on real outcome" call site, not a new trigger mechanism.
- **Provenance:** inherited from whatever `CorrectionLearner`'s existing capture path already
  records (not re-designed here).
- **Validation:** the function itself already validates internally (per its existing tests) —
  no new validation logic proposed.
- **Persistence:** unchanged — `CorrectionLearner`'s existing store.
- **Rollback:** the call can be removed with zero data consequence (it only updates confidence on
  existing lesson records; removing the call stops future updates, it does not need to undo past
  ones for the system to return to its current, safe, disconnected state).
- **Effect on future behavior:** a lesson's confidence, once wired, would affect how strongly it is
  weighted when later injected into a prompt — **UNVERIFIED whether the injection path actually
  reads a confidence-weighted selection today**; this must be confirmed as a second prerequisite
  before wiring `validate_lesson()` is worth doing (wiring the write side without a read side that
  uses the result would just be another orphaned mechanism, the exact pattern this whole
  reconciliation is trying to stop creating).
- **Tests required:** an integration test asserting a real (mocked-outcome) execution cycle that
  used a tagged lesson calls `validate_lesson()` exactly once, with the correct `outcome_good`
  value derived from the actual `completed`/`reward` state.

**Sequencing (answering the task's explicit question):** **after** the first L4 proof (§23's E1),
not before — per this document's overall ordering (§25), R8 is scheduled after R3-R7 specifically
because its value is highest once the reward-attribution chain it depends on (which lesson was
active, what the real outcome was) is itself trustworthy, and because it is explicitly the
cheapest item on the list (per Task 86's own characterization, independently found accurate this
session), it can absorb being scheduled later without cost.

---

## 15. R9 — epistemic prerequisites (Section 15 of the task)

**Design only. `belief:*` is NOT connected to scoring anywhere in this document, per Rule 14.**

**Traced this session, consistent with this conversation's own prior direct DB read (not
re-queried this session since the underlying `epistemic.db` state has not changed):**
`action_domain:*` (3 claims: `git`, `commit`, `search`) is read by `_epistemic_penalty()` before
every score; `belief:*` (4 claims: presence, screen-activity ×2, goal-progress summary) is written
every cycle by `track_beliefs()` and read by nothing that scores a decision.

**Contradiction, previously confirmed, cited not re-derived:** `belief:presence:absent` (confidence
0.70) and `belief:screen_activity:active_coding` (confidence 0.70) held simultaneously — the table
has no mechanism to flag this as inconsistent; same-key writes simply overwrite, cross-key
inconsistency is not modeled at all.

**Design, prerequisites only:**

1. **`last_write_attempt` vs. `last_seen_at` — evaluated, and adopted as necessary.** The staleness
   decay currently cannot distinguish "this domain's evidence genuinely aged out" from "nothing
   attempted to write to this domain because execution itself starved" (§9's veto loop being the
   exact cause for `action_domain:*`). Recording `last_write_attempt` (updated every time the code
   *tries* to record an outcome, even if the outcome never materializes because execution was
   vetoed) separately from `last_seen_at` (updated only on an actual successful write) lets a
   future consumer distinguish "72h since anyone even tried" from "72h since the last real
   measurement" — a one-field addition to the existing claim-write function, not a new subsystem.
   **This belongs in the epistemic write path itself** (`record_epistemic_belief()`), not in a
   separate tracker.
2. **Contradiction detection.** A same-key write with a materially different value inside the TTL
   window should emit a `contradiction` log/event rather than silently overwrite — a comparison and
   a log line, confirmed feasible with no new persistence. **Cross-key contradiction** (the
   presence/screen-activity example) requires a small, explicit, hand-maintained list of
   known-incompatible key pairs (e.g., `presence:absent` vs. `screen_activity:active_*`) checked at
   write time — this is a finite, reviewable list, not a general inference engine, and should stay
   that way.
3. **Bounded, symmetric influence, if and when belief→scoring is ever built (not now):** reuse the
   existing `[0.70, 1.0]` clamp from `_epistemic_penalty()` verbatim; never widen it; a belief may
   dampen a score, it may never veto one outright (satisfying Rule 14's spirit even for future
   work, not just the present).
4. **Calibration before consumption.** Before any belief namespace is allowed to influence scoring,
   its agreement with ground truth should be measured over a window — an offline check, not a
   subsystem, and one that `presence` demonstrably fails today given the contradiction in (this
   section, above).

**Explicitly NOT designed further here, per Rule 14:** any actual connection from `belief:*` into
`_score_candidate()`. This section defines only the four gates that would need to pass first.

---

## 16. R10 — decision provenance (Section 12/14 of the task)

**Design only.**

Building on R7's `decision_id`/`candidate_id` (§13): once every candidate in a tick carries an id,
`Decision.all_candidates` (already existing, §13.1) provides the runner-up(s) "for free" — no new
generation mechanism needed. **Decision provenance** (recording which alternatives were considered
and what happened to the chosen one) is achieved by: on veto or execution, write a `scenario` row
(reusing `CounterfactualMemory`'s existing, currently-empty `scenarios` table) referencing
`{chosen_candidate_id, alternative_candidate_id, decision_id}`, with the alternative's outcome
left explicitly `null` forever (it was never run) — exactly Task 85's "do not fabricate" principle,
now given a concrete id-based shape rather than a hand-rolled reference. No write-back aggregate
into `PolicyMemory` is included in this design (§17 explains why that specific idea is dropped).

---

## 17. Counterfactual / exploration future plan (Section 14 of the task, "future plan" framing)

**Not implemented. Prerequisites only, per Rule 13 (do NOT enable exploration).**

**Renaming, adopted:** the near-term capability built by R10 should be called **decision
provenance / alternative tracking**, not counterfactual reasoning. Confirmed this session (no
counter-evidence found): the existing `scenarios`/`outcomes` tables have zero rows across the
entire lifetime of the DB per Task 84's prior full dump, and nothing in current source computes or
stores a predicted/simulated outcome for an untaken alternative — recording "what else was
considered" is honest; claiming to know "what would have happened" is not, and R10 does not claim
the latter.

**Why the write-back aggregate (Task 85's §5 idea) is dropped:** an aggregate like "of the last K
close calls where A beat B, how did A's outcomes trend" contains no information about B — it is a
statistic about A conditioned on B having existed, and writing it into A's own policy value as
though it were comparative evidence would double-count A's own rewards. This document does not
carry that idea forward.

**Prerequisites for real (exploration-based) counterfactual learning, specified but explicitly not
implemented:**
- ≥2 candidates competing in the same tick, reliably (R6's outcome, measured via E6).
- A clean reward channel, uncontaminated by suppression (R4).
- Stable attribution (R7).
- Working, canonical persistence (R5).
- **Permission-tier filtering at selection time, not execution time** — an exploration policy must
  never be able to select a YELLOW or RED action; the tier check must gate *which candidates are
  eligible to be explored*, before any selection logic runs.
- An explicit epsilon (small — 1-2%, per the range discussed in Task 86's proposal, evaluated here
  and found architecturally sound but **not adopted as an implementation** per Rule 13).
- A cooldown on exploration frequency, independent of the fanout cooldown (R2).
- An explicit kill switch (a config flag defaulting to off).
- Owner visibility — any exploration event should be logged distinctly and surfaced, not buried in
  routine dispatch logs.

**This document does not design the exploration mechanism itself beyond this prerequisite list**,
per Rule 13's explicit instruction.

---

## 18. TrustLadder interaction (Section 18 of the task)

**Independently verified this session, from source, not accepted on citation.**

`core/loop/trust_ladder.py`, read this session: `trust_promotion_streak` defaults to **20**
(`CONFIG["permission"].get("trust_promotion_streak", 20)`, line 85). Promotion logic (line 115):
`if not promoted and bad == 0 and streak >= self._threshold(): ...promote...`. Streak increments on
every explicit owner approval of a YELLOW action (line 105). Streak **resets to 0** on an explicit
owner rejection (line 140) or an execution failure (line 157). `promote()` (line 195) exists as the
actual state-transition function; a corresponding demotion path exists (line 216,
`"UPDATE trust_ladder SET promoted = 0, streak = 0, demoted_at = ?"`).

**Modeled interaction, per the task's exact chain:**
```
good reward (R3/R4/R5 working correctly)
   → higher policy score for that action_type
   → proposed more often (more ticks where it wins the argmax)
   → more chances for the owner to approve it
   → streak accumulates faster in wall-clock terms
   → crosses the promotion threshold (streak >= 20, zero bad outcomes) sooner
   → PermissionGateway's YELLOW branch begins auto-executing without a prompt
```

**Is this path actually reachable for any YELLOW action?** Yes, structurally — confirmed this
session that `commit_code` is a YELLOW-tier action (consistent with this conversation's own prior
direct reads of `config.py`'s tier lists in Tasks 82-85, not re-derived line-by-line again here),
and nothing in `TrustLadder`'s promotion logic references *how quickly* the 20 approvals
accumulated, only that they are consecutive and free of a "bad outcome." **A working policy-
learning loop that successfully increases how often a good YELLOW action is proposed would,
as a direct and intended-by-neither-mechanism side effect, shorten the wall-clock time to
promotion**, because more proposals in less time still only need 20 consecutive approvals to
reach the same threshold.

**Required controls (not implemented — recommendations only, per the task's instruction "recommend
controls if required"):**
1. **A minimum elapsed wall-clock window in addition to the streak count** — so an increase in
   proposal *rate* alone cannot manufacture promotion faster than some owner-reviewable pace (e.g.,
   "20 approvals **and** at least N days since the first approval in the current streak").
2. **Streak reset on any material change to the scoring path** — specifically, a `policy_key`
   schema version bump (R5's `v2:` prefix) should invalidate in-flight streaks, since the streak's
   evidentiary basis (repeated approval of what the *scorer* considers "the same" action) changes
   meaning when the scorer's own notion of sameness changes.
3. **Promotion events surfaced to the owner as an explicit notification**, not merely a database row
   — matching the existing pattern already used elsewhere in the gateway (Pushover approval
   requests), so a promotion is a visible event, not a silent state change discoverable only by
   querying `trust_ladder` directly.

**This document does not modify `TrustLadder`**, per Rule 18's explicit instruction.

---

## 19. Agent lifecycle deferred analysis (Section 17 of the task)

**HP shaping and successor lifecycle are NOT fixed in this document, per Rules 15/16.**

### 19.1 APITester stale-reference hypothesis tree (static tracing only, no runtime interaction)

Restating and organizing this conversation's own prior direct findings (Tasks 82/83, re-affirmed
by Task 84/86, not re-derived from scratch this session since the underlying source and historic
log evidence have not changed):

**Established facts:**
- `AgentRegistry.deregister("api_tester_001")` fired exactly once in the 107h boot examined,
  succeeded (ghost saved, ID popped from `_agents`), hit the `spawn_successor()` dict/attribute
  `AttributeError`, and correctly executed the fallback path (`fallback spawn: APITester gen=2`,
  a fresh UUID, generation 2, 500 HP).
- From that point forward, zero further `[VECTOR][agent_registry]` log lines of any kind appear,
  yet `"Agent APITester gen 1 DIED"` continues to fire (5,558 times across the full boot), always
  `0->0` HP, always `generation 1`, always the domain-specific `api_failing`/`api_test_failed`
  reason.
- `Governor.dispatch()`'s agent-selection code re-queries `self._get_registry().get_by_district(district)`
  **fresh, every call** — confirmed via direct source read in this conversation's own prior turn —
  ruling out a stale reference held *inside Governor's own dispatch method*.

**Hypothesis tree (none confirmed; static tracing only, as instructed):**

1. **H1 — A closure or callback captured the original object by reference before deregistration,
   and something re-invokes that captured reference directly, bypassing `get_by_district()`
   entirely.** Candidate locations, none traced to a specific line this session: an event-bus
   subscriber list built once at boot (`auto_subscribe_all()`, if it captures agent objects rather
   than looking them up by id at dispatch time); a scheduled/`APScheduler` job registered with a
   bound method of the original object; a `functools.partial` or lambda created during agent
   registration that closes over `self` and outlives deregistration.
2. **H2 — A second, independent code path holds its own agent cache**, separate from
   `AgentRegistry._agents`, populated once and never invalidated on death. Candidate: any module
   that calls `get_by_district()` once at import/init time and caches the result, rather than
   calling it per-dispatch (the opposite of `Governor.dispatch()`'s own confirmed-fresh pattern —
   worth checking whether every *other* caller of `get_by_district()`/`get_registry()` in the
   codebase shares Governor's fresh-query discipline, which was not exhaustively checked this
   session).
3. **H3 — A task object itself captured the agent reference at construction time**, and something
   re-submits an old task object (from a queue, a retry mechanism, or the fanout's own
   `_tracked_task` set) that still points at the pre-deregistration object rather than re-resolving
   the agent at execution time.
4. **H4 — The observed "gen 1" behavior is not the same Python object surviving, but a
   *reconstruction* that happens to reproduce identical state** (e.g., something re-imports and
   re-instantiates `APITester()` fresh, which would explain `generation=1`/hardcoded `agent_id` per
   its own `__init__`, but would contradict the earlier finding that `instantiate_all()` is
   boot-only with no periodic re-invocation — this hypothesis requires finding a *second* call
   site to `APITester()`'s constructor beyond `ManifestLoader`, which was not found in any of
   Tasks 82-86's greps and is therefore the **least likely** branch of this tree, listed for
   completeness rather than promise).

**Recommended next static-tracing step (not performed in this session — explicitly deferred as the
next investigation, not this document's job to complete):** grep every call site of
`get_by_district(` and `get_registry(` repo-wide and check, for each, whether the result is stored
in a variable that outlives the calling function's scope (H2), and separately grep for anywhere an
`AgentBase`/`APITester` instance is passed into a `functools.partial`, a lambda, an
`asyncio.create_task` closure, or an `APScheduler` job registration (H1/H3).

### 19.2 Future lifecycle repair (defined separately, per the task's instruction, NOT designed in
detail here)

Once the stale reference is traced (§19.1's next step), the successor dict/attribute contract fix
(call `spawn_from_ghost()`, the already-correct object-returning API, instead of patching
`spawn_successor()`'s dict-returning legacy path) and the HP habituation-asymmetry fix (make
`deduct_points()`'s shaping symmetric with `award_points()`'s, or otherwise address the fact that
`_reason_award_counts` is in-memory-only and resets every boot/successor-spawn) should ship
**together, as one "agent lifecycle correctness" change, after the cognitive/reward measurements
in §23 are no longer in flight** — per Task 86's reasoning, independently endorsed here: changing
agent selection during the exact window used to measure whether policy learning changes behavior
would confound attribution of any observed change.

---

## 20. Memory simplification (Section 19 of the task)

Reusing and independently cross-checking this session's own verified facts against the
classification the task requires:

| Mechanism | Classification | Disposition |
|---|---|---|
| Agent HP → selection | ACTIVE-BUT-SATURATED | **FREEZE** (Rule 15; do not touch until after the learning-measurement window per §19.2) |
| Goal progress → `goal_alignment` | **DANGEROUSLY-MISLEADING** (its own label as reward-accumulator wearing a progress label; already deleted one goal) | **CONNECT/REPAIR** — R3, highest priority in this document |
| PolicyMemory (veto writer) | ACTIVE-BUT-SATURATED (constant) | **REPAIR** — R4 |
| PolicyMemory (5-factor/VC/plan writers) | ORPHANED | **CONNECT** — R5 |
| PolicyMemory (Hands writer) | ORPHANED, structurally — no matching `Candidate` is ever built for a hand's `action_type` | **DEPRECATE** — cannot be connected without inventing hand-originated candidates, out of scope here |
| CounterfactualMemory `rejections` | ACTIVE | **FREEZE** — it works, as designed, for its one job |
| CounterfactualMemory `scenarios`/`outcomes` | DORMANT (0 rows, schema present) | **FREEZE until R10/exploration prerequisites are met** |
| Epistemic `action_domain:*` | ACTIVE mechanism / DORMANT signal (starved by the veto loop, not by its own design) | **CONNECT via R3's execution unstarving — not via a new write path** |
| Epistemic `belief:*` | ORPHANED | **FREEZE** (Rule 14) until R9's four gates pass |
| EpisodicMemory | ACTIVE (anticipation) / AUDIT-ONLY (everything else) | **KEEP as ground truth, unchanged** |
| SemanticMemory | Effectively DORMANT (`goals_v1` is its only decision-relevant key, itself now understood to carry the R3 defect) | **KEEP for now** — moving goals to their own table (Task 86's suggestion) is a real, reasonable idea but is a schema change beyond this document's "no new memory subsystem" constraint (Rule 7) interpreted conservatively; **flagged for owner decision, not adopted as a change here** |
| ReasoningMemory (`reasoning_chains`) | DORMANT, HTTP-endpoint-only reader | **DEPRECATE the "learning signal" framing** — relabel as an export/debug view in any future report; do not delete the table or its writer |
| ReasoningBank (file) | **DANGEROUSLY-MISLEADING** — injected into a field (`reasoning_steps`) that `total_score` never reads, giving the appearance of reasoning-informed scoring with zero actual effect | **DEPRECATE the injection call specifically** — this is the one item in this whole document recommended for outright removal (of the injection call only, not the file/bank itself), because it costs a read+write per scoring cycle for a provably zero behavioral effect and creates a specific, named misleading appearance (a "reasoning_steps" field on every candidate that looks consulted and is not) |
| Ghost memory / `agent_history` | DORMANT (`get_system_prompt()`, its only consumer, has zero callers — confirmed independently in this conversation's own prior Task 82/84 greps, not re-run this session) | **KEEP `agent_history` as an audit record; do not build the prompt-injection consumer as part of this programme** |
| CorrectionLearner | PARTIALLY ACTIVE (capture/store/inject real; `validate_lesson` unwired) | **CONNECT** — R8 |
| Anticipation | ACTIVE, deterministic | **FREEZE** |
| `TrustLadder` | ACTIVE, real streak/promotion machinery | **FREEZE** (Rule 18) — controls recommended, not applied |

**Is "approximately five load-bearing stores" (Task 86's proposed end-state) achievable without
breaking functionality?** Directionally yes — episodic (ground truth), policy (reward, post-R4/R5),
epistemic (reliability + belief, post-R9), counterfactual (rejection blocklist + dormant scenarios),
and a slimmed semantic store (once goals move out, which this document does **not** do) would
approximate that count. **This document does not perform that consolidation** — it is a
multi-step migration touching several schemas and is explicitly out of scope for a
read-only specification whose own Rule 7/9 constrain it from creating *or*, by extension,
prematurely collapsing memory structures without a dedicated, reviewed migration plan. It is
recorded here as a plausible **future** direction, not a change in this document.

**Conservatism, per the task's explicit instruction:** no historical data is deleted anywhere in
this section's dispositions. `ReasoningBank`'s injection call is the sole exception recommended for
outright removal, and even there, only the *call site*, not the underlying file/bank or any
historical data it holds.

---

## 21. Model vs. architecture (Section 21 of the task)

| Limitation | Cause | A larger/better LLM would NOT help because |
|---|---|---|
| One candidate per cycle, 1,198/1,198 identical | **D** (memory/connectivity — the goal-progress loop, §9) + **C** (orchestration — `generate_immediate_actions` takes no context argument, confirmed this session) | No LLM participates in candidate generation at all; the function is a pure loop over a persisted list |
| Policy value frozen at 0.05 | **F** (attribution — key mismatch, §11) + **G** (data/schema — suppression merged into reward, §10) | Neither defect is a reasoning failure; both are serialization/schema bugs |
| No situation similarity, exact-hash only | **B/G** (architecture/schema) — and this is the one place model capability (embeddings) is plausibly the *right* tool for a **future**, separate phase | A bigger model does not change how `sha256(action_type+params)` behaves; the architecture would need to consume a different kind of input before a bigger model could help at all |
| `_multi_backend_fallback` unbounded | **E** (runtime — confirmed this session, §5) | Purely a missing bound on a synchronous call chain; no model involved |
| Event-loop ~1,000× slowdown | **E** (runtime) + **C** (orchestration — the fanout load) | Same reasoning |
| "AI trends" ×7,401 | **G** (data/schema — hardcoded default) + **C** (orchestration — task_type discarded by the event bus) | The prompt/topic is a Python literal string; no model call is even reached with distinguishing information |
| Event fanout repetition (43,312/107h, 2 closed cycles) | **C** (orchestration) | Structural, in the event-wiring tables, not in any model's output |
| Beliefs disconnected from scoring | **D** (memory/connectivity — disjoint namespaces) | The read call site simply does not exist; no model change adds a call site |
| TrustLadder promotion sensitivity to learning rate | **F/H** (governance + mixed) | A scheduling/threshold design gap, not a capability gap |
| No consequence prediction / world model | **A** (model capability) **and G** (architecture — no substrate exists to consume a prediction even if one were generated) | The one item on this list where a model genuinely matters, and even here, architecture must exist first to use it |

**Adopted verdict, matching Task 86's and independently consistent with everything re-verified
this session: nothing in R0-R10 is a model-capability problem. No model change is warranted
anywhere in this specification.** `situation_class`-style generalization (§9's deferred item, §11's
item 10) is flagged as the one place a future phase should evaluate model capability (embeddings)
against hand-rolled architecture (bucket functions) rather than assuming architecture is the
answer by default.

---

## 22. Understanding boundary (Section 20/22 of the task)

| Capability | CURRENT | AFTER R0–R10 | Requires |
|---|---|---|---|
| A. Reward learning | Broken (mis-keyed, contaminated, confounded by the goal-progress loop) | **Real, honest, closed** — the actual deliverable of this document | Architecture only (this spec) |
| B. Policy adaptation | Frozen at a constant | **Real**, measurable via E1/E6 | Architecture only |
| C. Contextual decision making | Absent — no context reaches candidate generation | **Still absent** — R0-R10 does not add context to `generate_immediate_actions()` beyond goal state itself | New architecture (a future, separate phase) |
| D. Situational understanding | Absent — identity is a hash, not a representation | **Still absent** | New architecture + likely model capability |
| E. Causal reasoning | Absent — `causal_graph` is written every cycle **[V, confirmed this session]** and never read by anything | **Still absent** — R0-R10 does not add a reader | New architecture |
| F. Self/world model | Absent | **Still absent** | New architecture + model capability |
| G. Consequence prediction | Absent | **Still absent** | New architecture + model capability |
| H. Generalization | Architecturally impossible today (exact-hash keying) | **Still architecturally impossible** — R5 fixes the hash's correctness, not its coarseness | New architecture (situation representation), evaluate model capability (embeddings) before building a hand-rolled bucket |
| I. Self-correction | `validate_lesson()` exists, unwired | **Wired (R8)** — a real, if narrow, capability gain | Architecture only |
| J. Autonomous agency | Real but decentralized-and-ungated-for-district-dispatch by design (Task 84's finding, unchanged) | **Unchanged** — R0-R10 touches none of the safety architecture | Not in scope for this document |

**Explicit statement, per the task's instruction:** R0-R10 does not create, and does not claim to
create, a foundation for C, D, E, F, G, or H. It closes A and B, and makes I real. **The
Understanding Architecture (V3, or whatever it is eventually named) remains a wholly separate,
later programme**, whose first design question — "what representation does the decision layer
consume?" — has not been asked or answered anywhere in this document, per Rule 20.

---

## 23. Behavioral experiment programme (Section 22 of the task)

Adopting Task 86's E0-E6 sequence, independently reviewed this session against current source and
found sound; not altering its structure, since no evidence surfaced this session that would change
its design. Every experiment runs on Task 78's existing isolated lab first, then a disposable
clone. **None runs on the live process.**

- **E0 — Loop liveness.** *Setup:* disposable clone, R0's diagnostic instruments enabled.
  *Control:* none (this is the baseline-establishing experiment). *Treatment:* observe
  `observe_loop`/`think_loop` over a bounded window. *Expected result:* tick count and sleep-drift
  stay within a defined bound. *Falsification:* drift exceeds the bound, or tick count is far below
  the design cadence. *Confounders:* background load on the clone host must be controlled/noted.
  *Cleanup:* disable diagnostics after the run. *Live VECTOR prohibited:* yes. *Lab sufficient:*
  no — this specifically tests the runtime, which the lab does not model. *Clone required:* yes.

- **E1 — Policy learning.** *Setup:* lab first, then clone, post-R4/R5. *Control:* a key with zero
  prior samples. *Treatment:* feed N outcomes of a known reward to that key via the repaired
  writer. *Expected result:* `get_score()` for that key returns a value consistent with the
  cumulative-mean formula. *Falsification:* returned value does not match the formula's prediction.
  *Confounders:* ensure no other writer touches the same key during the test window. *Cleanup:*
  drop the test key's rows. *Live VECTOR prohibited.* *Lab sufficient:* yes, for the arithmetic;
  clone needed to confirm the real writer call sites reach it.

- **E2 — Outcome attribution.** *Setup:* post-R7, clone. *Control:* a second, concurrent, unrelated
  `decision_id`. *Treatment:* one `decision_id`'s outcome is resolved. *Expected result:* a single
  query returns the candidate/disposition/outcome/policy-row chain for the treated `decision_id`,
  and the control `decision_id`'s own chain is provably unaffected. *Falsification:* the control's
  state changes, or the treated chain cannot be reconstructed from one query. *Confounders:*
  concurrent dispatch activity must be bounded (this is exactly why R2's fanout cooldown must
  precede this experiment — otherwise the noise floor makes the control comparison unreliable).
  *Clone required.*

- **E3 — Persistence.** *Setup:* post-R3/R4/R5, clone. *Treatment:* E1's learned state, then a
  clean process restart on the clone. *Expected result:* the policy value survives; the (separately
  frozen, per Rule 15) HP habituation counters do **not** survive (an explicit, named, expected
  asymmetry, not a surprise). *Falsification:* the policy value is lost, or the habituation
  counters unexpectedly persist. *Live VECTOR prohibited* — restart testing never touches the live
  process.

- **E4 — Update-rule characterization.** *Setup:* lab, any stage after R4. *Treatment:* feed k
  reversed-sign outcomes to keys pre-seeded at `n ∈ {1, 10, 100, 10000}` samples. *Expected result:*
  record how many reversed outcomes are needed to flip the `argmax` at each `n`, characterizing
  whether the existing plain cumulative mean (confirmed this session to have no decay term visible
  in the reader/writer contract re-checked) can represent "this stopped working" in a reasonable
  number of samples. *Falsification:* not applicable in the pass/fail sense — this experiment
  produces a characterization, and its "failure" is a finding (e.g., "at n=10,000 no realistic k
  flips the winner") that would itself justify a future EMA/decay design, not something this
  document assumes the answer to in advance.

- **E5 — Contradiction handling.** *Setup:* post-R9's contradiction-logging addition, lab or clone.
  *Treatment:* write the exact pair already observed live (`presence:absent` +
  `screen_activity:active_coding`). *Expected result:* a contradiction event is logged. *Falsification:*
  silent overwrite with no event. *This is the precondition for ever allowing belief:* → scoring,
  per Rule 14 — a pass here does not unlock that connection, it only proves the logging mechanism
  itself works.

- **E6 — Native candidate competition.** *Setup:* post-R6, the **unmodified live candidate
  generator** running against the real (repaired, per R3) goal set, on a disposable clone, for a
  bounded window, unattended. *Control:* the same generator's behavior pre-R6 (the historical
  1,198/1,198-identical baseline, already established and frozen). *Treatment:* count ticks
  producing ≥2 distinct `action_type`s. *Expected result:* a nonzero, measurable percentage of
  ticks show real competition. *Falsification:* the percentage is statistically indistinguishable
  from the pre-R6 baseline (i.e., R6 did not actually change anything observable). **This is the
  gate this document treats as decisive**, per Task 86's correct observation, independently
  endorsed: **every other experiment in this list can pass using experimenter-constructed
  candidates and still leave open whether VECTOR's own generator, unattended, ever produces
  competition. E6 is what closes that gap, and if it fails, no claim of L4-in-production may be
  made regardless of what E1-E5 show.**

**Additional experiments judged necessary beyond E0-E6, this session:** none identified beyond
what Task 86 already specified — the six-stage sequence, gated in order, is judged sufficient for
the scope of R0-R10 (a reward loop, not an understanding system). Generalization (Task 85's
Experiment C, Task 86's "E7") remains explicitly unschedulable until a situation representation
exists (§22), and this document does not invent one to make it schedulable early.

---

## 24. L0–L5 ladder, VECTOR-specific (Section 23 of the task)

Adopted from Task 86, independently checked against this session's own source re-reads and found
consistent; the plain-cumulative-mean characterization (no decay, `new_avg = (old_avg·n +
reward)/(n+1)`) was not itself re-derived line-by-line from `policy.py`'s `update_from_outcome`
this session, but is consistent with the reader/writer contract re-confirmed here and with every
prior task's independent citation of it, so it is carried forward as **[T86, consistent]** rather
than re-verified from scratch.

- **L0 — Storage.** A row appears under the canonical key. *Current state: PASS* (29,164 samples,
  under the pre-fix key — historically real, informationally near-empty per §10).
- **L1 — Retrieval.** Reader-key ≡ writer-key for the same logical situation. *Current state: FAIL
  for 3 of ≥8 writer implementations* (§11.1). *After R5: PASS, pending the allowlist/version-prefix
  design landing correctly.*
- **L2 — Influence.** The retrieved value is non-constant and demonstrably changes `total_score`.
  *Current state: FAIL* (`policy=0.05` in all 1,198 measured cycles). *After R4+R5: testable via E1.*
- **L3 — Persistent learning.** A named `decision_id`'s outcome is shown to move a specific row by
  the predicted amount, surviving a restart. *Current state: mechanically available, never
  demonstrated with attribution.* *After R3+R4+R5+R7: testable via E2+E3.*
- **L4 — Behavioural adaptation.** The winner changes between otherwise-matched candidates as a
  direct, controlled result of an L3 update. *Current state: LAB PROVEN (Task 78), never CLONE
  PROVEN or PRODUCTION PROVEN.* *After R0-R10 + E1/E6: CLONE PROVEN would become achievable; this
  document explicitly does not claim PRODUCTION PROVEN without a live-system experiment, which
  remains prohibited by this task's own rules regardless.*
- **L5 — Generalization.** A zero-sample key inherits a non-default score from a related key, and
  an unrelated key demonstrably does not. *Current state: architecturally impossible* (exact-hash
  keying, confirmed again this session via the `params` allowlist design in §11 — which
  *intentionally* keeps generalization impossible by excluding cross-goal sharing, per §11.2 item
  10). *Remains impossible after R0-R10, by design — deferred to the separate Understanding
  programme (§22).*

**Explicit distinction maintained throughout this document, per the task's requirement: LAB PROVEN
≠ CLONE PROVEN ≠ PRODUCTION PROVEN.** No claim in §32 upgrades any of these without the
corresponding experiment having actually run.

---

## 25. Implementation order (Section 25 of the task)

**Adopted, with the reasoning independently re-derived this session from the reconciliation in §3,
not merely copied from Task 86's own ordering.**

| Stage | Why now | Why not earlier | Why not later | Dependencies | Risk | Blast radius | Baseline required | Tests | Behavioral proof | Rollback |
|---|---|---|---|---|---|---|---|---|---|---|
| **R0** | Nothing else may safely ship without naming the starvation mechanism first, and doing it first preserves the one loud anomaly signal that exists | N/A — first step | Every later stage's measurements would otherwise run inside unexplained noise | None | None (read-only instrumentation) | Zero (disposable clone only) | Immutable DB snapshot | N/A (diagnostic, not code) | Named mechanism or explicit bounded-unknown | Disable instruments |
| **R1** | The proven unbounded primitive (§5) sits upstream of every coroutine and the entire dispatch path; fixing it here fixes 21 coroutines and 43,312/107h of dispatch exposure at once | Before R0's result would mean fixing before diagnosing | After R1, every later stage's clone-based experiments run against a system that cannot hang indefinitely mid-measurement | R0 (diagnostic informs whether R1 alone is sufficient or a second mechanism remains) | Low — strictly bounds an unbounded call; cannot introduce new blocking (per §7's own analysis of what it cannot fully solve — cancellation) | One function (+ optionally two call sites) | R0's snapshot | Mocked-hang unit test | Thread dump shows no unbounded frame post-fix | Revert one function |
| **R2** | It is the load generator for R1's problem and the noise floor for every future measurement (§8); monotonically safe by construction | Before R1 it would reduce noise but not remove the underlying unbounded risk | After R2, every clone-based experiment from E2 onward runs against a materially quieter system | R1 (recommended, not strictly required — R2 is safe independent of R1) | Very low — can only reduce dispatch volume | In-process dict, one function | None beyond R0's | Cooldown-hit/duplicate-suppressed unit tests | Dispatch rate falls; no new `(district,task_type)` pairs; `strategy` gone | Remove the cooldown check |
| **R3** | The largest (0.30-weight) persisted input to scoring is currently pathological and irreversibly self-destructive (§9); every day it ships later is a day closer to consuming the remaining goal set | Nothing later makes sense to build on top of a scoring input that is still actively deleting the data it depends on | Doing it after R6 (candidate diversity) would, per §9.6, actively accelerate the self-destruction under more candidates | R0 (baseline snapshot) | Medium — touches a live write path in the hot loop; mitigated by removing a write, not adding one | `goal_system.py` + one call site removal in `autonomous_loop.py` | `goals_v1` immutable snapshot | Unit tests asserting no `progress` change on execution; no auto-complete without an explicit criterion | E0 must already pass; a successful action no longer moves `goal_alignment` for its own goal | Revert the write removal; goal set is untouched by the fix itself (only future writes stop) |
| **R4** | Canonicalizing the key before this would merge a control-flow constant into the reward mean, permanently (§10) | Only makes sense once R3 stops corrupting the *other* half of the scoring input at the same time | Doing it after R5 would make R5 land the contamination it exists to fix | R3 (not strictly technical, but sequencing sense — no reason to separate channels while the other major scoring input is still broken) | Low-medium — a schema-additive change (new column/table), not a rewrite | `autonomous_loop.py`'s veto-write call site + a small schema addition | R0's snapshot | Tests in §10.1 | Veto and reward channels shown independently movable | Revert the write-site change; existing rows untouched |
| **R5** | The richest, most correct reward signal in the codebase (the 5-factor writer) is stranded by a byte-format mismatch; this is the single highest-leverage reconnection available, once R4 ensures it won't reconnect to something contaminated | Before R4, per above | Delaying past R6 would mean diversified candidates (R6) compete on a still-meaningless policy term | R4 | Low-medium — reuses an existing, already-correct function; the risk is entirely in the allowlist/version-prefix design being right, not in the mechanism | `policy.py` (wrapper), 4-5 writer call sites, the reader | R0's snapshot; old rows explicitly untouched | Cross-writer key-equality tests (§11.3's exact examples) | E1 | Revert the key function; writers resume writing unreadable (but harmless) keys |
| **R6** | A precondition for measuring anything L4-shaped (Task 78's own precondition); should not ship before R3 (§9.6) or before R4/R5 give the resulting competition a meaningful policy term to compete on | Before R3, would accelerate goal self-destruction (§9.6); before R4/R5, diversified candidates would compete on a meaningless/contaminated term | Nothing later depends on delaying it further once its prerequisites are met | R3, R4, R5 | Medium — the composed staleness+tags case is a real permission-relevant escalation path if shipped without the GREEN-only allowlist (§12.3) | `goal_system.py`'s eligibility check; `_TAG_TO_ACTION` call site, if/when tags ship | R0's snapshot | The composed test in §12.3, mandatory | E6 | Revert the eligibility threshold; `GOAL_ACTION_MAP` untouched throughout |
| **R7** | Needed to make R6's diversified competition measurable end-to-end (E2) | Before R5/R6 there is little to correlate yet | Delaying past R6 would leave E2 unrunnable when it's otherwise ready | R5 (shares canonical key concept), R6 (produces the multi-candidate ticks worth correlating) | Low — additive stamping, no new table (§13) | ULID minting + stamping into existing rows | None new | Round-trip stamping test | E2 | Remove the stamping calls; existing rows lose the new field, nothing else changes |
| **R8** | Cheapest real capability gain identified anywhere in this document; safe to schedule late because its value does not degrade by waiting | Its dependency (trustworthy outcome attribution) is only solid after R3-R7 | No reason to delay further once dependencies are met | R3–R7 (trustworthy `completed`/`reward`/attribution) | Low | One new call site in `correction_learner.py`'s consumer, at an existing "on real outcome" trigger | None new | Integration test in §14 | A tagged lesson's confidence measurably updates post-outcome | Remove the call |
| **R9** | Prerequisites-only (contradiction logging, starvation-vs-age distinction) are cheap and independently valuable; the actual belief→scoring connection stays frozen regardless of ordering (Rule 14) | Could technically run earlier (no hard dependency on R3-R8), but scheduled here because it is lower-leverage than R3-R7 and its own gates (calibration) are not yet met even after R7 | N/A — this is prerequisite work for a connection this document does not make | None strictly, though R0's snapshot helps | Low — logging additions only | `record_epistemic_belief()`'s write path | None new | E5 | E5 passes | Remove the added fields/log line |
| **R10** | Decision provenance is a natural consequence of R7's ids existing; scheduled last because it is the least urgent of the ten (nothing downstream currently depends on it) | Needs R7's ids to exist first | N/A — last by leverage, not by difficulty | R7 | Low | Populate the already-existing, currently-empty `scenarios` table | None new | Scenario-row creation test | Manual inspection: scenario rows correctly reference real alternative candidates | Stop writing scenario rows; table remains empty as today |

**Where this document changes Task 86's own stated order:** it does not, in substance — R0
through R10 above is Task 86's own corrected sequence, independently re-derived from the
reconciliation table in §3 rather than copied, and found, on that independent re-derivation, to
already be the leverage-correct order. The one addition is the explicit dependency/rationale table
above, which Task 86's own §14.2 stated more briefly.

---

## 26. Hard freeze list (Section 26 of the task)

All of the following remain untouched by this document and must not be touched by the first
implementation task that follows it:

- Understanding Layer (entire programme, §22)
- World model, self-model, causal reasoning (including `causal_graph`'s existing write path —
  audit its readers before building anything on top of it, do not build yet)
- Generalization / `situation_class` / embeddings
- Any new memory subsystem (Rule 7) and specifically the Experience table as Task 85 specified it
  (Rule 9, §13.1)
- New districts, new agents (Rule 17)
- HP shaping (Rule 15, §19.2)
- Successor lifecycle (Rule 16, §19.2)
- `GOAL_ACTION_MAP` (Rule 11, verified untouched by every R-stage above)
- Autonomous RED exploration, autonomous YELLOW exploration (Rule 12/13; §17's exploration
  prerequisites are specified, not implemented)
- Per-cycle LLM calls (Rule 19; none introduced anywhere in R0-R10)
- Frontend/HUD (Rule 18 of the top-level rules)
- The live experiment process itself, in its entirety (Rules 1-4)
- The historical 29,164-sample policy bucket (§10, explicitly frozen and relabeled, not migrated)
- The historical 30,504-row counterfactual history (§17, explicitly frozen)
- `TrustLadder` itself (Rule 18; controls recommended in §18, not applied)
- `belief:*` → scoring (Rule 14; §15/§9's prerequisites specified, connection not made)
- `ReasoningBank`'s underlying file/data (only its injection *call site* is recommended for
  removal, §20 — the bank itself is not deleted)
- Ghost memory / `ancestry` computation (§20 — kept as an audit record, no new consumer built)
- SemanticMemory's schema (§20 — flagged for a future, separate decision, not changed here)

---

## 27. Data migration / safety strategy (Section 27 of the task)

| Change | Schema change | Migration | Backup | Compatibility | Rollback | Historical preservation | Versioning |
|---|---|---|---|---|---|---|---|
| R3 (goal progress) | None (removes a write, adds a conditional guard) | None required | `goals_v1` snapshot before shipping | Existing goal records read identically; new `recurring`/`completion_criterion` fields are additive and optional | Revert the code; no data was transformed | All existing `progress`/`status` values frozen exactly as-is; `g_daily_commit`'s `completed` status is NOT reversed automatically | N/A — no schema version needed for an additive optional field |
| R4 (suppression separation) | Additive (new column or new small table) | None — new writes only; old rows unaffected | Not separately required beyond R0's general snapshot | Old rows remain readable exactly as before; new field defaults to a neutral value for pre-existing rows | Drop the new column/table; `avg_reward` writes resume their pre-fix (contaminated but unchanged) behavior | The 29,164-sample bucket is explicitly relabeled (in documentation, not in the DB) as "suppression-channel history", never migrated or deleted | N/A |
| R5 (key canonicalization) | None to the table; a new key *format* for new rows only | None — old and new rows coexist under different key prefixes forever | Not separately required | Old un-prefixed rows are simply never looked up by new code — they remain in the table, inert, forever, unless explicitly queried for historical analysis | Revert the key function; new writes resume using the old (broken) formulas | Old rows never modified or deleted | `v2:` prefix is the version marker; a hypothetical future `v3:` would coexist the same way |
| R6 (candidate diversity) | None | None | `goals_v1` snapshot (shared with R3's) | No effect on existing goal records | Revert the eligibility threshold function | N/A — no new data created that needs preserving | N/A |
| R7 (decision identity) | Additive fields inside existing JSON columns; possibly one new nullable column on `gateway_audit` (open question, §13.2) | None for existing rows (they simply lack the new field, which is treated as "pre-instrumentation, unknown") | Not separately required | Existing rows without a `decision_id` are valid and simply not correlatable — no consumer should assume every historical row has one | Remove the stamping calls; existing stamped rows keep their (now-unused) field, harmlessly | Nothing removed | N/A |
| R8, R9, R10 | None beyond what's described in their own sections | None | Not separately required beyond R0's general snapshot | Additive only | Remove the added call sites/fields | Nothing removed | N/A |

**Explicit, per the task's requirement:** at no point in R0-R10 is the 29,164-sample policy bucket
or the 30,504-row counterfactual history deleted, rewritten, or migrated. Both are explicitly
named, in this document, as **frozen baselines** — historical evidence of the pre-repair system's
actual behavior, valuable specifically because they are large, real, and now fully explained,
against which any future claim of improvement should be measured.

---

## 28. Exact implementation spec, per approved change

Per the task's instruction: no full source code; pseudo-code only where necessary to remove
ambiguity. Ordered per §25.

### R0 — Diagnostic
**FILE:** `core/loop/thread_dump.py` (enable only, no change); new temporary probe lines in
`core/loop/autonomous_loop.py` (`observe_loop`, `think_loop`).
**FUNCTION:** none changed; two new local blocks around existing `await asyncio.sleep(...)` calls.
**CURRENT BEHAVIOR:** sleeps are unmeasured; `thread_dump.py` exists but is off by default.
**DEFECT:** no evidence exists correlating the ~1,000× cadence collapse to a specific mechanism.
**DESIRED BEHAVIOR:** a named mechanism, or an explicit, bounded "unknown" with evidence of what
was ruled out.
**MINIMAL CHANGE:** enable `VECTOR_THREAD_DUMP_SEC` on a disposable clone; add the drift-probe
pseudo-code from §6.
**DO NOT CHANGE:** anything about sleep durations, timeouts, or coroutine structure — this is
observation only.
**DEPENDENCIES:** none.
**TESTS:** none (diagnostic, not production code) — but the probe's own log-line format should be
reviewed for correctness before use.
**BEHAVIORAL PROOF:** a run producing either a named blocking frame or a specific drift timestamp.
**ROLLBACK:** remove the probe lines; disable the env var.

### R1 — Bound `_multi_backend_fallback`
**FILE:** `core/inference/ollama_safe.py`.
**FUNCTION:** `_multi_backend_fallback(model, messages, timeout, *, caller_id)`.
**CURRENT BEHAVIOR:** accepts `timeout`, never uses it; three sequential `engine.generate(...)`
calls with no bound and no circuit breaker.
**DEFECT:** unbounded synchronous blocking, reachable from the highest-volume code path in the
system.
**DESIRED BEHAVIOR:** the entire fallback chain returns within `timeout` seconds regardless of
which engine is attempted or how it behaves.
**MINIMAL CHANGE (pseudo-code):**
```
def _multi_backend_fallback(model, messages, timeout, *, caller_id=...):
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_try_all_engines, model, messages)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            _record_observability(caller_id, model, "fallback", "", timeout*1000, status="timeout")
            return ""
```
where `_try_all_engines` is the existing three-engine sequential body, extracted unchanged.
**DO NOT CHANGE:** engine order; the "never raises, returns `""` on failure" contract; the Ollama
path's own semaphore/circuit-breaker (untouched by this function).
**DEPENDENCIES:** confirm (before implementation, not assumed here) whether each of
`LiteLLMEngine`/`AppleFMEngine`/`GemmaCppEngine`'s own `generate()` accepts a `timeout` kwarg — if
so, passing it through directly may be preferable to the thread-pool wrapper above; this is an
implementation-time decision this document flags but does not resolve, since the three engine
files were not read this session.
**TESTS:** mocked-hang unit test per §7; fallback-order regression test; status-field
distinguishability test.
**BEHAVIORAL PROOF:** R0's thread dump shows no main-thread frame inside a fallback call beyond
the bound, post-fix.
**ROLLBACK:** revert the one function.

### R2 — Fanout cooldown + retire `strategy`
**FILE:** `core/loop/autonomous_loop.py` (`_fanout_handler`); `core/event_bus/wiring.py`
(`EVENT_TRIGGER_MAP`, one entry removed).
**FUNCTION:** `_fanout_handler(event)`.
**CURRENT BEHAVIOR:** fires every matching downstream dispatch unconditionally, every time,
including into the unstaffed `strategy` district.
**DEFECT:** no dedup/cooldown; `strategy` dispatches are pure waste.
**DESIRED BEHAVIOR:** an edge that fired within its cooldown window is skipped; `strategy` no
longer receives dispatches at all.
**MINIMAL CHANGE (pseudo-code):**
```
_edge_last_fired: dict[tuple, float] = {}
def _fanout_handler(event):
    for (district, task_type, params_template) in get_downstream_tasks(event.event_type):
        edge = (event.event_type, district, task_type)
        now = time.monotonic()
        if now - _edge_last_fired.get(edge, -inf) < COOLDOWN_SECONDS:
            continue
        _edge_last_fired[edge] = now
        _tracked_task(governor.dispatch(build_task(district, task_type, params_template)))
```
Plus: remove the `ANALYTICS_READY -> strategy::review_analytics_insights` entry from
`EVENT_TRIGGER_MAP`.
**DO NOT CHANGE:** any other edge; the fanout's fire-and-forget task-tracking mechanism itself;
`Governor.dispatch()`.
**DEPENDENCIES:** none.
**TESTS:** cooldown-hit/duplicate-suppressed unit test; first-fire-always-succeeds test;
`strategy` edge absence test.
**BEHAVIORAL PROOF:** measured dispatch rate materially lower on a clone; no new
`(district, task_type)` pairs appear; zero `"no agents in strategy"` log lines post-change.
**ROLLBACK:** remove the cooldown check (revert to unconditional firing); re-add the `strategy`
entry if desired.

### R3 — Decouple goal progress from reward
**FILE:** `core/loop/autonomous_loop.py` (two write sites); `core/brain/goal_system.py`
(`update_goal_progress`).
**FUNCTION:** the goal-feedback block at `~1283-1298` and its plan-step equivalent at `~1515-1520`;
`GoalSystem.update_goal_progress()`.
**CURRENT BEHAVIOR:** `progress += round(0.10 * reward, 3)` on every successful linked action;
auto-`completed` at `progress >= 1.0` with no reactivation path.
**DEFECT:** `progress` measures accumulated reward, not achievement; auto-completion is
irreversible and has already permanently deleted one goal (`g_daily_commit`).
**DESIRED BEHAVIOR:** `progress` no longer moves as a side effect of reward; goals without an
explicit completion criterion do not auto-complete; a `recurring` goal resets rather than
permanently completing.
**MINIMAL CHANGE (pseudo-code):**
```
# autonomous_loop.py — REMOVE this block entirely (both write sites):
#   _increment = round(0.10 * reward, 3)
#   ... gs.update_goal_progress(_gid, _new_progress, ...)

# goal_system.py — update_goal_progress():
def update_goal_progress(self, goal_id, progress, note=""):
    goal = ...find by id...
    goal["progress"] = clamp(progress, 0.0, 1.0)
    if goal["progress"] >= 1.0 and goal.get("completion_criterion"):
        goal["status"] = "completed"
    elif goal["progress"] >= 1.0 and goal.get("recurring"):
        goal["progress"] = 0.0  # reset, stay active
    # else: no completion_criterion and not recurring -> stays active at >=1.0, no auto-complete
    ...persist...
```
**DO NOT CHANGE:** `GOAL_ACTION_MAP`; any existing goal's current `progress`/`status` value;
`g_daily_commit`'s `completed` status (left as-is unless the owner separately decides to recreate
it with `recurring=True`).
**DEPENDENCIES:** `goals_v1` snapshot taken first (shared with R0).
**TESTS:** a mocked successful-execution cycle asserting `progress` is unchanged; a goal without a
`completion_criterion` reaching `progress=1.0` via some other path (e.g., a manual API call)
asserting `status` stays `active`; a `recurring=True` goal at `progress=1.0` asserting it resets to
`0.0` and stays `active`.
**BEHAVIORAL PROOF:** E0 must pass first (per §23); then, a successful action on a linked goal
produces no `goal_alignment` change for that goal in the next scoring cycle.
**ROLLBACK:** revert the write-removal and the `update_goal_progress` conditional; no data
transformation was performed, so rollback is a pure code revert.

### R4 — Separate suppression from reward
**FILE:** `core/loop/autonomous_loop.py` (veto-write call site); `core/memory/policy.py`
(schema-additive).
**FUNCTION:** the counterfactual-veto block (`~1112-1118`).
**CURRENT BEHAVIOR:** `update_from_outcome(action_type, hash, reward=0.05)` — a hardcoded constant
written through the same channel as real outcome rewards.
**DEFECT:** merges a control-flow artifact with outcome measurements once keys are canonicalized.
**DESIRED BEHAVIOR:** vetoes are recorded, but never contribute to `avg_reward`.
**MINIMAL CHANGE (pseudo-code):**
```
# REMOVE: pm.update_from_outcome(action_type, hash, reward=0.05)
# ADD (new, additive column or small table):
pm.record_suppression(action_type, hash)   # increments a veto_count, never touches avg_reward
```
`CounterfactualMemory.record_rejection()` (already called at this site) is unchanged — the veto
remains fully observable there.
**DO NOT CHANGE:** `CounterfactualMemory.rejections`; the veto-detection logic itself
(`should_avoid()`).
**DEPENDENCIES:** none beyond R0's snapshot.
**TESTS:** per §10.1, all five listed.
**BEHAVIORAL PROOF:** a veto no longer changes `avg_reward` for its key; a real outcome still does.
**ROLLBACK:** revert the call-site change; drop the new column/table if added.

### R5 — Canonicalize the PolicyMemory key
**FILE:** `core/memory/policy.py` (wrapper around the existing `make_situation_hash`);
`core/loop/decision_engine.py` (reader); `core/loop/autonomous_loop.py` (3-4 writer call sites);
`hands/runner.py` (writer call site, if judged in-scope for this pass — see note below).
**FUNCTION:** `PolicyMemory.make_situation_hash()`.
**CURRENT BEHAVIOR:** exists, correct, unused by the reader or by four of the autonomous-loop
writers.
**DEFECT:** eight independent serialization implementations; the richest reward writer is
unreadable.
**DESIRED BEHAVIOR:** one function, imported everywhere; a versioned, allowlisted key.
**MINIMAL CHANGE (pseudo-code):**
```
class PolicyMemory:
    @staticmethod
    def make_policy_key(action_type: str, params: dict, source: str) -> str:
        defining = {k: params[k] for k in ("goal_id",) if k in params}  # allowlist; excludes "title"
        payload = json.dumps({"a": action_type, "p": defining, "s": source_category(source)},
                              sort_keys=True, default=str)
        return "v2:" + hashlib.sha256(payload.encode()).hexdigest()[:12]
```
Reader and all writers call `PolicyMemory.make_policy_key(...)` instead of their own formula.
**Note on `hands/runner.py`:** per §20's disposition (Hands writer = DEPRECATE, not connect), this
writer is **not** migrated to the new key in this pass — it has no matching `Candidate` to ever be
read back against, so canonicalizing its key would not connect anything.
**DO NOT CHANGE:** old, un-prefixed rows — left in place, never queried by new code, never deleted.
**DEPENDENCIES:** R4 (must ship first, per §11.4).
**TESTS:** the four exact examples in §11.3, as literal test cases.
**BEHAVIORAL PROOF:** E1.
**ROLLBACK:** revert the wrapper and the call sites; writers resume writing under their old
(disconnected but harmless) formulas.

### R6 — Candidate diversity (staleness only, this pass)
**FILE:** `core/brain/goal_system.py` (`generate_immediate_actions`).
**FUNCTION:** `generate_immediate_actions(self, limit=4)`.
**CURRENT BEHAVIOR:** admits a MID/LONG goal to the unstarter branch only at `progress == 0.0`
exactly.
**DEFECT:** post-R3, `progress` means something real again, but the exact-equality gate is still
needlessly narrow.
**DESIRED BEHAVIOR:** admits any goal that is genuinely under-attended, per a graded, deterministic
rule.
**MINIMAL CHANGE (pseudo-code):**
```
STALE_THRESHOLD = {"MID": 0.10, "LONG": 0.10}  # example, tune during implementation
for goal in self.get_active_goals():
    if goal["horizon"] in ("LONG", "MID") and goal.get("progress", 0) < STALE_THRESHOLD[goal["horizon"]]:
        # eligible — existing GOAL_ACTION_MAP mapping unchanged
        ...
```
**Tag propagation is explicitly NOT included in this pass** (per §12.2 item 5 — a separate,
later, reviewed change) — this minimal change is staleness-only.
**DO NOT CHANGE:** `GOAL_ACTION_MAP`; `_TAG_TO_ACTION` (still dead code after this specific change,
deliberately).
**DEPENDENCIES:** R3.
**TESTS:** a goal at `progress=0.076` (matching the live, currently-ineligible goals) becomes
eligible under the new threshold; `g_daily_commit`-shaped (`completed`) goals remain excluded
regardless of threshold (via the existing `status=="active"` filter, unchanged).
**BEHAVIORAL PROOF:** E6.
**ROLLBACK:** revert the threshold check to the original exact-equality condition.

*(A follow-on, separately-reviewed sub-change — tag propagation with the GREEN-only allowlist from
§12.2 item 5 — is specified but explicitly deferred past this pass, per the task's own sequencing
preference in Section 11.)*

### R7 — Decision identity
**FILE:** `core/loop/decision_engine.py` (`Candidate`, `evaluate()`); `core/loop/autonomous_loop.py`
(stamping into the existing episodic write).
**FUNCTION:** `Candidate` dataclass; `DecisionEngine.evaluate()`.
**CURRENT BEHAVIOR:** candidates have no persistent identity beyond their content.
**DEFECT:** no way to correlate a decision to its eventual outcome in one lookup.
**DESIRED BEHAVIOR:** every candidate in a tick carries a `decision_id` (shared across the tick)
and a `candidate_id` (unique per candidate).
**MINIMAL CHANGE (pseudo-code):**
```
# at the top of _think_tick(), once per tick:
decision_id = ulid()
# when building each Candidate:
Candidate(..., decision_id=decision_id, candidate_id=ulid())
# when writing the existing decision_candidate episodic row, include both ids in context_snapshot
```
**DO NOT CHANGE:** the episodic table's schema; `gateway_audit`'s schema (per §13.2's open
question — resolve at implementation time whether a new column or a `reason`-field encoding is
used, do not assume).
**DEPENDENCIES:** none beyond R5/R6 being useful to correlate against.
**TESTS:** round-trip stamping test — a tick's `decision_id` appears identically on every
candidate's episodic row from that tick.
**BEHAVIORAL PROOF:** E2.
**ROLLBACK:** remove the id-minting and stamping calls.

### R8 — Wire `validate_lesson()`
**FILE:** `core/loop/autonomous_loop.py` (the 5-factor reward block, new call).
**FUNCTION:** the existing outcome-computation block; `CorrectionLearner.validate_lesson()`
(unchanged).
**CURRENT BEHAVIOR:** `validate_lesson()` exists, correct, zero production callers.
**DEFECT:** an outcome→belief-confidence loop is built and tested but never closed.
**DESIRED BEHAVIOR:** every real outcome that used a tagged lesson updates that lesson's confidence.
**MINIMAL CHANGE (pseudo-code):**
```
if active_lesson_id is not None:  # requires confirming the injection path tags this — see below
    correction_learner.validate_lesson(active_lesson_id, outcome_good=(completed >= 1.0))
```
**DEPENDENCIES: UNVERIFIED prerequisite** — confirm the prompt-injection path actually records
which `lesson_id` (if any) was active for the current action before implementing this call; if it
does not, that tagging must be added first (a separate, smaller sub-task) or `validate_lesson()`
has no `lesson_id` to call with.
**DO NOT CHANGE:** `validate_lesson()` itself; the capture/injection side of `CorrectionLearner`.
**TESTS:** integration test per §14.
**BEHAVIORAL PROOF:** a tagged lesson's confidence measurably changes after a real outcome.
**ROLLBACK:** remove the call.

### R9 — Epistemic prerequisites
**FILE:** `core/loop/context_engine.py` or wherever `record_epistemic_belief()` lives (per Task
84's citation, not re-read line-by-line this session for this specific function's exact file).
**FUNCTION:** the belief-write function.
**CURRENT BEHAVIOR:** same-key writes silently overwrite; no starvation-vs-age distinction.
**DEFECT:** staleness is currently indistinguishable from starvation; contradictions are invisible.
**DESIRED BEHAVIOR:** both are recorded and distinguishable; a defined cross-key contradiction list
is checked at write time.
**MINIMAL CHANGE (pseudo-code):**
```
def record_epistemic_belief(key, value, confidence, ...):
    last_write_attempt = now()   # NEW — always updated
    if existing_value_differs_materially(key, value):
        log_contradiction_event(key, old_value, value)
    if CROSS_KEY_CONTRADICTIONS.get(key) matches a currently-held contradicting belief:
        log_contradiction_event(...)
    ...existing write, now also setting last_write_attempt...
```
**DO NOT CHANGE:** any scoring call site (`belief:*` remains unread by scoring, per Rule 14).
**TESTS:** E5.
**BEHAVIORAL PROOF:** E5.
**ROLLBACK:** remove the added fields/log lines; existing behavior resumes exactly.

### R10 — Decision provenance
**FILE:** `core/memory/counterfactual.py` (populate the existing, empty `scenarios` table).
**FUNCTION:** a new small function, e.g. `record_scenario(decision_id, chosen_candidate_id,
alternative_candidate_id)`, called once per tick where `len(all_candidates) >= 2`.
**CURRENT BEHAVIOR:** `scenarios`/`outcomes` tables exist, zero rows, ever.
**DEFECT:** no record of what alternatives were ever considered.
**DESIRED BEHAVIOR:** every multi-candidate tick records which alternative was foregone; its
outcome stays permanently `null`.
**MINIMAL CHANGE:** one function, one call site, at the point `evaluate()` returns a `Decision`
with `len(all_candidates) >= 2`.
**DO NOT CHANGE:** `should_avoid()`; no write-back into `PolicyMemory` (explicitly excluded, §17).
**DEPENDENCIES:** R7 (needs `candidate_id`s to reference).
**TESTS:** scenario-row creation test.
**BEHAVIORAL PROOF:** manual inspection — scenario rows correctly reference real, distinct
candidates from the same tick.
**ROLLBACK:** stop calling the function; table remains empty as it is today.

---

## 29. Test strategy (Section 29 of the task)

Applied uniformly across R1-R10, avoiding every brittle pattern the task explicitly names:

1. **Unit tests** — per-function correctness (e.g., R5's key-equality examples, R3's
   conditional-completion logic) using real inputs and real assertions on output values, never
   "was called" mocks.
2. **Integration tests** — R8's tagged-lesson-to-confidence-change round trip; R7's
   tick-to-episodic-row stamping round trip — using real (in-memory or temp-file) SQLite, not
   mocked persistence layers, per the task's explicit preference for "real serialization, real
   persistence."
3. **Regression tests** — pin the *old* key formats (R5) and the *old* fallback behavior (R1) so a
   future accidental reversion is caught immediately, not just the new behavior.
4. **Behavioral tests** — E1/E2/E6 as formal, repeatable test suites, not one-off manual
   experiments, so they can be re-run after any future change to the same subsystems.
5. **Safety tests** — R6's composed staleness+tags test (§12.3) asserting `code_task` (or any
   RED-tier type) never reaches a constructed `Candidate` without passing the GREEN-only allowlist,
   even when both the staleness and tag changes are active together.
6. **Persistence tests** — E3, using a real process restart on a disposable clone, not a simulated
   in-process reload.
7. **Restart tests** — E3's explicit habituation-non-survival assertion, kept as a named, expected
   result rather than treated as a surprise if a future engineer notices it.
8. **Concurrency tests** — E2's control-`decision_id`-unaffected assertion, run under realistic
   concurrent dispatch load (post-R2, so the load is bounded and the test is not fighting an
   unbounded noise floor).
9. **Failure-injection tests** — see §30.

**Explicitly avoided everywhere:** asserting a function "was called" via mock without checking its
real effect; asserting a row count increased without checking the row's content is causally
connected to anything; asserting "learning" from a confidence number moving with no downstream
consumer proven to read it.

---

## 30. Failure injection (Section 30 of the task)

Designed, not implemented, against a disposable clone only — never live production:

- **Provider timeout / provider hangs / Ollama unavailable:** mock `ollama.Client` to hang past
  the semaphore timeout, forcing the `_multi_backend_fallback` path; assert R1's bound holds.
- **Fallback timeout:** mock all three fallback engines to hang; assert the wrapped deadline in R1
  fires and returns `""` within bound.
- **Fanout burst:** synthetically publish the same event N times in rapid succession; assert R2's
  cooldown suppresses all but the first within the window.
- **Duplicate event:** publish an identical event twice within the cooldown window; assert only
  one downstream dispatch occurs.
- **Restart during action:** kill the clone process mid-`_act_on()` (a real, controlled kill, not a
  graceful shutdown); assert `policy_memory`/`goals_v1` are left in a consistent (if
  possibly-incomplete) state on next boot, per the existing crash-recovery pattern already proven
  for `PlanStore` (Task 52) — this failure-injection test extends that existing discipline to the
  reward-write path, not a new mechanism.
- **Veto:** the existing `should_avoid()` path; assert R4's suppression channel records it and
  `avg_reward` is unaffected.
- **Gateway denial:** an action classified YELLOW/RED and explicitly denied; assert the
  `disposition` (R7) records `gated_denied`, distinctly from `vetoed`.
- **Action failure:** a mocked exception during `agent.run()`; assert `disposition="failed"` and
  no `progress` change occurs (post-R3, since `completed` would be `0.0`).
- **Partial outcome:** a mocked `result` with `status="ok"` but a downstream indicator that the
  output was never consumed (e.g., `ScriptGenerator`'s case, §14/§28) — assert this does not
  silently count as `completed >= 1.0` for goal-progress purposes once/if that distinction is ever
  built (explicitly out of scope for R0-R10 itself, per §14's framing, but the test should exist
  to guard the current, honest "we don't yet distinguish this" state from silently regressing into
  a false-positive completion).
- **Missing outcome:** an action dispatched but never resolved (simulating an async/lost outcome);
  assert `disposition` stays `executed` (not silently promoted to any terminal state) until an
  explicit resolution occurs.
- **Policy key schema change:** simulate a `v2:` → hypothetical `v3:` bump; assert old `v2:` rows
  remain readable under `v2:` logic and are not merged with `v3:` rows.
- **Goal rename:** edit a goal's `title` after R5 ships; assert its policy key (which excludes
  `title` per the allowlist) is unchanged.
- **Recurring goal:** a `recurring=True` goal reaching `progress=1.0`; assert it resets to `0.0`
  and stays `active`, per R3's design.
- **Completed goal:** a goal without `recurring` or `completion_criterion` reaching
  `progress=1.0` via some path; assert it stays `active` (does not auto-complete), per R3.
- **Conflicting belief:** the exact live `presence:absent`/`screen_activity:active_coding` pair;
  assert R9's contradiction event fires (E5).
- **Stale sensor:** a belief whose `last_seen_at` is old but `last_write_attempt` is recent (or
  vice versa); assert R9's two fields are distinguishable in the record.
- **TrustLadder promotion interaction:** simulate an accelerated approval streak (e.g., 20
  approvals in an artificially short wall-clock window) and assert whether promotion fires — this
  test's purpose is to **demonstrate the interaction described in §18**, not to fix it (per Rule
  18, `TrustLadder` itself is not modified); the test documents the current, unmitigated behavior
  as a known risk, for the owner's visibility, rather than silently leaving it unverified.

---

## 31. Success criteria — "READY TO IMPLEMENT" gate (Section 31 of the task)

Implementation of **R1** (the first approved change, §33) may begin only when all of the following
hold. This document itself satisfies every item below for R1 specifically; later stages (R2-R10)
must each separately re-satisfy the applicable items before *their own* implementation begins:

- [x] Every critical current-source claim relevant to R1 is verified — §5, §7 (this session,
  full function read, zero-match grep).
- [x] R0 diagnostic is defined — §6.
- [ ] **Runtime root cause is sufficiently established** — per §5.3, this is **PLAUSIBLE, not
  PROVEN**, for the specific 69.9h-hang attribution; R0 must actually run and produce a result (or
  an explicit bounded-unknown) before this checkbox is honestly satisfied. **R1 may still ship
  before this resolves**, per §5.1's framing (it is a proven defect independent of the specific
  attribution), but any claim that R1 "fixed the starvation" must wait for R0's result.
- [x] Reward/progress semantics are resolved (as a design; R3 is specified, not yet implemented) —
  §9.
- [x] Suppression/reward semantics are resolved — §10.
- [x] Policy key semantics are resolved — §11.
- [x] Candidate diversity is permission-safe (as a design, gated by the GREEN-only allowlist
  requirement) — §12.
- [x] Attribution identity is resolved (as a design; no new table) — §13.
- [x] Historical data treatment is resolved — §27.
- [x] Rollback is defined for every stage — §25, §28.
- [x] Tests are defined for every stage — §28, §29, §30.
- [x] Behavioral proof is defined for every stage — §23, §25, §28.

**This document is the gate artifact.** The one open item (runtime root-cause attribution
strength) does not block starting R1 itself, because R1 is justified as a proven-defect fix
independent of the specific 69.9-hour attribution; it does block claiming R1 "solved the
starvation" as a fact rather than a hypothesis-consistent-with-evidence, per §5.3's classification
discipline.

---

## 32. Anti-overclaim section (Section 32 of the task)

**VECTOR must not be described, after R0-R10, as:** understanding anything; a causal learner; a
world-model agent; self-aware; generalizing; a counterfactual reasoner; Astra-equivalent; or
"cognitive" in any sense beyond "produces a numeric decision from a fixed formula."

**Language that should be used instead, after R0-R10 ships and its behavioral proofs (§23) pass:**

- "VECTOR has a closed, honest reward-learning loop for a fixed set of scalar-scored action
  types" — **if and only if E1/E2/E3 pass.**
- "VECTOR's own candidate generator produces genuine multi-way competition in production" —
  **if and only if E6 passes**, and never before, regardless of what a hand-constructed fixture
  demonstrates.
- "VECTOR recorded which alternative it considered and what happened to the one it chose" —
  for R10's decision-provenance capability, specifically **never** "VECTOR reasoned about the
  counterfactual" or "VECTOR learned from the alternative", since the alternative's outcome is
  never observed.
- "A specific lesson's confidence was updated based on a specific outcome" — for R8, specifically
  **never** "VECTOR corrected itself" as a general capability claim.
- "VECTOR's [specific mechanism] demonstrated L4 behavioral adaptation **in a lab / on a disposable
  clone**" — with the LAB PROVEN / CLONE PROVEN / PRODUCTION PROVEN distinction (§24) stated
  explicitly every time, never collapsed into an unqualified "VECTOR learns."

**The single sentence this document asks any future report to use, verbatim or in close
paraphrase, to describe what R0-R10 achieves:** *"VECTOR has a repaired, honest, closed
reward-adaptation loop over a fixed, gateway-safe action taxonomy — not an understanding system,
and not yet proven to adapt unattended in production until E6 and its neighbors pass."*

---

## 33. Final executive decision (Section 33 of the task)

**1. CURRENT VECTOR.** Safe (zero unauthorized consequential actions across 107+ hours, gateway
architecture adversarially tested across Tasks 53-60), stable (12% average CPU, no crashes, no
restarts), and genuinely autonomous (43,312 dispatches, 19,115 LLM calls, 64,043 memory writes
unattended). Its decision layer is a fixed, six-scalar linear form with no LLM participation, fed
by two closed feedback loops — one (PolicyMemory) broken by a key mismatch, one (goal progress)
working exactly as coded and actively self-destructive as a result. It has produced the identical
decision 1,198 out of 1,198 times across the observed window.

**2. TASK 85 VERDICT.** A competent, well-disciplined, evidence-cited plan that correctly
diagnosed and precisely specified a real defect (PolicyMemory's key mismatch), but examined only
one of the two closed loops that determine VECTOR's decisions, and as a direct result of that gap,
proposed an implementation order (P0-P2 especially) that would have shipped a runtime fix at the
wrong layer, contaminated the reward channel it was trying to repair, and accelerated the very
goal-set self-destruction it never detected.

**3. TASK 86 VERDICT.** An adversarial review that found the loop Task 85 missed, traced it to an
exact formula and an exact live consequence (one goal already permanently deleted), found the
actual unbounded runtime primitive (`_multi_backend_fallback`'s discarded `timeout`), found a
real, previously-unmentioned safety-adjacent interaction (TrustLadder promotion accelerated by
working policy learning), and produced a corrected implementation order. Every one of its
load-bearing new claims was independently re-verified from current source in this session and
found accurate without exception.

**4. FINAL RECONCILED DIAGNOSIS.** VECTOR's decision loop is not open at one point with everything
else closed, and it is not merely "missing a foundation" — it has **two closed loops, one broken
by a fixable serialization bug, one working exactly as designed and actively harmful.** The
correct immediate objective is not a cognitive foundation, an experience table, or an
understanding layer — it is repairing both loops, in the order the dependency structure in §25
demands, and proving the repair with experiments that test VECTOR's own unattended machinery
(E6), not experimenter-constructed fixtures.

**5. FIRST CHANGE.** R1 — bound `_multi_backend_fallback`'s ignored `timeout` parameter. Smallest
possible blast radius (one function), addresses the single cleanest, most unambiguous defect found
in this entire reconciliation, and unblocks every later clone-based measurement by removing the
one proven-unbounded primitive from the critical path.

**6. SECOND CHANGE.** R2 — per-edge TTL cooldown in `_fanout_handler`, plus retiring the
zero-agent `strategy` edge. Monotonically load-reducing by construction, cannot introduce new
reachability, and removes the noise floor that would otherwise make every later measurement
unreliable.

**7. THIRD CHANGE.** R3 — decouple `goal.progress` from the 5-factor reward formula and stop
auto-completing goals that carry no explicit completion criterion. The highest-leverage cognitive
repair in this entire document, and the one this session independently confirmed, from the live
data itself, is not hypothetical: it has already deleted one goal and will delete the rest if left
running under any version of increased candidate eligibility.

**8. WHAT MUST NOT BE TOUCHED.** Per §26 in full: the Understanding Layer, HP shaping, successor
lifecycle, `GOAL_ACTION_MAP`, autonomous RED/YELLOW exploration, per-cycle LLM calls, the frontend,
the live experiment process, `TrustLadder`, `belief:*`→scoring, and both historical baselines
(the 29,164-sample policy bucket and the 30,504-row counterfactual history) — frozen, not
migrated, not deleted.

**9. WHAT SUCCESS LOOKS LIKE.** A named or explicitly-bounded-unknown runtime mechanism (R0); a
measured, materially lower dispatch/noise floor (R2); a goal set that stops permanently deleting
itself (R3); a reward channel free of control-flow contamination (R4); a policy value that
actually moves in response to real outcomes (R5, proven via E1); VECTOR's own unmodified candidate
generator producing genuine multi-type competition in a bounded fraction of ticks, unattended, on
a disposable clone (R6, proven via E6) — and, only if all of that holds, a documented, honest
demonstration of L4 behavioral adaptation with an explicit LAB/CLONE/PRODUCTION provenance label,
never an unqualified claim of learning, understanding, or cognition.

**10. WHAT COMES AFTER THE REWARD LOOP.** A separate, later, explicitly-distinct programme whose
first and only opening question is "what representation does the decision layer consume?" — not
"which key should the reward be written under?" That programme requires new architecture and, for
several of its components (consequence prediction, world-modeling), genuine new model capability;
it should not be started, planned in detail, or referenced as "P7" of this one, until R0-R10 have
shipped and their behavioral proofs have passed.

**11. WHETHER VECTOR IS READY FOR IMPLEMENTATION.** **Ready for R1, specifically, now** — its
defect is proven, its fix is minimal, single-function, and fully specified in §28. **Not ready**
for R2 onward until R1 ships and R0's diagnostic has run (§31's one open checkbox). Each
subsequent stage's own readiness is gated by its predecessor per the dependency table in §25, not
by this document's completion alone.

**12. THE EXACT NEXT IMPLEMENTATION TASK.** A single, bounded task: **implement R1 exactly as
specified in §28 — bound `_multi_backend_fallback()`'s existing, currently-ignored `timeout`
parameter so the three-engine fallback chain returns within it under all conditions — and nothing
else.** Scope explicitly excludes: any other file; any coroutine timeout beyond this one function;
any change to `ollama_safe.chat()`'s own (already-correct) semaphore logic; any change to
`Governor._llm_classify()` or `AgentBase.vchat()`'s call sites (a separable follow-on, not part of
this task); any fanout, goal, or PolicyMemory change. Deliverable: the one function change, the
three tests specified in §28's R1 entry, and a thread-dump run on a disposable clone confirming
the behavioral proof. This is reviewable in one sitting, testable in isolation, revertible with a
single-function revert, and directly comparable against the 107-hour baseline this and the three
preceding tasks have already established.

---

## 34. Self-critique (Section 34 of the task)

Answering each required question directly:

- **Did I accidentally create another memory subsystem?** No — R7 stamps ids into existing rows
  (§13.1's explicit rejection of the Experience table); R4 uses an additive column/small table on
  the *existing* `policy_memory` table, not a new independent store; R9/R10 populate
  already-existing, currently-empty structures (`epistemic.db`'s own fields, `counterfactual.db`'s
  own `scenarios` table).
- **Did I accidentally change permissions?** No — `TrustLadder`, `PermissionGateway`, and the
  tier lists in `config.py` are read-only referenced throughout, never modified. R6's design is
  explicit that the composed staleness+tags case must be tested precisely because it *could*
  otherwise cause a permission-relevant behavior change (autonomous RED-tier proposal) — and the
  minimal-change spec in §28 for R6 explicitly ships staleness-only, deferring tags to a separately
  reviewed follow-on with the GREEN-only allowlist as a hard prerequisite, not an afterthought.
- **Did I accidentally create RED candidates?** No — checked explicitly in §12/§28's R6 spec; the
  tag-propagation half that would do this is not part of the approved implementation in this
  document.
- **Did I accidentally make beliefs a veto?** No — §15/§22 confirm `belief:*`→scoring is not
  connected anywhere in R0-R10; the `[0.70, 1.0]` clamp language is repeated as a bound for *any
  future* connection, explicitly never a veto, matching the existing `_epistemic_penalty()`
  pattern's own design intent.
- **Did I accidentally mix reward and suppression?** No — R4 is specifically the change that
  un-mixes them, and R5 is explicitly sequenced after R4 for exactly this reason (§11.4).
- **Did I accidentally erase historical data?** No — §27 traces every change and confirms none
  deletes, migrates, or rewrites the 29,164-sample or 30,504-row baselines; §26 lists both as
  explicitly frozen.
- **Did I accidentally make progress mean reward again?** No — R3's design (§9.6, §28) removes the
  reward-derived increment entirely and does not reintroduce any reward-linked write to `progress`
  anywhere else in this document.
- **Did I accidentally claim counterfactual learning without alternative outcomes?** No — §17
  explicitly renames the near-term capability "decision provenance," explicitly states the
  alternative's outcome remains permanently `null`, and explicitly drops Task 85's write-back
  aggregate for exactly this reason.
- **Did I accidentally treat a laboratory fixture as production learning?** No — §24's L0-L5 table
  and §32's anti-overclaim section both maintain the LAB PROVEN / CLONE PROVEN / PRODUCTION PROVEN
  distinction explicitly, and §33 item 9 repeats it in the executive summary itself.
- **Did I accidentally fix a symptom instead of the primitive?** Checked specifically for R1: the
  primitive (`_multi_backend_fallback`'s missing bound) is fixed directly, not a downstream symptom
  of it (e.g., not just adding a timeout to `hypothesis_loop` alone, which §3/§7 explicitly reject
  as symptom-fixing).
- **Did I accidentally optimize activity instead of cognition?** R2 is explicitly framed as
  *reducing* activity (a monotonic decrease), not increasing it — the opposite of optimizing for
  more activity; R6 increases candidate *count* only as a measured, bounded precondition for a
  cognition-adjacent measurement (E6), not as an end in itself.
- **Did I accidentally introduce an LLM call into a hot path?** No — checked every R-stage's
  pseudo-code in §28; none adds a new LLM call anywhere. Rule 19 is satisfied throughout.
- **Did I accidentally make fanout behavior more complex?** No — R2 adds one dict lookup and one
  comparison per fanout event; it does not add new event types, new districts, or new trigger
  logic, and explicitly defers the larger re-keying idea (§8) to avoid exactly this risk.
- **Did I accidentally make a recurring goal behave like a one-shot goal?** Checked: R3's design
  explicitly adds a `recurring` field and a reset-not-complete path specifically to prevent this
  (the failure mode that already consumed `g_daily_commit`); the pseudo-code in §28's R3 entry
  shows the reset branch explicitly.
- **Did I accidentally allow learning to accelerate TrustLadder promotion?** Not fixed (Rule 18
  forbids modifying `TrustLadder`), but not silently ignored either — §18 names the interaction
  explicitly, recommends (without implementing) three controls, and §30 includes a failure-injection
  test specifically to keep the risk visible rather than hidden by this document's own silence.
- **Did I accidentally move Understanding Architecture into this phase?** No — §22 explicitly
  tabulates every understanding-adjacent capability and marks each "still absent" after R0-R10,
  and §26/§32 both reiterate the freeze and the anti-overclaim language specifically to prevent
  a future reader from conflating this document's scope with that separate programme.

**No answer above is YES.** No revision to the specification was required as a result of this
self-critique pass.

---

## Integrity statement

Production source modified: **none**. Configuration modified: **none**. `.env` modified: **none**.
Databases written: **none** — every database access this session used a `mode=ro` SQLCipher
connection via `_get_db_key()`. Logs modified: **none**. Runtime state modified: **none**. VECTOR
process started, stopped, signaled, restarted, or interacted with: **none**. Destructive commands
run: **none**. Permissions modified: **none**. Scheduler state modified: **none**. Experiment
configuration altered: **none**. Packages installed: **none**. Dependencies modified: **none**.
No fix was implemented. No prototype was created. No new memory subsystem, understanding
subsystem, Experience table, or PolicyKey module was created (the last per Rule 10's explicit
"unless proven necessary" test, which this document's own source-verification found **not**
proven — the existing `PolicyMemory.make_situation_hash` is confirmed adequate as the canonical
function). `GOAL_ACTION_MAP` was not modified. No autonomous action permission was widened. No
exploration mechanism was enabled. `belief:*` was not connected to decision scoring. HP shaping
was not modified. The successor lifecycle was not fixed. The civilization/agent architecture was
not redesigned. The frontend/HUD was not redesigned. No per-cycle LLM call was introduced. No
Astra-level Understanding Architecture implementation was begun. Files created: exactly one — this
document.

**Task artifacts read this session:** 84 (in full), 85 (in full, own prior authorship this
session), 86 (in full). Tasks 51-83 were not individually re-opened this session; their findings
are carried forward via Task 84's own structured summary of them (§7 of Task 84) and via this
conversation's own direct, independent prior-session source reads of the same files during Tasks
82-85, neither of which is contradicted by anything found in this session's fresh reads. **No task
artifact was found unavailable** — all of 51-86 are confirmed present in
`VECTOR_TECHNICAL_KNOWLEDGE/` by directory listing this session, though not all were individually
re-opened, per the reasoning above.
