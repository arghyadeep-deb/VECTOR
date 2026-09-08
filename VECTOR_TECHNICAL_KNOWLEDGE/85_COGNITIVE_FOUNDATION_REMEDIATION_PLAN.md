# Task 85 — VECTOR Cognitive Foundation Remediation Plan

**Mode:** read-only architectural audit + plan. Nothing in this document was implemented. No
production file, config, database, or experiment artifact was modified. No process was
started, stopped, signaled, or steered.

**Method:** this report treats `VECTOR_TECHNICAL_KNOWLEDGE/84_CURRENT_STATE_RECONSTRUCTION.md`
as evidence, not ground truth, per this task's explicit instruction. Every load-bearing claim
from Task 84 that this plan depends on was either (a) independently re-derived from current
source this session — marked **[VERIFIED-HERE]** — or (b) left attributed to Task 84 and
explicitly marked **[FROM TASK 84, not re-verified this session]**. Six claims were
independently re-checked from scratch this session and one of them **materially corrects**
Task 84 (§4 below — the exact goal causing the single-candidate lock is now identified by
name, not just by mechanism). All dollar-value counts (dispatch totals, sample counts,
row counts) are carried from Task 83/84's own read-only measurements and are not re-measured
here — this task's evidence requirement is architectural, not a fresh census.

**Evidence labels used throughout:** **PROVEN** (source-read + data-read agree, no gap),
**LIKELY** (strong source evidence, one plausible alternative not fully excluded), **POSSIBLE**
(named hypothesis, real but unresolved gap), **UNKNOWN** (genuinely open).

---

## 1. Executive diagnosis

VECTOR is a safe, stable, 107+-hour-uninterrupted, genuinely autonomous system whose cognitive
loop is **structurally complete but causally open at exactly two points**: outcome attribution
(no experience carries an identity that survives to be looked up later) and update-to-future-
decision (the one reward the system can currently read is a hardcoded constant). Every other
transition in the intended chain — observation, context, memory retrieval, candidate
generation, scoring, counterfactual veto, governance, gated action — is wired, reachable, and in
several cases test-verified. **The system does not need a new brain. It needs three or four
specific keys to match, one goal's progress field to stop being the sole source of candidate
diversity, and one coroutine to stop hanging forever.** This is confirmed independently in this
session, not merely inherited from Task 84: the exact goal responsible for "0 alternatives"
every cycle is `g_kiit_attendance` (§4), and the `ollama_safe.chat()` semaphore that looked like
a plausible hang mechanism is in fact provably bounded and safe (§3) — narrowing, not widening,
the open question about the 1,000× perception-loop slowdown.

**Formal foundation maturity: L1–L2 on the L0–L7 ladder** (Task 72's scale, reused here because
it is the correct instrument and re-deriving a new one would be exactly the kind of unnecessary
proliferation this task's Phase 12 warns against). One mechanism (Agent HP → agent selection)
reaches L3–L4 in principle but is currently saturated by its own habituation dampener (§9). No
mechanism observed in the live 107-hour run reaches L4 in practice. Task 78's isolated lab
proved L4 is *reachable* by the existing, unmodified classes given ≥2 competing candidates and
an unambiguous reward — which is the single most important fact in this whole plan, because it
means **the remediation is connective, not inventive.**

---

## 2. Current cognitive-loop diagram (as-built, not as-designed)

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  observe_loop (design 0.5s, actual ~50min late-phase — §3)              │
 │       └─> get_world_state()  [S5 — real, 16-key dict]                   │
 └───────────────────────────────┬───────────────────────────────────────┘
                                  ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  think_loop (design 10s, actual ~1-4h late-phase — §3)                  │
 │   world_state ──> track_beliefs() ──> belief:* (epistemic.db)  [S3, no  │
 │                                        reader in the score path]        │
 │   world_state ──> goals.generate_immediate_actions(limit=4)             │
 │       └─ SHORT goals (active, progress<1) -> research_topic             │
 │       └─ MID/LONG goals with progress == 0.0 EXACTLY -> analyze_progress│
 │            (GOAL_ACTION_MAP: SHORT->research_topic, MID/LONG->          │
 │             analyze_progress — deliberate, by design, §4)               │
 │       └─ tags never copied into the action dict -> _TAG_TO_ACTION dead  │
 │       + plan-step candidates (PlanStore) — real, but add_goal() has no  │
 │         autonomous caller, so nothing self-initiates a plan             │
 │   candidates ──> decision_engine.evaluate()                             │
 │       score = .30·goal_align + .25·conf + .20·policy + .15·urgency      │
 │               + .10·timing − .05·cost, × epistemic_penalty[0.70,1.0]    │
 │       policy read: get_score(sorted(params.items()))  <-- KEY MISMATCH  │
 │       epistemic read: action_domain:{verb} <-- real, but never written  │
 │                        in Segment 2 because execution never happens     │
 │   winner ──> ContinueGate.evaluate(step, since_ckpt=step-0)             │
 │       since_ckpt == step ALWAYS -> verdict is always "checkpoint",      │
 │       every other branch (stop/pause/throttle) is unreachable           │
 │   winner ──> _act_on(winner)                                            │
 │       ├─ proactive_*, plan:*, 5 VC types, skill>0.6  ──> GATED (34/107h)│
 │       └─ CounterfactualMemory.should_avoid() ──> veto (1,198/1,198)     │
 │             veto path: record_rejection() + update_from_outcome(0.05)  │
 │             ──> RETURN. Never reaches execution, outcome, or reward.    │
 └───────────────────────────────┬───────────────────────────────────────┘
                                  ▼ (separate, parallel system)
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  Governor.dispatch()  [43,312 calls/107h, 8 dominant district::type     │
 │  pairs forming 2 closed cycles via district-keyed event fan-out]        │
 │       agent selection: capability match else max(HP) — the ONE L3-L4   │
 │       mechanism in the whole system, currently saturated (§9)           │
 │       ──> agent.run(task)  ──> HP award/deduct  ──> _publish_district_  │
 │           event()  ──> next fixed dispatch, forever, no dedup/cooldown  │
 │       Never touches PermissionGateway. Gates at point-of-effect inside  │
 │       each agent instead (decentralised-by-design, Task 84 §6).         │
 └─────────────────────────────────────────────────────────────────────────┘

 WHERE PAST EXPERIENCE COULD BECOME FUTURE BEHAVIOUR, AND CURRENTLY DOESN'T:
   1. update_from_outcome() writer key ≠ get_score() reader key (3 of 5 writers)
   2. record_epistemic_belief() never reached (only called downstream of a real
      execution outcome, which the vetoed path never produces)
   3. the only reward the reader CAN see is a hardcoded 0.05 constant
   4. no experience/outcome carries a stable identity that a later cycle can
      look up — Task 72's "Attribution: S0" finding, independently confirmed
```

---

## 3. Runtime / event-loop starvation investigation (Phase 2)

**Independently re-investigated this session, not merely inherited.**

Task 84 §9.1/§9.3 established, from source and telemetry: (a) `hypothesis_loop` wraps its LLM
call in no timeout while `think_loop`/`observe_loop` do; (b) one hypothesis call hung for 69.9
hours starting ~16:50 IST on 09-03, inside the exact 64-minute gap between Segment 2's burst and
sparse decision-cadence phases; (c) `observe_loop`'s `_tick_count` shows a ~1,000× slowdown with
timeouts and a slow tick body both excluded by direct measurement; (d) `Governor._llm_classify()`
and `AgentBase.vchat()` both call the **synchronous** `ollama_safe.chat()` with no
`asyncio.to_thread`, from inside `async def` functions. Task 84 classified this as **"leading
hypothesis, not established"** and named the exact next diagnostic.

**This session's independent addition:** I read `core/inference/ollama_safe.py:184-320` in full,
specifically to check whether the semaphore machinery cited in Task 84's evidence could itself be
an unbounded-hang mechanism (a plausible reading of the file's own `KNOWN_ISSUES #0` comment).
**It is not, in current source:**

```python
_sem_timeout = CONFIG.get("ollama_semaphore_timeout_sec", 60.0)
if not _OLLAMA_SYNC_SEMAPHORE.acquire(timeout=_sem_timeout):   # bounded — confirmed
    ...
    return fallback   # never blocks past 60s
try:
    with ollama.Client(host=..., timeout=timeout) as client:   # caller's timeout, default 8.0s
        ...
finally:
    _OLLAMA_SYNC_SEMAPHORE.release()                            # guaranteed release
```

The historical "blocks forever, no timeout" comment describes a **prior** bug that a
2026-08-06 fix (bounded `acquire(timeout=...)`, `finally`-guaranteed `release()`) already closed.
**[VERIFIED-HERE, PROVEN]: the semaphore is not the mechanism.** This narrows Task 84's leading
hypothesis rather than confirming it: the 69.9-hour hang, if it is a genuine in-thread block,
must be occurring either (a) entirely inside `hypothesis_loop`'s own unguarded `await` with no
internal bound at all (Task 84's original claim, still standing and now strengthened by
elimination), or (b) inside `_multi_backend_fallback()`'s own retry logic, which was **not**
traced this session and is the one remaining unexamined branch — **[UNKNOWN]**.

### Classification (per the task's required A/B/C scheme)

| Candidate mechanism | Classification | Basis |
|---|---|---|
| `hypothesis_loop` missing `asyncio.timeout` around its LLM call | **A — confirmed event-loop-relevant defect** (the missing timeout itself, source-read, unambiguous) | Direct source comparison against `think_loop`/`observe_loop`'s own timeout pattern [VERIFIED-HERE via Task 84 citation, re-confirmed structurally] |
| That missing timeout is the *specific* cause of the 69.9h hang | **B — plausible, strengthened by elimination, not proven** | The semaphore alternative is now excluded (§3 above); `_multi_backend_fallback` remains untraced |
| Synchronous `ollama_safe.chat()` calls from `Governor._llm_classify()`/`AgentBase.vchat()` blocking the *shared* event-loop thread for the duration of every Ollama round-trip | **B — plausible, unproven at scale** | Call sites confirmed synchronous-in-async [VERIFIED-HERE]; but 8,223 Ollama calls succeeded across the same 107h window, so if this were the dominant mechanism it would need to explain a ~50-minute-per-tick average, and 23.5s-average Ollama latency × even hundreds of calls does not obviously sum to that without a second contributing factor |
| `_OLLAMA_SYNC_SEMAPHORE` unbounded block | **C — disproven this session** | Source-verified bounded acquire + guaranteed release |
| Unbounded fire-and-forget task growth from `_fanout_handler`'s `_tracked_task()` starving the asyncio ready-queue under load | **B — plausible, unproven** | Structure confirmed (Task 82/83/84, no semaphore/depth limit found); causal link to the *specific* ~1,000× slowdown not measured |
| Uninstrumented synchronous I/O elsewhere in the tick (SQLCipher writes into a 350MB DB, screen OCR, Merkle hashing, prompt-injection scan) contributing cumulative in-thread blocking | **B — plausible, unproven, unquantified** | Named correctly by Task 84; none of these paths were traced to a specific blocking duration this session or that one |

**Conclusion: no single mechanism is confirmed (A) as the full explanation for the ~1,000×
slowdown. One candidate mechanism is confirmed absent (C). Four remain B.** This is not a
"probably" — it is a precise map of what has and has not been excluded, which is what the task
asked for when full proof was not reachable read-only.

### Diagnostic instrumentation design (not implemented, smallest possible)

Reusing Task 84's own recommendation because it is already minimal and correctly scoped, with
one refinement:

1. **Read-only, zero-code-change first pass:** the repository already ships
   `core/loop/thread_dump.py`, opt-in via `VECTOR_THREAD_DUMP_SEC`. Enable it for one disposable
   run and read `data/logs/thread_dumps.log` — if the main thread is repeatedly captured inside
   `ollama.Client`/`httpx` frames, that is direct proof of in-thread blocking without writing a
   single new line of code.
2. **If (1) is inconclusive, minimal instrumentation (design only):** wrap `_think_tick()`,
   `_observe_tick()`, and the `hypothesis_loop` body's LLM call each in a `loop.time()`-vs-
   `time.monotonic()` drift probe emitting one log line per invocation:
   `event_loop_drift_ms = (monotonic_now - loop.time()) - expected_sleep_ms`. A drift that tracks
   1:1 with Ollama call volume distinguishes "this call blocked the loop" from "something else
   did." This is a 4-line diagnostic, reversible, and does not touch scheduling behavior.
3. **Do not** add `PYTHONASYNCIODEBUG=1` to the *live* Segment-2-successor process without first
   running it on a disposable clone — that flag adds meaningful overhead and would itself change
   timing.

---

## 4. PolicyMemory audit (Phase 3)

**[VERIFIED-HERE this session — re-read all five writer lines and the one reader line myself,
not accepted from Task 84 on citation alone.]**

Reader (`core/loop/decision_engine.py:268`, called from `get_score()` at `:379`):
```python
key = f"{action_type}:{sorted(candidate.params.items())}"
```

Five writers, confirmed by direct read:

| # | File:line | Formula | Matches reader |
|---|---|---|---|
| 1 | `autonomous_loop.py:1112` (counterfactual-veto penalty) | `f"{action_type}:{sorted(params.items())}"` | **YES** |
| 2 | `autonomous_loop.py:1046` (VectorCode reward) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO** |
| 3 | `autonomous_loop.py:1263` (main 5-factor reward — the richest signal in the codebase) | same `json.dumps` form | **NO** |
| 4 | `autonomous_loop.py:1493` (plan-step reward) | `f"plan_step:{action_type}:{json.dumps(...)}"` — extra prefix too | **NO** |
| 5 | `hands/runner.py:145` | `sha256(f"hand:{name}")` — no params at all | **NO** |

`sorted(dict.items())` and `json.dumps(..., sort_keys=True)` produce different byte strings for
identical logical content (`[('a',1)]` vs `{"a":1}`), hence different SHA-256 digests, hence
different rows. **Only writer #1 — the constant-penalty veto write — can ever be read back.**
This is exactly why the live `policy_memory` row for `analyze_progress` (situation_hash
`1b48b8edba94`, `avg_reward=0.04999999999997448`, `sample_count=29,164`) is bit-identical to a
literal `0.05` averaged with itself 29,164 times: **it is the only writer that has ever landed in
the bucket the reader looks in.**

**Identity/hash contract summary (as-is):**
- Situation identity = `action_type + params`, no context, no timestamp, no experience id.
- No canonicalization shared between writer and reader — each site re-implements its own
  serialization.
- No decay: `PolicyMemory` (unlike `CounterfactualMemory`) has no age-weighting found this
  session or in Task 84 — an EMA-style `update_from_outcome` presumably blends old/new by
  `sample_count`, but with 29,164 identical inputs the distinction is moot.
- Reward provenance: writer #3 (the 5-factor formula) genuinely incorporates real owner feedback
  (`_get_recent_feedback()`) — the richest, most legitimate reward in the system — and it is the
  one writer whose key the reader can never open.

### Designed canonical PolicyKey contract (design only, not implemented)

```
PolicyKey = sha256(
    canonical_action_type            # str, already consistent across writers
    + "|" +
    canonical_params(params)         # ONE shared function, not five ad-hoc ones
)

def canonical_params(params: dict) -> str:
    # single source of truth — importable by every writer AND the reader
    return json.dumps(params, sort_keys=True, default=str, separators=(",", ":"))
```

Three design requirements, in priority order:
1. **One function, one import.** `_make_situation_hash()` must move out of `decision_engine.py`
   into a shared module (e.g. `core/loop/policy_key.py`) that every writer imports, so drift
   becomes a compile-time impossibility rather than a five-way convention to keep in sync by
   hand. This is Task 80/84's own top recommendation and this session's independent read agrees
   it is correct and sufficient — no new field is required to fix the mismatch itself.
2. **A schema-version prefix** (`v1:` or similar) baked into the canonical form, so a future
   change to `canonical_params` does not silently re-merge historically-incompatible rows —
   this is new to this document, motivated by not wanting to repeat the exact failure mode being
   fixed.
3. **Do not** add richer situation context (world-state hash, timestamp bucket, etc.) to the key
   at the same time as the canonicalization fix. That is a separate, much larger design decision
   (situation granularity — too coarse and unrelated actions collide; too fine and nothing ever
   accumulates samples) that deserves its own falsifiable experiment (§18) before being built.
   Fixing the byte-format mismatch alone is sufficient to reconnect writer #3, and should be
   shipped and observed alone first.

---

## 5. CounterfactualMemory audit (Phase 4)

**[FROM TASK 84 §4.4/§9.6, independently consistent with this session's own Task-82/83 findings
already in this conversation's history — not re-queried against the live DB this session since
the experiment's DB state is unchanged since Task 83/84 and re-querying would add no new
information.]**

30,504 rejections, lifetime, one distinct `decision_id` (`analyze_progress`), `scenarios` and
`outcomes` tables both empty. `should_avoid()` is a post-selection veto only — `decision_engine.py`
has zero references to `CounterfactualMemory`, so it never *shapes* candidate scoring, it only
*blocks after the fact*. The 7-day exponential decay can never engage because a fresh matching
row is written every single cycle, so the "most recent match" is always seconds old.

**Classification: (B) — a deterministic blocklist, not (A) genuine counterfactual reasoning.**
It has never, across 81 days of production history, evaluated an actual alternative scenario. It
is closer to (C) memory storage with no reasoning than to (A), but it does have one real,
repeatedly-exercised causal effect (blocking), which (C) alone would not — so it sits precisely
at B.

### Designed bounded counterfactual loop (design only)

The current mechanism's actual job — "don't repeat an action that was just rejected" — is doing
real, useful work and should not be removed. The missing piece is that it has never been asked to
do the *other* job its name promises: comparing a chosen action against a plausible alternative
and learning something from the difference. Design, without an LLM call on every cycle:

**Trigger condition (bounded, not per-cycle):**
- Fire genuine counterfactual reasoning only when **(a)** the decision engine had ≥2 candidates
  within 0.05 of each other in total_score (a genuine close call — this is exactly Task 78's own
  Level-4 precondition) **and (b)** at least `N` (e.g. 6) hours have elapsed since the last
  counterfactual-reasoning event for this `action_type` pair (cooldown). Both conditions are
  computable from state already in memory (`DecisionResult.candidates`, a new
  `last_counterfactual_ts` per action-type pair) — no new subsystem needed.

**What constitutes a scenario:**
- `{chosen: Candidate, alternative: Candidate, situation_snapshot: coarse world-state summary,
  decision_id: stable id shared with the PolicyKey scheme in §4}` — reusing the canonical
  `PolicyKey` machinery for the situation/action identity rather than inventing a second one.

**How alternatives are generated:** the runner-up candidate from the same `evaluate()` call —
never synthesized, never LLM-imagined. This keeps the mechanism cheap (zero extra LLM calls) and
grounded (the alternative was a real thing the system actually considered).

**How outcomes are represented:** once the *chosen* action's real outcome is attributed (§7), the
scenario row is updated with `chosen_outcome`. The *alternative's* outcome is never observed
(it wasn't run) — so `outcomes` for the untaken branch stays explicitly `null`/`unknown`, not
fabricated. This is the honest version of "counterfactual": it records what was foregone and
what actually happened, not a simulated guess at what would have happened.

**How confidence is represented:** carried through unchanged from the alternative candidate's own
`confidence` field — no new number invented.

**How results influence future decisions:** aggregate, not per-row — a periodic (e.g. daily,
during `reflect_loop`) batch job computes "of the last K close calls where A beat B, how did A's
outcomes trend" and writes ONE summary adjustment into PolicyMemory via the *same* canonical key
from §4, rather than creating a second parallel scoring input. This directly serves Phase 12's
anti-fragmentation goal — counterfactual reasoning becomes a periodic *contributor* to the one
policy signal rather than a second competing memory.

**Cooldown/duplicate suppression:** the existing `_decay_factor()` machinery is fine and should be
kept for the blocklist function; the *new* reasoning trigger above needs its own independent
per-action-pair cooldown (§ above) so it cannot fire more than once per `N` hours regardless of
how many times the pair is proposed.

---

## 6. Candidate-generation audit (Phase 5) — **the highest-precision finding in this document**

**[VERIFIED-HERE this session — read `goal_system.py` in full and read the live persisted goal
set directly from `semantic_memory.goals_v1` via a read-only SQLCipher connection.]**

Task 84 correctly identified the mechanism ("only the `progress == 0.0` exact-equality branch
ever fires") but did not identify *which* goal, *why only one*, or *what `GOAL_ACTION_MAP` maps
to*. This session closes all three:

**`GOAL_ACTION_MAP` (`goal_system.py:19-23`) is an explicit, commented, deliberate design
decision, not a fallback default:**
```python
# Maps goal horizon to a gateway-registered action type so every generated
# action passes the GREEN/YELLOW gate without being classified as UNKNOWN.
GOAL_ACTION_MAP = {"SHORT": "research_topic", "MID": "analyze_progress", "LONG": "analyze_progress"}
```
Every MID and every LONG "unstarter" candidate — regardless of the underlying goal's actual
subject — collapses onto the identical action_type `analyze_progress`. This is architecturally
equivalent to the `ScriptGenerator`/`APITester` "task-type-blind hardcoded default" bug shape
Task 82 found twice elsewhere (§10), now confirmed a **third** time, at the goal-candidate layer
itself.

**The live persisted goal set (`semantic_memory.goals_v1`, read this session):**

| goal_id | horizon | progress | status | qualifies for unstarter branch? |
|---|---|---|---|---|
| `g_kiit_attendance` | LONG | **0.0** | active | **YES — the only one** |
| `g_karpathy_30` | MID | 0.076 | active | no |
| `g_vector_phase1` | MID | 0.25 | active | no |
| `g_placement_prep` | LONG | 0.076 | active | no |
| `g_daily_commit` | SHORT | 1.0 | **completed** | no (excluded from `get_active_goals`) |
| `g_first_revenue` | MID | 0.076 | active | no |
| `g_equation_portfolio` | LONG | 0.076 | active | no |

**This is the exact, complete, no-further-uncertainty explanation for "Winner: analyze_progress,
0 alternatives" across every one of the 1,198+ decision cycles measured in Tasks 79–83:**
`g_kiit_attendance` is the only goal whose `progress` field is bit-exactly `0.0`; the
exact-equality check (`goal.get("progress", 0) == 0.0`) in `generate_immediate_actions()`
therefore admits exactly this one goal into the unstarter branch; `GOAL_ACTION_MAP["LONG"]`
deterministically maps it to `analyze_progress`; and the SHORT branch, which would contribute a
second, differently-typed candidate (`research_topic`), is empty because the only SHORT goal
(`g_daily_commit`) is marked `completed` and `get_active_goals("SHORT")` correctly excludes it.

**Secondary observation, not chased further this session:** four goals (`g_karpathy_30`,
`g_placement_prep`, `g_first_revenue`, `g_equation_portfolio`) share the *exact same*
`progress=0.076` value despite being unrelated in subject. This is suspicious of a single bulk
update event rather than four independent, goal-specific progress computations — **[POSSIBLE]**,
flagged for a future audit, not investigated here (out of this session's scope; it does not
change the candidate-generation diagnosis above, which depends only on which goals equal exactly
`0.0`).

**`_TAG_TO_ACTION` (`autonomous_loop.py:833-856`) is confirmed dead code, and the reason is a
one-line propagation gap, not a design flaw:** `Goal.add_goal()` stores a real, populated `tags`
list on every goal (`entry["tags"] = tags or []`, `goal_system.py:277`) — the data exists — but
`generate_immediate_actions()`'s two candidate-dict builders (`goal_system.py:221-228` and
`:233-240`) never copy `goal["tags"]` into the returned dict. `autonomous_loop.py:861`'s
`tags = a.get("tags", [])` is therefore always `[]`, and the 21-entry `_TAG_TO_ACTION` map, which
would otherwise route e.g. a `karpathy`-tagged goal to `search_arxiv` instead of the generic
`analyze_progress`, never fires.

### Minimum change for real candidate diversity (design only — not implemented)

Two independent one-line-scale fixes, either alone sufficient to break the single-candidate
lock, together sufficient to make it contextually meaningful rather than accidental:

1. **Propagate `tags`:** add `"tags": goal.get("tags", [])` to both dict literals in
   `generate_immediate_actions()`. This alone reconnects a 21-entry, already-written,
   already-tested-shape mapping with zero new code, and would immediately diversify MID/LONG
   unstarter candidates by subject (`karpathy` → `search_arxiv`, `git` → `git_status`, etc.)
   instead of all collapsing to `analyze_progress`.
2. **Replace exact-equality staleness with a graded signal:** change
   `goal.get("progress", 0) == 0.0` to something like `progress < 0.05 and days_since(last_note or
   created_at) > threshold_for(horizon)` — turning "has literally never been touched" into "is
   overdue for attention," which is both more correct (a goal at progress=0.01 is just as
   unstarted in spirit as one at 0.0) and would admit more of the six currently-excluded goals
   into rotation, each contributing its own real `action_type` once (1) is also applied. This
   must be **bounded** (a `limit=4` cap already exists and should stay) and **reproducible**
   (a deterministic threshold function, not a random sample) to satisfy this task's own
   "contextually justified, goal-relevant, bounded, reproducible, testable" requirement — no
   noise injection anywhere in this design.
3. **Do not** touch `GOAL_ACTION_MAP` itself yet. It is a deliberate, documented, gateway-safety
   decision (every generated action must already be gateway-classified), and widening it is a
   larger, separate change than fixing the two propagation bugs above. Fix (1)+(2) first, observe
   the resulting diversity, then decide whether `GOAL_ACTION_MAP` also needs new entries.

---

## 7. Outcome-attribution audit (Phase 6)

**[Synthesized from Task 84 §4.5/§10/§11 plus this session's independent PolicyMemory re-read,
§4 above.]**

Every reward/outcome mechanism found, and its status:

| Mechanism | Generated? | Persisted? | Correctly attributed? | Retrievable? | Consumed by decisions? |
|---|---|---|---|---|---|
| Agent HP (`award_points`/`deduct_points`) | yes | in-proc + `loop_state`/`agent_history` | yes, direct | yes | **yes** — the one real loop, but habituation-saturated (§9) |
| PolicyMemory veto penalty (0.05) | yes, every cycle | yes | direct | yes | yes — but constant |
| PolicyMemory 5-factor reward (real outcome + owner feedback) | yes, on execution | yes | direct | **no — wrong key** | no |
| PolicyMemory VectorCode/plan-step rewards | yes | yes | direct | **no — wrong key** | no |
| EpistemicTracker `action_domain:*` | only on real execution | yes | direct | yes | yes, but zero writes in 107h (execution never happens on the dominant path) |
| User feedback (`_get_recent_feedback()`) | yes, when it exists | via episodic | folded into the 5-factor reward | inherits that reward's key problem | no |
| Correction learning (`CorrectionLearner`) | yes, voice-path only | yes | direct | prompt-injection only | `validate_lesson()` — the actual outcome-feedback closer — has zero production callers |
| Task completion / exceptions | yes (implicit in HP deduct reasons) | via HP + episodic tags | direct | yes | folds into HP only |
| Repetition penalties | yes (`repeat_multiplier`) | in-proc only, not persisted | direct | **no — resets every boot/successor spawn** | yes, until reset |
| Hands outcomes | yes | `reasoning_chains` | direct | HTTP endpoint only | no autonomous consumer |
| Agent evolution / ghost inheritance | yes | `agent_history` | direct | `get_system_prompt()` — **zero callers** | no |

**Pattern, confirmed independently: every reward that is generated correctly and persisted
correctly fails at either retrieval (wrong key) or consumption (no caller) — never at
generation.** The generation side of outcome attribution is, almost everywhere, already correct.
The system has plenty of opinions about whether an action went well. It has almost no way to look
those opinions up again.

### Designed canonical outcome-attribution model (design only)

Rather than adding a fifteenth parallel reward system, one canonical `Experience` record,
written once per completed action cycle, consumed by everything downstream:

```
Experience {
    experience_id: uuid                       # NEW — the missing primitive (Task 72 §7, agreed)
    policy_key: PolicyKey                      # §4's canonical key — shared identity
    action_type: str
    params: dict
    situation_class: str                       # coarse bucket, NOT full context (see §16)
    proposed_at: timestamp
    executed: bool                             # false for vetoed/never-run candidates
    outcome_status: ok | error | vetoed | no_agents | timeout
    reward: float | null                       # null, not 0.0, when no real outcome exists
    reward_components: {hp_delta, user_feedback, goal_progress_delta, ...}  # provenance, not just a scalar
    source: str                                 # which subsystem produced this experience
}
```

- **Every existing writer keeps writing to its own table** (HP stays HP, PolicyMemory stays
  PolicyMemory) — this is not a rewrite. `Experience` is an **append-only correlation log**, one
  row per decision cycle, carrying the `experience_id`/`policy_key` that lets every other table's
  row be found again from a single starting point. This directly satisfies Phase 12's
  "reduce fragmentation, don't add subsystems" instruction: it is a connective index, not a new
  memory tier competing with the existing ones.
- **`reward: null` is a first-class, required state**, not a default `0.0`. The single most
  damaging silent conflation in the current system is that a vetoed action and a genuinely
  neutral outcome are currently indistinguishable once they reach a `0.0`-shaped value; an
  explicit `null` fixes that at the schema level.
- **PolicyMemory becomes a read-through cache over `Experience`, not an independent write
  target.** Writers stop hand-rolling their own key; they write an `Experience` row, and a single
  shared `update_policy_from_experience(exp)` function (importing the same `canonical_params`
  from §4) is the only code path that ever touches `policy_memory`.

---

## 8. Epistemic / hypothesis audit (Phase 7)

**[FROM TASK 84 §4.3/§9.1, cross-checked against this session's independent read of
`decision_engine.py`'s epistemic-penalty call site structure — consistent, not re-queried
against `epistemic.db` since Task 84's full 7-row dump is definitive and unlikely to have
changed.]**

Two disjoint namespaces share one table:
- `action_domain:*` (3 claims, `git`/`commit`/`search`) — **the real, decision-influencing
  namespace.** `_epistemic_penalty()` reads it before every score. Every entry predates Segment
  2's boot; zero writes in 107 hours because `record_epistemic_belief()` is only reachable
  downstream of a real execution outcome, and the dominant vetoed path never executes. All three
  are now stale past their 72h TTL, so any revived candidate in these domains would receive the
  heaviest possible dampening — a self-inflicted, decay-driven handicap rather than a genuine
  reliability signal.
- `belief:*` (4 claims — presence, screen activity ×2, goal-progress summary) — written every
  cycle by `ContextEngine.track_beliefs()`, read by **nothing that scores a decision** (Task 78's
  paired experiment proved this).

Hypothesis engine: three historical defects (missing `await`, key mismatch, dict/str contract)
were all correctly fixed in earlier tasks and are confirmed present-and-correct in current
source. The pipeline is nonetheless silent in Segment 2 — one call attempted, hung 69.9 hours,
errored (§3). Zero hypotheses stored. `suggestion_queue.db`'s newest row predates Segment 2
entirely.

### Minimal epistemic architecture (design only)

```
evidence (an execution outcome, a sensed world-state fact, an owner correction)
   -> claim/belief write, ALWAYS through one function:
        record_belief(namespace, key, value, confidence, source, provenance)
   -> a claim's namespace determines its consumer contract, not its storage:
        "action_domain:*"  -> read by decision_engine's epistemic penalty (existing, keep)
        "belief:*"         -> read by goal/candidate generation (NEW connection needed —
                              e.g. belief:presence:absent should suppress or deprioritize
                              proactive-nudge candidates; it currently does not)
   -> contradiction handling: a same-key write with materially different value inside the TTL
      window should be logged as a contradiction event (NEW, small — a comparison + a log line,
      not a new subsystem) rather than silently overwritten, so confidence swings are auditable
   -> retrieval: unchanged — the read call sites already exist for action_domain:*; belief:*
      needs exactly one new read call site to stop being an S3-with-no-consumer namespace
```

**What must stay separate from PolicyMemory, explicitly:** epistemic claims are about
**reliability/context** ("is this domain trustworthy right now", "is the owner present"), not
about **reward** ("was this specific action good"). Merging them would make the epistemic penalty
just another badly-named policy write, losing the ability to reason about *why* a score is
low (staleness vs. genuine failure) — which is exactly the distinction that let this session
diagnose the self-inflicted TTL handicap above. Keep two mechanisms; fix the wiring between them
and the decision, not their separation.

---

## 9. Complete memory connectivity matrix (Phase 8)

Reusing Task 84 §11's table (independently consistent with every fact already re-verified this
session — HP, PolicyMemory, epistemic — so re-deriving it from zero would add no new
information) and adding the four-way classification this task requires:

| Mechanism | Purpose | S-level | Classification |
|---|---|---|---|
| Agent HP | agent selection | S3→S4 mechanism, saturated in current regime | **ACTIVE**, but self-limiting (§9.1 below) |
| PolicyMemory (veto writer) | penalty for repeated vetoed action | S3 | **SATURATED** — connected, but the only value it can ever receive is a constant |
| PolicyMemory (5-factor/VC/plan writers) | rich real-outcome reward | S1 | **ORPHANED** — real writer, real intended reader, keys don't match |
| PolicyMemory (Hands) | hand outcome reward | S1 | **ORPHANED** — writer exists, no `Candidate` with that `action_type` is ever built to trigger a read |
| CounterfactualMemory (blocklist) | avoid repeating a rejected action | S5 | **ACTIVE**, one-directional (block only) |
| CounterfactualMemory (scenarios/outcomes) | genuine what-if reasoning | S0 | **DEAD** — tables exist, schema exists, zero rows ever |
| EpistemicTracker `action_domain:*` | reliability-aware scoring | S3, mechanically closed | **ACTIVE mechanism / DEAD signal** — reader is real and live, writer starved |
| EpistemicTracker `belief:*` | situational awareness | S3 | **ORPHANED** — real writer, zero scoring readers |
| EpisodicMemory | raw event log | S5 for anticipation, S0 otherwise | **ACTIVE** for one narrow consumer, **DEAD** for 99.94% of its own writes |
| SemanticMemory | consolidated facts | S1 | **DEAD** — no autonomous consolidation step exists; only `goals_v1` is read, and it is 2 months stale |
| ReasoningMemory (SQL `reasoning_chains`) | training-data-quality chains | S1 | **DEAD** — only reader is an HTTP endpoint, zero autonomous consumers, zero new rows in 107h |
| ReasoningBank (file, `vectorcode/`) | inject past reasoning into scoring | S2 | **DEAD** — injected into a field (`reasoning_steps`) that `total_score` never reads |
| Ghost memory / agent_history | inherited lessons across generations | S2 | **DEAD** — inheritance happens; `get_system_prompt()`, its only consumer, has zero callers anywhere |
| Skill memory (`skill_memory` table) | matched-skill routing | not independently re-verified this session | **[FROM TASK 84 context, not directly audited — flagged as a gap in this plan, not a finding]** |
| Correction memory (`CorrectionLearner`) | owner-correction lessons | S2 (capture/store/inject real) / S1 (`validate_lesson` unwired) | **PARTIALLY ACTIVE** — prompt-injection works, outcome-feedback closing does not |
| Anticipation | proactive prediction from episode history | S5, deterministic | **ACTIVE**, but its one observed "change" (Task 66) was a clock artifact, not learning |

**Aggregate: of ~14 distinct persistence mechanisms, one (Agent HP) is genuinely ACTIVE and
currently saturated; two (CounterfactualMemory blocklist, Anticipation) are ACTIVE but narrow
and one-directional; two (PolicyMemory veto write, EpistemicTracker action_domain mechanism) are
mechanically connected but informationally starved or constant; the remaining ~9 are DEAD or
ORPHANED.** No memory subsystem in this list should be kept merely because it exists — see §12
for the explicit keep/repair/merge/freeze/deprecate disposition of each one.

### 9.1 Why even the one ACTIVE loop cannot currently demonstrate learning

`AgentBase.award_points()` applies `repeat_multiplier = 1/(1+count)` and
`headroom_multiplier = (1000-hp)/1000`; `deduct_points()` applies neither, by explicit design
("the Darwinian death mechanic must stay at full strength" — source comment, re-confirmed
consistent with Task 84's citation). In the fixed 8-step fan-out rotation, every agent's work is
by construction repetitive, so the positive half of the only real reward signal decays toward
zero (`repeat#10301 → ×0.000` observed live in Task 83) while the negative half never does. HP
in the current regime can only ratchet down. This is not a new memory-architecture problem — it
is a **shaping-function asymmetry** in an otherwise-working mechanism, and it is the highest-
leverage *single-function* fix available anywhere in this plan (§17).

---

## 10. Agent / district learning audit (Phase 9)

**[Independently re-confirmed this session — this conversation's own Task 82/83 work already
read `agent_registry.py:deregister()`, `evolution_engine.py:spawn_successor()`, and
`api_tester.py:run()` in full; Task 84's §5.3 account matches exactly.]**

- **The successor bug is confirmed, independently, twice now** (once in this conversation's own
  Task 82/83 source+live-log tracing, once via Task 84's citation): `deregister()` calls
  `spawn_successor(dead_agent: dict) -> dict` then immediately evaluates
  `successor_agent.generation` — attribute access on a dict, guaranteed `AttributeError`. Falls
  back to a bare `AgentBase(gen+1)`. A correctly-designed object-returning alternative
  (`spawn_from_ghost()`) exists in the same file, called from nowhere.
- **This session's own Task 83 finding, which Task 84 correctly incorporates and which stands as
  the more precise account than "the bug repeats":** the registry-level path fired **exactly
  once** in the 107-hour boot under observation (17:01:42 on 09-03), produced a fallback, and
  logged nothing since, while `"Agent APITester gen 1 DIED"` continued 5,558 more times — meaning
  **one orphaned object, held by an untraced stale reference outside `AgentRegistry._agents`, not
  a repeating registry-level death/rebirth cycle.** This remains the single most concrete
  unresolved object-lifetime question in the codebase and is carried forward into §17 as a
  priority item, not re-investigated further this session (it would require tracing beyond
  `Governor.dispatch()`'s immediate selection block, confirmed this session to re-query
  `get_by_district()` fresh every call — meaning the stale object must be reachable through that
  fresh query, which itself argues the FIX must be in what `_agents` or `get_by_district()`
  actually contains, not in Governor's selection logic).
- **Agent evolution currently produces state replacement, not behavioral evolution.** HP
  determines *which* pre-existing agent object runs; nothing in the successor/inheritance chain
  changes *what* an agent does — `get_system_prompt()` (the only place inherited
  lessons/best_decisions could reach an LLM-facing prompt) has zero callers. A gen-5 agent
  behaves identically to a gen-1 agent of the same class.
- **District activity is deterministic orchestration, not cognitive diversity.** The 8 dominant
  district::task_type pairs form two closed cycles (§11) driven entirely by `EVENT_TRIGGER_MAP`,
  with agent selection itself deterministic (`max(HP)` or exact capability match) — there is no
  point in this pipeline where an LLM chooses *which* task to do next; only *how* to execute an
  already-fixed task is delegated to a model.

**Recommendation, explicit per this phase's own instruction: do not redesign the civilization
layer.** HP-based selection is sound and is the one mechanism in the system that already reaches
L3+. The only two changes warranted here are (1) the successor dict/attribute fix (§4.5's exact
same pattern class as the PolicyMemory key fix — a one-function contract repair, not a redesign)
and (2) the HP habituation asymmetry (§9.1). Both are surgical.

---

## 11. Event-fanout audit (Phase 10)

**[Independently re-derived in this conversation's own Tasks 82/83 from `core/event_bus/wiring.py`
in full, cross-checked against Task 84 §5.4's cycle diagram — matches exactly, including the
arithmetic consistency check between dispatch counts and the two-cycle structure.]**

`PUBLISH_EVENTS` is keyed by district only; `task_type` is passed to
`_publish_district_event()` and discarded. `EVENT_TRIGGER_MAP` then maps each event to a fixed
downstream list. The result, confirmed arithmetically against Task 83's live dispatch counts, is
**two genuine closed cycles**, not a loose "rotation":

```
Cycle A: marketing -> {intelligence, data_analytics} -> strategy(dead)/content/marketing -> marketing
Cycle B: content -> {marketing, qa} -> content -> content
```

`_fanout_handler` creates each downstream dispatch as an unbounded fire-and-forget tracked task
— no semaphore, no depth limit, no dedup, no cooldown, no cycle detection anywhere in the code.
The only thing bounding the rate is `Governor.dispatch()`'s own per-district GCRA limiter and LLM
latency — a throttle, not a design control.

**Classification (per this phase's required A/B/C/D scheme):**
- The *existence* of event-driven cross-district triggering is **(D) — useful, intentional
  event-driven autonomy.** A district finishing work legitimately should be able to wake up
  downstream districts without polling.
- The *specific implementation* — district-keyed (not task-type-keyed) publish events feeding a
  fixed trigger table with zero cycle detection — is **(B) an accidental feedback loop.** Nothing
  in the source, comments, or commit history (per Task 82's original trace) suggests this
  self-sustaining-cycle behavior was intended; it is the natural, unexamined consequence of
  collapsing `task_type` out of the event key.
- It is not **(C) harmful self-amplification** in the safety sense — dispatch volume is bounded
  by rate limiting and the loop has run 107+ hours without runaway resource growth (Task 83 §G) —
  but it *is* harmful in the cognitive sense: it is the majority of what "activity" looks like in
  every log and dashboard, and Task 84's whole document is substantially the story of that
  activity being repeatedly mistaken for progress.

### Smallest correction (design only, not implemented)

1. **Re-key `PUBLISH_EVENTS` and `EVENT_TRIGGER_MAP` by `(district, task_type)` instead of
   `district` alone.** This is a data-structure change (dict keys), not a rewrite of the fan-out
   mechanism itself — `_fanout_handler`'s logic can stay exactly as-is; it would simply look up a
   more specific key. Every existing edge remains expressible; the fix only stops UNRELATED
   task types within a district from being force-fed the same downstream list.
2. **Add per-edge cooldown and dedup**, keyed by `(source_event, target_district, target_type)`,
   stored in-process (a simple TTL dict, not a new persistence subsystem) — refuse to re-fire an
   edge that fired in the last `N` seconds. This single change, applied to the two identified
   cycles, converts them from "fires every ~9 seconds forever" into "fires when there is
   genuinely new information, rate-limited" without removing the autonomy.
3. **Staff or retire `strategy`.** The district receives 4,655 dispatches/107h and has zero
   registered agents, every single one logging `"no agents in strategy"` before falling through.
   This is free to fix (either register a real agent or remove the edge) and has zero
   architectural risk.
4. **Do not** add global cycle-detection graph analysis (e.g., a full DAG-cycle-checker across
   the whole `EVENT_TRIGGER_MAP`) as a first step — that is exactly the kind of "giant rewrite"
   this phase explicitly warns against, and per-edge cooldown/dedup achieves the same practical
   protection at a fraction of the implementation and testing cost.

---

## 12. Understanding-gap analysis (Phase 11)

Evaluated only after the foundation above, as instructed. For each of the 13 requested
capabilities: does VECTOR have it, where, is it connected, what is the minimum missing
primitive.

| # | Capability | Have it? | Where | Connected? | Evidence | Minimum missing primitive |
|---|---|---|---|---|---|---|
| 1 | Situation representation | Partial | `ContextEngine.get_world_state()` (16-key dict) | Yes, to belief-writing; **no**, to scoring | S5 for context generation, S3-dead-end for its use in decisions | A `situation_class` coarse bucket (§16) consumed by `get_score()` |
| 2 | Entity/state tracking | Minimal | `belief:*` claims (presence, screen activity) | No | 4 static claims, no entity graph | A durable per-entity (not per-fact) record — does not exist at all today |
| 3 | Temporal understanding | Partial | TTL/decay in EpistemicTracker and CounterfactualMemory | Yes, mechanically | Decay formulas exist and run | Neither decay can currently express "genuinely stale because unchanged" vs "stale because starved" — the exact confusion in §8 |
| 4 | Causal interpretation | Minimal | `core/brain/causal_graph.py` (Gap 6, per CLAUDE.md, marked ✅ WIRED) | **Not independently verified this session** — flagged, not audited | — | Out of this session's scope; worth a dedicated future audit before building anything new here |
| 5 | Uncertainty | Yes, real | `confidence` fields throughout (Candidate, epistemic claims, hypothesis marker) | Partially — confidence flows into scoring (S5) but is often hardcoded (e.g. `confidence=0.7` at candidate construction, §2) | Verified in `_score_candidate()` | Replace the hardcoded 0.7 with a genuine per-candidate-type calibration — small, not a new capability |
| 6 | Self-model | Minimal | Agent HP as a self-state number; no model of VECTOR's own competence/limits beyond that | No broader self-model exists | — | Not a "minimum primitive" gap — this is a real, larger missing capability; do not build it before §4/§6/§9 are fixed, per this task's own ordering instruction |
| 7 | World-model | Minimal | `get_world_state()` is a snapshot, not a predictive model | No forward-simulation exists | — | Genuinely absent; correctly out of scope until the loop below it closes |
| 8 | Intent inference | No | — | — | No mechanism found reading owner intent beyond literal commands/corrections | Absent; not a near-term priority |
| 9 | Mental simulation | Yes, in isolation | Task 78's Digital Twin Lab | **Not connected to production** — a standalone lab, never wired to the live decision path | 28 tests, 4 replays, one real L4 winner-flip demonstrated | The lab already proves the *mechanism* works; the missing primitive is a production bridge, not new simulation capability |
| 10 | Consequence prediction | No | — | — | — | Absent |
| 11 | Abstraction/generalization | No | — | Task 72's proposed `situation_class` fallback was designed, never implemented | — | This is the correct next primitive once §4/§6 are fixed — see §16 |
| 12 | Contradiction detection | No | — | `EpistemicTracker` overwrites same-key claims silently; no contradiction event exists | — | A small addition to §8's `record_belief()`, not a new subsystem |
| 13 | Self-correction | Partial | `CorrectionLearner` capture/store/inject | Real for prompt-injection; `validate_lesson()` (the actual before/after outcome comparison) has zero callers | — | Wire the one existing unwired function — no new mechanism needed |

**Conclusion for this phase: VECTOR is closer to "understanding" than a from-scratch assessment
would suggest — 5 of 13 capabilities have real, working, if disconnected, machinery (situation
representation, temporal decay, uncertainty, mental simulation, self-correction), and three of
those five need only a wiring fix, not new code (contradiction detection, self-correction,
mental-simulation-to-production bridge). The remaining capabilities (entity tracking,
self-model, world-model, intent inference, consequence prediction, abstraction) are genuinely
absent and, per this task's explicit instruction, are correctly out of scope until §§3–11's
foundation closes. Building any of them now would be adding a fourteenth, fifteenth, sixteenth
memory system on top of thirteen that already don't close.**

---

## 13. Architectural simplification (Phase 12)

| Disposition | Systems | Why |
|---|---|---|
| **KEEP as-is** | Agent HP/selection mechanism; `Governor.dispatch()`'s routing + rate-limiting/taint/audit layer; `PermissionGateway`'s GREEN/YELLOW/RED/FORBIDDEN tiering and point-of-effect gating pattern; `PlanStore`'s execution/crash-recovery machinery; Anticipation's episode-matching; `ContinueGate`'s taxonomy (GREEN/YELLOW/RED reuse) | Each is sound, tested, and doing real work. Task 78 proved the decision/policy/counterfactual classes are mechanically correct in isolation. |
| **REPAIR (surgical, small)** | PolicyMemory canonical key (§4); `generate_immediate_actions()` tags propagation + staleness condition (§6); `spawn_successor()` dict/attribute contract (§10); HP habituation asymmetry (§9.1); `hypothesis_loop`'s missing timeout (§3); `ContinueGate`'s missing `last_checkpoint_step` argument (Task 84 §9.2, independently plausible from the same call-site pattern this session confirmed elsewhere — not re-verified line-by-line this session, carried as **[FROM TASK 84]**) | Each is a one-function or one-argument fix at an already-correct boundary — exactly the "smallest change at the closest existing boundary" discipline Task 52 established and every later remediation in the 51-83 series followed successfully. |
| **CONNECT (wire an existing S1/S2 into an existing S3/S5, no new subsystem)** | `belief:*` namespace into candidate generation/scoring; `validate_lesson()` into the correction-outcome path; Task 78's lab into a production-facing (but still non-autonomous, read-only-first) bridge; `EVENT_TRIGGER_MAP`/`PUBLISH_EVENTS` re-keying (§11) | These already have both a real writer and a real intended consumer; the gap is purely a missing call site or a key mismatch, not missing logic. |
| **MERGE** | The five independent `situation_hash`/key formulas across PolicyMemory's writers into the one canonical `PolicyKey` (§4); the counterfactual "blocklist" and "reasoning" functions into one module sharing that same canonical key (§5) | Reduces five ad-hoc identity schemes to one, which is this task's explicit anti-fragmentation goal. |
| **FREEZE (do not touch until the above lands)** | Any new memory subsystem; any new agent/district; any expansion of `GOAL_ACTION_MAP`; any new LLM-call-per-cycle mechanism (e.g. a "real" per-cycle counterfactual LLM call); the civilization/evolution layer beyond §10's two fixes; the Understanding Layer (§12) in its entirety | Per this task's explicit instruction and Task 71/72's own precedent: adding more before the loop closes would produce more DEAD/ORPHANED memory, not more learning. |
| **DEPRECATE (real candidates, not confirmed — flag for owner decision, do not remove unilaterally)** | `ReasoningBank`'s file-backed injection into an unread field (either wire it to something `total_score` reads, or stop injecting it — currently pure overhead with zero effect); ghost-memory's `get_system_prompt()` path (either wire it into an actual prompt builder, or stop computing/persisting `lessons`/`best_decisions` if nothing will ever read them); `reasoning_chains`' HTTP-only reader (either build the autonomous consumer Task 72 envisioned, or accept it as a pure export/debug table and stop treating its row count as a learning signal in any future report) | Each of these currently costs real write/compute effort for zero behavioral effect. This is a judgment call for the project owner, not a unilateral deletion — flagged, not decided, here. |
| **REMAIN INDEPENDENT (explicitly do not merge)** | EpistemicTracker (`action_domain:*`/`belief:*`) vs. PolicyMemory (§8); CounterfactualMemory's blocklist function vs. its (to-be-built) reasoning function (§5) — different cooldowns, different purposes, sharing only the identity key | Merging reliability-context with reward, or blocking with reasoning, would lose the ability to diagnose *why* a score moved — already argued in §8. |

---

## 14. Proposed Cognitive Foundation architecture (Phase 13)

```
A. PERCEPTION/OBSERVATION        observe_loop -> get_world_state()          [KEEP, repair timing §3]
                                        │
B. SITUATION UNDERSTANDING       track_beliefs() -> belief:* claims          [CONNECT to E]
                                  + NEW: situation_class(world_state) -> coarse bucket (§16)
                                        │
C. MEMORY (episodic/semantic/    unchanged storage; ONE addition —          [MERGE identity,
   policy/counterfactual/        Experience{} correlation log (§7) carrying  KEEP storage]
   epistemic/ghost/reasoning)    policy_key + experience_id through every
                                  existing table, no table replaced
                                        │
D. WORLD/SELF MODEL              [ABSENT — correctly frozen, §12/§13]
                                        │
E. CANDIDATE GENERATION          GoalSystem.generate_immediate_actions()     [REPAIR §6: tags +
                                  + PlanStore.active_plans()                  staleness condition]
                                        │
F. DECISION                      DecisionEngine.evaluate() — 5-factor score  [KEEP mechanism,
                                  reading PolicyMemory + EpistemicTracker      REPAIR key §4/§8]
                                        │
G. SIMULATION/COUNTERFACTUAL     should_avoid() veto (KEEP) +                [CONNECT lab §12,
                                  NEW bounded reasoning trigger (§5)           MERGE key §5]
                                        │
H. ACTION                        _act_on() branches -> gated / dispatch      [KEEP — decentralised
                                                                                gating is sound]
                                        │
I. OUTCOME ATTRIBUTION           [THE MISSING LINK] -> NEW Experience{}      [BUILD — the one
                                  write, once, per completed cycle             genuinely new thing
                                                                                in this whole plan]
                                        │
J. LEARNING                      update_from_outcome() / record_epistemic_   [REPAIR keys, not
                                  belief() — already correct logic             logic — §4/§8]
                                        │
K. GOVERNANCE/SAFETY             PermissionGateway (point-of-effect) +       [KEEP — proven safe
                                  Governor's rate-limit/taint/audit layer      across 107h+107h]
                                        │
L. PERSISTENT STATE              SQLite/SQLCipher tables, unchanged schemas  [KEEP, add one table:
                                  except one new `experiences` table           `experiences`]
                                        │
M. AGENT/DISTRICT ORCHESTRATION  Governor.dispatch() + HP selection +        [REPAIR successor bug
                                  event fan-out                                §10, re-key events §11]
```

### The exact point where PAST EXPERIENCE becomes FUTURE BEHAVIOUR

This is the link this task explicitly requires to be made explicit, and it is currently **not
explicit anywhere in the codebase** — this is the single sentence that names the fix:

> **`DecisionEngine._score_candidate()`'s `policy` term (weight 0.20) is the only place in the
> entire system where a persisted value from a past cycle changes a future decision's score.**
> Every remediation in §§3–11 either (a) makes more real rewards reach that one term through the
> canonical key (§4/§7), or (b) makes more real candidates exist for that term to discriminate
> between (§6), or (c) removes the artificial ceiling on the one other value that already reaches
> a decision — Agent HP → agent selection (§9.1). There is no second link to build. The
> architecture does not need a new mechanism for experience to become behavior; it needs the one
> mechanism it already has to actually receive the experiences that are already being generated.

---

## 15. Implementation roadmap (Phase 14)

Ordered by leverage, per this task's instruction, using the P0–P8 categories with one reordering
justified below.

### P0 — Runtime/event-loop integrity
- **Files:** `core/loop/autonomous_loop.py` (`hypothesis_loop`), `core/loop/thread_dump.py`
  (enable, don't modify).
- **Prerequisite:** none — can run first, in isolation.
- **Production risk:** very low. Adding a timeout to a currently-unbounded await can only reduce
  worst-case blocking, never introduce new blocking.
- **Expected behavioral effect:** `hypothesis_loop` starts producing bounded failures instead of
  indefinite hangs; if §3's leading hypothesis is even partially correct, the observe/think
  cadence should partially recover.
- **Tests required:** a unit test asserting `hypothesis_loop`'s LLM call site is wrapped in
  `asyncio.timeout`; an integration test simulating a hung provider and asserting the coroutine
  returns within the bound.
- **Behavioral proof required:** re-run the thread-dump diagnostic (§3) after the fix and confirm
  no main-thread frame is captured inside a hung Ollama call for longer than the configured bound.
- **Rollback:** revert one function; no persisted state changes.
- **Must NOT touch:** `think_loop`/`observe_loop`'s own already-correct timeout pattern; the
  `_supervised()` restart wrapper.

### P1 — Canonical experience/outcome identity
- **Files:** new `core/loop/policy_key.py` (extracted from `decision_engine.py`); the five writer
  sites in `autonomous_loop.py`/`hands/runner.py` updated to import it.
- **Prerequisite:** P0 not required but recommended first (cheaper to validate against a
  non-hanging system).
- **Production risk:** low-medium. This changes what `policy_memory` rows get written from this
  point forward; **existing rows (including the 29,164-sample `analyze_progress` bucket) must be
  left untouched**, not migrated — the old bucket is a valuable baseline (Task 71's LEARN-01
  point, endorsed by Task 84 §12.6 and this document).
- **Expected behavioral effect:** the 5-factor reward and VectorCode/plan-step rewards start
  landing in readable buckets; `policy` term in scoring should begin showing real variance for
  any action_type that gets executed and re-proposed.
- **Tests required:** a test asserting all five writer call sites and the one reader call site
  produce byte-identical keys for the same logical `(action_type, params)`; a regression test
  pinning the *old* format so accidental future drift is caught immediately.
- **Behavioral proof required:** Experiment F (§18) — two competing candidates, one given a real
  positive reward via the repaired path, verify ranking changes on the next cycle.
- **Rollback:** the new key function can be reverted independently of the `Experience` table
  (P3); writers simply resume writing unreadable keys, which is the current (safe, if useless)
  state.
- **Must NOT touch:** `CounterfactualMemory`'s own veto key, which already matches the reader and
  should not be refactored in the same change (keep the working one untouched while fixing the
  broken ones).

### P2 — Real candidate diversity
- **Files:** `core/brain/goal_system.py` (`generate_immediate_actions`).
- **Prerequisite:** none functionally, but **should ship after P1**, not before — diversifying
  candidates before the policy signal is readable would just create more actions competing on a
  score whose `policy` term is still meaningless for all of them.
- **Production risk:** low. Both changes (§6) are additive/threshold changes to an existing pure
  function; worst case is more candidates than before, still capped at `limit=4`.
- **Expected behavioral effect:** `decision_engine.evaluate()` starts seeing `>0 alternatives`
  regularly instead of the current 100%-single-candidate pattern; `_TAG_TO_ACTION` starts firing.
- **Tests required:** unit tests asserting `generate_immediate_actions()`'s output dicts contain
  a `tags` key matching the source goal; a test asserting the staleness condition admits goals at
  low-but-nonzero progress after the configured threshold.
- **Behavioral proof required:** Experiment C (§18).
- **Rollback:** revert the one function; goal set and `GOAL_ACTION_MAP` untouched.
- **Must NOT touch:** `GOAL_ACTION_MAP` itself (§6.3); the goal set's persisted progress values
  (no data migration).

### P3 — Closed outcome→learning→retrieval loop
- **Files:** new `experiences` table + accessor module; `_act_on()`'s branches in
  `autonomous_loop.py` updated to write one `Experience` row per cycle (both executed and vetoed
  paths, so `reward: null` vs. real reward becomes visible for the first time).
- **Prerequisite:** P1 (shares the canonical key).
- **Production risk:** medium — this is the first genuinely new table in this plan. Mitigate by
  making the write **append-only, best-effort, and non-blocking to the decision path** (wrap in
  the same try/except-log-continue pattern already used throughout `_act_on()`), so a failure to
  write an `Experience` row can never affect the decision or action itself.
- **Expected behavioral effect:** for the first time, a single query can answer "what did VECTOR
  decide, and what happened, and did it use that later" — the exact question every task 79-84
  has had to answer by manually joining five tables with mismatched keys.
- **Tests required:** a full round-trip test — propose, veto, execute, observe outcome — asserting
  the `Experience` row's `policy_key` matches what `get_score()` will look up next time.
- **Behavioral proof required:** Experiment A (§18).
- **Rollback:** drop the new table; nothing else depends on it existing (by design — P1/P2 do not
  require it).
- **Must NOT touch:** any existing table's schema.

### P4 — Epistemic integration
- **Files:** `core/loop/context_engine.py` (`track_beliefs`), `core/loop/decision_engine.py`
  (one new read call site for `belief:*`).
- **Prerequisite:** P2 (more candidate diversity makes a presence/activity-aware penalty
  meaningful — with only one candidate ever proposed, a belief-aware penalty has nothing to
  discriminate between).
- **Production risk:** low — additive read, same pattern as the existing `action_domain:*` read.
- **Expected behavioral effect:** `belief:presence:absent` should measurably deprioritize
  proactive/interactive candidate types when the owner is away — a testable, meaningful behavior
  change.
- **Tests required:** a scoring test with `belief:presence:absent=True` asserting a lower score
  for an interaction-shaped candidate than the same candidate scored with presence absent.
- **Behavioral proof required:** Experiment D (§18), adapted to a belief rather than a policy
  reward.
- **Rollback:** revert the one read call site.
- **Must NOT touch:** the `action_domain:*` mechanism, which already works and only needs P0-class
  execution volume to stop starving.

### P5 — Counterfactual reasoning (bounded)
- **Files:** new small module reusing `CounterfactualMemory`'s existing schema plus the
  `scenarios`/`outcomes` tables that already exist and are empty.
- **Prerequisite:** P1/P3 (needs the canonical key and the `Experience` log to populate
  `chosen_outcome` after the fact).
- **Production risk:** low if the cooldown/trigger-condition design in §5 is respected (no
  per-cycle LLM cost); medium if implemented naively as "call an LLM every cycle to imagine
  alternatives" — **explicitly rejected in §5's design.**
- **Expected behavioral effect:** `scenarios`/`outcomes` tables receive their first-ever rows;
  periodic aggregate adjustments start contributing to PolicyMemory via the shared key.
- **Tests required:** a test asserting the trigger condition (≥2 close candidates + cooldown
  elapsed) is both necessary and sufficient to create a scenario row.
- **Behavioral proof required:** Experiment C (§18), the generalization experiment, is the
  natural fit here.
- **Rollback:** the new trigger function can be disabled; the existing blocklist function is
  untouched.
- **Must NOT touch:** the existing `should_avoid()` veto behavior.

### P6 — Memory consolidation/generalization
- **Files:** new, small — a `situation_class()` function (design in §16) plus one new consolidation
  step in `reflect_loop`.
- **Prerequisite:** P1–P3 (generalization requires enough real, keyed experiences to generalize
  over — building this first would have nothing to consolidate).
- **Production risk:** medium — the coarseness of `situation_class` is a real design decision with
  a failure mode in both directions (§4's warning). Ship with a conservative, small bucket count
  and measure before widening.
- **Expected behavioral effect:** SemanticMemory's `goals_v1`-only staleness should end; genuinely
  new consolidated facts should start appearing after the first reflect cycle post-deployment.
- **Tests required:** Experiment C (§18) directly targets this phase.
- **Behavioral proof required:** as above.
- **Rollback:** disable the new consolidation step; `SemanticMemory`'s existing content untouched.
- **Must NOT touch:** `EpisodicMemory`'s raw event log, which should remain the ground truth
  underneath any consolidation.

### P7 — Understanding layer
- **Explicitly frozen** until P0–P6 close and are behaviorally verified (§18). Per §12/§13, this
  is not a near-term priority and building it earlier would add fragmentation, not capability.

### P8 — Higher-order agent/civilization evolution
- **Explicitly frozen**, with two exceptions already scheduled earlier for unrelated reasons: the
  successor dict/attribute fix (P1-adjacent, listed under §10, ships whenever the team addresses
  M in §14) and the HP habituation fix (also P1-adjacent). No new civilization-layer capability
  (more districts, new evolution mechanics, richer inheritance) should ship before P3 closes —
  there would be nothing yet for a richer civilization layer to learn from.

**Reordering note (per the task's own allowance):** the source evidence in this document supports
keeping the suggested P0–P8 order essentially as given, with one adjustment already reflected
above — **P2 (candidate diversity) is sequenced after P1 (canonical key), not before**, because
Task 84's own evidence (§4.5/§7) shows that diversifying candidates onto a still-broken policy
signal would produce more actions competing on a still-meaningless score, which is not a genuine
improvement and would be hard to distinguish from one in later measurement.

---

## 16. Behavioral proof plan (Phase 15)

Six experiments, each specified with the required before/stimulus/action/outcome/learning-event/
persistence/retrieval/decision/delta shape. None of these have been run. All are designed to run
against **Task 78's existing isolated Digital Twin Lab first** (zero production risk, reuses
already-built, already-tested machinery) and only against a disposable non-Segment-2 clone of the
live system second, never against a running experiment.

**Experiment A — Repeated experience, verify future decision changes.**
*Before:* two candidates, `action_type=X` and `action_type=Y`, scoring within 0.05 of each other,
`policy` term equal (fresh keys). *Stimulus:* run the repaired P1 pipeline through 5 outcome
cycles where `X` consistently receives `reward=0.9` via the real 5-factor formula. *Action:*
propose `{X, Y}` again. *Outcome/learning event:* `update_from_outcome(X, canonical_key, 0.9)` ×5.
*Persistence:* `policy_memory` row for `X`'s canonical key shows `sample_count=5`,
`avg_reward≈0.9`. *Retrieval:* next `get_score(X)` call returns ≈0.9, not the old default.
*Decision:* `X` wins where the initial scores were tied. *Measurable delta:* winner changes from
whichever was previously an arbitrary tiebreak to `X`, deterministically, across repeated runs.

**Experiment B — Change outcome from Y to Z, verify preference reverses.**
*Before:* Experiment A's end state (`X` preferred). *Stimulus:* 5 more outcome cycles where `X`
now receives `reward=0.1` (a genuine reward reversal, e.g. simulating a changed environment).
*Outcome:* `avg_reward` for `X`'s key trends down; `Y`'s (previously untouched) stays at its
prior baseline. *Decision:* `Y` becomes preferred within N cycles matching the EMA's own
convergence rate (this bounds N — no vague "eventually"). *Measurable delta:* winner flips back,
on a schedule predictable from the EMA formula itself, not just "eventually."

**Experiment C — Introduce a new but related situation, verify appropriate generalization.**
*Before:* `X` has a strong learned reward under `situation_class=S1`. *Stimulus:* propose `X`
under a genuinely different but related situation, `situation_class=S1` again but with different
non-defining params (e.g. same goal, different `title` string) vs. a genuinely unrelated
`situation_class=S2`. *Expected:* the S1-variant should benefit from `X`'s learned reward
(generalization within class); the S2 case should not (no leakage). *Measurable delta:*
score(X, S1-variant) significantly exceeds score(X, S2) even though neither has direct sample
history — proof the `situation_class` bucketing (§6, P6) works as designed rather than either
over-fitting (S1-variant treated as unrelated) or over-generalizing (S2 wrongly benefiting).

**Experiment D — Contradictory evidence, verify belief/confidence changes.**
*Before:* `action_domain:search` claim at confidence 0.275 ("ok"), per the live 7-row epistemic
state read this session. *Stimulus:* force N consecutive real `search_*` outcomes of the opposite
sign (if 0.275 reflects past failures, feed successes, or vice versa). *Learning event:*
`record_epistemic_belief()` fires post-execution (requires P0/P2 — execution must actually
happen). *Persistence:* claim confidence moves, `last_seen` updates. *Decision:* a subsequent
`search_*` candidate's `epistemic_penalty` factor changes correspondingly (should move toward
1.0 if evidence trends positive). *Measurable delta:* penalty factor before vs. after, same
candidate shape, different confidence input.

**Experiment E — Restart VECTOR, verify learned state survives and still changes behavior.**
*Before:* Experiment A's end state. *Stimulus:* a clean process restart (on a disposable clone,
never the live process, per this task's constraints). *Verify:* `bootstrap_agents()` (one-time,
per Task 82/83/84's own confirmed trace) does not reset `policy_memory` — it never has, since
that table is not agent-instance state — so this experiment is really testing whether **P1's**
canonical key survives a restart intact (it should, trivially, since it's a plain SQLite table)
and whether the *repeat-multiplier* habituation state (§9.1, confirmed in-memory-only and
reset-on-restart) does **not** survive — an explicit, named, expected asymmetry this experiment
should assert rather than be surprised by. *Measurable delta:* `X` still wins post-restart
(policy survives); HP habituation counters are back at zero (confirmed non-survival, by design,
unless P1-adjacent work decides to persist them — an open question this experiment settles).

**Experiment F — Two competing actions, verify learned policy affects ranking.**
*Before:* `X` and `Y`, tied on every factor except `policy`. *Stimulus:* the P1-repaired 5-factor
writer deposits a real, single, unambiguous reward difference for `X` over `Y`. *Action:* propose
both again. *Outcome:* `X` wins. This is deliberately the simplest experiment in the set and
should be run **first**, immediately after P1 ships, exactly reproducing Task 78's own
already-successful Level-4 result but against the *production* key-fix rather than the lab's
already-correct one — closing the gap Task 84 §3.4/§13 identified between "mechanically capable"
and "actually demonstrated in the live system."

**Explicitly rejected as proof, per this task's instruction, and not used anywhere above:** a
database row count increasing, a function executing without error, an LLM call completing, a
memory write occurring, a confidence number changing with no downstream consumer, an agent's HP
changing with no resulting selection change. Every experiment above requires a **decision-level,
before/after, same-input delta** as its actual measurement.

---

## 17. Risks and rollback strategy

| Change | Primary risk | Mitigation | Rollback |
|---|---|---|---|
| P0 (hypothesis timeout) | none material — strictly bounds existing unbounded behavior | test against a simulated hang first | revert one function |
| P1 (canonical key) | historical `policy_memory` rows become a mixed-format table (old unreadable rows alongside new readable ones) | leave old rows untouched, do not migrate/delete; the 29,164-sample bucket is a valuable frozen baseline, not garbage | revert the key function; writers resume writing (safely) unreadable keys |
| P2 (candidate diversity) | more candidates could, in theory, increase decision latency or gateway load | `limit=4` cap already exists and is preserved; measure latency before/after on a disposable clone | revert one function |
| P3 (`Experience` table) | a new always-on write in the hot decision path | make it best-effort/non-blocking (try/except/log, matching existing `_act_on()` conventions); it must never be able to affect the decision or action if it fails | drop table, remove call sites |
| P4 (epistemic → scoring) | a belief bug could wrongly suppress legitimate candidates | ship with a bounded penalty range (matching the existing `[0.70, 1.0]` `_epistemic_penalty()` clamp — do not widen it) | revert the read call site |
| P5 (bounded counterfactual reasoning) | scope creep into "LLM call every cycle" if the cooldown/trigger design is not respected | the design in §5 is the guardrail; any implementation must be checked against it before merge | disable the trigger function |
| P6 (consolidation) | over- or under-coarse `situation_class` degrading rather than improving generalization | ship conservative (few, wide buckets), measure via Experiment C before widening | disable the consolidation step; `EpisodicMemory` unaffected |
| Successor-bug fix (§10) | touches the Darwinian death/rebirth path directly, which is safety-adjacent (agent capabilities) | reuse the existing `spawn_from_ghost()` object-returning API rather than patching the dict-returning one — it already exists, is correctly designed, and is simply uncalled | revert to current fallback behavior, which is itself already a safe (if capability-losing) no-crash path |
| HP habituation fix (§9.1) | changing a shaping function changes which agent wins ties across the whole city, a wide blast radius | ship as a config-toggleable dampening curve, not a hardcoded change, so it can be A/B'd | revert to current asymmetric formula |

**General rollback posture for the whole plan:** every item above is designed to be revertible by
reverting a single function or dropping a single new table, specifically *because* Phase 12's
instruction (repair/connect over rewrite) was followed. Nothing in this plan requires a schema
migration of an existing table, a data backfill, or a change to `PermissionGateway`'s
enforcement semantics.

---

## 18. Explicit list of things NOT to change

- `PermissionGateway`'s GREEN/YELLOW/RED/FORBIDDEN taxonomy and enforcement point — proven safe
  across 107+ hours, and multiple prior tasks (53/57/58/59/60) already hardened it adversarially.
- The 21-coroutine `_supervised()` never-die pattern — it works exactly as designed.
- `Governor.dispatch()`'s decentralised-gating philosophy — Task 84 §6.3's reframe (a pattern, not
  a single chokepoint) is correct and should not be "fixed" into a single central gate, which
  would be a large, risky rewrite of a currently-working safety model for no demonstrated benefit.
- The existing `GOAL_ACTION_MAP` mapping itself (§6.3) — deliberate, documented, gateway-safety
  reasoning; only its two upstream feeder bugs should change.
- Any existing table's schema (all fixes in this plan are either new tables or corrected
  write-paths into existing schemas).
- The `EpisodicMemory` raw event log's write volume or format — it is the ground truth every
  consolidation/generalization step should read from, not filter at the source.
- Task 78's Digital Twin Lab's own code — it is correct, tested, and isolated; it should be
  *reused* (P5/P7 bridges) not modified.
- The 29,164-sample `analyze_progress` policy bucket and the 30,504-row counterfactual history —
  explicitly preserve as a frozen baseline (Task 71's LEARN-01, endorsed again here) against
  which every remediation above should be measured.
- Anything in the civilization/district layer beyond the two named surgical fixes (§10) — no new
  districts, no new agents, no richer inheritance mechanics, until P3 gives them something real
  to learn from.
- The Understanding Layer (§12/§13/§15 P7) — entirely frozen, as instructed, until the foundation
  closes.

---

## 19. Top 10 highest-leverage changes

1. **Canonical `PolicyKey` function (§4/P1).** Reconnects the single richest, already-correct
   reward signal in the codebase with a one-function fix. Highest leverage in the document by a
   wide margin — every other repair either depends on it or is smaller in scope.
2. **`generate_immediate_actions()` tags propagation (§6/P2).** A one-line fix that reconnects a
   21-entry, already-written mapping (`_TAG_TO_ACTION`) at zero new-code cost.
3. **`generate_immediate_actions()` staleness condition (§6/P2).** Turns "one goal frozen at
   exactly 0.0" into genuine multi-candidate competition — the precondition for P1's fix to be
   measurable at all (Task 78's own Level-4 precondition).
4. **`hypothesis_loop`'s missing timeout (§3/P0).** Cheapest, lowest-risk, and the leading
   candidate mechanism for the ~1,000× perception-loop slowdown that has masked every other
   measurement in Tasks 79–84.
5. **HP `award_points` habituation asymmetry (§9.1).** The one mechanism that already reaches
   L3-L4 is currently mathematically prevented from ever moving upward under repetitive work —
   fixing the shaping function's asymmetry unblocks it without touching selection logic itself.
6. **`spawn_successor()` dict/attribute contract (§10).** A one-function fix (call the already-
   existing, already-correct `spawn_from_ghost()` instead) that closes the only concretely
   identified object-lifetime bug in the system.
7. **New `Experience{}` correlation log (§7/P3).** The single new primitive this plan proposes;
   turns "join five mismatched tables by hand" (which every one of Tasks 79-84 had to do) into
   one queryable identity.
8. **Re-key `PUBLISH_EVENTS`/`EVENT_TRIGGER_MAP` by `(district, task_type)` (§11).** Removes the
   root cause of the two closed fan-out cycles without touching the fan-out mechanism itself.
9. **Per-edge cooldown/dedup on the event fan-out (§11).** Converts "fires every ~9 seconds
   forever" into "fires when something changed," directly reducing the noise-to-signal ratio in
   every future measurement.
10. **`belief:*` → scoring connection (§8/P4).** The cheapest capability upgrade available —
    real, already-written situational data (presence, activity) currently has zero effect on any
    decision.

## 20. Top 10 tempting changes that should NOT be made yet

1. **Building a full "Understanding Layer" (Phase 11's 13 capabilities) before the foundation
   closes.** Would add fragmentation on top of fragmentation — explicitly frozen (§13/§15 P7).
2. **Widening `GOAL_ACTION_MAP` to give every horizon a unique action type.** Tempting because it
   looks like it would "fix diversity" faster than the tags/staleness fix — but it bypasses the
   actual bug (tags never propagate) and risks breaking the deliberate gateway-safety property
   the current map was built for (§6.3).
3. **Adding richer situation context (full world-state hash, timestamps) directly into the
   `PolicyKey` at the same time as the canonicalization fix.** Two changes, two failure modes, at
   once — ship the byte-format fix alone first (§4).
4. **A per-cycle LLM call for "real" counterfactual reasoning.** The literal naive reading of
   "make counterfactual reasoning real" — explicitly rejected in §5's design in favor of a
   bounded, cooldown-gated trigger reusing the runner-up candidate that already exists for free.
5. **Merging EpistemicTracker and PolicyMemory into one table** because they're both "learning
   memory." Explicitly kept separate in §8 — they answer different questions and merging would
   lose diagnostic power.
6. **Migrating or deleting the existing 29,164-sample `analyze_progress` policy bucket** to
   "clean up" the data once the key fix ships. It is the project's most statistically unambiguous
   negative-result baseline (§18) — preserve it.
7. **A global cycle-detection graph analysis across the entire event-trigger table** instead of
   the smaller per-edge cooldown fix (§11). Solves the same problem at far higher implementation
   and testing cost — exactly the "giant rewrite" this task's Phase 10 warns against.
8. **Deleting `ReasoningBank`/ghost-memory/`reasoning_chains` outright** because they're
   currently DEAD. Flagged for an owner decision (§13), not a unilateral removal — they may be
   cheap to wire correctly instead of removing, and this plan has not fully evaluated that
   tradeoff.
9. **Restarting or re-running the Segment 2 (or a Segment 3) experiment to "test" any of this
   plan's fixes against the live system before validating them on a disposable clone.** Every
   experiment in §18 is specified to run on Task 78's lab or a disposable clone first — the live
   experiment's data is now historical evidence, not a test harness.
10. **Building a new "Self-Model" or "World-Model" subsystem to unlock understanding-layer
    capabilities faster.** Both are correctly diagnosed as genuinely absent in §12 — and both are
    exactly the kind of large, speculative addition Phase 12 and this task's framing (Astra-level
    understanding is a later stage, not this one) explicitly defer.

---

## 21. Integrity statement

Production source modified: **none**. Configuration modified: **none**. Databases written:
**none** — every database access this session used a `mode=ro` SQLCipher connection via the
project's own `_get_db_key()`, exactly as established in Tasks 79/81/83. VECTOR process
started/stopped/signaled/interacted with: **none**. Tests executed: **none**. Synthetic stimulus
introduced: **none**. New dependencies added: **none**. Files created: exactly one — this
document.

---

## TASK 85 VERDICT

- **Current foundation maturity: L1–L2** (Task 72's ladder). One mechanism (Agent HP → agent
  selection) reaches L3-L4 in principle and is currently self-saturated. Zero mechanisms
  demonstrate L4 in the live 107-hour run; Task 78's isolated lab proves L4 is mechanically
  reachable by the unmodified existing classes.
- **Biggest bottleneck:** the PolicyMemory canonical-key mismatch (§4) — it is the single point
  where the richest, most correct, real-outcome reward signal in the entire codebase is generated
  correctly, persisted correctly, and permanently unreadable. Fixing it is a one-function change
  that reconnects more of the intended loop than any other single item in this plan.
- **Biggest safety concern:** none observed in the live run (zero RED/YELLOW/FORBIDDEN, zero
  external/financial/destructive actions across 107+ hours, per Tasks 83/84) — but the honest
  residual is architectural, not observed: ~40 subprocess-using files were never individually
  traced, and the decentralised point-of-effect gating model means the *next* undiscovered bypass
  (four were found, each by accident, after the system was first declared "conditionally ready")
  is a real, standing possibility that no amount of clean 107-hour operation retires.
- **Biggest architectural disconnect:** outcome attribution (§7) — there is no `experience_id` or
  equivalent stable identity connecting a proposed candidate to its eventual outcome to its
  eventual retrieval. Every other disconnect in this document (policy key mismatch, epistemic
  starvation, dead ghost memory) is a *symptom* of the same missing primitive: nothing in VECTOR
  can currently answer "what happened as a result of this specific decision" in one lookup.
- **First subsystem to implement:** P0 (hypothesis-loop timeout) first, because it is the
  cheapest, lowest-risk, and most likely to unblock accurate measurement of everything that
  follows it; P1 (canonical `PolicyKey`) immediately after, because it is the highest-leverage
  single change in the whole plan.
- **First behavioral experiment to run:** Experiment F (§16) — two competing actions, a real
  learned reward via the P1-repaired path, verify the ranking changes. It is the simplest
  possible reproduction of Task 78's already-successful lab result, now against the production
  key fix, and is the fastest way to convert this plan's central claim ("the fix is connective,
  not inventive") from an architectural argument into a measured fact.
- **What must remain frozen until then:** the Understanding Layer in its entirety (§12); any new
  memory subsystem; any expansion of `GOAL_ACTION_MAP`; any new district, agent, or civilization
  mechanic; the existing `analyze_progress` policy baseline and counterfactual history (preserve,
  don't touch); and the live experiment process itself, which this task — like every task before
  it in the 51-85 series — was run against read-only, start to finish.
