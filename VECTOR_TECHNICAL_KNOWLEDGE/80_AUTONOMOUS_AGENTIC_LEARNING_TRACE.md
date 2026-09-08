# Executive Verdict

**The autonomous agentic/district subsystem is genuinely autonomous, but is
not a closed learning/adaptation loop.** It has exactly one working,
closed, causal write→read→decision-influence loop:
`Agent.health_points` (Darwinian HP) → `Governor.dispatch()`'s
`max(agents, key=lambda a: a.health_points)` agent-selection tiebreak. Every
other candidate "learning" mechanism this task traced — `PolicyMemory`,
`CounterfactualMemory`, `reasoning_chains`, ghost-memory `lessons`/
`best_decisions` — has a real, persistent **write** side, but the **read**
side is either absent, unreachable from this subsystem, or (in the single
most important finding of this trace) silently broken by a hash-format
mismatch that makes three of the four real-outcome `PolicyMemory` writers
write to keys the scorer can never look up. Darwinian agent succession is
also, as of this trace, **guaranteed to fail on every single death** due to
a confirmed return-type contract mismatch (`spawn_successor()` returns a
`dict`; the caller immediately does attribute access on it) — meaning
successors always fall back to a bare, capability-less `AgentBase`, and even
when reconstruction succeeds in principle, inherited ghost `lessons`/
`best_decisions` are proven dead code (the one method that would surface
them into an LLM prompt is called nowhere in production).

---

## 1. Scope and Experiment Isolation

Pure static source-code tracing. No file was modified. No VECTOR process was
started, signaled, or queried. No database — production or otherwise — was
opened. Every fact below is either a direct source-code quote/citation (file
+ line) or an explicit inference labeled as such. Task 79's report was read
for context (its own evidence, not re-collected). Task 71/72's own findings
(`analyze_progress` dominance, the dead `_TAG_TO_ACTION` map, the hardcoded
`reward=0.05` counterfactual penalty) are cited, not re-derived, per this
task's explicit instruction not to repeat them.

## 2. Autonomous Agentic Architecture

Three largely-independent trigger sources feed into one shared hub
(`Governor.dispatch()`), which fans out to district agents:

```
GoalSystem.generate_immediate_actions()  ──┐
  (Task 71/78/79's fully-traced pathway)    │
                                             ├──> DecisionEngine.evaluate() ──> winner ──> autonomous_loop._act_on() ──> Governor.dispatch()
Plan steps (core/runtime/plans.py)      ──┘                                                      (line 1234)

HandRunner.run_hand()  (hands/runner.py, scheduled cron jobs:              ──> Governor.dispatch()  (hands/runner.py:77, _dispatch())
  researcher/collector/trader/predictor/content/...)

Direct/other callers (chief_of_staff escalations, API routes,             ──> Governor.dispatch()
  event-bus fan-out, voice intents, scheduler jobs — not exhaustively
  enumerated in this trace)
```

`Governor.dispatch()` (`core/city/governor.py:1970`) is confirmed (by direct
source read, matching Task 79's live log line
`core.city.governor:dispatch:1994`) to be the **single shared execution
hub** for essentially all real-world district work, regardless of which of
the three trigger sources above produced the task. This is the key
structural fact this trace adds beyond Task 79: **`analyze_progress`'s
saturated loop and the "agentic.loop"/hand/district activity are not two
fully separate subsystems — they share one dispatch hub — but
`analyze_progress` specifically never reaches it**, because it is vetoed by
`CounterfactualMemory` inside `autonomous_loop.py` *before* the code
path that calls `Governor().dispatch()` (§8, §16).

## 3. Agentic Decision Path

**A. Entry**: `HandRunner.run_hand()` is invoked from `register_all()`
(`hands/runner.py:216`), which registers every non-`on_demand` `Hand`
(`researcher`, `collector`, `trader`, `predictor`, `content`, ...) against
the durable APScheduler-style cron scheduler via
`core/loop/cron_jobs.py::_try_register`. This is a **scheduled, cron-driven
entry point**, not a decision made by `DecisionEngine` — Hands do not
compete as `Candidate`s in `DecisionEngine.evaluate()` at all.

**B. Cognition**: `HandRunner._task_type_for(hand)` deterministically maps a
hand name to a governor `task_type` via a fixed dict
(`_TASK_TYPE_OVERRIDES`, `hands/runner.py:44-49`: `"researcher"→"deep_research"`,
`"collector"→"osint_collect"`, `"trader"→"trading_analysis"`). No candidate
set, no scoring, no LLM decision about *whether* or *what* to run — the
schedule alone decides. Inside the district, the actual work (e.g. deep
research synthesis) is real LLM-driven cognition (confirmed:
`MODEL_HEAVY_HANDS = {"researcher","collector","predictor","trader"}` are
explicitly the ones "whose district route does substantive local-LLM
reasoning", `hands/runner.py:24-34`), but *which* hand runs and *when* is
100% deterministic (cron schedule), not adaptive.

**C. Experience**: `HandResult.status` (`"ok"`/`"error"`/whatever the
district returns, `hands/runner.py:176-180`) is the success/failure signal.
It is NOT linked to the originating decision by any `decision_id` — there is
no decision to link to, since no `DecisionEngine.Decision` object was ever
produced for a Hand run.

## 4. District Execution Path

`Governor.dispatch(task)` (`core/city/governor.py:1970-2419`), traced
end-to-end from source:

1. `route_task(task_type)` picks a district (deterministic keyword map;
   `_llm_classify()` is an LLM fallback used only for un-mapped/freeform
   task types).
2. Security/compliance gates run unconditionally: rate limiter (GCRA per
   district), taint tracker (shell/fetch sinks), prompt-injection scan,
   budget-quota check (warn-only), Merkle audit log, OTel span.
3. Agent selection within the district: **declared-capability match wins if
   one exists; otherwise `agent = max(agents, key=lambda a: a.health_points)`**
   (`governor.py:2272`) — the highest-HP agent in the district, *regardless*
   of whether it declares the capability. This fallback exists explicitly
   ("Task A.3's unconditional fallback") so a district is never unstaffed.
4. `agent.run(task)`, bounded by `asyncio.wait_for(..., timeout=CONFIG["loop"]["agent_dispatch_timeout_sec"])`.
5. **RULE 9 outcome recording** (`governor.py:2368-2395`): on
   `status=="ok"` **and** a genuine capability match, `agent.award_points(50, "task_completed_by_governor")`;
   on `status in ("error","failed")`, `agent.deduct_points(30, "task_failed_by_governor")`.
   If the agent won purely by HP (no capability declared for this
   task_type), **HP is deliberately withheld** even on success — "so the HP
   signal still means 'this agent is good at what it's actually being asked
   to do'" (governor.py:2373-2385, direct quote).
6. `EpisodicMemory().store(event_type="governor_dispatch", ...)` — write,
   confirmed by Task 79 (8,569 in-window rows), no autonomous reader found
   anywhere in this trace (§7).

**No call to `PolicyMemory`, `CounterfactualMemory`, or `EpistemicTracker`
exists anywhere in `governor.py`.** This is a direct, confirmed negative
finding (`grep` across the whole file), not an inference.

## 5. Outcome/Experience Path

Two independent, non-overlapping outcome-recording mechanisms exist for
work that flows through `Governor.dispatch()`:

1. **HP** (governor.py itself, §4 point 5) — the only mechanism intrinsic to
   `dispatch()`.
2. **`HandRunner`'s own post-dispatch bookkeeping** (`hands/runner.py:188-195`,
   called after `_dispatch()`/`_dispatch_via_gateway()` returns) — runs a
   **second, independent** HP award/deduct (`_award_hp()`,
   `hands/runner.py:125-139`, same `award_points(50, ...)`/`deduct_points(30, ...)`
   shape as governor's own RULE 9) **in addition to** whatever
   `Governor.dispatch()` already did internally for the same task. This is a
   **double-HP-award finding**: a successful Hand run can award HP to the
   district's max-HP agent twice for the same outcome (once inside
   `governor.dispatch()`'s own RULE-9 block, once again in
   `HandRunner._award_hp()`) — not confirmed to be intentional redundancy or
   a bug; flagged in §17 as RELIABILITY, not fixed.
3. For non-Hand work that reaches `autonomous_loop._act_on()` (i.e., a
   `DecisionEngine` winner that survived the counterfactual veto — §8),
   a **third**, much richer outcome path exists: the 5-factor reward at
   `autonomous_loop.py:1254-1260`
   (`uf*0.40 + goal_progress*0.25 + not_overridden*0.15 + not_corrected*0.15 + completed*0.05`,
   using real user feedback via `_get_recent_feedback()` when available) —
   this is the single richest, most genuinely outcome-sensitive reward
   signal found anywhere in this trace, and it is the one whose write is
   silently orphaned (§9).

## 6. Learning Writes

| Mechanism | Real writer(s) found | Situation-hash / key format |
|---|---|---|
| `PolicyMemory` | `autonomous_loop.py:1048` (VectorCode reward), `:1115` (counterfactual-veto 0.05 penalty), `:1265` (main 5-factor reward), `:1495` (plan-step reward); `hands/runner.py:147` (`_update_policy`); `districts/chief_of_staff/chief_of_staff.py`, `districts/reflection/daily_reviewer.py` | **Three different, mutually incompatible formats** — see §9 |
| `CounterfactualMemory` | `autonomous_loop.py` (`record_rejection`, `should_avoid`) — only reached from the `_act_on()` post-selection veto and one retry-queue pre-filter (`:444-455`) | proposal string, real |
| `EpisodicMemory` | `governor.py` (`governor_dispatch`), `hands/runner.py` (`hand_execution`), `DecisionEngine.evaluate()` (`decision_candidate`), many district files | write-only from every reader traced in this task — see §7 |
| `reasoning_chains` (`ReasoningMemory.store_chain`) | `hands/runner.py:113-121` (`hand:<name>` situation, real reward 1.0/0.0), `DecisionEngine._get_reasoning_bank()`'s injection path is a *reader* only (see §7) | `situation=f"hand:{hand.name}"` — no params variation at all |
| `EpistemicTracker` | `DecisionEngine.record_epistemic_belief()`, called from `autonomous_loop.py:1271` and `:1501` (only reached for winners that survive to real execution/outcome — i.e. NOT Hands, NOT most direct governor-only dispatches) | `action_domain:<action_type.split("_")[0]>` |
| Ghost memory (`lessons`, `best_decisions`, `personality_traits`) | `AgentBase.die()`→`AgentBase.inherit_ghost()` (`core/city/agent_base.py:237-264`) | in-memory object attributes + SQLite `agent_history.ghost_memory` (JSON) |
| Agent HP | `AgentBase.award_points()`/`deduct_points()`, called from `governor.py`, `hands/runner.py`, `autonomous_loop.py` (avatar mood nudge, other paths not exhaustively enumerated) | in-memory `agent.health_points`, checkpointed via `core/loop/loop_state.py::restore_agent_hp` (referenced at `autonomous_loop.py:2456-2467`, not independently traced further this task) |

## 7. Learning Reads

| Write | Reader(s) found | Can it influence a future decision? |
|---|---|---|
| `PolicyMemory` rows | **Only** `DecisionEngine._score_candidate()` (`decision_engine.py:379`) among autonomous callers; `core/api/crud.py`/`core/memory/router.py` are generic passthroughs requiring caller-supplied hash (no autonomous caller found using them) | **Only for rows keyed with the `sorted(params.items())` hash format** — see §9 |
| `CounterfactualMemory` rejections | `CounterfactualMemory.should_avoid()`, called from `autonomous_loop.py:1095` (post-selection veto) and `:446` (retry-queue pre-filter) | Yes, but only vetoes an *already-selected* winner — never a scoring input (Task 71/72/78 finding, re-confirmed here for the governor/hands pathway: **`CounterfactualMemory` is never consulted anywhere in `governor.py` or `hands/runner.py` either** — Hand-dispatched and most governor-only-dispatched actions are never counterfactually checked at all) |
| `EpisodicMemory` rows | **None found.** `ContextEngine.get_world_state()` reads `mem.recall()` into `recent_episodes`, but per `decision_engine.py`'s own comment (re-confirmed, not re-derived, from Task 78) that value does not feed the score formula. No other autonomous reader of `episodic_memory` rows was found in this trace. | No |
| `reasoning_chains` | `DecisionEngine._get_reasoning_bank()` reads a **separate, file-backed `ReasoningBank`** (`vectorcode/src/reasoning_bank.py`), not the SQL `reasoning_chains` table `hands/runner.py` writes to — **these are two different storage backends with the same conceptual purpose and no confirmed bridge between them in this trace** (flagged as unconfirmed, not asserted either way — see §18) | Unconfirmed |
| `EpistemicTracker` claims | `DecisionEngine._epistemic_penalty()` (`decision_engine.py:271-312`), reads `action_domain:<domain>` | **Yes — the one other partially-working loop**, but only for candidates that (a) reach `DecisionEngine.evaluate()` at all (Hands never do) and (b) survive to the real-outcome recording point (`autonomous_loop.py:1271`/`:1501`) that writes the belief in the first place |
| Ghost `lessons`/`best_decisions` | `AgentBase.get_system_prompt()` (`agent_base.py:294-322`) is the **only** method that reads them into anything LLM-facing. **Confirmed by repo-wide search: `get_system_prompt()` is called from exactly one place in the entire codebase, `tests/unit/test_permission_gateway_extra.py:400` — zero production call sites.** | **No — dead code in production** |
| Agent HP | `Governor.dispatch()`'s `max(agents, key=lambda a: a.health_points)` (`governor.py:2272`), `HandRunner._award_hp()`'s identical selection (`hands/runner.py:131`) | **Yes — real, working, closed loop** (§8) |

## 8. Closed-Loop Analysis

Applying the task's own required chain
(`EXPERIENCE → OBSERVATION/OUTCOME → INTERNAL STATE UPDATE → PERSISTENCE → LATER RETRIEVAL → SAME/RELATED FUTURE SITUATION → DECISION CHANGE → BEHAVIOR CHANGE`)
to each candidate mechanism:

| Mechanism | Experience | State update | Persistence | Retrieval | Decision change | Behavior change | **Loop closed?** |
|---|---|---|---|---|---|---|---|
| Agent HP → district agent selection | task success/failure | `award_points`/`deduct_points` | in-process + `loop_state.py` checkpoint | `max(agents, key=health_points)` every dispatch | which agent instance runs | yes — a different agent (possibly different capabilities/behavior) does the work | **YES** |
| `PolicyMemory` (3 of 4 real writers) | task outcome, incl. real user feedback | `update_from_outcome` | SQLite | `_score_candidate()`'s `get_score()` | candidate score | winner selection | **NO — hash-format mismatch (§9) severs retrieval** |
| `PolicyMemory` (counterfactual-veto writer) | a veto event | `update_from_outcome(reward=0.05)` | SQLite | `get_score()` | candidate score | winner selection, in principle | **Technically yes, but the only "experience" it encodes is "I was vetoed" — it cannot represent a real task outcome, and for `analyze_progress` it has converged to a frozen constant (Task 79)** |
| `EpistemicTracker` | task outcome | `record_epistemic_belief` | SQLite | `_epistemic_penalty()` | score multiplier | winner selection, in principle | **YES for the narrow slice of traffic that reaches it** (§7) — not exercised at all by Hands or governor-only dispatches |
| `CounterfactualMemory` | rejection event | `record_rejection` | SQLite | `should_avoid()` | post-selection veto, not score | which action executes this cycle | **YES, but only a veto, never a re-ranking; not reachable from Hands/governor-only dispatches at all** |
| Ghost memory `lessons`/`best_decisions` | agent's own accumulated experience | `inherit_ghost()` | in-process object + `agent_history` table | `get_system_prompt()` | would-be LLM context | none | **NO — reader is dead code** |
| `reasoning_chains` (hand-written) | hand run outcome | `store_chain` | SQLite | none confirmed | none | none | **NO — no confirmed reader** |
| `EpisodicMemory` (all writers) | any event | `store()` | SQLite | none confirmed (beyond non-score-affecting `recent_episodes`) | none | none | **NO** |

## 9. PolicyMemory Causal Trace

This is the central finding of this task. Four real-outcome write call
sites exist in `core/loop/autonomous_loop.py`, plus `hands/runner.py`:

| Call site | Situation-hash formula | Matches `DecisionEngine._make_situation_hash()`? |
|---|---|---|
| `decision_engine.py:268` (the **reader**, `_score_candidate()`) | `f"{action_type}:{sorted(params.items())}"` | — (this is the reference) |
| `autonomous_loop.py:1112-1113` (counterfactual-veto 0.05 penalty) | `f"{action_type}:{sorted(params.items())}"` | **YES — exact match** |
| `autonomous_loop.py:1046` (VectorCode reward, 0.8/0.3) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO** |
| `autonomous_loop.py:1263` (main 5-factor reward) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO** |
| `autonomous_loop.py:1493` (plan-step reward, 0.7/0.3) | `f"plan_step:{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO (also has an extra `"plan_step:"` prefix)** |
| `hands/runner.py:145` | `hashlib.sha256(f"hand:{hand.name}".encode())` — no params at all | **NO (structurally different key space entirely)** |

`sorted(dict.items())` produces a Python list-of-tuples repr (e.g.
`[('goal_id', 'g1'), ('title', 'x')]`); `json.dumps(dict, sort_keys=True)`
produces a JSON object string (e.g. `{"goal_id": "g1", "title": "x"}`).
These are different byte strings for the same logical params, and SHA-256
is not collision-tolerant of that — **the three call sites using
`json.dumps` write to a `policy_memory` row that
`DecisionEngine._score_candidate()`'s own read (`get_score()`, using the
`sorted(...)` format) can never find**, and will instead see `DEFAULT_SCORE`
(0.5) or whatever the *counterfactual-veto* writer (the one matching format)
happened to leave there.

**This means the single richest, most genuinely-outcome-sensitive reward
signal in the entire codebase — the 5-factor formula at
`autonomous_loop.py:1254-1260`, which incorporates real user feedback — is
persisted but structurally unreadable by the only production consumer of
`PolicyMemory` scores.** The only `PolicyMemory` signal `DecisionEngine` can
actually see, for any candidate that ever gets vetoed and re-proposed, is
the flat, uninformative `reward=0.05` counterfactual penalty — which is
exactly why Task 79 found `analyze_progress`'s policy score frozen at
`≈0.05` rather than reflecting any real task outcome.

**`hands/runner.py`'s `PolicyMemory` writes for `researcher`/`collector`/
`trader`/`predictor` are structurally orphaned for a different reason**: no
`Candidate(action_type="researcher", ...)` (etc.) object is ever constructed
anywhere in this trace — Hands dispatch directly via `Governor().dispatch()`,
bypassing `DecisionEngine.evaluate()` entirely, so there is no future
`_score_candidate()` call that would ever look up a `hand:<name>`-hashed row
in the first place, regardless of hash format. **Task 79's observed diverse
`policy_memory` rows for these action types (§7 of that report) are real,
genuine Level-0 storage with a real, differentiated reward signal — but this
trace finds no code path, anywhere, that reads them back for any purpose.**

**Direct answer to this task's PolicyMemory question**: no real production
pathway reaches `stored reward → changed score → changed winner/behavior`
for any of the five-plus diverse action types Task 79 observed. The one
pathway that *can* reach that chain (the counterfactual-veto writer) only
ever encodes "this exact proposal was vetoed," never a genuine task outcome.

## 10. Counterfactual Causal Trace

Confirmed not reachable from `governor.py` or `hands/runner.py` at all — see
§7. Within `autonomous_loop.py`, the mechanism (Jaccard similarity +
exponential staleness decay, `core/memory/counterfactual.py`, already
documented in Task 71/72/78/79) is real and functioning as designed for the
one pathway it is wired into (`_act_on()`'s post-selection veto). No new
counterfactual-specific mechanism was found for the agentic/district
subsystem.

## 11. Episodic/Semantic Memory Causal Trace

No autonomous reader of `episodic_memory` rows was found anywhere in the
agentic/district subsystem in this trace (§7). `SemanticMemory` was not
independently re-traced this task (Task 79 already established
`goal_summary`/`goals_v1` as its only actively-read key, via `GoalSystem`,
already fully characterized in Tasks 71/72/78/79 — not re-derived here).

## 12. Epistemic Causal Trace

See §7/§8. The one epistemic write/read pair that is genuinely closed
(`record_epistemic_belief()` → `_epistemic_penalty()`) is scoped to
`action_type.split("_")[0]` domain buckets and is only exercised by winners
that (a) came from `DecisionEngine.evaluate()` and (b) survived to a real
outcome. Hands and most governor-only dispatches never touch it at all —
confirmed by the complete absence of any `EpistemicTracker`/
`record_epistemic_belief` reference in `governor.py` or `hands/runner.py`.

## 13. Agent Lifecycle / Ghost Memory

Full trace, `core/city/agent_base.py` + `core/city/agent_registry.py` +
`core/city/evolution_engine.py`:

```
deduct_points() reaches 0 HP
  → AgentBase.die()  (agent_base.py:237)
      → builds ghost dict {name, district, generation, final_hp,
        lessons_learned (last 20), best_decisions (last 10),
        personality_traits, died_at}
      → self.ghost_memory = ghost
      → AgentRegistry.deregister(self.id)
          → ghost_data assembled (adds `capabilities`, explicitly carried
            through because ManifestLoader injects capabilities post-
            construction, not in __init__ — agent_registry.py:93-101)
          → _persist_ghost(agent)  → SQLite agent_history row (final_hp,
            ghost_memory JSON, died_at) — this is Task 79's observed
            `agent_history` table
          → EvolutionEngine.spawn_successor(ghost_data)
              *** CONFIRMED ROOT CAUSE, source-verified this task ***
              spawn_successor()'s own signature (evolution_engine.py:97)
              is `def spawn_successor(self, dead_agent: dict) -> dict`
              — it returns a plain dict.
              agent_registry.py:139 immediately does
              `successor.generation = successor_agent.generation`
              (attribute access) on that dict's return value.
              A dict has no `.generation` attribute — this raises
              AttributeError on every single successful
              spawn_successor() call, 100% of the time, not
              intermittently. This is the exact, byte-for-byte match
              for Task 79's observed live error:
              "'dict' object has no attribute 'generation'".
          → except Exception: falls back to a bare `AgentBase(gen+1)`,
            with `capabilities` explicitly re-applied
            (agent_registry.py:171 — contradicts the FALLBACK LOG
            MESSAGE's own text, "no capabilities", which appears to be
            stale relative to the current code; the fallback's capability
            list is real, only the *behavioral* logic — the original
            subclass's `run()` override, any district-specific state — is
            lost) → successor.inherit_ghost(ghost_data) either way
              → sets self.lessons, self.best_decisions,
                self.personality_traits on the NEW object (real transfer)
              → self.get_system_prompt() is the only method that would
                surface these into an LLM-facing prompt — confirmed
                (repo-wide search, §7) to be called from ZERO production
                code paths, only one unit test.
```

**Direct answer to this task's question**: ghost memory is **merely
archival** in the currently-running architecture. The data genuinely
transfers (`inherit_ghost()` is real, unconditional, and runs on both the
success and fallback paths), but there is no causal path from that
transferred data to any different behavior — because (a) the successor's
own class/capabilities are lost on the (now confirmed **always-triggered**)
reconstruction failure, and (b) even when a real subclass successor is
produced, the one prompt-injection method that would make `lessons`/
`best_decisions` behaviorally relevant is dead code.

**Fitness/mutation**: no mutation mechanism (e.g. personality-trait
perturbation, generation-based strategy variation) was found in
`evolution_engine.py` beyond generation-number incrementing and HP
inheritance — not exhaustively verified beyond what `spawn_successor`'s
dict-return path exposes, since that path currently never completes
successfully in production.

## 14. Learning-Level Scorecard L0–L7

| Mechanism | L0 Storage | L1 Retrieval | L2 Decision influence | L3 Persistent state | L4 Behavioral adaptation | L5 Generalization | L6 Correction | L7 Meta-learning |
|---|---|---|---|---|---|---|---|---|
| Agent HP → agent selection | PASS | PASS | PASS | PASS | **PASS** | UNTESTED (cross-district?) | NOT IMPLEMENTED | NOT IMPLEMENTED |
| `PolicyMemory` (3 of 4 real writers) | PASS | **FAIL (hash mismatch)** | FAIL | PASS (orphaned) | FAIL | N/A | N/A | N/A |
| `PolicyMemory` (counterfactual writer) | PASS | PASS | PASS (but only encodes "vetoed") | PASS (converges to a constant) | **FAIL** (Task 79: frozen) | N/A | N/A | N/A |
| `PolicyMemory` (Hands: researcher/collector/trader/...) | PASS | **FAIL (no reader exists)** | FAIL | PASS (orphaned) | FAIL | N/A | N/A | N/A |
| `EpistemicTracker` | PASS (narrow traffic) | PASS (narrow traffic) | PASS (narrow traffic) | PASS | UNCONFIRMED (not directly observed changing a winner this task) | Task 78 found a real cross-action-type channel via domain-prefix bucketing (synthetic, not re-confirmed against live traffic here) | NOT IMPLEMENTED | NOT IMPLEMENTED |
| `CounterfactualMemory` | PASS | PASS | PASS (veto only, not scoring) | PASS | FAIL (veto ≠ adaptation) | N/A | NOT IMPLEMENTED (no provenance field, Task 78 finding, re-confirmed absent here too) | NOT IMPLEMENTED |
| Ghost memory (`lessons`/`best_decisions`) | PASS | **FAIL (dead-code reader)** | FAIL | PASS | FAIL | N/A | N/A | N/A |
| `reasoning_chains` (hand-written) | PASS | **FAIL (no confirmed reader)** | FAIL | PASS | FAIL | N/A | N/A | N/A |
| `EpisodicMemory` (all writers) | PASS | **FAIL (no score-affecting reader)** | FAIL | PASS | FAIL | N/A | N/A | N/A |

**Highest defensible learning level anywhere in this subsystem: L4
(behavioral adaptation), and only for the Agent-HP → district-agent-
selection mechanism.** Every memory-based mechanism (`PolicyMemory`,
`CounterfactualMemory`, ghost memory, `reasoning_chains`, `EpisodicMemory`)
tops out at L3 (persistent state) with a broken or absent L1/L2 retrieval
step, for this subsystem specifically.

## 15. Complete Causal Graph

```
TRIGGER                       CONTEXT               AGENT/COGNITION            DECISION/GOVERNOR         ACTION                OBSERVATION/OUTCOME        LEARNING WRITE                 PERSISTENCE   LEARNING READ                    NEXT DECISION
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Cron schedule (Hands)    ──WIRED──> hydrate() ──WIRED──> (no candidate scoring —
                                    (ContextEngine)       schedule alone decides)  ──WIRED──> Governor    ──WIRED──> agent.run() ──WIRED──> HP award/deduct     ──WIRED──> SQLite     ──WIRED──> max(HP) agent select ──WIRED──> next dispatch, same district
                                                                                    .dispatch()                                 ──WIRED──> episodic "hand_execution" ──WIRED──> SQLite ──DEAD (no reader)──> ✗
                                                                                                                                 ──WIRED──> reasoning_chains "hand:x" ──WIRED──> SQLite ──DEAD (no confirmed reader)──> ✗
                                                                                                                                 ──WIRED──> PolicyMemory (wrong key space) ──WIRED──> SQLite ──DEAD (no reader ever looks up hand:x)──> ✗

GoalSystem (Task 71/78/79) ──WIRED──> DecisionEngine ──WIRED──> counterfactual   ──DEAD (returns  ✗ never reaches Governor for analyze_progress (Task 79)
  progress==0.0 filter        .evaluate()               veto check              before dispatch)
                                                          (autonomous_loop:1090)

Plan step / other DecisionEngine winners ──WIRED──> Governor.dispatch() ──WIRED──> agent.run() ──WIRED──> HP award/deduct        ──WIRED──> SQLite     ──WIRED──> max(HP) select        ──WIRED──> next dispatch
                                                                                                 ──WIRED──> 5-factor reward write ──PARTIAL (writes,   ──DEAD (hash mismatch, §9)──> ✗
                                                                                                             (autonomous_loop:1263)   but wrong key)
                                                                                                 ──WIRED──> record_epistemic_belief ──WIRED──> SQLite ──WIRED (narrow traffic)──> _epistemic_penalty ──WIRED──> score multiplier

Agent death (any path)   ──WIRED──> AgentBase.die() ──WIRED──> deregister() ──BROKEN (100% of the time — §13, type mismatch)──> spawn_successor() reconstruction
                                                                              ──WIRED (fallback)──> bare AgentBase, capabilities preserved, class/behavior lost
                                                                              ──WIRED──> inherit_ghost() sets lessons/best_decisions/traits
                                                                              ──DEAD (get_system_prompt() never called in production, §7/§13)──> ✗ no behavioral effect
```

## 16. Where the Learning Loop Breaks

Ranked by how much real signal is lost at each break:

1. **`PolicyMemory` hash-format mismatch** (§9) — loses the single richest
   real-outcome reward signal in the codebase (the 5-factor formula with
   real user feedback). **Single biggest missing link in the entire
   subsystem** (see Final Verdict §9).
2. **`spawn_successor()` dict/attribute type mismatch** (§13) — loses class
   identity and behavioral continuity on every agent death, unconditionally.
3. **`get_system_prompt()` never called in production** (§7/§13) — loses
   the one mechanism that would make ghost-memory inheritance behaviorally
   real rather than archival.
4. **Hands' `PolicyMemory`/`reasoning_chains` writes have no reader at all**
   (§9) — not a bug in the traditional sense (nothing is mismatched — there
   simply is no consumer), but it means Task 79's "diverse policy reward
   histories" for `researcher`/`collector`/`trader` are pure, currently-
   inert storage.
5. **`CounterfactualMemory` and `EpistemicTracker` are unreachable from
   Hands and governor-only dispatches** (§7/§10/§12) — the two richest
   safety/calibration mechanisms in the codebase only ever see the narrow
   slice of traffic that flows through `DecisionEngine.evaluate()` AND
   survives to a real outcome.

## 17. Real Bugs Discovered

**Not fixed, per task instruction.**

1. **`SAFETY-RELEVANT`**: none discovered in this trace beyond what Task 79
   already found (subconscious_loop signature bug, prior successor-
   reconstruction observation). Nothing found here rises to a safety
   concern — the successor-reconstruction failure degrades capability, it
   does not create an unauthorized action pathway (the fallback bare
   `AgentBase` still goes through the same `Governor.dispatch()`/HP/
   permission machinery).
2. **`COGNITIVE/LEARNING LIMITATION`**:
   - The `PolicyMemory` hash-format mismatch (§9) — three of four real-
     outcome writers use `json.dumps(sort_keys=True)`, the reader uses
     `sorted(dict.items())`.
   - `get_system_prompt()` (ghost-memory-to-prompt bridge) has zero
     production callers.
   - Hands' `PolicyMemory`/`reasoning_chains` writes have no reader.
3. **`RELIABILITY`**:
   - `EvolutionEngine.spawn_successor()`'s return-type contract
     (`-> dict`) does not match its caller's usage
     (`agent_registry.py`'s attribute access) — this is the precise,
     source-confirmed root cause of the successor-reconstruction failure
     Task 79 observed live, and it is **deterministic (100% of deaths)**,
     not intermittent.
   - Double HP award for Hand-dispatched work (governor's own RULE-9 award
     plus `HandRunner._award_hp()`'s independent award for the same
     outcome) — not confirmed intentional.
   - The fallback path's own log message ("no capabilities") does not
     match the fallback code's actual behavior (capabilities ARE carried
     through, `agent_registry.py:171`) — a stale/inaccurate log string, not
     a functional bug.
4. **`EXPERIMENT-RELEVANT`**: the `PolicyMemory` hash mismatch and the
   successor-reconstruction failure are both directly relevant to
   interpreting Segment 2's Day-7 results — any Day-7 conclusion of "no
   learning happened" for the diverse action types Task 79 found must be
   read as "no learning happened *because the read path is broken*," not
   "the architecture was exercised and failed to adapt."
5. **`PERFORMANCE`**: none identified in this trace's scope.
6. **`COSMETIC/DOCUMENTATION`**: the stale fallback log message (above).

Per task instruction, the two previously-known bugs (subconscious_loop
signature defect, agent successor reconstruction) were **not** re-
investigated beyond what was directly necessary to understand the learning
architecture — the successor-reconstruction root cause above was found as a
direct, unavoidable byproduct of tracing ghost-memory causality (§13), not
as separate rediscovery work.

## 18. What Task 79's Live Evidence Can and Cannot Mean

- Task 79's **diverse `PolicyMemory` reward histories** for `git_status`,
  `trader`, `researcher`, `collector`, `commit_code` (12–118 samples, real
  varied `avg_reward` values) **can** mean: real, differentiated task
  outcomes are genuinely occurring and genuinely being recorded. They
  **cannot** mean: this diversity has ever influenced, or ever could
  influence, a future `DecisionEngine` scoring pass for the *same* Hand-name
  action type, because no code path reads a `hand:<name>`-keyed row back
  (§9). For `git_status`/`commit_code`/`set_reminder`/`check_attendance`/
  `research_topic` specifically, this trace did not conclusively identify
  their write source (plausibly `api/crud.py`'s generic `update_policy()`,
  reachable from an owner/MCP-triggered API route, or a VectorCode/plan-step
  write using the mismatched hash) — flagged as unresolved rather than
  guessed.
- Task 79's **8,569 `governor_dispatch` events** and **3,731 telemetry-
  autonomous inference calls** **can** mean: the system is doing real,
  voluminous, genuinely autonomous work. They **cannot** mean: that work is
  adapting based on past outcomes beyond the one real HP-based agent-
  selection loop (§8) — volume and diversity of *activity* is not evidence
  of *learning*, and this trace found no mechanism by which the bulk of
  that activity (Hand dispatches, most governor-only dispatches) could
  learn even in principle, independent of whether it currently does.
- The **real agent death Task 79 observed live** **can** mean: the
  Darwinian HP mechanic is functioning exactly as designed up to and
  including triggering succession. It **cannot** mean: the successor
  inherited anything behaviorally meaningful — §13 establishes the
  reconstruction step fails deterministically and the archival-only ghost
  data would not have mattered even had it succeeded.

## 19. Post-Day-7 Engineering Priorities

Not implemented in this task, listed for the post-experiment backlog:

1. **Fix the `PolicyMemory` situation-hash format mismatch** — make all
   writers use `DecisionEngine._make_situation_hash()`'s exact formula (or
   centralize the hash computation in one shared function all four call
   sites and `PolicyMemory` itself import, eliminating the possibility of
   drift entirely). This single fix reconnects the richest existing reward
   signal in the codebase to the scorer with no new design work required.
2. **Fix `EvolutionEngine.spawn_successor()`'s return type** (or its
   caller's usage) so successor reconstruction stops failing
   deterministically.
3. **Either wire `AgentBase.get_system_prompt()` into a real district
   agent's LLM call path, or remove it** — currently dead, misleading code
   that looks like a working feature.
4. **Decide deliberately whether Hands should participate in
   `DecisionEngine`/`CounterfactualMemory`/`EpistemicTracker` at all** —
   currently they structurally cannot, which may be an intentional
   architecture boundary (cron-scheduled utility work vs. goal-driven
   candidate competition) or an oversight; this trace cannot determine
   intent, only structure.
5. **Resolve the double-HP-award question** for Hand-dispatched work
   (§5/§17) — confirm intentional or fix.

## 20. Final Verdict

1. **Is this subsystem genuinely autonomous?** Yes — scheduled/triggered
   without owner input, executing real work through a real permission-gated
   dispatch hub, confirmed by direct source trace (§2–§4).
2. **Is it genuinely adaptive?** Only in one narrow respect: which agent
   instance handles a given district's work shifts over time based on HP
   (§8). No other adaptive behavior was found with a complete causal path.
3. **Does it genuinely learn?** Not in the sense of "stored experience
   changes future scoring/behavior" — that chain is broken or absent for
   every memory-based mechanism traced (§9, §14).
4. **What is the highest defensible learning level?** **L4 (behavioral
   adaptation)**, and only for the Agent-HP → agent-selection mechanism.
   Every memory-based mechanism tops out at **L3 (persistent state)** with
   a broken or missing L1/L2 step.
5. **Which persistent state actually influences future behavior?**
   `Agent.health_points`, read by `Governor.dispatch()`'s and
   `HandRunner._award_hp()`'s `max(agents, key=lambda a: a.health_points)`.
   That is the complete list found in this trace.
6. **Which memories are merely logs?** `EpisodicMemory` (all writers),
   `reasoning_chains` (hand-written entries), ghost `lessons`/
   `best_decisions`, and — for this subsystem specifically — the majority
   of `PolicyMemory` (three of four real writers, plus all Hand writes).
7. **Is there a closed experience→learning→behavior loop?** One, narrowly:
   HP → agent selection. No other complete loop was found.
8. **Can Darwinian agent replacement transmit learned behavior?** No, as
   currently implemented. Reconstruction fails deterministically (§13,
   confirmed root cause), and even on success, the one prompt-injection
   path for inherited lessons is dead code.
9. **What is the single biggest missing link?** The `PolicyMemory`
   situation-hash format mismatch (§9, §16) — it silently disconnects the
   single richest, most genuinely outcome-sensitive reward signal in the
   entire codebase (the real-user-feedback-aware 5-factor formula) from the
   only code that ever reads a policy score. Fixing this one mismatch (not
   done in this task) would do more to enable genuine learning than any
   other single change identified across Tasks 71/72/78/79/80.
10. **What should be changed after the 7-day experiment?** See §19,
    ranked: (1) the `PolicyMemory` hash fix, (2) the `spawn_successor()`
    type-contract fix, (3) either wire or remove `get_system_prompt()`, (4)
    a deliberate design decision on whether Hands should participate in the
    scoring/counterfactual/epistemic machinery, (5) resolve the double-HP-
    award question.

---

## FINAL INTEGRITY CHECK

- Zero production source files modified — this task only created the one
  new Markdown artifact (`VECTOR_TECHNICAL_KNOWLEDGE/80_AUTONOMOUS_AGENTIC_LEARNING_TRACE.md`).
- Zero configuration changes (`.env`, `core/config.py`, or otherwise).
- Zero database changes — no database, production or otherwise, was opened
  at any point in this task (pure static source-code reading only).
- Zero interaction with the running VECTOR process — it was never queried,
  signaled, or connected to.
- Zero experiment stimulus or steering of any kind.
- **Only file created/modified this task**:
  `VECTOR_TECHNICAL_KNOWLEDGE/80_AUTONOMOUS_AGENTIC_LEARNING_TRACE.md`.
