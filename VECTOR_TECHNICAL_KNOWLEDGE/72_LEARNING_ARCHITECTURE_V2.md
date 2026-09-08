# Task 72 — VECTOR Learning Architecture V2 (Offline Design Only)

Design/analysis only. Segment 2 was not interacted with at any point. See STATUS at the end for full
disclosure.

---

## 1. Executive Summary

VECTOR has at least **six** independent, real, source-confirmed persistence mechanisms that write
state on every autonomous cycle — `PolicyMemory`, `CounterfactualMemory`, `EpisodicMemory` (via three
different writers), `epistemic_tracker` (via two different writer call sites with two different
key-namespace conventions), `reasoning_bank`, and `loop_state`'s checkpoint keys. Every one of them
is genuinely integrated (S2/S3 on the S0-S5 ladder) — this is not a codebase full of dead code. What
this audit found, and what Task 71 already found in five independent passes, is that **almost none of
these write→read loops actually close** for the specific behavior dominating the running experiment.

The most important new finding in this task, not previously identified across five Task-71 audit
passes: **`decision_engine.py` has a real, working, closed-loop epistemic-confidence mechanism**
(`record_epistemic_belief()` writes a per-domain confidence after every action outcome;
`_epistemic_penalty()` reads it back and applies a real multiplicative dampening factor, 0.70-1.0, to
every future candidate score in that domain). This is a genuine Level-3/4 learning candidate by this
document's own definitions (§5) — and it is the single clearest counter-example to Task 71's
"no consumer of epistemic beliefs was found" claim. But three-way source tracing (decision_engine.py's
read/write pair, cross-referenced against autonomous_loop.py's two `record_epistemic_belief()` call
sites, cross-referenced against the confirmed early-return line in the counterfactual-block path)
shows precisely *why* it never engages for `analyze_progress`: both call sites that would write the
belief live strictly downstream of a real execution outcome, and the counterfactual-block path returns
before reaching either one. The mechanism is not broken. It has simply never been fed an input, for
one specific, well-understood, structural reason. This is offered as the report's central worked
example of why "genuine learning" cannot be assessed as "write exists" + "read exists" — the two must
be shown to actually connect for the specific behavior in question.

Building on this and on Task 71's own findings (independently re-verified where load-bearing, not
assumed), this document designs a **Learning Architecture V2**: not a rewrite, but a coherent set of
additions — a first-class Learning Event model, a genuine experience→state→decision provenance chain,
a bounded/decaying policy update rule, a counterfactual-decay fix, and a staged, falsifiable
experimental-proof framework — all explicitly deferred until after the 7-day experiment concludes.

## 2. Current Learning Architecture (Inventory)

All entries below are traced to source this task, or re-confirmed from Task 71's own source-cited
findings (marked accordingly). Format: file / purpose / persistence / callers / reachability /
decision-influence / decay / provenance / confidence / contradiction-handling / S-level.

### 2.1 PolicyMemory
- **File:** `core/memory/policy.py`. **Purpose:** online average reward per `(action_type,
  situation_hash)`. **Schema (verified this task, full file read):**
  `policy_memory(action_type, situation_hash, avg_reward, sample_count, last_updated)` — no
  confidence column, no provenance column, no decay column.
- **Persistence:** SQLite, shared episodic-memory DB connection (`get_temp_cursor()`), lock-protected
  read-modify-write.
- **Callers:** `decision_engine._score_candidate()` (read, `get_score()`, before every scoring);
  `autonomous_loop._act_on()` (write, `update_from_outcome()`, after every outcome — both the
  real-execution path at line ~1265 and the counterfactual-block path at line 1115, per Task 71's
  F-LOOP-02).
- **Reachability:** production R3, autonomous R3 (fires every ~10s cycle, confirmed across Tasks
  62-69).
- **Decision influence:** yes — 20% weight in `decision_engine`'s 5-factor formula (`W_POLICY`,
  confirmed this task via source read of `_score_candidate()`).
- **Planning influence:** not traced this task — no reference found connecting `PolicyMemory` to any
  plan-creation code path.
- **Decay:** **none.** Unbounded cumulative average (verified this task — full file read, no decay
  term anywhere).
- **Provenance:** none — no field records *why* a given reward was assigned or what evidence produced
  it. `.claude/rules/memory.md`'s own documented convention ("Always tag source + confidence") is not
  followed by this specific table.
- **Confidence:** none as a first-class concept — `sample_count` is the closest proxy (more samples =
  more confidence in the average), but this is never exposed or used as a confidence value anywhere.
- **Contradiction handling:** none — a contradicting outcome simply pulls the average toward it,
  proportionally to `1/(n+1)`, which becomes negligible at high `n`.
- **S-level: S3** (integrated, runtime reachable, behaviorally verified — Task 62-69's `analyze_progress`
  score, frozen at exactly 0.050 across 27,393→27,965+ samples, is the single most-repeated piece of
  behavioral evidence in this entire experiment).

### 2.2 CounterfactualMemory
- **File:** `core/memory/counterfactual.py`. **Purpose:** "what if I had done X instead of Y" +
  rejection tracking. **Schema (verified this task, full file read):** three tables —
  `scenarios(id, original_action, chosen_reason, alternative, alternative_outcome, context, useful,
  feedback_reason, created_at)`, `rejections(id, decision_id, proposal, reason, context, created_at)`,
  `outcomes(id, decision_id, expected_outcome, actual_outcome, delta, ...)` — the `scenarios` table's
  `useful`/`feedback_reason` columns are a real, if apparently unused, self-feedback mechanism worth
  noting: this table structurally supports recording "was this counterfactual reasoning actually
  useful," which is precisely the kind of meta-signal a genuine learning system needs, but no writer
  or reader of `useful`/`feedback_reason` was located within this task's time budget — flagged as an
  open question in §17, not claimed as dead code without further tracing.
- **Persistence:** dedicated SQLite file (`counterfactual.db`), own connection, own lock.
- **Callers:** `autonomous_loop._act_on()` (write, `record_rejection()`, every counterfactual block);
  same function (read, `should_avoid()`, before every action attempt).
- **Reachability:** R3, fires every ~10s cycle for `analyze_progress` specifically.
- **Decision influence:** yes, but only as a post-selection interceptor — `decision_engine.py` itself
  has zero references to `CounterfactualMemory` (confirmed this task via grep), so rejection history
  never shapes what candidates get *generated*, only whether an already-chosen candidate gets blocked.
- **Decay:** implemented (`_decay_factor()`, exponential, `decay_days=7.0` default) but **self-defeating
  for the exact failure mode it targets** — re-confirmed this task by re-reading `should_avoid()`/
  `get_similar_rejections()`: because a fresh `rejections` row is written every single cycle a
  candidate is blocked, `get_similar_rejections()` always matches against a row that is, at most,
  ~10 seconds old, so `_decay_factor()` evaluates to ≈1.0 forever for a continuously-repeated
  candidate (Task 71 T71-M03, re-verified).
- **Provenance:** partial — `reason` (free text) and `context` (JSON) are stored per rejection, which
  is more provenance than `PolicyMemory` has, but there is no structured link back to *which specific
  belief/policy value* motivated the rejection.
- **Confidence:** the Jaccard-similarity score functions as a confidence proxy for "is this the same
  situation," not a confidence in the rejection's own validity.
- **Contradiction handling:** none observed — no code path was found that reverses or discounts a
  rejection based on a later successful outcome of a similar action.
- **S-level: S3.**

### 2.3 EpistemicTracker — two independent writer pathways (a genuinely new distinction this task)
- **File:** `core/brain/epistemic_tracker.py`, consumed via `core/loop/context_engine.py` and
  `core/loop/decision_engine.py`.
- **Pathway A — `ContextEngine.track_beliefs()`** (called every think_tick per Task 71 F-LOOP-04,
  re-confirmed): writes free-form keys like `belief:presence:absent`, `belief:screen_activity:*`,
  `belief:goals:active_progress`. **No consumer of this specific key namespace was found** by Task 71
  or by this task — this remains an open, unresolved gap.
- **Pathway B — `DecisionEngine.record_epistemic_belief()`** (this task's central new finding, §1):
  writes keys of the form `action_domain:{domain}` where `domain = action_type.split("_")[0]`, called
  from exactly two sites in `autonomous_loop.py` (lines ~1271 and ~1501), both strictly downstream of
  a real execution `result`. **This IS consumed** — `DecisionEngine._epistemic_penalty()` reads
  `action_domain:{domain}` beliefs before every candidate score and applies a real multiplicative
  dampening factor (0.70 stale, 0.80 low-confidence, 0.90 medium-confidence, 1.0 unknown-or-high-confidence)
  to the final score.
- **Decay:** implemented for Pathway B — `DecisionEngine.decay_epistemic()` → `epistemic.decay_all()`
  + `check_staleness()`, called from `autonomous_loop._reflect_tick()` during the 2AM reflection cycle
  (source-confirmed this task via the docstring at `decay_epistemic()`'s definition; the reflect-tick
  call site itself was not independently re-verified this task — flagged as R2, not R3, for that
  specific link).
- **Why it never engages for `analyze_progress`:** the domain string for `analyze_progress` is
  `"analyze"`. For a belief keyed `action_domain:analyze` to exist, `record_epistemic_belief()` must
  have been called with that action_type at least once — which requires reaching line ~1271/1501,
  which requires the counterfactual block to NOT have intercepted the action first. Since
  `analyze_progress` is blocked essentially every cycle (Task 63-69's unbroken observation), this
  belief was, with high confidence, never written even once during Segment 1 — meaning
  `_epistemic_penalty()` returns `(1.0, 0.0)` ("unknown domain — neutral") for this action indefinitely.
  This is consistent with, and offered as independent corroborating evidence for, the observed
  candidate score being *exactly* 0.66 in every single log line across Tasks 62-69 — if any dampening
  factor below 1.0 were ever applied, the total score (computed *after* the dampening multiply, per
  `_score_candidate()`'s own code) would show a value other than the undamped formula's output at
  least once. It never has.
- **S-level: Pathway A — S3 write / S0-for-consumption (no reader found). Pathway B — S3 write, S3
  read, S2 for the specific `analyze_progress` case (integrated and reachable in principle, but never
  actually exercised for this action given the observed conditions — this is the precise distinction
  S2 vs S3 exists to capture).**

### 2.4 EpisodicMemory (three writers, one FTS5 store)
- **File:** `core/memory/episodic.py`. Confirmed writers this task/Task 71: (1) ambient voice
  interaction summaries (`core/voice/ambient_listener.py`, broken by a kwarg mismatch — Task 71
  T71-M06, re-confirmed at source this task not re-derived); (2) `loop_state.py`'s three fixed-key
  UPSERT checkpoints (`loop:current_goal`, `loop:last_decision`, `loop:agent_hp` — Task 71 OBS-02,
  the semantic-memory-row-count correction); (3) general system event logging throughout the codebase
  (not individually enumerated here — the episodic store is the project's general-purpose event log,
  confirmed growing steadily — +580 rows across Segment 1's ~2h03m per Task 66).
- **Reachability:** R3 for the general logging path; R2 for the ambient-voice path (reachable, but
  100% failing per the confirmed kwarg bug).
- **Decision influence:** `reasoning_bank.retrieve()` and `_episode_pattern_predictions()` (see §2.5,
  §2.6) both read from episodic memory and demonstrably influence live decisions — this is the
  clearest Level-2 (retrieval → influence) evidence in the whole system.
- **Decay:** none observed for the general event log (append-only, no pruning found, per Task 71
  PERF-02's analogous finding for `gateway_audit`/`inference_calls` — not independently re-checked
  for `episodic_memory` specifically this task, flagged as UNCONFIRMED for this exact table).
- **S-level: S3** (general logging), **S2** (ambient-voice path — integrated and reachable, but its
  one specific write always fails).

### 2.5 Anticipation engine (`core/brain/anticipation.py::_episode_pattern_predictions`)
- Already fully traced in Task 66 and Task 71 (TEST-01) — re-confirmed here only for completeness,
  not re-derived: matches historical episodic events within a ±1-hour window of the current hour,
  requires ≥2 matches, confidence `min(0.5 + count*0.1, 0.90)`. This is genuine Level-2 evidence
  (retrieved episodic history → a live prediction), but is **not** a learning mechanism by this
  document's Level-3+ bar (§5) — it is a deterministic function of wall-clock time against a fixed
  historical dataset, which is why its one observed "change" (the `observation` prediction
  disappearing at the 01→02 hour boundary, Task 66) is not evidence of adaptation.
- **S-level: S5** (behaviorally verified, including its one confirmed behavior change, with a
  confirmed non-learning explanation).
- **Test coverage:** S0 for direct behavioral verification of the function's own correctness — Task
  71's TEST-01 finding (only ever mocked out in tests) stands, re-confirmed as still relevant to how
  much trust to place in the §2.5 characterization itself.

### 2.6 reasoning_bank (`vectorcode/src/reasoning_bank.py`)
- JSON-file-backed, 57 fixed entries, loaded once at process start. `decision_engine.py` calls
  `inject_past_reasoning()` (read) every scoring cycle; zero calls to `.store()` exist anywhere in
  `decision_engine.py` (Task 71 T71-M05, re-confirmed via a fresh grep this task: `store(` appears
  in `decision_engine.py` only once, at an unrelated `mem.store(` call — not a `reasoning_bank.store(`
  call). A project-owned integration check (`scripts/integration_check.py:73`) asserts
  `"reasoning_bank.store(" in de_src` — this check would very likely fail if run against current
  source; **not independently executed to confirm** (execution forbidden this task), flagged as a
  likely-stale check, not a confirmed one.
- **S-level: S3 read, S0 write-back** (no path exists from the live decision loop back into this
  store).

### 2.7 CorrectionLearner
- **File:** `core/memory/correction_learner.py`. Requires a detected owner-correction speech act to
  activate (per its own module docstring). `belief:presence:absent = owner_absent` held continuously
  throughout every hour of Segment 1 observed so far (Tasks 63-69) — this mechanism has had, on
  current evidence, **zero opportunity to fire** during the running experiment, independent of
  whether it is implemented correctly.
- **S-level: S2** (implemented, integrated into the conversational-input path in principle) — **S0 for
  demonstrated firing** under the conditions actually observed.

### 2.8 GoalSystem / plan creation
- Re-confirmed from Task 71 (F-G01, F-G03), not re-derived: `generate_immediate_actions()`'s exact
  `progress == 0.0` equality filter is the reason only `g_kiit_attendance` ever produces a
  "kickstarter" candidate; `_decompose_to_plan()` is only triggered from `add_goal()`, never from
  `_load_or_seed()` (the path all 7 pre-seeded goals, including the one dominating every cycle, enter
  through) — meaning the plan store very likely contains zero plans for any currently-active goal
  (**UNCONFIRMED**, requires a post-experiment read-only DB check to settle).
- **S-level: S3** for candidate generation itself (fires every cycle); **S1-S2, UNCONFIRMED** for
  plan creation ever actually occurring for any goal driving the current experiment.

## 3. Verified Source-Level Dataflow

```
 experience (ambient voice / screen / clock / action outcome)
        │
        ▼
 ┌─────────────────────┐        S3, but 1 of 3 writers (ambient-voice
 │  EpisodicMemory      │◄────── summarization) is 100% broken; general
 │  (append-only log)   │        event logging works
 └──────────┬───────────┘
            │ read                                  ┌───────────────────────┐
            ├──────────────────────────────────────►│ _episode_pattern_      │
            │                                        │ predictions()  (S5)   │
            │                                        │ → anticipation nudges │
            │                                        └───────────────────────┘
            │ read
            └──────────────────────────────────────►┌───────────────────────┐
                                                      │ reasoning_bank.       │
                                                      │ inject_past_reasoning │
                                                      │ (S3 read, S0 write-   │
                                                      │  back — dead end)     │
                                                      └───────────────────────┘

 ┌──────────────────────┐   write (loop_state, fixed keys)
 │  SemanticMemory       │◄── S3 (real UPSERT activity — Task 71 OBS-02 —
 │  (key-value, UPSERT)  │    but row count never grows; no read-back
 └───────────────────────┘    influencing any decision was found)

 decision_engine._score_candidate()  [S3, runs every cycle]
        │
        ├─► PolicyMemory.get_score()  ──── S3 read (20% weight)
        │        ▲
        │        │ write, reward=0.05 constant on every
        │        │ counterfactual block (S3, but converges
        │        │ to a fixed point — no further movement)
        │        │
        ├─► CounterfactualMemory.should_avoid()  ── S3, POST-SELECTION ONLY
        │        │  (never consulted during candidate generation — S0 for
        │        │   that link)
        │        │  decay: S1 implemented, S0 EFFECTIVE for a repeated
        │        │  candidate (self-defeating, §2.2)
        │        │
        ├─► _epistemic_penalty()  ── S3 mechanism, reads action_domain:*
        │        │  beliefs written by record_epistemic_belief()
        │        │  (S3 write path — BUT only reachable after a REAL
        │        │  execution outcome, which analyze_progress never
        │        │  reaches — S2 for this specific action: integrated,
        │        │  reachable in general, NEVER EXERCISED here)
        │        │
        └─► goal_alignment / urgency / timing / cost  (S3, GoalSystem-derived)
                 │
                 ▼
         candidate.total_score  (observed frozen at 0.66, exactly,
         across every cycle Tasks 62-69 — fully explained by the
         above: nothing in this formula has moved for this action)
                 │
                 ▼
         action attempted?
           │              │
      YES  │              │  NO — CounterfactualMemory blocks (this is
           │              │  what happens essentially every cycle for
           ▼              │  analyze_progress)
   ┌───────────────┐      │
   │ Action executes│      ▼
   │ (or is GREEN-  │  early return (autonomous_loop.py:1118)
   │  tier auto-run) │  — PolicyMemory.update_from_outcome(reward=0.05)
   └───────┬────────┘     fires; NOTHING ELSE downstream of this branch
           │               (record_epistemic_belief, goal-progress
           ▼               update, plan progress — none of it) ever runs
   real outcome (status, reward)
           │
           ├─► PolicyMemory.update_from_outcome(real reward)   [S3]
           ├─► record_epistemic_belief(domain, status, reward)  [S3 —
           │      but only reached on THIS branch]
           └─► (goal progress update — not confirmed reachable for
                any currently-active goal, §2.8)
```

**Disconnected/broken edges, summarized:**
- `reasoning_bank`: read-only, no write-back (`S0`).
- `CounterfactualMemory` → candidate generation: no feedback path at all (`S0`).
- `ContextEngine.track_beliefs()`'s belief namespace: write-only, no confirmed consumer (`S0` for
  consumption).
- `PolicyMemory`: closes the loop (write and read both real) but the update rule has no decay, so a
  high-`n` entry is *effectively* disconnected from further influence even though the code path is
  technically S3.
- `_epistemic_penalty()`/`record_epistemic_belief()`: the loop is real and closes *in general*, but is
  provably never exercised for the one action that would matter most to observe it on.
- Plan creation: very likely never triggered for any currently-active goal (`UNCONFIRMED`, likely S1).

## 4. S0-S5 Integration Matrix (consolidated)

| Component / edge | S-level | Basis |
|---|---|---|
| Episodic write (general log) | S3 | Task 66 row-count growth |
| Episodic write (ambient-voice summarization) | S2 | Reachable, 100% failing (kwarg bug) |
| Episodic → anticipation (`_episode_pattern_predictions`) | S5 | Task 66's confirmed behavioral change |
| Episodic → reasoning_bank read | S3 | Fires every cycle, same 3 entries |
| reasoning_bank write-back | S0 | Zero call sites in decision_engine.py |
| Semantic write (`loop_state` UPSERT) | S3 | Real activity, no row growth (§2.4/OBS-02) |
| Semantic → any decision | S0 | No reader found beyond the UPSERT's own checkpoint purpose |
| PolicyMemory write/read loop | S3 (mechanism) / effectively-frozen (outcome) | Frozen score, 27k+ samples |
| CounterfactualMemory write/read loop | S3 | Fires every cycle |
| CounterfactualMemory decay | S1 implemented / S0 effective | Self-defeating, §2.2 |
| CounterfactualMemory → candidate generation | S0 | Zero references in decision_engine.py |
| Epistemic Pathway A (context_engine writes) | S3 write / S0 read | No consumer found |
| Epistemic Pathway B (decision_engine writes/reads) | S3 (mechanism) / S2 (for `analyze_progress` specifically) | Never exercised for this action, traced this task |
| Epistemic decay | S2 | Reflect-tick call site not independently re-verified |
| CorrectionLearner | S2 (implemented, integrated) | S0 (never fired — owner absent) |
| Goal candidate generation | S3 | Fires every cycle |
| Plan creation for active goals | S1-S2, UNCONFIRMED | Never triggered from `_load_or_seed()` |
| PermissionGateway (for context — not a learning system, included for completeness) | S5 | 58A-58G series + Task 60 red-team |

No edge in this matrix reaches S4 (test-verified) for its *specific* claimed behavior except where a
direct test was located and read (none were, for the core learning mechanisms — Task 71's TEST-01
found the opposite: the one function most central to the experiment's one confirmed behavioral change
has zero direct test coverage).

## 5. Definition of Genuine Learning

| Level | Name | Necessary evidence | Insufficient evidence | False positives | Instrumentation required |
|---|---|---|---|---|---|
| 0 | Storage | A row/value is written that did not exist before, or an existing value changes | N/A (this is the floor) | None at this level | A queryable log of writes with timestamps |
| 1 | Retrieval | A later process reads that stored value | Storage alone | Assuming storage implies retrieval | A queryable log of reads, correlated to what was stored |
| 2 | Influence | The retrieved value is shown, via the actual scoring/decision formula, to change the output of a decision (e.g. a specific weighted term is nonzero and traceable to the retrieved value) | Retrieval alone; "the code path that reads it exists" | The value is read but multiplied by a term that is always 0, or gated behind a condition never true for the case observed | The decision engine's own per-factor breakdown (already exists — `candidate.reasoning_chain`, confirmed in `decision_engine.py:408-424`) logged and retained |
| 3 | Internal learning | An experience causes a *persistent* state change (not a transient in-memory value) that is provably attributable to that specific experience, via a traceable id or timestamp correlation | A state change occurred; a policy value moved | The state "changed" only because of floating-point noise, decay of an unrelated entry, or an unrelated write to the same key | Before/after snapshots of the specific state, keyed to the specific experience |
| 4 | Behavioral adaptation | A **later** decision's chosen candidate, or a later score, is different **because of** the Level-3 state change, not because of an unrelated factor (context, clock, provider availability) that also happened to change | The state changed AND the decision later changed, without ruling out other causes | Two changes are merely correlated in time | A controlled comparison: same situation, with vs. without the Level-3 state change, all else held constant (Experiment A/B, §12) |
| 5 | Generalization | A behavior learned in situation X is shown to transfer to situation Y, where Y is similar-but-not-identical to X by some declared similarity metric, and the transfer cannot be explained by X and Y hashing to the same `situation_hash` | Applying a learned score to the literal same `situation_hash` again (that is Level 4, not 5) | A `situation_hash` collision between two "different" situations masquerading as generalization | A declared, inspectable similarity metric, distinct from the exact-match hash used for Level 4 |
| 6 | Correction | Contradictory evidence measurably revises a previously-learned value in the direction the new evidence supports, not merely dilutes it toward the mean at whatever rate the update rule happens to produce | A new data point was added to an average that happens to move it | A correction that is actually just Level 3's ordinary update rule doing what it always does, relabeled | A declared, distinguishable "correction" event type, separate from ordinary reward accumulation, with its own before/after record |
| 7 | Meta-learning | VECTOR's *learning-rate or learning-strategy itself* changes based on evidence about how well it has been learning (e.g. "my policy updates on domain X have been unreliable predictors of outcome — widen exploration there") | Any of Levels 0-6 in isolation | Confusing "VECTOR discussed learning" (an LLM generating text about learning) with the system's own parameters actually changing as a result | A record of the meta-parameters themselves (e.g. a per-domain learning rate) changing over time, correlated with evidence about prior prediction accuracy |

**Everything currently traced in VECTOR reaches, at best, Level 2 (episodic → anticipation, and
episodic → reasoning_bank retrieval) with clean evidence, and Level 3 partially (PolicyMemory's state
does change, attributably) — but **no mechanism in the current system has been shown to reach Level 4**
for any observed behavior. This is the precise, defensible restatement of Tasks 63-71's repeated "no
demonstrated learning" conclusion, now expressed against an explicit ladder rather than an intuition.

## 6. Learning Architecture V2

For each area: what should be stored, where, who writes/reads, update trigger, guard against
accidental updates, confidence evolution, staleness decay, contradiction handling, behavioral
influence. This is a **design**, not a description of existing code — every item here is a proposal.

### A. Episodic memory
Keep as the append-only ground truth log (this is architecturally correct already). **Add:** a
first-class `experience_id` (ULID, monotonic + random) on every row, generated at write time,
returned to the caller — this is the load-bearing primitive the entire provenance model (§8) depends
on. Writers: any subsystem observing something real. Readers: consolidation (below), anticipation,
reasoning retrieval. Update trigger: any real event. Guard against accidental writes: none needed —
episodic memory should be cheap and liberal, since it is the raw material, not the learned conclusion.

### B. Semantic memory
Redefine its role explicitly: **consolidated, curated facts derived FROM episodic memory by an
explicit consolidation step**, not a general-purpose key-value checkpoint store (that's what
`loop_state` already correctly does — its use of `semantic_memory`'s table is a layering violation,
not a bug per se, but worth separating conceptually in V2: give `loop_state` its own table, or a
clearly namespaced key prefix that a future semantic-memory dashboard can filter out). Writer: a
`consolidate()` step (already conceptually named "consolidation_bot" in
`districts/memory_curator/`, per Task 71's T71-M04) that reads a batch of episodic rows and decides
whether they constitute a fact worth promoting. Reader: `decision_engine` (new — currently doesn't
read semantic memory at all, a genuine gap). Update trigger: consolidation pass (scheduled or
threshold-triggered, e.g. "N new episodic rows since last consolidation for this topic"). Guard:
require ≥2 corroborating episodic rows before promoting a new semantic fact (mirrors
`_episode_pattern_predictions`'s own `count>=2` convention, which is a reasonable, already-precedented
threshold in this codebase). Confidence: starts at a function of corroboration count, same
`min(0.5+count*0.1, 0.9)`-style formula already used elsewhere for consistency. Decay: yes — see §9.
Contradiction: see §10.

### C. Beliefs (epistemic tracker)
**Unify the two namespaces (§2.3).** Either (a) have `ContextEngine.track_beliefs()`'s output
actually feed `_epistemic_penalty()`'s `action_domain:*` lookups (e.g., let a screen-activity or
presence belief modulate the SAME dampening mechanism, not a parallel unread one), or (b) explicitly
document that Pathway A is a pure situational-awareness/observability feature never meant to
influence decisions, and stop implying otherwise. Given Pathway B already has a working
write→read→influence loop, V2 should extend Pathway B's pattern rather than build a third one.
Writer: `record_epistemic_belief()`, extended to fire on *every* attempted action's terminal state,
including the counterfactual-block outcome (see §D below — this is the single highest-leverage change
in this whole document). Reader: `_epistemic_penalty()`, unchanged. Confidence: already modeled
(0.0-1.0, with staleness). Decay: already implemented (`decay_all()`/`check_staleness()`) — this is
one of the few genuinely complete decay implementations in the codebase; V2 should reuse its pattern
rather than reinvent one for other subsystems.

### D. Preferences
Not currently a distinct subsystem — folded into semantic memory and goal priorities today. V2
should treat "preference" as a specific semantic-fact subtype with an explicit owner-attribution
requirement: a preference should only ever be written from a Level-6-eligible correction event (an
explicit owner statement), never inferred silently from behavior, to avoid the exact
confirmation-bias failure mode named in §13.

### E. Policy (the central fix)
**Change the update rule from an unbounded cumulative mean to a bounded, decaying one** — e.g. an
EMA with a fixed or slowly-annealing learning rate α (`new = old*(1-α) + reward*α`), so recent
evidence always has a non-vanishing ability to move the score, and/or a hard cap on effective sample
count (e.g. `n_effective = min(n, N_max)` inside the update formula). **Make the counterfactual-block
penalty a function of the actual counterfactual confidence/rejection count, not a hardcoded 0.05** —
e.g. `reward = base_penalty * (1 - decay_factor)`, so a freshly-repeated block is penalized more
sharply than a stale, decayed one, creating actual pressure to diversify rather than converging to a
fixed point. Writer: `_act_on()`, both branches (unchanged structurally, changed formula). Reader:
`decision_engine._score_candidate()` (unchanged). Guard against accidental updates: keep the existing
pattern (updates only from `_act_on()`'s two call sites) — this is already correctly scoped, the
problem was never *who* writes, only *what value*.

### F. Counterfactual memory (the second central fix)
**Fix the decay-defeat**: key `_decay_factor()`'s reference point off the *first* occurrence of a
matching rejection pattern for a given `(action_type, situation_hash)`, not the most recent — track a
`first_seen_at` alongside `created_at`/`last_seen_at`, updating a rejection's `last_seen_at` and
`occurrence_count` in place (an UPSERT, mirroring `PolicyMemory`'s own pattern) rather than inserting
a fresh row every cycle. This has two benefits: it lets genuine staleness decay work as originally
intended, AND it turns `occurrence_count` into a real escalation signal usable elsewhere (e.g., feed
it into E's penalty formula). **Wire `should_avoid()`'s outcome into candidate generation itself** —
today, decision_engine never learns "don't even bother generating this candidate" from repeated
rejections; it re-generates and re-blocks every cycle. A minimal fix: expose a
`get_currently_suppressed_action_types()` query and have `GoalSystem.generate_immediate_actions()` or
`decision_engine`'s candidate-assembly step filter them out above some occurrence-count threshold,
with an explicit, logged, periodic "cooldown expired, retry" re-inclusion (not a permanent ban — that
would just create a different stuck state).

### G. Outcome/reward system
Currently: reward is either a hardcoded constant (blocked path) or derived from `result.get("status")`
(executed path, exact derivation not traced this task — flagged as an open question for §17). V2
should make reward-derivation an explicit, inspectable function per action_type (not a single global
formula), with its inputs logged alongside the resulting reward value, so a future observer can
audit *why* a given reward was assigned without re-deriving it from log text.

### H. Goal learning
Currently: goals are static (pre-seeded) with a manual `update_goal_progress()` API and no automatic
progress-inference from action outcomes. V2: an action's outcome should be able to propose a
goal-progress delta (bounded, capped per cycle to prevent runaway), reviewed the same way a semantic
fact promotion is reviewed (§B) — i.e. corroborating evidence required, not a single action's say-so.

### I. Strategy learning
Not currently a distinct concept in the codebase (the closest existing thing is `PolicyMemory`'s
per-`situation_hash` granularity, which is really "tactic learning," not strategy). Out of scope for
a first V2 pass — flagged as a genuine gap, not designed further here, to avoid over-scoping this
document beyond what current architecture can support.

### J. Skill learning
Not located anywhere in this task's or Task 71's tracing (`skill_memory` table exists per CLAUDE.md's
own "5 tables" convention, but no writer was found). Genuinely unknown — flagged for a dedicated
future investigation, not designed here without evidence of what currently exists.

### K. Epistemic confidence
Already the most complete subsystem in the current codebase (§2.3 Pathway B) — V2's job here is
mainly "feed it more inputs" (§C above: extend to the blocked-action path), not redesign it.

### L. Hypothesis formation
`hypothesis_engine`/`suggestion_queue` exists (195 rows per Task 66) but Task 71's OBS-05 found no
confirmed correlation between a suggestion and any downstream decision. V2: give every suggestion a
`suggestion_id`, thread it into any `Action` proposed as a direct result of that suggestion (via
`Action.params`), and persist that link in `gateway_audit` (see §7's provenance design) so this
correlation becomes queryable instead of merely hoped-for.

### M. Contradiction handling
See §10 — this needs a genuinely new concept, not an extension of an existing one; nothing in the
current codebase has a "revise this specific belief because new evidence disagrees" primitive that
is distinguishable from ordinary averaging.

### N. Forgetting/decay
See §9 — partially solved (epistemic beliefs), partially broken (counterfactual), entirely absent
(policy, semantic memory, `gateway_audit`/`inference_calls` retention per Task 71 PERF-02).

### O. Provenance
See §8 — entirely absent today (no table has an `experience_id`-style field); this is the single
architectural addition every other improvement in this document depends on.

### P. Causal attribution
See §8.

### Q. Generalization
See §11 — not designed anywhere in the current codebase (everything is exact-hash-keyed); a genuinely
new concept for V2.

### R. Exploration vs. exploitation
Not currently a distinct concept — `PolicyMemory`'s `DEFAULT_SCORE` (0.5, neutral) for an unseen
`(action, situation)` pair is the closest thing to "optimism under uncertainty," but there is no
explicit exploration bonus, no epsilon-greedy or UCB-style mechanism, and (per §5) `analyze_progress`
never gets to explore an alternative because none is ever generated. V2 should treat "does the
candidate-generation step ever intentionally propose something purely to reduce uncertainty" as an
open design question — flagged, not resolved, here.

## 7. Causal Attribution Model

**Core primitive: `experience_id`.** Every episodic-memory write already returns a row id (confirmed:
`EpisodicMemory.store()` returns a string per Task 66/68's own characterization of its signature) —
V2 proposes formalizing this as the universal lineage key, threaded (not stored redundantly, just
*referenced*) through every downstream state change:

```
experience_id (episodic row)
    │
    ▼
consolidation/observation event  →  tags this experience_id as contributing evidence
    │
    ▼
internal-state-change event  (a NEW state-change LOG, not a new schema on every table —
    │                          see below for why this avoids "add a schema now")
    ▼
policy/belief value change  →  the state-change log entry records: which table, which
    │                          key, old value, new value, and the experience_id(s) that
    │                          contributed
    ▼
subsequent decision  →  decision_engine's ALREADY-EXISTING `candidate.reasoning_chain`
    │                    (confirmed present in source, §4) is extended with one more
    │                    entry: which prior state-change event(s) fed into this factor
    ▼
action → outcome  →  the outcome itself becomes a new episodic experience_id, closing
                      the loop for the NEXT cycle's attribution
```

**Explicitly avoiding a new database schema now**, per the task's own instruction: this can be
achieved without touching any existing table's schema by introducing a single new, append-only
**state-change log** (conceptually — not implemented now) that records `(timestamp, subsystem, key,
old_value, new_value, contributing_experience_ids: [list])`. Every existing writer (`PolicyMemory.
update_from_outcome`, `CounterfactualMemory.record_rejection`, `epistemic.merge_belief`, a future
semantic-fact promotion) would emit ONE additional log line to this store, without changing its own
existing table at all. This is deliberately the smallest possible addition that makes attribution
representable — a genuinely new table, but exactly one, generic, and additive, not a redesign of the
five existing ones.

**Preventing false attribution from mere correlation:** three concrete guards:
1. **Recency window, not "most recent."** An `experience_id` should only be eligible to be cited as
   "contributing" to a state change if the state-change happened within a declared, bounded window of
   the experience (e.g. same decision cycle, or the specific outcome the update function was literally
   passed as an argument) — not "whatever was logged most recently," which is exactly the bug
   underlying CounterfactualMemory's self-defeating decay (§2.2) and would reproduce the same failure
   mode in a naive attribution log.
2. **Single-writer attribution.** Each state-change log entry should record the *specific function
   call* that produced it (e.g. `autonomous_loop._act_on:1265`), not merely "something changed around
   this time" — this is achievable today with zero schema change by simply including the call site in
   the log message, and is already loguru's implicit behavior (module:function:line is already in
   every log line) — V2's job is just to make this queryable rather than only grep-able.
3. **A/B counterfactual requirement for Level-4+ claims.** Per §5's own definition, no Level-4 claim
   should be accepted from attribution-log evidence alone — it additionally requires the controlled
   comparison described in Experiment A/B (§12). The attribution log tells you *what the system
   believes influenced it*; the controlled experiment tells you *whether that belief is actually
   true*. Conflating these two is exactly the trap this document is designed to avoid.

## 8. Reward Design (Audit of Current Mechanism + Future Proposal)

**Where rewards originate today (verified):** exactly two sources found — (1) a hardcoded constant
`0.05` on every counterfactual block (`autonomous_loop.py:1115`); (2) some derivation from
`result.get("status", "unknown")` on the real-execution path (the exact formula was not traced within
this task's time budget — flagged as an open question, §17, rather than guessed).

**Is reward hardcoded?** Partially — yes for the (currently dominant) blocked path; unknown, not
confirmed either way, for the executed path.

**Does reward reflect outcome quality?** Cannot be confirmed for the executed path without tracing
the status→reward mapping (open question). For the blocked path: no, by construction — a constant
cannot reflect anything about the specific situation.

**Do repeated identical experiences dominate the cumulative average?** Yes, definitively — this is
the entire mechanism behind §2.1's frozen score, and is a direct, unavoidable mathematical consequence
of an unbounded arithmetic mean.

**Is reward magnitude meaningful?** Only weakly — `0.05` is close to the low end of the documented
`[0.0, 1.0]` scale, presumably intended to discourage the blocked action, but its meaning relative to
a *real* execution's reward (unknown formula) cannot be assessed without that formula.

**Can negative outcomes reverse previous learning?** In principle yes (the averaging formula would
pull the average down given enough low-reward samples) — but at the sample counts already accumulated
(tens of thousands), no realistic number of future rewards could move the average by more than a
negligible amount, so the answer in practice is effectively no for this specific entry.

**Can successful outcomes reinforce behavior?** Same answer, symmetrically — yes in principle, no in
practice once `n` is large, for the same arithmetic reason.

**Can reward be gamed by the agent?** No evidence of intentional gaming was found or is architecturally
plausible given the current design (VECTOR does not choose its own reward function or observe reward
before choosing an action) — this is a low-concern item given the current architecture, not
investigated further.

**Proposed future reward architecture (design only, not implemented):**
- Per-action-type reward functions, explicit and inspectable (§G above), replacing any single global
  status→reward mapping.
- A bounded/decaying update rule (§E above) so reward always retains real influence.
- A distinct, non-constant penalty for counterfactual blocks, scaled by the counterfactual's own
  occurrence-count/confidence (§F above) rather than a flat number.
- Reward provenance logged via the state-change log (§7) so a future auditor can always answer "why
  was this specific reward value assigned" without re-deriving it.

## 9. Forgetting/Decay Model

| Mechanism | Current state | V2 proposal |
|---|---|---|
| Policy decay | **None** — unbounded mean | Bounded EMA or `n`-cap (§E) |
| Memory (episodic) decay | Not confirmed either way this task — append-only by design, likely intentional (it's the ground-truth log) | Keep as append-only; decay belongs at the semantic/consolidated layer, not the raw log |
| Counterfactual decay | **Implemented but self-defeating** (§F) | Fix the reference-point bug (first-seen, not most-recent) |
| Confidence decay (epistemic) | **Implemented and working** (`decay_all()`/`check_staleness()`) | Reuse this exact pattern for semantic-fact confidence and policy confidence (a metric that doesn't currently exist, per §2.1) |
| Stale observations | Only the epistemic-belief staleness check exists; nothing analogous for semantic facts | Extend the same TTL-based staleness pattern to semantic memory once §B's consolidation layer exists |
| Obsolete preferences | N/A — preferences aren't a distinct subsystem yet (§D) | Design alongside §D — a preference should decay toward "unknown" (not toward some default value) if unconfirmed for a long period, since silently reverting to a default is itself a form of unattributed behavior change |
| Retention/pruning of audit tables | **None** for `gateway_audit`/`inference_calls` (Task 71 PERF-02) — deliberately correct for now | Schedule `InferenceObservability.prune()` and an equivalent for `gateway_audit`, but ONLY after the experiment's need for full-fidelity retention has passed |

**Special note on the counterfactual self-defeat (repeating for emphasis since it's the report's own
required special focus):** the fix is not "add decay" — decay already exists and is well-designed. The
fix is "stop resetting the clock on every observation of the same thing." This distinction matters
because a naive "add more decay" instinct would not fix the actual bug.

## 10. Contradiction/Reversal Model

Nothing in the current codebase has a primitive that is *distinguishable* from ordinary averaging for
"this new evidence contradicts and should specifically revise, not merely dilute, a prior belief."
Proposed V2 primitive: a **correction event**, structurally distinct from an ordinary outcome-reward
event, triggered only by:
1. An explicit owner statement (routes through `CorrectionLearner`, §2.7 — already the intended
   trigger, just never yet exercised).
2. A repeated, high-confidence outcome that is the opposite sign of an existing high-confidence belief
   (e.g. 5+ consecutive high-reward outcomes for an action_type whose policy score is currently low) —
   this is NOT the same as ordinary reward accumulation, because it should trigger a *step change*
   (e.g. resetting `n` partway, or applying a one-time larger update) rather than the same
   `1/(n+1)`-weighted nudge every other sample gets — precisely so that Level 6 (§5) is behaviorally
   distinguishable from Level 3's ordinary update rule, not just "the same mechanism, relabeled," which
   the task explicitly warned against accepting as sufficient evidence.

Every correction event should be logged via the same state-change log (§7), with an explicit
`event_type="correction"` tag, so a future observer can query "how many genuine corrections has
VECTOR undergone" as a distinct number from "how many ordinary reward updates occurred" — these
should never be conflatable in any future report.

## 11. Generalization Model

Every scoring/learning mechanism traced in this document is keyed by an *exact* hash
(`situation_hash = sha256(action_type + sorted(params))[:12]`, or `_jaccard()`'s token-overlap
similarity for counterfactual matching — closer to fuzzy, but still keyed to the specific proposal
text, not an abstracted situation class). **Nothing currently generalizes** in the Level-5 sense — an
action in a genuinely novel but related situation gets `DEFAULT_SCORE` (neutral), exactly as if it
had never been tried, rather than inheriting any partial confidence from a similar-but-not-identical
prior situation.

**Proposed V2 direction (design only):** introduce a second, coarser situation key alongside the
exact `situation_hash` — e.g. `situation_class = f"{action_type}:{goal_id}"` (dropping the
fine-grained params) — and let `PolicyMemory.get_score()` fall back to the class-level average
(clearly flagged as such, at reduced confidence) when the exact hash has no data, rather than falling
back to the flat `DEFAULT_SCORE`. This is a minimal, additive change (a second, coarser lookup, not a
replacement) that gives the system a genuine generalization path without requiring any ML/embedding
infrastructure — consistent with the project's own stated preference for simple, auditable mechanisms
over black-box ones (`policy.py`'s own docstring explicitly frames itself as intentionally simple).
The key design discipline: **the reasoning_chain (§7) must record whether a given score came from the
exact match or the generalized fallback**, so Level 4 and Level 5 evidence are never accidentally
conflated in a future observation report.

## 12. Experimental Proof Framework

Design only — none of these are to be executed now.

**Experiment A — experience → later behavior change.**
Initial state: capture `PolicyMemory.get_score(action_type, situation_hash)` for a specific pair.
Stimulus: a controlled, single real outcome for that exact pair (not fabricated data injection —
an actually-occurring, naturally-arising action/outcome, observed and recorded, consistent with this
whole experiment's "observe, don't manufacture" ethic). Expected learning event: `update_from_outcome`
fires, `sample_count` increments by exactly 1. Measurable internal-state change: `avg_reward` moves by
`(reward - old_avg)/(n+1)`. Later test: the SAME `(action_type, situation_hash)` pair is scored again
in a subsequent cycle; confirm the new score reflects the updated average. Control condition: a
different `(action_type, situation_hash)` pair that did NOT receive a new outcome in the interim,
confirmed unchanged. Success criterion: the treated pair's score changes by the exact predicted
amount; the control pair's does not change at all. Failure criterion: either moves unexpectedly.
Confounders: another cycle updating the SAME pair in between capture and test (mitigated by capturing
`sample_count`, not just the score, and confirming it incremented by exactly 1). Evidence required:
before/after `(avg_reward, sample_count)` pairs for both treated and control keys.

**Experiment B — same situation, with vs. without experience → different behavior.**
This is the controlled comparison Level 4 actually requires (§5). Initial state: two structurally
identical `situation_hash`es that have never been scored (both at `DEFAULT_SCORE`). Stimulus: feed a
real, high-reward outcome to ONE of the two (again, naturally-arising, not manufactured). Expected
learning event: only the treated key's row updates. Later test: both keys are scored in a subsequent
decision cycle where BOTH are legitimately viable candidates (this is the hard part — the current
architecture, per §5, essentially never generates more than one candidate, so this experiment cannot
even be RUN today without first fixing the candidate-diversification issue in §4/§B/§E — this
dependency should be stated explicitly as a precondition, not glossed over). Success criterion: the
treated key scores measurably higher and, critically, is *chosen* over the untreated one when both
are live candidates in the same cycle. Failure criterion: no measurable score difference, or a score
difference that does not change which candidate wins. Confounders: goal-alignment or urgency
differences between the two situations (control for this by using genuinely identical params).
Evidence required: full `reasoning_chain` breakdowns for both candidates in the deciding cycle.

**Experiment C — contradictory evidence → behavior reverses.**
Initial state: an established, high-`n`, high-average policy entry. Stimulus: a controlled sequence of
opposite-sign real outcomes for the same key, of sufficient count to test whether the (post-V2, per
§10) correction mechanism engages. Expected learning event: a `correction` event, not an ordinary
update. Measurable internal-state change: `avg_reward` moves by an amount inconsistent with the
ordinary `1/(n+1)` formula (i.e., larger than what accumulation alone would produce — this is exactly
how Level 6 becomes distinguishable from Level 3, per §10). Later test: the key's score, and whether
it's chosen. Control: a key that receives the SAME number of updates but consistent (not
contradictory) sign, confirmed to move by the ordinary formula's predicted amount, not the
correction-triggered amount. Success criterion: the treated key shows a discontinuity in its update
size; the control does not. Confounders: distinguishing genuine environmental change (the world
actually got different) from noise — this experiment cannot fully rule this out without a real
correction-detection mechanism (§10) actually being built first.

**Experiment D — generalization to a novel but related situation.**
Requires §11's proposed situation-class fallback to exist first. Initial state: a well-established
exact-hash entry, and a *different* `situation_hash` under the SAME `situation_class` that has never
been scored. Stimulus: none new — this tests whether the existing entry's confidence transfers.
Expected: the novel situation's score comes back above `DEFAULT_SCORE`, sourced (per §7's
reasoning_chain requirement) as "class-level fallback," not "exact match." Success criterion: score
differs from `DEFAULT_SCORE` AND is correctly labeled as a fallback, not silently presented as if it
were an exact match. Failure criterion: no transfer (still exactly `DEFAULT_SCORE`), OR transfer that
isn't correctly attributed as a fallback (a "looks right for the wrong reason" failure mode).

**Experiment E — learned behavior decays after sufficient time.**
Initial state: a confident belief/policy entry. Stimulus: none — pure time passage, no new evidence
either direction. Expected: for subsystems with decay (epistemic confidence today; policy/semantic
memory only after §9's proposed extensions), confidence measurably drops after the declared TTL/decay
window. Success criterion: a query of the same key before and after the window shows a lower
confidence value with NO intervening write. Failure criterion: no change (decay not actually firing on
a schedule), or a change that coincides with an intervening write (confound — must confirm no write
occurred via the state-change log, §7).

## 13. False-Positive Learning Patterns (Failure Modes)

| Pattern | Detection strategy |
|---|---|
| Retrieval mistaken for learning | Require Level 3+ evidence (§5) — a retrieval alone never qualifies, regardless of how sophisticated the retrieval mechanism looks |
| Repeated deterministic behavior mistaken for adaptation | Compare against a documented, source-traced deterministic explanation FIRST (this document's own central method, §1/§6C) before accepting a behavioral-change claim as learning |
| Clock/context change mistaken for learning | This document's own §6/anticipation finding is the worked example — always check whether a wall-clock-driven or context-driven deterministic function fully explains an observed change before crediting experience |
| Random variation mistaken for learning | Require the controlled comparison of Experiment A/B, not a single before/after snapshot |
| Prompt changes mistaken for learning | Log and diff the actual prompt template/version alongside any LLM-influenced decision; a score change coincident with an un-logged prompt edit is not learning |
| Model-provider changes mistaken for learning | `inference_observability`'s own `provider`/`model` columns (already exist, per Task 61) should be cross-checked against any claimed behavior change — a provider failover mid-comparison is a confound, not evidence |
| Memory contamination | The provenance model (§7) — an `experience_id` that could not plausibly have been observed before the decision it's cited as influencing is a contamination red flag |
| Reward leakage | Verify the reward-computing function never has access to information that wouldn't be available at real decision-time (not evaluated as a current risk, §8, but worth checking in any future reward-function redesign) |
| Confirmation bias | Require corroboration counts (§B's `count>=2` convention) before promoting any inferred fact, and never let a single self-generated action's own success/failure directly write a "preference" (§D) |
| Self-reinforcing policy loops | Exactly the `analyze_progress` pattern (§2.1/§2.2) — a loop where every rejection produces the identical evidence that generates the next identical rejection; detect via occurrence-count monitoring on the (proposed, §F) UPSERT-based rejection tracking |
| Stale knowledge | Require decay (§9) on every learned value, not just epistemic beliefs |
| Overfitting | Not yet a meaningful risk given the current architecture's simplicity (no generalization exists yet to overfit) — becomes relevant once §11 is implemented; flag for that future stage |
| Catastrophic forgetting | Not a current risk for the same reason; becomes relevant if/when any neural or embedding-based component is introduced — out of scope for this document's proposed (non-ML) architecture |
| False causal attribution | §7's entire design — recency-windowed, single-writer-attributed, A/B-verified |

## 14. Failure Modes (Systemic, Beyond the Table)

- **The biggest systemic risk in a V2 implementation is fixing §4/§E/§F in isolation** and declaring
  victory the moment `analyze_progress`'s score moves even slightly — a moving number is Level 3 at
  best, not Level 4, per §5's own bar. Any future report MUST run something like Experiment B, not
  just observe a score change, before claiming behavioral adaptation.
- **A second, subtler risk:** once candidate diversification (§4/§B) is fixed, the system may start
  generating MULTIPLE candidates per cycle for the first time in its observed history — this is
  itself a significant regime change that could be mistaken for "VECTOR learned to be more creative,"
  when it is actually just a bug fix removing a structural constraint. This should be documented
  explicitly as a known confound for the first post-fix observation period, not treated as evidence of
  anything.

## 15. Future Implementation Stages (Not Implemented Now)

| Stage | Scope | Source areas | Dependencies | Risks | Tests required | Behavioral verification | Rollback |
|---|---|---|---|---|---|---|---|
| **0 — Instrumentation** | Add the state-change log (§7) as a purely additive new table; no existing table touched | New module, e.g. `core/memory/learning_log.py` | None | Low — additive only | Unit test: every existing writer (`PolicyMemory`, `CounterfactualMemory`, `epistemic.merge_belief`) emits exactly one log line per call | A live run showing the log populating alongside existing tables, no behavior change | Drop the new table; zero impact on existing behavior |
| **1 — Clean learning-event model** | Define `LearningEvent` as a typed wrapper around what's logged in Stage 0 | Same module | Stage 0 | Low | Unit tests on the wrapper's own serialization | N/A yet — still purely additive | Same as Stage 0 |
| **2 — Experience/outcome linkage** | Thread `experience_id` through `Action.params` and into `_execute_action`'s result | `core/loop/permission_gateway.py`, `core/loop/autonomous_loop.py` | Stages 0-1 | Medium — touches the hot action-execution path; must not change any existing behavior, only ADD a field | Regression: full 58A-58G + Task 57 suite must still pass unchanged (113/113, per this experiment's own established baseline) | A live cycle where an action's outcome can be traced back to the experience(s) that motivated it | Revert the added field; `Action`/result shapes are additive-only by design so this should be a clean revert |
| **3 — Persistent internal-state updates (§E, §F fixes)** | Bounded/decaying policy update; counterfactual first-seen decay fix; counterfactual UPSERT | `core/memory/policy.py`, `core/memory/counterfactual.py` | Stages 0-2 (for attribution to be meaningful) | **Highest risk of this whole plan** — directly changes the exact mechanism this entire 7-day experiment exists to observe; must NEVER be done before Segment 2 concludes | Before/after comparison against Segment 1/2's own frozen-score baseline, explicitly as a regression check ("did we accidentally change historical interpretation") | Experiment A (§12), run for real post-fix | Feature-flag the new update formula so the old one can be restored instantly if Segment 3 (a post-fix validation run) shows unexpected behavior |
| **4 — Policy adaptation (candidate diversification, §4/§B)** | Fix `generate_immediate_actions()`'s exact-equality filter; fix `_TAG_TO_ACTION`'s missing `tags` key; wire counterfactual suppression into candidate generation | `core/brain/goal_system.py`, `core/loop/autonomous_loop.py` | Stage 3 (so a diversified candidate pool has a working policy signal to act on) | High — this is the change most likely to visibly alter VECTOR's day-to-day behavior; requires the owner's explicit sign-off given how central this is to the whole system's observed personality so far | New unit tests for `generate_immediate_actions()` covering multiple simultaneously-eligible goals | Experiment B (§12) | Revert the filter/tags changes independently of Stage 3 — designed as separable |
| **5 — Contradiction/reversal (§10)** | New `correction` event type, distinguishable update-size logic | `core/memory/policy.py`, a new correction-detection helper | Stages 0-4 | Medium — risk of over-triggering "corrections" on ordinary noise if the trigger threshold is too loose | Experiment C (§12) | Experiment C, run for real | Disable the correction-event trigger; falls back to Stage 3's ordinary update behavior |
| **6 — Generalization (§11)** | Situation-class fallback scoring | `core/memory/policy.py`, `core/loop/decision_engine.py` | Stages 0-5 | Medium — a badly-chosen situation_class could over-generalize (treat genuinely different situations as the same) | Experiment D (§12) | Experiment D, run for real | Remove the fallback lookup; exact-hash-only behavior is the safe default |
| **7 — Meta-learning (§5 Level 7)** | Track per-domain learning-rate/reliability meta-parameters | New, not yet scoped in detail — explicitly the least-designed stage in this document, consistent with it being the least-evidenced current capability | Stages 0-6 | Highest uncertainty — no current architecture to build on | Not yet specifiable | Not yet specifiable | Not yet specifiable |

## 16. Test Strategy (for the future stages, not run now)

- Every stage above requires, at minimum, a regression run of the existing 58A-58G + Task 57 suite
  (113/113 passing, this experiment's own established baseline) before being considered mergeable —
  none of these changes should touch permission/security behavior, but the suite is cheap insurance
  against an accidental interaction.
- Stage 1's TEST-01 finding (§4) should be closed BEFORE Stage 3 is attempted — `_episode_pattern_predictions()`
  should get real behavioral test coverage first, since Stage 3+ will make the system's overall
  behavior more complex to reason about, and this specific function is the one piece of evidence this
  document leans on most heavily for the "not learning, just deterministic" distinction (§6/§2.5) —
  losing confidence in that distinction as complexity grows elsewhere would be a real problem.
- Every experiment in §12 should be run, in order, before its corresponding implementation stage is
  declared complete — not as an afterthought.

## 17. Open Questions

- The exact `status → reward` derivation on the real-execution path (§8) — not traced this task, a
  genuine gap in this document's own coverage.
- Whether `CounterfactualMemory.scenarios`'s `useful`/`feedback_reason` columns have any writer/reader
  anywhere (§2.2) — flagged, not resolved.
- Whether `episodic_memory` itself has any retention/pruning (assumed append-only, not independently
  re-confirmed this task specifically).
- Whether `_reflect_tick()` actually calls `decay_epistemic()` on the documented 2AM schedule (the
  docstring claims this; the call site itself was not independently re-verified this task).
- Whether plans are genuinely never created for any pre-seeded goal (§2.8) — requires a post-experiment,
  read-only DB check to settle with certainty.
- Where, if anywhere, `skill_memory` is written (§J) — genuinely unknown, not merely unconfirmed.
- Whether any currently-existing mechanism reads `ContextEngine.track_beliefs()`'s belief namespace
  (Pathway A, §2.3) — a repo-wide search beyond this task's time budget would be needed to state this
  with full confidence; treated as "no consumer found" (not "no consumer exists") throughout.

## 18. Exact Source References

`core/memory/policy.py` (full file read this task) · `core/memory/counterfactual.py` (lines 1-100
read this task, remainder per Task 71's own citations) · `core/loop/decision_engine.py` (lines
265-424 read this task — the central new finding of this document) · `core/loop/autonomous_loop.py`
(lines 1090-1118, 1260-1276, 1490-1507 — the last two read this task specifically to confirm the
`record_epistemic_belief()` call-site reachability question) · `core/brain/goal_system.py`,
`core/brain/anticipation.py`, `core/voice/ambient_listener.py`, `vectorcode/src/reasoning_bank.py`,
`scripts/integration_check.py` — all per Task 71's own direct citations, treated as verified-by-Task-71
rather than re-read from scratch this task, per this document's own stated policy of not blindly
re-deriving already-source-confirmed findings · `.claude/rules/memory.md` (read this task, for the
documented-vs-actual provenance/confidence convention gap noted in §2.1).

## 19. Verified Facts vs. Inferred Behavior vs. Proposed Architecture

- **Verified facts** (source read this task or Task 71, with exact file/line citations): §2's entire
  inventory table content marked with a specific line number or "confirmed this task"/"re-confirmed";
  the full dataflow diagram in §3 for every edge marked S2 or higher; the S0-S5 matrix in §4.
- **Inferred behavior** (a reasoned conclusion from verified facts, not itself directly observed):
  the claim that `action_domain:analyze` was never written during Segment 1 (§2.3) is an inference
  from the confirmed call-site structure, not a direct database observation (which this task was
  forbidden from making) — presented with its reasoning shown, not as an established fact. Similarly,
  every "why the frozen score is exactly 0.66" explanation in §1/§3 is an inference chain, clearly
  reasoned, but not a database-confirmed fact.
- **Proposed architecture** (this document's own design work, not existing in the codebase in any
  form): all of §6 (Learning Architecture V2), §7 (causal attribution), §9's proposed extensions,
  §10, §11, §12's experiments, and §15's implementation stages. None of this exists in VECTOR today.
  None of it was implemented by this task.

---

## STATUS

```
Production code changed: NO
Runtime configuration changed: NO
Database changed: NO
Running VECTOR interacted with: NO
Experiment stimulus introduced: NO
Documentation created: YES — VECTOR_TECHNICAL_KNOWLEDGE/72_LEARNING_ARCHITECTURE_V2.md
```

**5 most important architectural conclusions:**

1. VECTOR's learning subsystems are not dead code — they are real, integrated, and mostly S3 — but
   almost none of the write→read loops actually *close* for the specific behavior the experiment has
   observed. The gap is connective, not existential.
2. The `analyze_progress` stall has a complete, multiply-corroborated, four-part mechanistic
   explanation (§1) spanning goal-filtering, dead refinement logic, an unbounded policy average, and
   a self-defeating counterfactual decay — this is the single most load-bearing finding across Tasks
   66-72 combined.
3. `decision_engine.py` contains a genuinely working, closed epistemic-confidence loop
   (`record_epistemic_belief()` / `_epistemic_penalty()`) that this task is the first to fully trace
   — it simply has never been fed an input for the one action that matters most, because that
   action's own early-return (the counterfactual block) sits upstream of the only two call sites that
   would populate it.
4. Nothing in the current system demonstrates Level 4 (behavioral adaptation) by this document's own
   definition — the strongest current evidence tops out at Level 2-3. This is a precise, defensible
   restatement of every prior observation task's conclusion, not a new finding, but now backed by an
   explicit ladder rather than intuition.
5. The single highest-leverage, lowest-risk future change is fixing the counterfactual decay
   reference point (§F) — unlike the policy-averaging fix or the candidate-diversification fix, it
   does not require deciding on a new reward formula or risking a large behavioral regime change; it
   restores an already-designed, already-intended mechanism to working order.

**5 things that must NOT be implemented until after Segment 2:**

1. Any change to `core/memory/policy.py`'s update formula (§E) — directly alters the mechanism the
   experiment exists to observe.
2. Any change to `core/memory/counterfactual.py`'s decay/rejection-storage logic (§F) — same reason.
3. Any change to `core/brain/goal_system.py`'s candidate-generation filter or `_TAG_TO_ACTION`'s
   `tags`-key wiring (§4/§B) — the single most behavior-altering change identified in this whole
   document; requires explicit owner sign-off even after the experiment concludes, given how central
   it is to VECTOR's observed personality so far.
4. Any change to `decision_engine.py`'s `record_epistemic_belief()` call sites or `_epistemic_penalty()`
   thresholds — this mechanism's current inertness for `analyze_progress` is itself part of what
   Segment 2 is measuring.
5. Any new database table or schema addition (§7's state-change log, or any other proposal in this
   document) — every design in this document is explicitly future work, gated on the experiment's
   conclusion, per the task's own absolute rule against schema changes now.
