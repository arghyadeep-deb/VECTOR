# 86 — Adversarial Architecture Review of Task 85

**Reviewer role:** independent senior AI-systems architect. Not the implementer. Not the author of
Tasks 51–85. My prior turn produced Task 84; I have treated it as evidence to be attacked, not as
my own settled conclusion, and I contradict it in two places below.

**Mode:** read-only. No source, config, database, or runtime state modified. No process started,
stopped, signaled, or interacted with. No implementation. One file created: this document.

**Evidence labels:** **[V]** verified by me this session from current source; **[V-DB]** verified
by me from a read-only query; **[85]** claimed by Task 85 and re-checked by me; **[85-U]** claimed
by Task 85 and *not* independently verifiable in my environment; **[NEW]** finding not in Tasks
51–85.

**Environment limitation, stated up front:** `vector_memory.db` is SQLCipher-encrypted and no
`sqlcipher3`/`pysqlcipher3` binding exists in my inspection environment. I therefore **could not
independently verify Task 85's live goal-table read** (§6 of that document). I verified the
*source* that produces and consumes those values instead — which turned out to be more damaging
to Task 85's plan than the table itself.

---

## 0. Verdict in one paragraph

Task 85 is a competent, well-disciplined plan that correctly identifies **a** bottleneck and
mis-identifies it as **the** bottleneck. Its central thesis — "three or four keys and one progress
field" — is **half right and half backwards**. The half that is right: the PolicyMemory key
mismatch is real, I re-verified all of it, and it does strand the richest reward signal in the
codebase. The half that is backwards: Task 85's single most emphatic architectural claim — that
`_score_candidate()`'s `policy` term (weight 0.20) is *"the only place in the entire system where
a persisted value from a past cycle changes a future decision's score"* — is **factually false**.
There is a second such place, it carries **1.5× the weight** (`goal_alignment`, 0.30), it is
already fully closed, and it is **pathological**: it is a negative-feedback loop with an absorbing
state that has been progressively deleting VECTOR's own candidate diversity for two months and
will, if Task 85's P2 ships as written, delete the goal set entirely. Task 85 proposes to optimise
the smaller, broken loop while leaving the larger, working, self-destructive one untouched — and
its P2 accelerates the destruction. Separately, its P0 is the wrong fix at the wrong layer and
would destroy the only loud diagnostic signal the project has; its P2 contains a direct internal
contradiction with a live RED-tier permission consequence; its P4 would suppress the only 34
actions VECTOR actually performed in 107 hours; and its Experience table is a fifteenth memory
system wearing an index costume, under-specified on every hard question the owner asked about it.

---

## 1. Independent reconstruction of the core loop

Traced from current source this session. I have deliberately **not** awarded "learning" for a
write.

| # | Transition | Status | Basis |
|---|---|---|---|
| 1 | world → **observation** | **PROVEN present, PROVEN degraded** | `observe_loop` real; `_tick_count` (increments only on a completed non-timeout tick, `autonomous_loop.py:653`, initialised 0 and never restored) advanced 23,545 in the first ~20 h and **103 in the next ~85 h** against a 0.5 s design interval. Zero observe timeouts logged. |
| 2 | observation → **context** | **PROVEN** | `get_world_state()` returns a real 16-key dict, six-plus consumers. |
| 3 | context → **beliefs** | **PROVEN write / PROVEN no scoring reader** | `track_beliefs()` writes 5 `belief:*` claims; `_epistemic_penalty()` reads only `action_domain:*` (`decision_engine.py:291`). Disjoint namespaces, one table. |
| 4 | beliefs → **goals** | **PROVEN absent** | `generate_immediate_actions()` reads no belief, no world state. It reads only the persisted goal list. |
| 5 | goals → **candidates** | **PROVEN, and PROVEN degenerate** | Two branches only: active SHORT goals; and LONG/MID goals with `progress == 0.0` *exactly*. `GOAL_ACTION_MAP = {"SHORT":"research_topic","MID":"analyze_progress","LONG":"analyze_progress"}` **[V]** — every MID and LONG goal, whatever its subject, collapses to one action type. |
| 6 | candidates → **scoring** | **PROVEN** | 5-factor linear form, weights `W_GOAL .30 / W_CONF .25 / W_POLICY .20 / W_URGENCY .15 / W_TIMING .10 / W_COST .05` **[V]**, × epistemic factor ∈ [0.70, 1.0]. **No LLM participates in scoring.** |
| 7 | scoring → **counterfactual** | **PROVEN, post-selection only** | `should_avoid()` runs in `_act_on()` after the winner is chosen; `decision_engine.py` has zero references to `CounterfactualMemory`. |
| 8 | counterfactual → **decision/action** | **PROVEN blocked** | The veto `return`s before execution, outcome, reward, epistemic write, goal-progress update, and the Permission Gateway. |
| 9 | action → **outcome** | **PROVEN for the executed path, PROVEN unreachable for the dominant path** | The 5-factor reward at `autonomous_loop.py:1254-1260` is real and reads owner feedback. The dominant candidate never gets there. |
| 10 | outcome → **reward** | **PROVEN** | Two reward channels: the 5-factor formula (real) and a hardcoded `reward=0.05` on the veto branch (`:1115`) **[V]**. |
| 11 | reward → **persistence (policy)** | **PROVEN, mis-keyed** | Five writers, three serialisations, one reader **[V]** — see §4. |
| 12 | reward → **persistence (goal progress)** | **PROVEN, and this is the finding Task 85 missed** | `_increment = round(0.10 * reward, 3)`; `progress = min(1.0, progress + _increment)`; persisted **[V]** (`autonomous_loop.py:1291-1298`, and again at `:1515-1520` for plan steps). |
| 13 | persistence → **retrieval** | **PROVEN for goal progress. FALSE for the rich policy reward.** | `_score_goal_alignment()` reads `progress` every score **[V]**. `get_score()` reads a key three of five writers never write **[V]**. |
| 14 | retrieval → **future decision** | **PROVEN via goal_alignment (0.30). ABSENT via policy (0.20, constant).** | `progress_gap = 1.0 - progress`; `score = max(priority/10 × progress_gap)` **[V]**. |

**Conclusion of §1, and the core of this review:** the loop is not open at one point and closed
everywhere else. **There are two closed experience→behaviour loops. Task 85 found the broken one
and missed the working one — and the working one is destroying the system.**

---

## 2. Attack on Task 85's central thesis

> *"The system does not need a new brain. It needs three or four specific keys to match, one
> goal's progress field to stop being the sole source of candidate diversity, and one coroutine to
> stop hanging forever."*

### 2.1 The claim is refuted on its own terms **[NEW]**

Task 85 §14 states, in bold, as the single sentence that names the fix:

> *"`DecisionEngine._score_candidate()`'s `policy` term (weight 0.20) is the only place in the
> entire system where a persisted value from a past cycle changes a future decision's score.
> … There is no second link to build."*

There is a second link. It is already built. Verified this session:

```
reward  ──0.10×reward──>  goal["progress"]  ──persisted to semantic_memory.goals_v1──>
        get_active_goals()  ──>  _score_goal_alignment()
        score = (priority/10) × (1.0 − progress)   ── weight 0.30 ──>  total_score
```

Every element is source-verified **[V]**: the increment (`autonomous_loop.py:1291`), the
persistence (`goal_system.update_goal_progress`, which writes and calls `_persist()`), the
retrieval (`get_active_goals()`), and the consumption (`_score_goal_alignment`, `decision_engine.py`).
It is a complete experience → outcome → persistence → retrieval → changed-future-decision chain at
**1.5× the weight of the policy term**.

Task 85's thesis is therefore not merely incomplete — the plan is built on an inventory of the
scoring function that is wrong about its largest persisted input.

### 2.2 The second loop is pathological, and that is worse than it being missing **[NEW]**

The loop's sign is **negative**, and it has an **absorbing state**:

- Success on a goal raises `progress` → raises nothing; it *lowers* `progress_gap` → *lowers*
  `goal_alignment` → *lowers* the score of every future candidate for that goal.
- `update_goal_progress()` sets `status = "completed"` at `progress >= 1.0` **[V]**, and
  `get_active_goals()` filters to `status == "active"` **[V]**. Completion is **permanent and
  irreversible** — there is no code path that reactivates a completed goal.
- `progress` is therefore **not a measure of goal achievement**. It is a cumulative reward counter.
  A goal is auto-retired after roughly ten successful actions of reward ≈1.0, **whether or not the
  goal was achieved**.

This explains the candidate-diversity collapse far better than Task 85's account does. Task 85
says: *the lock exists because `g_kiit_attendance` happens to be the only goal at exactly 0.0.*
The source says something stronger and much more alarming: **the seed data has six goals at
exactly `progress: 0.0`** **[V]** (`g_kiit_attendance`, `g_karpathy_30`, `g_placement_prep`,
`g_daily_commit`, `g_first_revenue`, `g_equation_portfolio`; only `g_vector_phase1` starts at
0.25). Task 85's own live read reports four of those now sitting at 0.076 and `g_daily_commit` at
1.0/`completed` **[85-U]**.

So VECTOR did not start with one candidate. **It started with six and acted its way down to one.**
Every goal it successfully executed against got bumped off exactly-0.0 and became permanently
ineligible for the unstarter branch. The single goal it *never* successfully executed against —
because the counterfactual veto blocks it on 100% of cycles — is the only one still at 0.0, and is
therefore the only candidate left.

That is a **deadlock that is stable precisely because the veto works**:

```
veto blocks analyze_progress → no execution → no reward → no progress increment
   → progress stays exactly 0.0 → goal stays eligible → same candidate re-proposed
   → veto blocks it → …  (30,504 times, one distinct decision_id, over 81 days)
```

And `g_daily_commit` — a *recurring daily habit* goal, the one goal that would have contributed a
differently-typed `research_topic` candidate — has been permanently deleted from the active set by
a mechanism that interpreted "VECTOR did ten successful things related to committing" as "the goal
of committing daily is now complete forever." **[NEW]**

### 2.3 Consequence: Task 85's P2 makes this worse, not better

P2 proposes replacing `progress == 0.0` with a staleness threshold so more goals re-enter
rotation. Under the mechanism above, that means: more goals re-enter → get executed → accumulate
`0.10 × reward` per success → climb → auto-`complete` → **leave the active set permanently**. The
end state of Task 85's P2, run long enough, is `get_active_goals()` returning `[]` and
`generate_immediate_actions()` returning `[]` and VECTOR proposing **nothing at all**.

This is not a hypothetical extrapolation. It is the mechanism that already consumed
`g_daily_commit`, applied to the remaining six goals with the eligibility gate removed.

### 2.4 So: could P0/P1/P2/P3 produce genuine behavioural learning?

**Yes — narrowly, and only after correcting the above.** With the key fixed, the veto channel
separated, and the progress loop repaired, VECTOR would have a real, honest, closed policy-learning
loop. That is genuine, valuable, and would legitimately reach L4 on the project's own ladder.

**But it would still fundamentally lack every capability the owner listed, and the reason is
structural, not incremental:**

- **Situation understanding.** The "situation" is `sha256(action_type + params)` where `params` is
  `{"goal_id": ..., "title": "Start: <free text>"}` **[V]**. That is an *identifier*, not a
  representation. It supports equality, not similarity, inference, or description. No amount of
  key-fixing turns an identifier into an understanding.
- **Causal attribution.** Attribution here means "which action produced this reward". The system
  would gain that. It would still have no notion of *why* — no mechanism relating an outcome to
  the state of the world that produced it, because the world state is explicitly excluded from the
  key (Task 85 §4.3 defers it) and `context_snapshot` is carried on the Candidate but never read
  by `total_score` **[V]**.
- **Temporal context.** `PolicyMemory` is a cumulative arithmetic mean with **no decay and no
  recency weighting** **[V]** (`new_avg = (old_avg*n + reward)/(n+1)`, `policy.py:92`). It cannot
  represent "this used to work and no longer does". At n = 29,164 it is numerically frozen.
- **Generalization.** Exact-hash keying only. Two situations that differ by one character of a
  goal title are, to this system, unrelated universes.
- **Self/world modelling and consequence prediction.** Absent, and nothing in P0–P3 creates a
  substrate for them.
- **Meaningful interpretation.** The decision layer is **model-free** — six scalars into a fixed
  linear form. No LLM participates in any decision. Interpretation cannot emerge from a weighted
  sum of six numbers regardless of how good the numbers get.

**The honest description of the post-P3 system is: a contextual bandit over roughly fifteen
hard-coded action types, keyed by a brittle exact hash, scored by a hand-tuned linear form.**
That is a real learning system. It is not a cognitive foundation, and calling the document a
"Cognitive Foundation Remediation Plan" is where the framing error enters.

---

## 3. Attack on P0 (hypothesis-loop timeout)

### 3.1 Task 85's own §3 is correct and I verified it

`ollama_safe.chat()`'s semaphore *is* bounded — `acquire(timeout=CONFIG.get("ollama_semaphore_timeout_sec", 60.0))`
with a `finally`-guaranteed `release()` **[V]**. Task 85 was right to exclude it, and right to flag
`_multi_backend_fallback()` as the one branch it had not traced.

### 3.2 I traced that branch. It is the actual defect, and it is not in `hypothesis_loop` **[NEW]**

`_multi_backend_fallback(model, messages, timeout, *, caller_id)` accepts a `timeout` parameter and
**never uses it.** A grep for `timeout` across the entire function body returns **zero matches**
**[V]**. Its three engine calls —

```python
LiteLLMEngine().generate(fallback_messages, model=litellm_model, max_tokens=2048)
AppleFMEngine().generate(fallback_messages, model=model, max_tokens=2048)
GemmaCppEngine().generate(fallback_messages, model=model, max_tokens=2048)
```

— pass **no timeout, no deadline, and no circuit breaker** (unlike the Ollama path, which wraps its
call in `_wrap_with_circuit_breaker`). This is an **unbounded synchronous blocking primitive**,
reachable whenever the Ollama daemon is unavailable *or* the 60 s semaphore acquire times out.

And `ollama_safe.chat()` is called **synchronously from inside `async def` functions** at
`Governor._llm_classify()` (`governor.py:1655`) and `AgentBase.vchat()` (`agent_base.py:335`)
**[V]** — i.e. on the event-loop thread, on the path taken by the 43,312-dispatch district
pipeline.

This is a third instance of the exact defect family Tasks 55, 56 and 80 kept finding: **a parameter
or key accepted at a boundary and silently discarded.** (55: `"hypothesis"` vs `"text"`. 80:
`sorted(items)` vs `json.dumps`. Here: `timeout` accepted and dropped.) That pattern — not any
individual bug — is the real recurring architectural weakness, and no task in the series has named
it as such.

### 3.3 Why Task 85's P0 is the wrong fix at the wrong layer

1. **Coverage.** Only **3 of 21 coroutines** have any `asyncio.timeout` — `observe` (15 s), `think`
   (60 s), `reflect` (config) **[V]**. Task 85's P0 fixes one of the eighteen unguarded ones.
   `anticipation`, `research`, `growth`, `predict`, `sync`, `scheduler`, `sense`, `command_poll`
   and nine others remain unbounded, and so does the entire district-dispatch path, which is 97% of
   all activity. Per-coroutine timeouts are whack-a-mole against a shared unbounded primitive.
2. **It masks the instrument.** The 69.9-hour `latency_ms` row in `inference_calls` is the single
   loudest anomaly signal this project has produced. Bounding the caller at 60 s converts a
   screaming, unmistakable artifact into a routine "timeout" indistinguishable from ordinary
   provider flakiness. **You would destroy the diagnostic before using it.** Task 85 schedules the
   thread-dump diagnostic *after* P0 ships; that ordering is exactly backwards.
3. **It is not established as the starvation cause, and Task 85 says so itself** (classification
   "B — plausible, strengthened by elimination, not proven"). Shipping an unproven fix first, and
   thereby removing the evidence needed to test it, is the worst available sequencing.
4. **The benefit is small even if it works.** It restores ~26 hypothesis attempts per 107 hours to
   a pipeline whose output goes to a `suggestion_queue` with **zero autonomous readers**.

### 3.4 Ranked runtime issues by actual causal importance

| Rank | Issue | Why | Evidence |
|---|---|---|---|
| 1 | `_multi_backend_fallback` ignores its own `timeout`; three unbounded `generate()` calls, no breaker | The only *unbounded* primitive found; reachable from the highest-volume path; fixes all 21 coroutines and the dispatch path at once | **[V]**, grep-confirmed |
| 2 | `ollama_safe.chat()` (sync) called from `async def` in `Governor._llm_classify()` and `AgentBase.vchat()` | Puts (1) on the event-loop thread; 8,223 Ollama calls / 49.3 cumulative hours | **[V]** |
| 3 | Event fan-out: unbounded `_tracked_task()`, zero dedup/cooldown/depth limit, two closed cycles | Generates the load that (2) blocks on; 43,312 dispatches; also the dominant measurement noise | **[V]** |
| 4 | 18 of 21 coroutines have no timeout | Systemic, but a symptom of (1) — fix the primitive, not each caller | **[V]** |
| 5 | `hypothesis_loop`'s missing timeout | Real, but one caller of (1), and its output has no consumer | **[V]** |

**Is Task 85's thread-dump diagnostic sufficient?** Necessary, well-scoped, and nearly sufficient —
but it is a *sampling* instrument and can miss a rare long block. I would add one deterministic,
zero-behaviour-change probe: log `time.monotonic()` deltas around each `await asyncio.sleep(...)`
in `observe_loop`/`think_loop` and compare against the requested interval. A sleep(0.5) that
returns after 3,000 s is unambiguous proof of loop starvation and tells you *when*, so it can be
correlated against `inference_calls.timestamp`. That is a two-line, revert-safe addition and it
discriminates "blocked in-thread" from "queued behind `to_thread`" without `PYTHONASYNCIODEBUG`.

**Verdict on P0: reject as scoped. Replace with "bound `_multi_backend_fallback`" and run the
diagnostic *first*.**

---

## 4. Attack on P1 (canonical PolicyKey)

### 4.1 Independent verification of every writer and reader

I re-read all of them **[V]**:

| Site | Formula | Matches reader |
|---|---|---|
| **Reader** `decision_engine.py:268` → `get_score()` `:379` | `f"{action_type}:{sorted(params.items())}"` | — |
| `autonomous_loop.py:1112` (veto penalty, `reward=0.05`) | `f"{action_type}:{sorted(params.items())}"` | **YES** |
| `autonomous_loop.py:1046` (VectorCode reward) | `json.dumps(params, sort_keys=True, default=str)` | NO |
| `autonomous_loop.py:1263` (5-factor reward) | same `json.dumps` form | NO |
| `autonomous_loop.py:1493` (plan-step reward) | `plan_step:` prefix + `json.dumps` | NO |
| `hands/runner.py:145` | `sha256(f"hand:{name}")`, no params | NO |

Task 85's table is accurate. **But it under-counts the problem: there are at least eight
serialisation implementations, not five.** Also present **[V]**:

- `PolicyMemory.make_situation_hash()` (`policy.py:24`) — a `@staticmethod` that already does
  `json.dumps(context, sort_keys=True, default=str)`. **A canonical function already exists, in the
  class that owns the table, and neither the reader nor any of the four `autonomous_loop` writers
  use it.**
- `core/api/routers/commands.py:44` — a *third* private `_make_situation_hash(params)`.
- `core/memory/router.py:180,316` — two more call sites routing through `PolicyMemory`'s version.

**Task 85 proposes creating a *new* module `core/loop/policy_key.py`.** That is larger than
necessary and adds a ninth thing. The minimal correct fix is to make `PolicyMemory.make_situation_hash`
the single source of truth and have the reader and all writers import it — the function is already
written, already correct, already co-located with the table it keys, and already used by two call
sites.

### 4.2 Is PolicyMemory actually the central learning mechanism? **NO.**

By weight it is second (0.20) behind `goal_alignment` (0.30) **[V]**. By *current* influence it is
last: its value has been the constant 0.05 for 29,164 samples. By *design* influence it is the
only one intended to carry outcome information — but §2 shows `goal_alignment` also carries outcome
information today, via `progress`, and does so more strongly and more destructively.

Calling PolicyMemory "the biggest bottleneck" is defensible only if you have already excluded the
goal-progress loop. Task 85 did not examine it.

### 4.3 Would canonicalizing the key make VECTOR learn from *noisier* rewards? **Yes — and worse than noise: it would learn from a category error.** **[NEW]**

This is the sharpest technical objection in this review.

Today, writer #1 (`reward=0.05`, hardcoded, written when the counterfactual **vetoes** an action
before it runs) and writer #3 (the real 5-factor outcome reward) write to **different buckets**,
because their serialisations differ. Canonicalizing the key **merges them**.

Post-fix, for any action type that is sometimes vetoed and sometimes executed, `policy_memory`'s
single `avg_reward` column becomes a plain arithmetic mean of:

- a **control-flow artifact** — "this proposal was suppressed before execution", and
- an **outcome measurement** — "this action ran and went well/badly".

These are not the same quantity, and `update_from_outcome` has no way to distinguish them
(`new_avg = (old_avg*n + reward)/(n+1)`, no channel, no tag, no decay) **[V]**. Since the veto
fires far more often than execution on any contested action, the constant would dominate the mean
and *suppress* the very signal P1 exists to reconnect.

**The current bug is accidentally protecting the reward channel from contamination.** Fixing the
key without first separating the channels converts a disconnected-but-clean signal into a
connected-but-corrupted one. That is a regression dressed as a repair.

There is also a second-order effect specific to the dominant action: `analyze_progress` is vetoed
on **100%** of cycles, so its new canonical bucket would immediately begin filling with 0.05s and
never receive a real reward. **P1 delivers exactly zero benefit for the currently-dominant path**,
and Task 85 does not say so.

### 4.4 Does `action_type + params` contain enough situation information? **No, and it fails in both directions simultaneously.**

- **Too specific.** `params` for the unstarter branch is `{"goal_id": ..., "title": f"Start: {goal['title']}"}`
  **[V]** — the key embeds a **free-text goal title**. Rename a goal and every learned value for it
  is silently orphaned. Learning is destroyed by an edit that has nothing to do with the action.
- **Too coarse.** No world state, no time-of-day, no presence, no resource state. `check_attendance`
  at 3 a.m. with the owner absent and `check_attendance` at noon mid-class are the *same* key.
- **Collision risk across sources.** Plan-step candidates and goal candidates for the same action
  type will collide once the `plan_step:` prefix is normalised away — Task 85's canonical form
  drops it without discussing what that merges.

**Is adding situation context now necessary rather than premature?** Not full situation context —
Task 85 is right that key granularity deserves its own experiment. But the **minimal** correct move
is not "canonicalize the bytes and change nothing else". It is:

1. Define the key over a **declared, whitelisted set of defining params** (`goal_id`, `action_type`,
   `source`) and explicitly exclude free-text display fields (`title`).
2. Add a `v2:` schema prefix so old and new rows can never silently merge.
3. Keep the *reward channel* separate from the *suppression channel*.

That is still a one-function change and it avoids building learning on a key that a typo can void.

### 4.5 **YES/NO verdict — is Task 85 correct to fix only serialization first?**

**NO.**

Fixing only serialization, first, in isolation:
- merges a control-flow constant with outcome rewards into one undifferentiated mean (§4.3);
- delivers zero benefit for the action that constitutes 100% of current decisions;
- leaves the key brittle to a goal-title edit (§4.4);
- and is sequenced ahead of the larger, pathological `goal_alignment` loop it never examined (§2).

**The correct first policy change is: stop writing the veto penalty into the reward channel.**
Canonicalization is second, with a param whitelist and a version prefix. That ordering costs the
same effort and does not manufacture a new attribution defect.

---

## 5. Attack on the Experience table

### 5.1 Is it a necessary missing primitive? **Partly — the *identity* is necessary; the *table* is not.**

The real missing primitive is a **stable id that survives from candidate to outcome**. Task 85 is
right that nothing today can answer "what happened as a result of *this* decision" in one lookup.

But it does not follow that a new eleven-field table is required, because **the correlation rows
already exist**:

- `DecisionEngine.evaluate()` already writes a `decision_candidate` episodic row per candidate.
- `PermissionGateway` already writes a `gateway_audit` row per gated action.
- `PolicyMemory` already writes the outcome row.
- `governor.dispatch()` already writes a `governor_dispatch` episodic row.

What is missing is a shared column, not a shared table.

**Smaller alternative (my counter-proposal):**

> Mint one `decision_id` (ULID, monotonic) per `_think_tick`, carry it on `Candidate`, and stamp it
> into (a) the `context` JSON of the existing `decision_candidate` episodic row, (b) the existing
> `gateway_audit` row, and (c) a single new nullable `decision_id` column on `policy_memory`'s
> update path — or, if adding a column is unacceptable, into the episodic outcome row only.
>
> Cost: one id generator, three stamp sites, no new table, no new write per cycle beyond what
> already happens. Correlation becomes a join on an existing column.

This satisfies the actual requirement (traceability) at roughly a fifth of the surface area, and it
does not create a fifteenth memory system in a codebase whose diagnosed disease is fourteen
disconnected memory systems. Task 85's own §13 sets "reduce fragmentation, don't add subsystems" as
the governing principle and then proposes a new table in §7; that is an internal tension it
resolves by asserting the table is "a connective index, not a new memory tier". An eleven-field
append-only table with its own accessor module and its own write path in the hot loop *is* a new
memory tier, whatever it is called.

### 5.2 The hard questions Task 85 does not answer

The owner asked seven specific design questions. Task 85's schema answers none of them, and each
is a genuine blocker:

| Question | Task 85's schema | Verdict |
|---|---|---|
| Write volume — "one row per decision cycle" | 1,198 cycles / 107 h ≈ **269 rows/day** — trivial | But **does a `governor.dispatch()` count as a decision cycle?** 43,312 / 107 h ≈ **9,700 rows/day**. Task 85 never says. This is a 36× ambiguity in the central new artifact. **UNDER-SPECIFIED.** |
| Should vetoed candidates get rows? | Yes (`executed: false`) | **Correct, and the best idea in the schema** — `reward: null` vs `0.0` is a genuine fix. |
| Should *unexecuted* (losing) candidates get identity? | Silent | They must, or §7's counterfactual work has nothing to reference. **MISSING.** |
| Does experience belong to decision, action, or outcome? | Conflated into one row | It spans all three with different lifetimes. One row forces a single write time, which is why async outcomes cannot be represented. **WRONG SHAPE.** |
| How are retries represented? | No `attempt`, no `parent_experience_id` | Two attempts of the same action produce two rows with the *same* `policy_key` and no relation. **CANNOT REPRESENT.** |
| How are multi-step plans represented? | No `plan_id`/`step_id` | Plan-step rewards already use a distinct prefix that Task 85's canonicalization removes. Step→plan attribution becomes impossible. **CANNOT REPRESENT.** |
| How are asynchronous outcomes attributed? | Single write "per completed action cycle", no `completed_at` | A content post whose real outcome (engagement) arrives days later cannot be attributed at all. **CANNOT REPRESENT.** |
| How is partial success represented? | One scalar `reward` | `reward_components` is present and is the right instinct, but there is no notion of "the action ran, produced output, and the output was unused" — precisely the `ScriptGenerator` case (7,401 scripts, zero consumers). **CANNOT REPRESENT.** |

### 5.3 If an Experience record is built anyway, this is the minimum schema

Drop to six fields plus two relations, and split the write:

```
decision_id     ULID          -- minted at candidate generation, one per tick
candidate_id    ULID          -- one per candidate in that tick (losers included)
policy_key      str           -- v2 canonical, whitelisted params
outcome_ref     ULID | null   -- filled later, possibly much later; null = not yet resolved
disposition     enum          -- proposed | vetoed | gated_denied | executed | failed | abandoned
reward          float | null  -- null until an outcome exists; never defaulted to 0.0
```

with `reward_components`, `situation_class`, `params`, `source`, and timestamps living in the
**already-existing** episodic row that this id points at. Two rules make it correct where Task 85's
is not: **`outcome_ref` is nullable and written by a second, later update** (async outcomes), and
**every candidate gets a `candidate_id`, not just the winner** (counterfactual reference).

### 5.4 One safety gap in the proposal, unmentioned

`params` is persisted verbatim. `params` carries free text today (`title`) and will carry more once
tag routing lands. There is no redaction rule and no field allowlist. An append-only log of every
decision's raw params is a new, permanent, un-reviewed data-retention surface. **A defining-field
allowlist should be a hard requirement, not an optimisation.**

---

## 6. Attack on P2 (candidate diversity)

### 6.1 Both claimed facts verified

- `GOAL_ACTION_MAP = {"SHORT": "research_topic", "MID": "analyze_progress", "LONG": "analyze_progress"}`
  with the gateway-safety comment **[V]** — Task 85 quoted it accurately.
- Goals **do** carry `tags` (`PRESEEDED_GOALS` entries and `add_goal()`'s `entry["tags"] = tags or []`)
  **[V]**, and `generate_immediate_actions()`'s two dict builders **do not copy them** **[V]**, so
  `_TAG_TO_ACTION` is dead. Task 85 is correct.

### 6.2 Tag propagation is a **RED-tier permission change**, and Task 85 contradicts itself about it **[NEW]**

Task 85 §6.3 says, correctly, that `GOAL_ACTION_MAP` must not be touched because it is *"a
deliberate, documented, gateway-safety decision"* — the map's own comment says it exists *"so every
generated action passes the GREEN/YELLOW gate without being classified as UNKNOWN."*

Task 85 then makes tag propagation its **#2 highest-leverage change**, described as *"a one-line
fix that reconnects a 21-entry, already-written mapping at zero new-code cost."*

Verified consequences of that one line **[V]**:

- `_TAG_TO_ACTION` maps `coding`, `build`, `debug`, `fix`, `implement`, `write_code`, `refactor`
  → **`code_task`**.
- `core/config.py:258` lists `"code_task", "code_generate", "code_fix", "code_debug"` in the **RED**
  tier, annotated *"code write + execute paths"*, moved there by the 2026-08-04 hardening.
- Goal `g_vector_phase1` carries `tags: ["vector", "coding", "build"]`. The builder takes the
  **first** tag present in the map — `"vector"` is absent, `"coding"` matches — so this goal would
  generate an `action_type="code_task"` candidate.

So P2's "zero-cost one-liner" **causes the goal system to autonomously generate RED-tier
candidates for the first time in VECTOR's history** — defeating the exact property Task 85 cites,
three paragraphs earlier, as the reason not to touch the map.

**Is it an escalation?** No, and I want to be precise rather than alarmist: `code_task` is a member
of `_VC_ACTION_TYPES` **[V]**, so `_act_on()` routes it through `gw.classify()` and, since the
2026-09-02 Task-53 fix, `gw.execute()` for `("RED","YELLOW")` **[V]**. The gateway holds. **It is
not a bypass.** But it is a real, unreviewed behavioural change: VECTOR would begin autonomously
raising RED-tier council reviews and Pushover approval requests for code tasks it decided to
propose on its own. That is a change in the *owner's* security posture (§15.3), shipped under the
label "zero new-code cost".

Note also that P2's two changes **combine** to produce this: `g_vector_phase1` sits at
`progress=0.25`, so it is ineligible today; only the *staleness-threshold* change admits it, and
only the *tags* change re-types it. Either alone is comparatively inert. Together they are the
escalation path. Task 85 evaluates them separately and never composes them.

### 6.3 Does more candidate diversity create meaningful cognition? **No.**

It creates more *arms on the bandit*. That is a genuine precondition for measuring policy learning
(Task 78's Level-4 result requires ≥2 close candidates) and it is worth having for that reason
alone. It is not cognition. Post-P2 the generator is still: iterate a fixed list of ≤7 persisted
goals, apply a fixed 21-entry string→string map, emit ≤4 dicts. **No world state, no beliefs, no
time, no context enters candidate generation at any point** **[V]** — `generate_immediate_actions()`
takes no arguments but `limit`. Diversity here means "a different deterministic constant", not "a
different judgement".

### 6.4 Could low-progress goals generate irrelevant actions? **Yes, and the mechanism guarantees it.**

Because `progress` is `0.10 × reward` accumulated (§2.2), a "stale" goal under Task 85's threshold
is not a goal that needs attention — it is a goal that **VECTOR has not recently been rewarded for
acting on**. Those are different things, and for a goal like "Maintain KIIT attendance above 75%"
they can be opposites: attendance may be perfectly fine while the goal reads 0.0 forever because
the action is vetoed. A staleness threshold built on this field will systematically surface goals
by *inaction-of-VECTOR*, not by *need-of-owner*.

### 6.5 Minimum candidate-generation architecture for meaningful competition

Not situation understanding — that is later and larger. The minimum is four properties, in this
order:

1. **A progress field that means progress.** Decouple `goal.progress` from reward accumulation
   (§14/R3). Until this holds, every eligibility rule built on `progress` is built on a reward
   counter wearing a progress label.
2. **≥2 candidates of *different* action types reaching scoring in the same tick**, produced
   deterministically and reproducibly. The cheapest honest source is the staleness threshold
   *alone*, without tag re-typing — it admits more goals, all still mapped through the
   gateway-safe `GOAL_ACTION_MAP`. This gets competition without touching permission tiers.
3. **Tag routing gated by a GREEN-only allowlist.** If tags are propagated, filter
   `_TAG_TO_ACTION`'s targets against `CONFIG["permission"]["green"]` at candidate-construction
   time and fall back to `GOAL_ACTION_MAP` otherwise. Two lines, and it preserves the invariant the
   map was written to hold.
4. **A recurrence model for recurring goals.** `g_daily_commit` is a *daily habit*; the schema has
   no way to say so, so it was auto-completed out of existence. A `recurring: bool` (or a
   `resets_at` cadence) is the smallest field that stops the goal system consuming itself.

Only after those four does "candidate generation should depend on situation understanding" become
a meaningful next step rather than a bigger version of the same open loop.

---

## 7. Attack on the counterfactual design

`Decision.all_candidates` exists **[V]**, so Task 85's runner-up design is *implementable*. Its
refusal to fabricate the untaken branch's outcome is **correct and should be preserved verbatim**.

But the name is wrong, and the mechanism as designed cannot learn. Taking the owner's five
distinctions in order:

| Concept | Requires | Does Task 85's design achieve it? |
|---|---|---|
| **Alternative selection** | Knowing what else was considered | **Yes** — `all_candidates` gives it for free |
| **Counterfactual representation** | A stored record of the road not taken | **Yes** — the scenario row |
| **Simulation** | A model that predicts the alternative's outcome | **No**, and correctly so — forbidden |
| **Causal inference** | Isolating the effect of choosing A over B | **No** |
| **Outcome comparison** | Outcomes for *both* branches | **No** — the alternative's outcome is permanently `null` |

**What VECTOR may legitimately claim after this change:** *"VECTOR records which alternatives it
considered and what happened to the one it chose."* That is **decision provenance**, and it is
genuinely valuable — every forensic task from 79 to 84 would have been faster with it.

**What it may not claim:** counterfactual reasoning, regret minimisation, or learning from
alternatives. Task 85's §5 proposes an aggregate — *"of the last K close calls where A beat B, how
did A's outcomes trend"* — and then writes an adjustment back into PolicyMemory. **That aggregate
contains no information about B.** It is a statistic about A's outcomes, conditioned on B having
existed. Writing it back into A's policy value as though it were comparative evidence is a
category error that would silently double-count A's own rewards.

### 7.1 The missing option Task 85 never considers: bounded exploration **[NEW]**

There is exactly one way to obtain a real outcome for the untaken branch without fabricating it:
**occasionally take it.** ε-greedy exploration — with ε small (1–2%), a cooldown, and a hard
restriction to **GREEN-tier action types only** — produces genuine paired outcomes over time at
zero LLM cost and zero fabrication. It is strictly smaller than a simulation layer and strictly
more informative than a null column.

Task 85 rules out fabrication (right) and then designs a mechanism that cannot learn (wrong)
without noticing that the honest third option exists. **Exploration is the correct minimum path to
real counterfactual learning, and it must be GREEN-only** — an exploration policy that can select
a YELLOW or RED action is a learning mechanism with a permission consequence (§15).

**Verdict: keep the scenario record, rename the capability to "decision provenance", delete the
write-back aggregate, and defer real counterfactual learning until bounded GREEN-only exploration
is on the table as its own reviewed change.**

---

## 8. Attack on the epistemic design

### 8.1 Is keeping `action_domain:*`/`belief:*` separate from PolicyMemory correct? **Yes.**

Task 85's argument is sound and I endorse it without qualification: reliability-context ("is this
domain trustworthy right now") and reward ("did this action go well") answer different questions,
and merging them destroys the ability to distinguish *stale* from *bad*. That distinction is
exactly what let Task 85 diagnose the self-inflicted TTL handicap. **Keep them separate.**

### 8.2 Connecting `belief:*` into scoring (P4) is the most dangerous proposal in the plan **[NEW]**

Three verified reasons to refuse it as specified:

**(a) The beliefs are mutually contradictory *right now*.** The live epistemic table holds, at the
same timestamp, `belief:presence:absent = owner_absent` (confidence 0.70) and
`belief:screen_activity:active_coding` (confidence 0.70) **[V-DB, prior turn]**. Someone is coding
on the machine while the presence detector reports nobody is there. The table has no contradiction
mechanism — same-key writes silently overwrite, cross-key inconsistency is not modelled at all.
**Connecting a sensor to scoring before it can be shown to be self-consistent is connecting noise
to behaviour.**

**(b) The proposed use would suppress the only actions VECTOR performs.** Task 85's worked example
is *"`belief:presence:absent` should suppress or deprioritize proactive-nudge candidates."* All 34
gateway actions in the entire 107-hour run were `proactive_*` **[V-DB, prior turn]**, and
`presence:absent` has held continuously for five-plus days. P4 as written would take VECTOR's real
external output from 34 actions to approximately zero and would look, in every dashboard, exactly
like the system becoming *more* thoughtful. That is the "hidden heuristic layer that suppresses
useful actions" the owner asked about, and it is not hypothetical — it is the predictable outcome
on the current data.

**(c) It inverts the intended semantics of the mechanism it copies.** `_epistemic_penalty()` is
carefully designed so that **ignorance is never penalised** — an unknown domain returns
`(1.0, 0.0)`, explicitly commented *"we don't penalise first-time actions"* **[V]**. A
presence-based suppressor penalises the *absence of an observation* (nobody detected) rather than
the presence of evidence. Same table, opposite epistemics.

### 8.3 What evidence should be required before a belief may affect a decision

Four gates, all cheap:

1. **Provenance mandatory.** `source` already exists on the claim row **[V-DB]** (`face_detector`,
   `screen_observer`, `goal_system`, `act_loop`). Make it required and make the consumer able to
   filter by it. A belief with no traceable sensor may never score.
2. **Calibration before consumption.** A sensor must demonstrate agreement with ground truth over a
   measured window before its output is allowed into scoring. `presence` currently fails this
   observably (§8.2a). This is one offline check, not a subsystem.
3. **Contradiction must be explicit.** A same-key write with a materially different value inside
   the TTL should emit a `contradiction` event rather than overwrite. Task 85 proposes this and it
   is right; I would make it a **precondition** for P4 rather than a companion to it.
4. **Bounded, symmetric influence.** Reuse the existing `[0.70, 1.0]` clamp and never widen it. A
   belief may dampen; it may not veto.

**Should belief confidence decay?** It already does (`decay_rate`, `ttl_hours=72`, `check_staleness`)
**[V-DB]**, and this is the single best-implemented piece of the epistemic subsystem. The bug is
not the decay — it is that decay currently produces a **self-inflicted handicap**: the three
`action_domain:*` claims are stale past TTL only because execution starved, so a revived candidate
would be maximally penalised for the system's own inactivity. **Staleness caused by starvation must
be distinguishable from staleness caused by genuine age.** That is a one-field fix
(`last_write_attempt` vs `last_seen_at`) and it should precede P4.

---

## 9. Attack on the memory architecture

### 9.1 Independent classification

I re-verified the three load-bearing "dead" claims myself this session **[V]**:
`CorrectionLearner.validate_lesson()` — zero callers in `core/`, `districts/`, `hands/`;
`AgentBase.get_system_prompt()` — zero callers; `ReasoningMemory.get_training_data` — reachable only
via `core/api/crud.py` → an HTTP router. Task 85's matrix is accurate.

| Mechanism | State | **My disposition** |
|---|---|---|
| Agent HP → selection | ACTIVE, saturated | **C — freeze** (see §10) |
| Goal progress → `goal_alignment` | **ACTIVE, pathological** — Task 85 omits it entirely | **A — repair first** (§14/R3) |
| PolicyMemory (veto writer) | Connected, constant | **A — split the channel** (§4.5) |
| PolicyMemory (5-factor / VC / plan writers) | Orphaned by key | **A — connect, second** |
| PolicyMemory (Hands writer) | Orphaned by design (no matching `Candidate` ever built) | **D — deprecate**; it cannot be connected without inventing hand-candidates |
| CounterfactualMemory `rejections` | ACTIVE, one-directional | **C — freeze**, it works |
| CounterfactualMemory `scenarios`/`outcomes` | DEAD, 0 rows in 81 days | **C — freeze until exploration exists** (§7) |
| Epistemic `action_domain:*` | Mechanism live, signal starved | **A — unstarve via execution, not via new writes** |
| Epistemic `belief:*` | Orphaned | **C — freeze** until §8.3's four gates pass |
| EpisodicMemory | ACTIVE for anticipation, log otherwise | **C — keep as ground truth, unchanged** |
| SemanticMemory | Effectively DEAD (`goals_v1` only, 2 months stale) | **B — merge**: it is being used as a KV store by `loop_state`; give goals their own table and stop calling this "semantic memory" |
| ReasoningMemory (`reasoning_chains`) | DEAD | **D — deprecate**: relabel as an export/debug table and stop reporting its row count as a learning signal |
| ReasoningBank (file) | DEAD, injected into an unread field | **E — delete the injection.** It costs a read and a write per scoring cycle for provably zero effect. This is the one clear deletion. |
| Ghost memory (`lessons`/`best_decisions`) | DEAD | **D — deprecate the computation**, keep `agent_history` as an audit record |
| CorrectionLearner | Partially active | **A — connect `validate_lesson()`**, cheapest real capability gain in the codebase |
| Anticipation | ACTIVE, deterministic | **C — freeze** |

### 9.2 Should we add an Experience table on top of this? **No — see §5.1.**

The diagnosed disease is fourteen disconnected persistence mechanisms. The proposed cure is a
fifteenth. Even accepting Task 85's framing that it is "an index, not a tier", an eleven-field
append-only table with its own module and its own hot-path write is a tier. **A `decision_id`
column stamped into rows that are already being written achieves the stated goal with no new
table.**

### 9.3 Smallest coherent memory architecture

Five stores, one identity, one rule:

```
episodic      (append-only ground truth; every row carries decision_id when one applies)
semantic      (consolidated facts ONLY; goals and loop_state move OUT to their own tables)
policy        (reward channel ONLY; suppression moves to its own column/table)
epistemic     (reliability + situational beliefs; two namespaces, one contradiction log)
counterfactual(rejection blocklist; scenarios frozen until exploration exists)

identity:  decision_id (ULID) minted per tick, carried on Candidate, stamped into every
           row any of the five writes as a consequence of that tick.
rule:      no store may be written by more than one serialisation of its own key.
```

Correction lessons live in episodic (they already do). Reasoning chains become an export view, not
a store. That is five, down from fourteen, with **zero new tables** and two things moved out of a
store they never belonged in.

---

## 10. Attack on agent evolution

**Recommendation: freeze both. Neither should ship before the learning loop is measurable.**

**HP habituation asymmetry — freeze, and Task 85's own reasoning shows why.** The dampener is not a
bug; it was a deliberate 2026-08-05 fix for an observed pathology (every agent pinned at 1000,
making `max(HP)` an arbitrary tiebreak) **[V, docstring]**. Changing the shaping function changes
**which agent instance runs for every district task in the city** — the single widest blast radius
of any change in Task 85's plan. And it changes it *precisely along the dimension you are trying to
measure*: if you alter agent selection while simultaneously trying to detect whether policy
learning changes behaviour, you cannot attribute an observed change to either. Task 85 lists it as
its #5 highest-leverage change and P1-adjacent; it should be **after** the first learning proof,
not before.

There is also a real reason to fix it eventually that Task 85 states less precisely than it could:
`_reason_award_counts` is an **in-memory dict, not persisted** **[V]**, so the dampener resets on
every boot and every successor spawn while HP itself persists. That makes the shaping
**boot-dependent** — the same work earns different HP depending on how recently the process
restarted. That is a genuine correctness defect and it is worth fixing *as a defect*, on its own,
with its own before/after measurement — not as a lever to unblock learning.

**Successor dict/object contract — freeze, but for a different reason.** The fix itself is correct
and Task 85's approach (call the already-correct `spawn_from_ghost()` rather than patch the
dict-returning legacy path) is right. But it is **not the bug that is currently firing**. Task 83
established, and Task 85 correctly carries forward, that the registry path executed exactly **once**
in 107 hours; the 5,558 subsequent "deaths" come from **one orphaned object held by an untraced
stale reference outside `AgentRegistry._agents`**. Fixing `spawn_successor()` fixes a path that
runs once every four days. **The stale-reference bug is the live defect and it is still untraced.**
Shipping the successor fix first would let the team believe the APITester problem is solved when
the actual mechanism is untouched.

**Precise recommendation:** freeze both. Trace the stale reference (read-only, cheap, and the last
concrete unexplained object-lifetime bug in the system). Fix the successor contract and the HP
persistence *together, afterwards*, as a single "agent lifecycle correctness" change with its own
measurement, once the cognitive measurements are no longer in flight.

---

## 11. Attack on event fan-out

**Classification: CRITICAL — and Task 85 ranks it #8 and #9 of 10, which is its second-largest
ordering error.**

**Could fan-out contribute to event-loop starvation? Yes, on verified evidence.** The chain is:

```
_fanout_handler → unbounded _tracked_task(governor.dispatch(...))   [V: no semaphore, no depth cap]
    → Governor.route_task() → _llm_classify()                       [V: governor.py:1655]
        → ollama_safe.chat()  — a SYNCHRONOUS function              [V]
            → (on daemon-unavailable or 60s semaphore timeout)
              _multi_backend_fallback() — UNBOUNDED                 [V: §3.2]
```

Every link verified. Fan-out is the **load generator** for the one unbounded blocking primitive in
the system, on the event-loop thread, 43,312 times in 107 hours. It is not a downstream cleanup
item; it is upstream of the runtime problem Task 85 puts at P0.

Three further reasons it must move early:

1. **It corrupts every measurement.** Any experiment run on the live system competes with ~9,700
   dispatches/day and ~19,000 LLM calls. You cannot cleanly measure a policy-ranking change inside
   that noise floor.
2. **It is the cheapest large win available.** A per-edge TTL dict is a few lines, in-process, no
   persistence, and it can only *reduce* activity — it is monotonically safe and trivially
   revert-safe.
3. **`strategy` is free.** 4,655 dispatches to a district with zero registered agents, each logging
   `"no agents in strategy"` **[V-DB, prior turn]**. Retire the edge or staff it. Zero risk.

**On the re-keying proposal:** re-keying `PUBLISH_EVENTS` by `(district, task_type)` is correct in
principle but is **not** the urgent part, and it is riskier than Task 85 implies — it changes which
downstream tasks fire, i.e. it changes behaviour. The cooldown/dedup is the safe, urgent half.
**Ship cooldown + `strategy` retirement now; defer re-keying until after the first measurement
baseline is established.**

---

## 12. The understanding gap — challenging the freeze

Task 85 freezes the Understanding Layer entirely. **I agree with freezing most of it and disagree
about three items**, and the disagreement matters because these three are not "understanding
features" — they are **preconditions for the learning loop being measurable at all**.

| Capability | Task 85 | **My call** | Why |
|---|---|---|---|
| Situation representation | Freeze | **Partially before P3** | Not full representation — but the *key* must at minimum exclude free-text and declare its defining fields (§4.4). Otherwise every learned value is one goal-title edit from deletion. This is key hygiene, not understanding. |
| Contradiction detection | Freeze (mentions it) | **BEFORE any belief→scoring** | §8.3. It is a comparison and a log line. It is the precondition for trusting the sensor at all. |
| Self-correction (`validate_lesson`) | Freeze | **BEFORE P3** | The function exists, is correct, and has zero callers **[V]**. Wiring it is the cheapest real capability gain available and it closes an outcome→belief loop that is otherwise open. |
| Temporal reasoning | Freeze | **Freeze, with one exception** | Distinguish starvation-staleness from age-staleness (§8.3) — one field, needed for P4 to be honest. |
| Uncertainty | Freeze | **Freeze** | `confidence=0.7` is hardcoded at candidate construction **[V]**; calibrating it is real work with no current consumer. |
| Entity/state tracking | Freeze | **Freeze — agree** | Genuinely absent, genuinely large. |
| Causal reasoning | Freeze | **Freeze — agree**, but audit first | `core/brain/causal_graph.py` is written to every cycle (`CausalGraph().add_edge()` in `_act_on`) and Task 85 flags it as never audited. Something is accumulating causal edges that nobody has read. Audit before building anything causal. |
| Self-model / world-model / intent inference / consequence prediction / simulation-in-production | Freeze | **Freeze — agree, emphatically** | Each would be a fifteenth-through-nineteenth subsystem on a foundation that does not close. |
| Generalization | P6 | **Move later than P6** | Requires a situation representation that does not exist. Hash-bucket `situation_class` is architecture substituting for what embeddings do natively (§13). |

**The honest answer to the owner's framing:** the roadmap as written does **not** create a
foundation for Astra-class situational understanding, and it is important to say why precisely
rather than as a complaint. **The decision layer is model-free.** Six scalars, six fixed weights, a
multiplicative clamp. No language model participates in any decision VECTOR makes about what to do
next — LLMs are used only *inside* district agents to execute an already-chosen task. Understanding
cannot be added to a weighted sum by improving the numbers. It requires the decision layer to
consume a *representation* rather than a *hash*, which is a different architecture, not a later
phase of this one.

That is not an argument against Task 85's roadmap. It is an argument against calling it a
*cognitive foundation*. It is a **reward-system foundation**, and it should be honestly scoped as
one so that the understanding work can be planned as the separate, larger programme it is.

---

## 13. Model capability vs architecture

| Limitation | Cause | Do **not** fix by |
|---|---|---|
| One candidate per cycle, 1,198/1,198 identical | **D** candidate generation (+ the goal-progress loop, §2.2) | a bigger model — no model is consulted |
| Policy value frozen at 0.05 | **F** attribution (key mismatch) + **I** learning (no channel separation) | a bigger model, or a new table |
| No situation similarity; exact-hash only | **G** decision architecture + **E** memory | adding `situation_class` buckets — this is **A/B territory** (embeddings do similarity natively); a hand-rolled hash bucket is architecture impersonating a model |
| No causal attribution across time | **F** attribution — no stable id | a new memory table (a column suffices) |
| Beliefs never reach decisions | **E** memory (disjoint namespaces) | connecting them before calibration (§8) |
| ~1,000× loop starvation | **H** runtime (unbounded fallback + sync-in-async) | anything cognitive |
| 43,312 dispatches, 8 pairs, 2 cycles | **C** orchestration | more districts or agents |
| "AI trends" ×7,401 | **B** prompt/context (hardcoded default) + **C** orchestration (task_type discarded) | a bigger model — the prompt is a constant |
| No consequence prediction / world model | **A** model capability **and** **G** architecture | a database of any kind |

**Two rules the plan should adopt verbatim:** (1) nothing in P0–P6 is a model-capability problem,
so no model change is warranted anywhere in this roadmap; (2) `situation_class` is the one place
the plan proposes architecture where model capability is the better tool — flag it, and when
generalization is eventually built, evaluate an embedding-based similarity before a hand-tuned
bucket function.

---

## 14. Red-teaming the roadmap

### 14.1 Where Task 85's ordering breaks

| Break | Consequence |
|---|---|
| **P0 ships before the diagnostic** | Destroys the 69.9 h latency signal — the loudest evidence available — before it has been used to test P0's own hypothesis (§3.3) |
| **P0 fixes a caller, not the primitive** | Leaves 17 other unguarded coroutines and the entire dispatch path exposed to the same unbounded fallback (§3.2) |
| **P1 before channel separation** | Merges a control-flow constant with outcome rewards in one mean; delivers zero benefit for the 100%-vetoed dominant action (§4.3) |
| **P2 before the goal-progress repair** | Accelerates irreversible auto-completion of the goal set (§2.3) |
| **P2's two halves composed** | Autonomous RED-tier candidate generation, contradicting P2's own stated constraint (§6.2) |
| **Fan-out at #8/#9** | It is the load generator for the runtime problem at P0, and the noise floor for every experiment (§11) |
| **P4 before belief calibration** | Would suppress the only 34 actions VECTOR performs (§8.2) |
| **HP + successor fixes "P1-adjacent"** | Changes agent selection city-wide during the exact window you are trying to measure learning in (§10) |
| **The goal-progress loop absent from the plan** | The largest persisted-state input to scoring (0.30) is unexamined (§2.1) |

### 14.2 My corrected ordering

**R0 — Measure before touching (no code change).**
Enable the existing `VECTOR_THREAD_DUMP_SEC` on a disposable clone; add the two-line
monotonic-drift probe around `observe_loop`/`think_loop`'s sleeps; snapshot `goals_v1`,
`policy_memory`, `epistemic.db`, `counterfactual.db` as an immutable baseline. **Nothing else may
ship until the starvation mechanism is named.**

**R1 — Bound the unbounded primitive.** Pass `_multi_backend_fallback`'s existing, ignored
`timeout` into its three `engine.generate()` calls and wrap the chain in one deadline. Fixes the
class for all 21 coroutines and the dispatch path at once. *This is the real P0.*

**R2 — Quiet the fan-out.** Per-edge TTL cooldown/dedup in `_fanout_handler`; retire or staff
`strategy`. Monotonically reduces activity; revert-safe; removes ~97% of measurement noise. Defer
the `(district, task_type)` re-key.

**R3 — Decouple reward from goal progress.** Stop `progress += 0.10 × reward`. Stop auto-`completed`
for goals without an explicit completion criterion; add `recurring`. *This is the highest-leverage
cognitive fix in the system and it appears nowhere in Task 85.*

**R4 — Separate the suppression channel from the reward channel** in PolicyMemory. A veto is not a
reward.

**R5 — Canonicalize the key** — reusing the existing `PolicyMemory.make_situation_hash`, with a
`v2:` prefix and a declared defining-field allowlist that excludes free text.

**R6 — Candidate diversity, staleness threshold only.** No tag re-typing yet. Then tags, gated by a
GREEN-only allowlist.

**R7 — `decision_id` correlation** stamped into rows that already exist. Not a new table.

**R8 — Wire `validate_lesson()`.** Cheapest real capability gain in the codebase.

**R9 — Epistemic: contradiction logging + starvation-vs-age staleness + sensor calibration.**
Only then consider `belief:*` → scoring, bounded to `[0.70, 1.0]`.

**R10 — Decision provenance** (record the runner-up; no write-back aggregate). Real counterfactual
learning waits for bounded GREEN-only exploration as its own reviewed change.

**Frozen throughout:** Experience table as specified; HP shaping; successor contract; understanding
layer; generalization/`situation_class`; new districts, agents, memories, or per-cycle LLM calls.

### 14.3 Summary of moves

- **Earlier:** fan-out cooldown (#8→R2); goal-progress decoupling (absent→R3); the diagnostic
  (after-P0→R0).
- **Later:** hypothesis timeout (P0→after R1, as a consequence of it); HP habituation (P1-adjacent→
  post-proof); successor contract (P1-adjacent→post-proof); belief→scoring (P4→R9 with four gates);
  generalization (P6→after a real situation representation).
- **Removed:** the Experience table (→R7 column); the counterfactual write-back aggregate;
  `ReasoningBank`'s injection (delete outright).
- **Merged:** the eight key implementations into `PolicyMemory.make_situation_hash`; goals and
  `loop_state` out of `semantic_memory` into their own tables.
- **Frozen:** everything in Task 85's own freeze list, plus HP, successor, and `belief:*`→scoring.

---

## 15. Safety review

**Baseline: nothing in Task 85 weakens `PermissionGateway`, the tier taxonomy, point-of-effect
gating, Governor routing, or taint/audit. No proposal removes or bypasses a gate.** The risks below
are indirect, and two of them are real.

### 15.1 Candidate generation → new action types **(REAL — must be blocked as specified)**

P2's tag propagation causes autonomous generation of `code_task`, which is **RED** **[V]**. The
gateway holds (`_VC_ACTION_TYPES` → `gw.classify()`/`gw.execute()` **[V]**), so this is **not an
escalation** — but it is an unreviewed change to what VECTOR autonomously asks permission *for*.
**Required control:** filter `_TAG_TO_ACTION` targets against the GREEN list at construction time.

### 15.2 Policy learning → trust-ladder promotion **(REAL, and unmentioned anywhere in Tasks 51–85)** **[NEW]**

`TrustLadder` promotes a YELLOW action to auto-execution after **a streak of
`trust_promotion_streak` consecutive approvals (default 20)** **[V, `trust_ladder.py`]**.
`PermissionGateway`'s YELLOW branch auto-executes a promoted action without owner confirmation.

Now compose that with working policy learning: a YELLOW action that earns good rewards scores
higher → is proposed more often → accumulates owner approvals faster → **crosses the promotion
threshold sooner** → begins auto-executing without a prompt.

**Learning does not bypass the gateway — it changes how quickly an action stops asking.** That is a
learning-driven change in effective permission friction, arriving through a mechanism nobody
designed to interact with learning. `commit_code` is YELLOW by explicit design **[V]** and is
exactly the shape of action that policy learning would favour.

**Required controls, all cheap:** (a) promotion should require a **minimum elapsed wall-clock
window** in addition to a streak count, so an increase in proposal *rate* cannot manufacture
promotion; (b) the streak should reset on any material change to the scoring path (a `policy_key`
schema bump should invalidate streaks); (c) promotion events should be surfaced to the owner as
notifications, not just DB rows.

### 15.3 Experience-driven learning → data retention **(REAL, unmentioned)**

Task 85's `Experience` persists `params` verbatim, append-only, forever, with no allowlist and no
redaction. `params` already carries free text and will carry more after P2. **A defining-field
allowlist must be a hard requirement**, and it is another reason to prefer the `decision_id`-column
approach (§5.1), which persists nothing new.

### 15.4 Exploration **(my proposal, §7.1 — must be constrained)**

ε-greedy exploration is a learning mechanism that **selects actions**. It must be hard-restricted to
GREEN-tier action types, with the tier check at selection time (not execution time), or it becomes
a learning mechanism that can choose to take a YELLOW/RED action. **GREEN-only, ε ≤ 0.02, cooldown,
and an explicit off switch.**

### 15.5 Agent HP → capability boundaries **(bounded, but non-trivial)**

Changing HP shaping changes which agent wins `max(HP)`. Capability matching still runs first
**[V]**, so an agent cannot acquire a capability it does not declare. But the *unconditional*
fallback (`max(agents, key=health_points)` when no agent declares the capability) means shaping
changes do alter who executes unmatched tasks. Bounded, not zero. Another reason to freeze (§10).

### 15.6 Event fan-out cooldown **(safe)**

Monotonically reduces dispatch volume. No new action types, no new reachability. **The safest
change in this entire review.**

### 15.7 Goal-progress decoupling **(safe)**

Touches no action type, no tier, no routing. Changes only a scoring input and an eligibility
predicate. Requires a `goals_v1` baseline snapshot first (data, not safety).

---

## 16. The minimum true learning loop, and L0–L5 for VECTOR

### 16.1 Smallest architecture that can prove X → Y → Z → persisted → retrieved → changed decision

No new tables. Six elements:

1. **`decision_id`** — ULID minted per `_think_tick`, carried on every `Candidate`, stamped into
   the `decision_candidate` episodic row that is *already written*.
2. **A reward channel that contains only rewards** — the veto penalty moves to its own column or
   table (R4). `reward = null` is a valid, distinct state from `reward = 0.0`.
3. **One canonical key** — `PolicyMemory.make_situation_hash`, `v2:` prefixed, over a declared
   defining-field allowlist (R5).
4. **≥2 competing candidates of different action types in the same tick**, deterministically
   produced (R6).
5. **A goal-progress field that is not a reward counter** (R3) — otherwise the 0.30-weight term
   moves for reasons unrelated to the experiment.
6. **A drift probe** confirming the loop is actually scheduling, so a null result means "no
   learning" rather than "the coroutine did not run" (R0).

That is the whole of it. Five repairs and one id. Nothing here is invention.

### 16.2 L0–L5, defined for VECTOR specifically

Each level is falsifiable against named tables and functions. **Each requires everything below it.**

- **L0 — Storage.** A row appears in `policy_memory` with a `situation_hash` produced by the
  canonical function. *Falsified by:* nothing written, or written under a non-canonical key.
  **Current state: PASS** (29,164 samples).

- **L1 — Retrieval.** `get_score(action_type, hash)` returns a value that a writer actually wrote —
  i.e. reader-key ≡ writer-key for the same logical `(action_type, params)`. *Falsified by:* the
  reader returning `DEFAULT_SCORE` for a pair that has samples. **Current state: FAIL for 3 of 5
  writers** — the whole of §4.

- **L2 — Influence.** The retrieved value appears as a non-constant `policy=` term in a logged
  `Winner:` line, and two candidates identical on all other factors receive different
  `total_score`s *because of it*. *Falsified by:* `policy=0.05` in 1,198 of 1,198 lines.
  **Current state: FAIL.**

- **L3 — Persistent learning.** A specific outcome, identified by `decision_id`, is shown to have
  moved a specific `policy_memory` row by exactly the amount `(old_avg·n + r)/(n+1)` predicts, and
  the row survives a process restart. *Falsified by:* a change that cannot be attributed to a named
  outcome, or that a restart loses. **Current state: mechanically available, never demonstrated
  with attribution.**

- **L4 — Behavioural adaptation.** In a tick where ≥2 candidates are live and equal on
  goal_alignment, confidence, urgency, timing and cost, **the winner changes** relative to a
  matched control run in which the L3 update did not occur. *Falsified by:* a score change that
  does not change the winner; or a winner change confounded by any other factor (this is why the
  goal-progress loop must be decoupled first — otherwise the 0.30 term is also moving).
  **Current state: proven in Task 78's lab, never in production.**

- **L5 — Generalization.** A candidate whose `policy_key` has **zero samples** receives a
  non-default score derived from a *related* key, and that inheritance changes the winner; and a
  matched *unrelated* key demonstrably does **not** inherit. *Falsified by:* leakage (unrelated
  keys benefiting) or no transfer. **Current state: architecturally impossible — exact-hash keying
  only.**

**Deliberately excluded from L0–L5:** row counts, function execution, LLM calls completing,
confidence numbers moving with no consumer, HP changing without a selection change, and "more
candidates were generated". None of these is evidence at any level.

---

## 17. Behavioural experiments

### 17.1 Review of Task 85's A–F

| Exp | Verdict |
|---|---|
| **A** — repeated experience → future decision changes | **Sound**, and it is the right first experiment. Note it and F are nearly the same experiment; A is the more complete of the two. |
| **B** — reverse the outcome, preference flips | **Unrunnable as written.** It bounds convergence by *"the EMA's own convergence rate"*. **There is no EMA.** `update_from_outcome` is a plain cumulative mean, `new_avg = (old_avg·n + reward)/(n+1)`, with no decay and no `n` cap **[V]**. Convergence time is `O(n)` in existing samples, so on any well-sampled key reversal is effectively impossible. The experiment must either be run only on low-`n` keys, or it becomes a test *of the update rule*, which is the more useful thing to test. |
| **C** — generalization | **Untestable today.** It depends on `situation_class`, which does not exist. Cannot be run before R5/R6 at the earliest, and honestly not before a real situation representation. |
| **D** — contradictory evidence changes a belief | **Sound in shape**, but depends on execution actually happening, which depends on R1–R3. Correctly identified as blocked. |
| **E** — restart persistence | **Sound and cheap.** Its most valuable assertion is the *negative* one — that HP habituation counters do **not** survive restart **[V]** — which is a real defect surfaced as a test. Keep. |
| **F** — two competing actions, learned policy changes ranking | **Proves policy adaptation. Proves nothing about understanding, and Task 85 nearly says so but then nominates it as the headline proof.** It demonstrates that a number written to a row can change an `argmax` over a linear form. That is L4 and it is worth having — but framed as validation of a *"Cognitive Foundation"* it overclaims by a wide margin. It should be labelled **"L4 policy adaptation"**, not "the plan's central claim proven". |

**The deeper problem with the set:** every experiment is run on candidates constructed *by the
experimenter* with hand-set scores. None tests whether VECTOR's own candidate generator, running
unattended against its own goals, ever produces two competing candidates at all. That is the
question 1,198 identical decisions actually pose, and no experiment in A–F addresses it.

### 17.2 Minimum progressive sequence

Each stage gates the next. Run every stage in Task 78's lab first, then on a disposable clone,
never on a live experiment.

- **E0 — Loop liveness (before any cognitive claim).** Assert `observe_loop` completes ≥ N ticks in
  M minutes and `sleep()` drift stays under a bound. *Proves:* the system is scheduling.
  *Without it, every null result below is uninterpretable.* **This is the experiment the whole
  series has been missing.**

- **E1 — Policy learning.** Task 85's Experiment A, unchanged, on a fresh low-`n` key.
  *Proves L1→L2→L3.*

- **E2 — Outcome attribution.** Given a `decision_id`, one query returns the candidate, the
  disposition, the outcome, and the exact policy row that outcome moved — and a *different*
  concurrent decision's row is shown **unaffected**. *Proves attribution, not just correlation.*
  The control is the point.

- **E3 — Persistence.** Task 85's Experiment E, with its habituation-reset assertion kept.
  *Proves L3 survives restart.*

- **E4 — Update-rule characterisation** (replaces Task 85's B). Feed k reversed outcomes to keys at
  `n ∈ {1, 10, 100, 10000}` and record how many are needed to flip the winner at each. *Proves*
  whether the current cumulative mean can ever represent "this stopped working" — and produces the
  evidence needed to decide whether an EMA or an `n`-cap is warranted, rather than assuming one.

- **E5 — Contradiction handling.** Write two mutually inconsistent beliefs (`presence:absent` +
  `screen_activity:active_coding` — the pair the system holds *right now* **[V-DB]**) and assert a
  contradiction event is emitted rather than a silent overwrite. *Proves the precondition for ever
  letting beliefs score.*

- **E6 — Native candidate competition (the one nobody has proposed).** Run the *unmodified* live
  generator against the real goal set for a bounded window and count ticks with ≥2 distinct
  `action_type`s. *Proves* the loop can produce competition on its own. **If E6 fails, E1's result
  is a laboratory artifact and L4 has not been achieved in the system, only in a fixture.**

- **E7 — Generalization.** Deferred until a situation representation exists. Not schedulable now.

**Note on what none of these prove:** situational or causal understanding. There is no experiment
in this sequence — or in Task 85's — that could demonstrate it, because the decision layer contains
no representation over which understanding could be assessed. Designing one would be premature and
I am explicitly not doing so.

---

## 18. Final verdict

### A. What Task 85 got exactly right

1. The PolicyMemory key mismatch — all five writers, the reader, the serialisation argument. I
   re-verified every line; the analysis is correct.
2. Excluding the Ollama semaphore as the hang mechanism, with the right evidence, and correctly
   flagging `_multi_backend_fallback` as the untraced branch. That pointer led directly to the real
   defect.
3. Identifying the tags-propagation gap and `GOAL_ACTION_MAP`'s collapse — accurate and precise.
4. Refusing to fabricate counterfactual outcomes.
5. Keeping EpistemicTracker separate from PolicyMemory, with the correct reasoning.
6. `reward: null` as a first-class state distinct from `0.0`. The best single idea in the plan.
7. Preserving the 29,164-sample bucket and the 30,504-row counterfactual history as a frozen
   baseline.
8. Its freeze list, which is disciplined and mostly correct.
9. Its evidence hygiene — the `[VERIFIED-HERE]` / `[FROM TASK 84]` labelling is exemplary and I have
   copied it.

### B. What Task 85 got wrong

1. **"The `policy` term is the only place a persisted value changes a future decision."** False.
   `goal_alignment` (0.30) does, via `progress`, which is written as `0.10 × reward` **[V]**.
2. **The goal-progress loop is pathological and absent from the plan** — negative feedback with an
   irreversible absorbing state that has already deleted one goal and explains the candidate
   collapse better than Task 85's account.
3. **P0 is the wrong layer** — one caller, not the unbounded primitive; and it destroys the
   diagnostic it depends on.
4. **P1 before channel separation** creates a new attribution defect and does nothing for the
   dominant action.
5. **P2's two halves compose into autonomous RED-tier candidate generation**, contradicting P2's
   own constraint.
6. **P4 would suppress the only actions VECTOR performs**, using a sensor that currently contradicts
   another sensor in the same table.
7. **Fan-out ranked #8/#9** when it is the load generator for the runtime problem at P0.
8. **"EMA-style"** — it is a plain cumulative mean, and Experiment B is built on the wrong model.
9. **HP and successor fixes scheduled during the measurement window.**

### C. What Task 85 over-engineered

1. The `Experience` table — eleven fields, a new module, a hot-path write, where a `decision_id`
   column on existing rows suffices.
2. A **new** `core/loop/policy_key.py` when `PolicyMemory.make_situation_hash` already exists,
   already canonical, already co-located **[V]**.
3. The counterfactual write-back aggregate, which double-counts A's rewards and contains no
   information about B.
4. `situation_class` as a hand-rolled bucket function — architecture where model capability is the
   better tool.

### D. What Task 85 under-specified

1. Whether a `governor.dispatch()` counts as a decision cycle for `Experience` — a **36×** ambiguity
   in write volume (269/day vs ~9,700/day).
2. Retries, multi-step plans, asynchronous outcomes, partial success — four of the owner's seven
   questions, none answerable in the proposed schema.
3. Whether losing candidates get identity (required for its own §5 to work).
4. `params` retention and redaction.
5. What happens when canonicalization merges the `plan_step:` prefix into the base key.

### E. What Task 85 completely missed

1. **The goal-progress → `goal_alignment` loop** (§2) — the largest persisted input to scoring.
2. **Auto-completion permanently deleting recurring goals** (§2.2) — already consumed
   `g_daily_commit`; will consume the rest under P2.
3. **`_multi_backend_fallback` ignoring its own `timeout`** (§3.2) — the actual unbounded primitive.
4. **`code_task` is RED** (§6.2) — the permission consequence of its own #2 change.
5. **The trust-ladder promotion path** (§15.2) — learning changing permission friction.
6. **Three more key implementations** (§4.1) — eight, not five.
7. **`presence` and `screen_activity` currently contradict each other** (§8.2a).
8. **Bounded GREEN-only exploration** — the only honest route to real counterfactual learning (§7.1).
9. **The recurring defect *family*** — a parameter or key accepted at a boundary and silently
   discarded (`"hypothesis"`/`"text"`; `sorted`/`json.dumps`; `timeout`). Three instances, never
   named as a class, never given a lint rule.

### F. Corrected implementation order

R0 diagnostic → **R1 bound the fallback** → **R2 fan-out cooldown + retire `strategy`** →
**R3 decouple reward from goal progress** → R4 separate the suppression channel → R5 canonical key →
R6 staleness-only diversity → R7 `decision_id` → R8 wire `validate_lesson()` → R9 epistemic gates →
R10 decision provenance. Everything else frozen.

### G. The first three changes I would permit

**Precondition (not a change): R0.** No code ships until the drift probe and thread dump have run
on a disposable clone and the starvation mechanism is named. Cost: zero code, one run.

1. **R1 — pass `_multi_backend_fallback`'s existing `timeout` into its three `engine.generate()`
   calls and wrap the chain in one deadline.** Strictly bounds an unbounded primitive; cannot
   introduce new blocking; fixes all 21 coroutines and the dispatch path at once; single-function
   revert. *Proof required:* thread dump shows no main-thread frame inside a provider call beyond
   the bound.
2. **R2 — per-edge TTL cooldown/dedup in `_fanout_handler`, plus retire or staff `strategy`.**
   Monotonically reduces activity; no new action types; no reachability change; removes ~97% of the
   noise floor. *Proof required:* dispatch rate falls and the 8 pairs persist at lower volume with
   no new `(district, task_type)` appearing.
3. **R3 — decouple `goal.progress` from reward; stop auto-completion for goals lacking an explicit
   completion criterion; add `recurring`.** Repairs a 0.30-weight pathological loop and stops
   irreversible goal deletion. *Precondition:* immutable `goals_v1` snapshot first. *Proof
   required:* a successful action no longer changes `goal_alignment` for that goal, and no goal
   transitions to `completed` without an explicit criterion.

All three are runtime/data-integrity fixes. **None changes what learning means**, so none
contaminates the measurements that follow — which is exactly why they go first.

### H. Changes I would explicitly prohibit for now

1. The `Experience` table as specified.
2. Tag propagation without a GREEN-only allowlist.
3. The staleness threshold **before** R3.
4. `belief:*` → scoring, until contradiction logging, provenance, calibration and
   starvation-vs-age staleness all land.
5. The HP habituation change.
6. The `spawn_successor()` contract fix — until the stale-reference bug is traced.
7. Key canonicalization **before** the suppression channel is separated.
8. `situation_class` / generalization.
9. The counterfactual write-back aggregate.
10. Any per-cycle LLM call, new memory subsystem, new district, new agent, or `GOAL_ACTION_MAP`
    widening.
11. Migrating or deleting the 29,164-sample bucket or the 30,504-row counterfactual history.
12. Any experiment on the live process.

### I. Behavioural proof required before advancing

| Gate | Proof |
|---|---|
| After R1 | Thread dump: no main-thread frame in a provider call beyond the bound. |
| After R2 | Dispatch rate materially down; no new `(district, task_type)` pairs; `strategy` gone. |
| After R3 | **E0** passes — `observe_loop` sustains its interval and `sleep()` drift stays bounded. *No cognitive claim may be made before E0 passes.* |
| After R4+R5 | **E1** (L1→L3) and **E2** (attribution, with a control row proven unaffected). |
| After R6 | **E6** — the unmodified generator produces ≥2 distinct `action_type`s in ≥X% of ticks *unattended*. **If E6 fails, L4 has not been achieved in the system.** |
| After R7+R8 | **E3** persistence, **E5** contradiction. |
| Before any generalization work | **E4** — characterise the update rule at `n ∈ {1,10,100,10000}`. |

---

## The question you actually asked

> *"After applying your corrections, will VECTOR actually be capable of learning from experience,
> or will we merely have a better-connected reward system?"*

**A better-connected reward system. An honest one, which it is not today — but a reward system.**

After R0–R10, VECTOR would have: a real reward channel uncontaminated by control-flow artifacts; a
key that survives a rename; genuine multi-candidate competition; traceable attribution from a
decision to the row its outcome moved; a goal system that stops eating itself; and a runtime that
actually schedules its own cognition. Every one of those is real, each is currently broken, and
together they would let VECTOR legitimately demonstrate **L4 behavioural adaptation in production** —
something it has never done outside a laboratory fixture. That is a genuine achievement and it is
worth doing.

It is not learning from *experience*. It is learning from *reward*, and the distinction is
structural, not semantic:

- **The situation is an identifier, not a representation.** `sha256(action_type + params)` supports
  equality and nothing else. Two situations either are the same or are unrelated; there is no
  similarity, no description, no inference, no partial match. Understanding requires a
  representation you can reason *over*, and there isn't one.
- **The decision layer is model-free.** Six scalars, six fixed weights, one clamp. No language model
  participates in any decision about what to do — LLMs run only *inside* agents executing an
  already-chosen task. You cannot improve judgement by improving inputs to a weighted sum.
- **There is no forward model.** Nothing predicts a consequence before acting. Without prediction
  there is no surprise; without surprise there is no error signal beyond scalar reward; without
  that, no causal learning.
- **Experience is compressed to one float at the moment of capture.** Everything that made the
  situation what it was — world state, time, presence, what else was happening — is discarded
  before persistence. You cannot later learn something from an experience you never stored.

So: **Task 85 is the correct minimum path to the thing it can actually reach, and it is not the path
to the thing its title claims.** Corrected as above, it produces a working, measurable, honest
reward loop. That is the right next objective, and it should be named as such.

Understanding is a **different programme** — one whose first question is *"what representation does
the decision layer consume?"*, not *"which key should the reward be written under?"*. It should be
planned separately, after the reward loop is measurably closed, and it should not be smuggled in as
"P7" at the end of a roadmap that has no substrate for it. The single most useful correction I can
offer is that renaming: **this is a Reward Loop Remediation Plan.** Scoping it honestly is what
makes it possible to plan the understanding work properly, instead of expecting it to emerge from a
better-connected bandit.

---

## Integrity statement

Production source modified: **none**. Configuration modified: **none**. Databases written:
**none** — the only database access this session was read-only, and the encrypted store could not be
opened at all. VECTOR process started, stopped, signaled, or interacted with: **none**. Tests
executed: **none**. Implementation performed: **none**. Files created: exactly one — this document.

**Disclosed limitation:** I could not open `vector_memory.db` (no SQLCipher binding available in my
environment), so Task 85's live goal-table read (§6) is carried as **[85-U]**, unverified by me. I
verified the source that writes and consumes those values instead — which is what produced §2, the
central finding of this review.
