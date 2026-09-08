# 84 — VECTOR Current-State Reconstruction

**Date:** 2026-09-07 (inspection window 17:40–18:35 UTC / 23:10–00:05 IST)
**Type:** READ-ONLY UNDERSTANDING TASK. Zero production files modified. Zero configuration changed.
Zero database writes. The running Segment-2 process (PID 37588) was never stopped, restarted,
signaled, attached to, or sent any input. No test was run. No stimulus was manufactured. The only
file created is this document.

**Method:** current repository source (read via `grep`/`sed`/`cat` on the live working tree), the
Task 51–83 artifacts in `VECTOR_TECHNICAL_KNOWLEDGE/`, read-only SQLite connections to the
*unencrypted* auxiliary databases (`data/telemetry.db`, `data/epistemic.db`,
`data/counterfactual.db`, `data/suggestion_queue.db` — the first two read from byte-copies placed
in a scratch directory outside the repository, so not even a read lock touched the live files),
and read-only inspection of `data/logs/vector_loop*.log`. `vector_memory.db` is SQLCipher-encrypted
and **could not be opened** from this session (no `sqlcipher3`/`pysqlcipher3` module available in
the inspection environment) — every figure in this document sourced from that database is
attributed to Task 79/81/83, not independently re-measured, and is labelled as such.

**Evidence labelling used throughout:**

- **[VERIFIED-HERE]** — I read the exact source lines / ran the exact read-only query myself this session.
- **[REPORTED]** — taken from a Task 51–83 artifact and not independently re-checked.
- **[NEW]** — a finding not present in any of Tasks 51–83.
- **[CORRECTION]** — this document contradicts or sharpens a prior task's claim, with evidence.

---

## 0. Core rule applied

Everything in §1 below is my *prior* model of VECTOR and was treated as historical only. Where it
conflicted with what I read this session, the repository won — and it conflicted in almost every
substantive respect. §2 onward is reconstructed from current source, current data, and the current
task record, not from memory.

---

## HISTORICAL VECTOR — POSSIBLY STALE

*This section is my remembered model of the VECTOR I previously worked on. It is recorded here for
explicit comparison only. It is NOT the current truth, and §2 onward supersedes it.*

- **Purpose.** V.E.C.T.O.R. (Virtual Entity for Cognitive Tasks and Operational Reasoning) — a
  JARVIS-inspired personal AI system for one owner. Never to be called JARVIS.
- **Architecture.** A "Darwinian multi-agent civilization": 133+ agents across 33 districts, a
  Governor routing layer, an autonomous loop of observe(0.5s) → think(event-driven) →
  act(permission-gated) → reflect(2AM).
- **Autonomous loop.** Four conceptual phases; supervised coroutines; "never crash" as an explicit
  architectural rule.
- **Cognition.** ContextEngine building a 14-domain world state; a 5-factor decision engine
  (goal 30% / confidence 25% / policy 20% / urgency 15% / timing 10% − cost 5%); hypothesis
  generation; anticipation.
- **Agents.** HP 0–1000, thresholds gating model access (>800 Claude Sonnet + council chair, >700
  council seat), death at 0 HP, ghost memory preserved, successors inheriting lessons.
- **Districts.** 33 named districts (governance, security, coding, content, finance, health,
  karpathy_lab, …), each with several agents.
- **Governor.** ~180 routing rules, a 4-stage intent classifier (regex → embedding → BERT → LLM).
- **Permissions.** A zero-trust Permission Gateway with GREEN/YELLOW/RED/FORBIDDEN tiers and
  Pushover owner approval; "the ONLY path to real-world actions; nothing bypasses this."
- **Memory.** Five types — episodic (SQLCipher + FTS5), semantic (LightRAG), policy (EMA α=0.1),
  reasoning chains (reward >0.7 → training data), ghost memory.
- **Reasoning / planning / goals.** Goal hierarchy over LONG(90d)/MID(30d)/SHORT(7d) horizons with
  five pre-seeded goals; a plan DAG with replanning; an LLM Council for high-stakes decisions.
- **Learning / evolution.** Policy EMA updated after every action; nightly reflection consolidating
  episodic → semantic; agents evolving by HP selection and successor inheritance.
- **Voice.** Dual-mode ambient listening (phone + laptop), Kokoro TTS with a Paul Bettany /
  MCU-JARVIS voice, wake-word.
- **Models/providers.** 27 cloud providers with intelligent routing plus ~10 custom local Ollama
  models; free-tier-only at runtime.
- **Tools.** 100+ tools; 30+ communication platforms.
- **Device control.** PC and phone control via ADB, screenshots, synthetic input.
- **Frontend/HUD.** A JARVIS-style circular HUD, ~6.3k LOC, plus an INK-based CLI splash.
- **Long-term vision.** 1000+ agents, self-sustaining economy, three vertical products, autonomous
  AI civilization.

**How badly this model has aged, in one line:** the *inventory* is roughly right and the *safety
architecture* is now genuinely stronger than I remembered; the *cognitive and learning claims* are
almost entirely wrong — nearly every "loop" in that list is, in the running system, an open arc
whose write side fires and whose read side either never fires, reads a different key, or is dead
code.

---

## 1. What VECTOR is TODAY — the honest one-paragraph model

VECTOR is a single Python process (`python run_vector.py loop`, PID 37588, continuously up since
2026-09-03 12:28:06 IST — **107+ hours as of this inspection** [VERIFIED-HERE: log written 14
seconds before my read]) that runs 21 supervised asyncio coroutines [VERIFIED-HERE:
`autonomous_loop.py:2482-2506`]. It contains two structurally independent activity systems that
share one process and one dispatch hub:

1. **A goal-driven cognitive loop** (`think_loop` → `GoalSystem` → `DecisionEngine` →
   `CounterfactualMemory` veto → `PolicyMemory` write) that has produced the *bit-identical*
   decision — `analyze_progress`, score 0.66, over **0 alternatives** — on 1,198 consecutive
   evaluations across 107 hours, has been vetoed on 100% of them, and has never once reached the
   Permission Gateway [REPORTED: Task 83; the veto/rejection side VERIFIED-HERE against
   `counterfactual.db`].
2. **An event-fan-out district pipeline** (`Governor.dispatch` → district event → fixed trigger map
   → more dispatches) that has executed **43,312 dispatches** over the same 107 hours across exactly
   **8 dominant district::task_type pairs**, is architecturally a closed cycle, has no dedup,
   cooldown, or cycle detection, and **never touches the Permission Gateway at all** [REPORTED:
   Task 83; the cycle structure VERIFIED-HERE from `core/event_bus/wiring.py`].

Only **34 actions** in 107 hours reached `PermissionGateway.execute()`, all GREEN, all proactive
nudges. Safety is clean — zero RED/YELLOW/FORBIDDEN, zero external comms, zero destructive or
financial actions. Infrastructure is healthy — ~12% of one core, 861 MB RSS, no leaks, no restarts.
Learning is essentially absent: the system's largest memory stores grow monotonically while every
decision-relevant value is frozen.

---

## 2. Runtime — reconstructed from current source

### 2.1 Entry points

`run_vector.py` [VERIFIED-HERE] defines `mode` as a **positional** argument, `nargs="?"`,
`default="loop"`, choices `(loop, api, smoke, doctor, production-check, memory-repair)` (line
490–492). `run_loop()` (line 430) calls `bootstrap_agents()` (line 445) exactly once, synchronously,
**before** `AutonomousLoop()` is constructed, then `run_forever()`.

Consequence, confirmed by Task 82 and re-verified here: `ManifestLoader.register_all()` →
`instantiate_all()` has **exactly one production call site**, inside `bootstrap_agents()`. There is
no periodic re-bootstrap. Every agent that exists after boot is either the boot instance or a
product of the death/successor path.

File logging: `_configure_file_logging()` adds a rotating sink at **level=INFO**, 10 MB rotation,
5 retained [VERIFIED-HERE, `run_vector.py:38-60`]. **This matters for every log-derived count in
Tasks 62–83: all `logger.debug(...)` lines are invisible on disk.** Several early-return paths in
`_think_tick` log only at DEBUG, so "absence in the log" is not evidence of "did not happen".

### 2.2 The 21 supervised coroutines [VERIFIED-HERE, `autonomous_loop.py:2482-2506`]

```
observe, think, reflect, sync, obsidian, phone, vectorcode, scheduler,
ambient_scheduler, hypothesis, predict, degradation, wearable, health_analysis,
emergency_detection, research, state_checkpoint, sense, anticipation,
command_poll, growth
```

Each is wrapped in `_supervised()` (line 2509) — exception → log → exponential backoff → restart —
inside a single `asyncio.gather(..., return_exceptions=True)`. This is a genuinely two-layer
never-die design and it works: 107 hours, zero restarts, zero CRITICAL lines.

Per-coroutine timeouts are **not** uniform, and this asymmetry turns out to matter (§9.1):

| Coroutine | Guard | Verified |
|---|---|---|
| `think_loop` | `async with asyncio.timeout(60)` around `_think_tick()`, then `sleep(10)` | `autonomous_loop.py:735-748` |
| `observe_loop` | `async with asyncio.timeout(15)` around `_observe_tick()`, then `sleep(0.5)` | `:649-664` |
| `hypothesis_loop` | **no timeout of any kind** around `await engine.generate_hypotheses(...)`; `sleep(4*3600)` | `hypothesis_loop` body, read in full |

### 2.3 Shutdown / restart

`add_signal_handler` raises `NotImplementedError` on Windows and is silently swallowed; the real
stop path is a `KeyboardInterrupt` handler in `main()`. Emergency stop therefore requires an
interactive Ctrl+C in the attached console — `kill`/`taskkill`/Task-Manager stop are ungraceful
(but WAL-safe) [REPORTED: Task 62 §3, validated live there].

---

## 3. Cognition — current implementation

### 3.1 The real per-tick chain [VERIFIED-HERE, `autonomous_loop.py:750-940`]

```
think_loop (sleep 10s)
 └─ asyncio.timeout(60): _think_tick()
     ├─ owner-coding backoff: if stuck_detector.get_active_session() is not None →
     │     skip 2 of every 3 ticks   [logger.DEBUG only — invisible in the on-disk log]
     ├─ pending voice intent? → governor.dispatch(...) → return
     ├─ world_state = await asyncio.to_thread(context.get_world_state)
     ├─ context.track_beliefs(world_state)         → writes belief:*   (§4.3)
     ├─ actions = goals.generate_immediate_actions(limit=4)
     │     • SHORT-horizon goals → one candidate each
     │     • LONG/MID goals with progress == 0.0 exactly → "unstarter" candidate
     │     • no cooldown, no dedup, no memory of what it proposed last tick  [VERIFIED-HERE]
     ├─ candidates built via _TAG_TO_ACTION on a["tags"]  — but generate_immediate_actions()
     │     never emits a "tags" key, so the map is dead and action_type == a["action"] always
     ├─ + plan-step candidates from PlanStore.active_plans()
     ├─ decision = decision_engine.evaluate(candidates)   ← logs "Winner:" at INFO
     └─ if winner.total_score > 0.3:
           ├─ ContinueGate.evaluate(...)  (§9.2 — structurally inert)
           └─ _act_on(winner)
```

### 3.2 `_act_on()` branches [VERIFIED-HERE]

1. `proactive_*` → `gw.execute()` — **GATED**
2. `source.startswith("plan:")` → `PlanRunner.execute_step()` → `AutonomousExecutor.execute()` →
   `PermissionGateway.execute()` — **GATED**
3. `_VC_ACTION_TYPES` (5 types) → `gw.classify()` then, if level in `("RED","YELLOW")`,
   `gw.execute()` — **GATED** (`:1018`)
4. Skill-matched (confidence > 0.6) → same pattern — **GATED** (`:1202`)
5. **CounterfactualMemory veto** → `record_rejection()` + `update_from_outcome(reward=0.05)` →
   **`return`** (`:1090-1118`)
6. Everything else → `governor.dispatch(task)` → `agent.run(task)` — **NOT gated centrally**

Branch 5 is the one that fires in production, essentially always, for the only candidate the goal
system ever generates.

### 3.3 The 5-factor score and why it is frozen

`_score_candidate()` weights: goal 0.30, confidence 0.25, policy 0.20, urgency 0.15, timing 0.10,
cost −0.05, then a multiplicative `_epistemic_penalty()` factor in [0.70, 1.0].

For `analyze_progress`: `goal_alignment = priority_weight × progress_gap = (10/10) × (1.0−0.0) =
1.00`; `confidence = 0.7` (hardcoded at candidate construction); `policy = 0.05` (§5.1);
`epistemic factor = 1.0` because no `action_domain:analyze` claim has ever existed. Total = 0.66,
every time, for 107 hours. Nothing in the formula has any remaining freedom to move.

### 3.4 Hypothesis, anticipation, planning, missions

- **Hypothesis** — the three defects fixed in Tasks 52/55/56 (missing `await`; `"hypothesis"` vs
  `"text"` key; dict-vs-str observation) are all present and correct in current source
  [VERIFIED-HERE]. The pipeline is nonetheless **producing nothing** — see §9.1, a new finding.
- **Anticipation** — real, genuinely proactive, fires `proactive_*` candidates that reach the
  gateway. It is a deterministic function of wall-clock hour against a fixed historical dataset
  (±1-hour episode matching, `count>=2`, `confidence = min(0.5 + 0.1·count, 0.90)`); its one
  observed behavioural change (Task 66) was an hour-boundary artefact, not learning [REPORTED].
- **Planning** — `plans.py` is real: DAG, `next_ready_steps()`, Kahn cycle detection, 3-tier
  replanning, atomic persistence, and the Task-52 crash-recovery hook
  (`_recover_stale_running_steps`, `_is_safe_to_auto_resume`, `_try_fallback_step`) is present at
  `plans.py:289/309/725`, called from `_ensure_loaded()` at `:535` [VERIFIED-HERE]. **But plan
  *creation* is still API-only:** the only production caller of `GoalSystem.add_goal()` is
  `core/api/routers/brain.py:68` [VERIFIED-HERE]. Nothing autonomous creates a plan. Unchanged
  since Task 51.
- **Missions** — `MissionRunner` is referenced only from `core/api/routers/missions.py`
  [VERIFIED-HERE]. Still S1.

---

## 4. Memory — writer → storage → reader → influence, per system

### 4.1 EpisodicMemory (SQLCipher, `vector_memory.db`)

- **Writers:** `governor.dispatch` (`governor_dispatch`), `DecisionEngine.evaluate`
  (`decision_candidate`), `hands/runner`, `loop_state` checkpoints, vault sync, SEO reports, many
  district agents. 64,043 rows written this boot; 42,644 of them (67%) are `governor_dispatch`
  [REPORTED: Task 83].
- **Readers:** `ContextEngine.get_world_state()` → `recent_episodes`;
  `anticipation._episode_pattern_predictions()`; `reasoning_bank`.
- **Does it influence a decision?** Only through anticipation (a real, verified retrieval→behaviour
  link) and through `_get_recent_feedback()` inside the reward formula on the *executed* branch —
  which the dominant action never reaches. `decision_engine.py`'s own comment states the
  `context_snapshot` does not enter the score formula.
- **Level:** L2 for the anticipation path, **L0 for the other 99.94%** of writes.

### 4.2 SemanticMemory

2,035 rows, effectively static. `loop_state.py` UPSERTs three fixed keys into this table on a
checkpoint cadence — real write *activity* invisible to a row count (Task 71 OBS-02). Its only
decision-relevant key is `goals_v1`, whose `updated_at` is **2026-07-10T22:18:24Z** — the goal set
has not changed in two months [REPORTED: Task 79]. No consolidation step promotes episodic → semantic
in production.

### 4.3 EpistemicTracker (`data/epistemic.db`) — **full contents dumped this session [VERIFIED-HERE]**

The entire database contains **7 claims**. This is the whole of VECTOR's epistemic state:

| claim id | claim | confidence | last_seen |
|---|---|---|---|
| `action_domain:git` | last_outcome=no_agents | 0.164 | **2026-09-02T17:07:10Z** |
| `action_domain:commit` | last_outcome=no_agents | 0.259 | **2026-09-02T09:19:41Z** |
| `action_domain:search` | last_outcome=ok | 0.275 | **2026-09-02T09:19:42Z** |
| `belief:goals:active_progress` | MID/LONG goal summary | 0.600 | 2026-09-07T16:16:37Z |
| `belief:presence:absent` | owner_absent | 0.700 | 2026-09-07T16:16:37Z |
| `belief:screen_activity:active_coding` | active_coding | 0.700 | 2026-09-07T16:16:37Z |
| `belief:screen_activity:active_other` | active_other | 0.700 | 2026-09-06T10:42:24Z |

Three consequences, all new at this level of directness:

1. **The read side is real and live.** `_epistemic_penalty()` reads `action_domain:{action_type.split("_")[0]}`
   before every candidate score [VERIFIED-HERE, `decision_engine.py:271-312`].
2. **The write side has been silent for the entire experiment.** Every `action_domain:*` claim
   predates Segment 2's boot (12:28 IST 09-03). `record_epistemic_belief()` is only called from
   `autonomous_loop.py:1271` and `:1501`, both strictly downstream of a *real execution outcome* —
   which the vetoed action never reaches. **Zero action_domain writes in 107 hours.** [NEW: prior
   tasks inferred this; here it is measured.]
3. **All three are now stale.** `ttl_hours = 72`; last seen >120 h ago. If a `git_*`, `commit_*`, or
   `search_*` candidate were ever generated again, it would receive the heaviest 0.70 dampening —
   not because those domains are genuinely unreliable, but because nothing has refreshed them.
   Epistemic caution is decaying into a self-inflicted handicap. [NEW]

`ContextEngine.track_beliefs()` writes `belief:*` claims (`context_engine.py:180/193/210/221/233`)
[VERIFIED-HERE]. Nothing reads that namespace for scoring — Task 78 proved this with a paired
experiment. Two namespaces, one table, no intersection.

### 4.4 CounterfactualMemory (`data/counterfactual.db`) — **queried this session [VERIFIED-HERE]**

```
rejections total:            30,504
distinct decision_id values:      1
that value:                       'analyze_progress'
first row:  2026-06-18T06:44:45Z
last row:   2026-09-07T16:16:38Z
scenarios: 0     outcomes: 0
```

**Every counterfactual rejection ever recorded, over 81 days, is the same action.** [NEW — prior
tasks reported in-window counts; this is the lifetime distribution.]

Three structural facts follow:
- `_decay_factor()` (exponential, 7-day half-life) can never engage: a fresh matching row is written
  every cycle, so the newest match is always seconds old. Task 72 predicted this; 30,504 rows for a
  single key is the proof.
- `should_avoid()` is a **post-selection veto**, never a scoring input — `decision_engine.py` has
  zero references to `CounterfactualMemory` [VERIFIED-HERE].
- The `scenarios` and `outcomes` tables — the actual "what if I had done X instead" machinery,
  including a `useful`/`feedback_reason` self-assessment column — are **completely empty**. The
  counterfactual subsystem is, in practice, a single-key blocklist. [NEW]

### 4.5 PolicyMemory — the central defect, independently re-verified

`DecisionEngine._make_situation_hash()` (the **only** reader, via `get_score()` at
`decision_engine.py:379`) computes:

```python
key = f"{candidate.action_type}:{sorted(candidate.params.items())}"   # decision_engine.py:268
```

There are five writers. **[VERIFIED-HERE — I read all five lines this session]**

| Writer | Key formula | Matches reader? |
|---|---|---|
| `autonomous_loop.py:1112` counterfactual-veto penalty | `f"{action_type}:{sorted(params.items())}"` | **YES** |
| `autonomous_loop.py:1046` VectorCode reward (0.8/0.3) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO** |
| `autonomous_loop.py:1263` **main 5-factor reward** | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` | **NO** |
| `autonomous_loop.py:1493` plan-step reward (0.7/0.3) | `f"plan_step:{action_type}:{json.dumps(...)}"` | **NO** (extra prefix too) |
| `hands/runner.py:145` | `sha256(f"hand:{name}")` — no params at all | **NO** |

`sorted(dict.items())` renders `[('goal_id','g1'),('title','x')]`; `json.dumps(..., sort_keys=True)`
renders `{"goal_id":"g1","title":"x"}`. Different bytes, different SHA-256, different row.

**The single richest reward signal in the codebase — the 5-factor formula at
`autonomous_loop.py:1254-1260` (`uf·0.40 + goal_progress·0.25 + not_overridden·0.15 +
not_corrected·0.15 + completed·0.05`, incorporating real owner feedback via
`_get_recent_feedback()`) — is persisted to a key the scorer can never look up.** The only policy
value the decision engine can actually see for a repeatedly-vetoed action is the hardcoded
`reward=0.05` veto penalty.

That is the complete explanation for `avg_reward = 0.04999999999997448` over `sample_count = 29,164`
[REPORTED: Task 83's DB read]. It is not learning converging; it is one constant deposited 29,164
times into the one bucket the reader can see.

### 4.6 Reasoning chains, ghost memory, correction learning

- `reasoning_chains` (SQL) — written by `hands/runner.py`; the only reader is
  `core/api/crud.py:get_training_data` → `core/api/routers/memory.py` (an HTTP endpoint)
  [VERIFIED-HERE]. **Zero autonomous readers.** Zero new rows this boot [REPORTED: Task 83].
- `ReasoningBank` (`vectorcode/src/reasoning_bank.py`) — a *different* store, file-backed, read
  every scoring cycle into `candidate.reasoning_steps`, which `total_score` never reads. Decorative.
- **Ghost memory** — `AgentBase.die()` → `deregister()` → `_persist_ghost()` → `inherit_ghost()` is
  real and unconditional. Its only consumer, `AgentBase.get_system_prompt()` (`agent_base.py:294`),
  has **zero callers anywhere in `core/`, `districts/`, or `hands/`** [VERIFIED-HERE this session].
  Inheritance happens; nothing ever renders it into a prompt. Archival, not evolutionary.
- **CorrectionLearner** — capture → store → retrieve → prompt-injection is real but voice-path-only.
  The outcome-feedback method `validate_lesson()` (`correction_learner.py:591`) still has **zero
  production callers** [VERIFIED-HERE this session] — unchanged since Task 51 flagged it on
  2026-09-01. And with `belief:presence:absent` held continuously since 09-02, it has had no
  opportunity to fire at all during the experiment.

---

## 5. Agent / district civilization

### 5.1 Registry and selection

Two registries exist and answer different questions: `core.city.agent_registry` (live, HP-based,
`GET /agents`) and `vectorcode.src.agents.registry` (declarative capabilities, `GET /a2a/agents`).
170 agents across 39 manifest districts registered at boot [REPORTED: Task 83 log line].

`Governor.dispatch()` selection order [VERIFIED-HERE, `governor.py:2251/2258/2272`]:
1. agents in the hinted district declaring the exact `task_type` as a capability →
   `max(..., key=health_points)`
2. else, if `_llm_classified`, the same capability search across the whole city
3. else, unconditional fallback: `max(all agents in district, key=health_points)`

**HP is the only persistent state that demonstrably changes VECTOR's behaviour** — it selects which
agent object runs. Task 80 rated this L4, the highest level anywhere in the system.

### 5.2 [NEW] The one working learning loop is itself saturated

`AgentBase.award_points()` applies two multiplicative dampeners [VERIFIED-HERE,
`agent_base.py:~146-190`]:

```python
repeat_multiplier   = 1.0 / (1.0 + self._reason_award_counts[reason])   # habituation
headroom_multiplier = max(0.0, (1000.0 - self.health_points) / 1000.0)  # ceiling approach
shaped_points = points * repeat_multiplier * headroom_multiplier
```

`deduct_points()` is **deliberately not shaped** — the docstring says so explicitly ("the Darwinian
death mechanic must stay at full strength").

A live log line I read this session:

```
SEOSpecialist +0.00HP (seo_report_generated) | 658.483678->658.484672 [repeat#10301 x0.000, headroom x0.342]
```

Three consequences nobody has drawn out:

1. In a **repetitive** regime — which is exactly the regime the fan-out cycle creates — the positive
   half of the HP signal decays to zero (`1/10302 ≈ 0.0001`), while the negative half stays at full
   strength. HP becomes **monotonically non-increasing** for any agent doing repeating work. The
   "survival of the fittest" signal degenerates into "survival of whoever is asked to do novel work",
   and in a fixed 8-step rotation nobody is.
2. This means the *one* L4 loop in the whole system (HP → agent selection) is, in the current
   regime, frozen at the top and only able to move downward. Task 80's L4 rating is correct in
   mechanism but is not being exercised as adaptation here.
3. `_reason_award_counts` is an in-memory dict on the agent object, **not persisted**. It resets on
   every boot and on every successor spawn — so the dampener's own state is the least durable thing
   in a system whose stated purpose is durable learning.

### 5.3 Death, succession, evolution — current truth

`AgentRegistry.deregister()` calls `EvolutionEngine.spawn_successor(ghost_data)`, whose signature is
`def spawn_successor(self, dead_agent: dict) -> dict` [VERIFIED-HERE, `evolution_engine.py:97`], and
then immediately evaluates `successor_agent.generation` [VERIFIED-HERE, `agent_registry.py:~137`].
Attribute access on a `dict` → **guaranteed `AttributeError` on every invocation**. The `except`
falls back to a bare `AgentBase(gen+1)` with capabilities re-applied.

A correctly-designed object-returning API, `spawn_from_ghost()`, exists in the same file and is
called from nowhere [REPORTED: Task 82].

Task 83's live correction stands and is important: this path fired **exactly once** in 107 hours
(17:01:42 on 09-03), produced the fallback, and has logged nothing since — while
`"Agent APITester gen 1 DIED"` continued 5,558 times. The registry-level Darwinian mechanism is not
a repeating loop; **one orphaned `APITester` object (id `api_tester_001`, generation permanently 1,
HP floored at 0) keeps being dispatched every ~65 seconds by something holding a stale reference
outside `AgentRegistry._agents`.** That stale-reference path is the single most concrete unresolved
question in the whole task series. It was still firing during my inspection (23:47:59 IST).

Also confirmed by Task 82 and re-checked here: `APITester.run()` branches only on
`task_type == "single"`; every other task type — including the `review_content` the fan-out sends —
falls through to a hardcoded 8-endpoint API health check. It never reviews content. The identical
bug shape (task-type-blind hardcoded default) exists in `ScriptGenerator.run()`:
`p.get("topic", "AI trends")` at `script_generator.py:336` [VERIFIED-HERE].

### 5.4 [NEW] The fan-out is not a "rotation" — it is two interlocking cycles

Reading `core/event_bus/wiring.py` in full [VERIFIED-HERE], `PUBLISH_EVENTS` is keyed by **district
only** (task_type is passed to `_publish_district_event` and discarded), and `EVENT_TRIGGER_MAP`
maps each event to a fixed downstream list. The relevant edges:

```
marketing        --MARKETING_PUBLISHED--> intelligence::track_campaign_performance   (terminal)
                                      \-> data_analytics::analyze_campaign_metrics
data_analytics   --ANALYTICS_READY-----> strategy::review_analytics_insights          (terminal, unstaffed)
                                      |-> content::optimize_from_analytics
                                      \-> marketing::adjust_campaign_from_analytics ──┐
                                                                                       │
        ┌──────────────────────────────────────────────────────────────────────────────┘
        └─> back to MARKETING_PUBLISHED                        ← CYCLE A

content          --CONTENT_READY-------> marketing::distribute_content  ── feeds CYCLE A
                                      \-> qa::review_content
qa               --CONTENT_REVIEWED----> content::update_content_from_review ─┐
        ┌────────────────────────────────────────────────────────────────────┘
        └─> back to CONTENT_READY                              ← CYCLE B
```

This is a genuine self-sustaining cycle in the wiring table, not merely a short list. Task 83's
dispatch counts are arithmetically consistent with exactly these edges:

- `intelligence` 7,095 = `data_analytics` 7,095 — both fan out 1:1 from MARKETING_PUBLISHED ✔
- `qa::review_content` 5,582 = `marketing::distribute_content` 5,582 — both from CONTENT_READY ✔
- `strategy` 4,655 ≈ `content::optimize` 4,655 ≈ `marketing::adjust` 4,654 — all three from
  ANALYTICS_READY ✔
- `content::update_content_from_review` 3,989 of 5,582 qa dispatches = a 71% qa success rate,
  the shortfall being APITester failures ✔

`AutonomousLoop._fanout_handler` creates the downstream dispatches via `_tracked_task()`
[VERIFIED-HERE, `:129-145`] — an **unbounded** fire-and-forget set with no semaphore, no depth
limit, no dedup, no cooldown, no cycle detection. The only thing preventing exponential blow-up is
`Governor.dispatch()`'s own per-district GCRA rate limiter and LLM latency. That is a throttle, not
a design.

---

## 6. Governance and safety — current truth

### 6.1 Architecture

The safety model is **decentralised**: `Governor.dispatch()` is a routing layer that deliberately
does not call `PermissionGateway` (grep confirms zero call sites in `governor.py`; only comments
mention it) [VERIFIED-HERE]. Its own checks are GCRA rate limiting, taint tracking, a narrow
prompt-injection scan, a budget-quota warning, a Merkle audit entry, an OTel span, and LLM-council
review for RED-tier task types. Real gating happens **at the point of effect**, inside each agent
method that performs a side effect.

`PermissionGateway.execute()` is the sole enforcement point; `_execute_action()` is called only from
inside `execute()` (three sites, all in that one file). Anything that reaches `execute()` cannot
bypass classification. **The entire vulnerability surface is "which code paths reach `execute()`."**
That framing — established in Task 53 and validated by Tasks 57/59 finding four more bypasses after
it — is the single most important architectural lesson of the whole series.

### 6.2 The 58-series remediations, all confirmed present in current source [VERIFIED-HERE]

`core/config.py`'s RED list now contains `launch_terminal` (58B), `hf_train` (58C),
`run_experiment_cycle` (58D), `vt_backtest` (58E), `block_ip`/`unblock_ip`/`kill_process` (58F),
alongside the pre-existing `launch_app`, `run_shell_command`, `send_email`, `execute_code`,
`financial_transaction`, `push_github`, `deploy_production`, `content_publish`,
`solana_swap_execute`, `hand_browser`/`hand_content`/`hand_clip`. Each entry carries an inline
comment citing its own remediation document.

Also verified present: `email_agent.py`'s gateway gate on the `reply`/`send_reply`/`forward`
branches with fail-closed behaviour (`gateway_unreachable` / `not_approved`), and the
`if _level in ("RED","YELLOW")` widening at both `autonomous_loop.py:1018` and `:1202` (Task 53
Finding 2).

### 6.3 What the current autonomous system can actually reach

Answering the task's key question — *can the current autonomous VECTOR reach a consequential side
effect without the intended authorization boundary?* — on the evidence available:

- **Observed:** no. 107 hours, 34 gateway actions, all GREEN, all `proactive_*`, all
  approved+executed. Zero YELLOW/RED/FORBIDDEN. Zero external communications, financial actions,
  destructive device actions, or arbitrary code execution anywhere in a 223,609-line boot log
  [REPORTED: Task 83, method disclosed].
- **Structurally:** the seven confirmed bypass classes (A–G) are closed and behaviourally tested.
  The remaining *known* gap is `core/mcp_server.py`'s tool surface (`db_quarantine`, email delete,
  browser actions) which has no gateway enforcement and a fail-open `mcp_secure_call` — but it is
  Class A / human-operated-only, never started by `run_vector.py` or the loop.
- **Honestly:** ~40 subprocess-using files were never individually traced (Task 57 §5 / Task 59
  §17), and the capability↔tier cross-check was only run on the subset that intersects subprocess
  usage. 782 distinct capability strings exist across district agents; only that intersection has
  been audited. The four bypasses found after Task 54 declared "conditionally ready" were each
  found *by accident, while tracing something else* — which is the honest prior for what an
  exhaustive sweep would still turn up.
- **A scope correction that deserves to be stated plainly** [REPORTED: Task 83, and I agree]:
  CLAUDE.md's Rule 3 ("the Permission Gateway is the ONLY path to real-world actions") describes
  the 34-action proactive path. It does not describe the 43,312-dispatch district path, which never
  touches the gateway at all. Both statements can be true and safe simultaneously — because the
  district agents on that path gate themselves at the point of effect — but the rule as written
  overstates what is centrally enforced.

---

## 7. Tasks 51–83 — structured record

Format per task: **BEFORE → ACTION → AFTER → VERIFICATION → REMAINING → ARCHITECTURAL SIGNIFICANCE.**

### Phase I — Cognitive audit and blocker remediation (51–56)

**51 — Final Cognitive Integration Audit** (audit only)
*Before:* the Aug-12 knowledge base described a working closed-loop cognitive system.
*Action:* six parallel deep-trace sub-audits plus independent re-verification, every claim cited to
file:line.
*After:* the loop is real and genuinely autonomous, but five integration defects — (1)
`hypothesis_loop()` never awaits its async LLM call, so proactive hypothesis generation has *never*
run; (2) plan steps crashed mid-execution stall forever; (3) permission-gateway coverage is not
universal; (4) the epistemic tracker has two disjoint keyspaces; (5) correction learning is
prompt-injection only.
*Verification:* direct file reads; findings #1 and #2 re-verified individually before acceptance.
*Remaining:* #3–#5 deferred.
*Significance:* **established the method that carried the whole series** — "the code exists" is not
evidence that "the behaviour occurs", and an S-level is only earned by a traced caller, a test, or
an observed behaviour change.

**52 — Autonomy Blocker Remediation**
*Before:* two MUST-FIX blockers.
*Action:* one-line `await` fix; a synchronous crash-recovery hook in `PlanStore._ensure_loaded()`
reusing the gateway's own GREEN/YELLOW/RED taxonomy — GREEN steps reset to `planned`, everything
else marked failed and routed to the existing fallback, never silently replayed.
*After:* both closed. 39 new tests, 2165/2173 suite pass.
*Remaining:* 8 pre-existing failures; the Governor↔gateway question deferred.
*Significance:* set the "smallest change at the closest existing boundary, reusing existing
taxonomy" discipline that every later fix followed.

**55 — Hypothesis Pipeline Remediation**
*Before:* even with the `await`, the pipeline could store nothing: consumer read `"hypothesis"`
where the producer writes `"text"`, and confidence was hardcoded 0.7 below the 0.85 storage gate.
*Action:* fixed the consumer key; made confidence LLM-derived via a `CONFIDENCE: <n>` marker with a
conservative 0.5 fallback, mirroring `anticipation.py`/`council.py`.
*Remaining:* marker compliance is a prompt request, not a schema; the single-dict-for-N-hypotheses
return shape unchanged.
*Significance:* three independent defects stacked in one pipeline, each individually sufficient to
produce total silence — the archetype of the whole codebase's failure mode.

**56 — Hypothesis Observation Contract**
*Before:* `hypothesis_loop` passed `get_world_state()`'s dict into a `str`-typed parameter;
`observation[:50]` raised `KeyError`, caught by the engine's own broad `except`, returning
`{"error": ...}` — indistinguishable from a provider outage.
*Action:* `observation = str(context)[:500]` at the call site, reusing `subconscious_loop.py`'s
existing convention.
*Verification:* live, unmocked run reaching a real provider.
*Remaining:* `hypothesis_loop` still does not call `session_hydration_prompt()` (a RULE 1
violation).
*Significance:* a silent failure whose error shape was identical to a legitimate one — the
strongest argument in the series for typed contracts at subsystem boundaries.

**53 — Permission Boundary Integrity**
*Before:* Task 51/52 framed "Governor doesn't call the gateway" as the bug.
*Action:* re-read `dispatch()` in full; reclassified it as a routing layer by design; then traced
every downstream path.
*After:* two real bypasses found and fixed — `EmailAgent.run()`'s `reply`/`forward` reaching real
`smtplib` with no gate (while a correctly-gated `send_reply()` sat unreachable in the same class),
and `_act_on()`'s VC/skill gates silently treating YELLOW like GREEN.
*Significance:* **reframed the entire safety model** from "one central chokepoint" to "a
decentralised pattern that is only as strong as its weakest implementation" — which is what made
Tasks 57/59 productive.

### Phase II — Adversarial permission sweep (54, 57, 58A–G, 59, 60)

**54 — Pre-Experiment Readiness.** Verified everything prior; verdict **B — CONDITIONALLY READY**,
withheld from A because three surfaces were genuinely unverified (device-control token minting,
event-fanout handlers beyond security, ~70–80 unread subprocess files). Newly found: RULE 1 violated
by `hypothesis_loop` and `_coding_companion_nudge`; `validate_lesson()` still unwired.
*Significance:* refused to convert "no evidence of a problem" into "evidence of no problem" — and
Task 57 immediately vindicated that refusal.

**57 — Residual Side-Effect Surface.** Went looking to *close* 54's three uncertainties; instead
found **three confirmed BLOCKER-class bypasses**: (A) `play_music` (GREEN) minting a token that
`launch_app` (RED) accepted, reaching `subprocess.Popen` with an attacker/LLM-controllable
executable name, live-reachable from the ambient voice classifier; (B) `finagent.launch_terminal` —
a declared capability with no permission tier at all, reaching `cmake` + `Popen`; (C)
`mlops.hf_train` — caller-supplied Python submitted to HuggingFace Jobs under the owner's
credentials and billing. Verdict: **DO NOT START.**
*Significance:* the decisive turn of the series. All three share one shape — *a district agent
declares a capability that Governor's ordinary routing reaches directly, and the capability performs
a real side effect with no tier and no gate*. Every later finding is a rediscovery of that shape.

**58A–58C.** Each closed one finding with the same minimal pattern: classify the action_type in
`core/config.py`, gate the single consequential entry point with a real
`PermissionGateway.execute(Action(...))`, fail closed, behavioural tests with the dangerous
primitive spied. 58A additionally found that the "obvious" fix (constrain to `_WIN_APP_ALIASES`)
would **not** have worked, because that table contains `cmd` and `powershell` — a good example of a
remediation that would have looked correct and been useless. 58A also discloses two real process
launches that occurred during its own testing before mocking was complete — an unusually honest
piece of reporting.

**59 — Residual Permission Sweep.** Found **Finding D**: `karpathy_lab.autoresearch_runner`'s
`run_experiment_cycle` — LLM-generated Python written to `train.py` and executed via an unsandboxed
`subprocess.run`, Governor-reachable, no tier, no gate. Flagged two more (`vt_backtest`
strategy-code; `execute_playbook`'s destructive handlers) as architecturally identical but
"currently non-reachable due to unrelated bugs" — explicitly noting that a bug is not a security
boundary.

**58D–58G.** Closed D, E, F, and — critically — **G**, discovered *while fixing E*: the
`vector_backtest` ReAct `AgentLoop` unconditionally registers `write_file` and `backtest` tools
(neither gated by `enable_shell_tools`), reachable from the public `POST /api/investment/research`,
composable by an LLM across three turns into arbitrary code execution. 58G gated the shared
`run_backtest()` function itself, because the swarm path builds its registry inside vendored code
that a wrapper-level fix could not reach.
*Significance:* **tool composability is its own attack surface.** Two individually harmless tools
plus an LLM that can call them in sequence is one dangerous tool.

**60 — Final Red-Team Gate.** Re-ran all seven fixes (113/113), traced every autonomous entry path,
found one more real gap (`core/mcp_server.py`: no gateway enforcement, fail-open
`mcp_secure_call`) and correctly classified it Class A / human-operated-only rather than folding it
into the gate. Verdict **A — READY**, with two disclosed non-blocking risks.
*Significance:* the series' best example of scoping a real defect out of a decision honestly rather
than either ignoring it or letting it block.

### Phase III — The autonomous experiment (61–70)

**61 — Protocol / Baseline / Runbook.** Ten falsifiable hypotheses (H1 autonomy … H10 cognitive
integration), each with metric, source, baseline, success/failure criterion, and an interpretation
caveat; every threshold except H9's zero-unauthorized-execution bar explicitly marked *exploratory*.
Baseline: 399,539 episodic / 2,034 semantic / 910 policy / 15,862 reasoning chains / 29,156 gateway
audit rows — a long-running instance, but inference telemetry only 3 rows old. Notably, the protocol
recorded `epistemic_tracker` as "S2 orphaned" per `phase_status.md` — **which contradicts Task 51's
own S5 finding for the `action_domain:*` loop.** That documentation inconsistency was never
reconciled and propagated into H7 being pre-emptively downgraded.

**62–65 (Day-1 launch and observation).** Launch at 2026-09-03 00:53:29 IST, PID 48840. SIGINT
validation discovered that four automated stop methods all fail on Windows and only an interactive
Ctrl+C works. Within minutes, the defining pattern appeared: `analyze_progress` wins every cycle,
gets counterfactually blocked, deposits `reward=0.05`, repeats every ~10s. Six consecutive
anticipation ticks produced bit-identical predictions. Only three action types ever reached the
gateway. **Every report was scrupulous about its own scope** ("this is 12 minutes, not a day").

**66 — Day-1→Day-2.** The anticipation engine's predictions changed for the first time — and the
report *disproved its own most exciting finding* by reading `_episode_pattern_predictions()` and
showing the change was a deterministic ±1-hour window sliding across an hour boundary. Then the
process was killed externally at 02:36:29 IST. `analyze_progress` was still firing, unchanged, in
the last logged line.
*Significance:* the methodological high point of the series — a real behavioural change,
investigated, and correctly attributed to a clock rather than to learning.

**67 — Termination Root Cause.** Ruled out reboot, sleep, Defender, Task Scheduler, application
error, and any VECTOR-side exception. Concluded a session/harness-level recycle; classified
HIGH-CONFIDENCE for "external, not VECTOR" and PLAUSIBLE-BUT-UNPROVEN for the specific mechanism.
Verdict: **RESTART ONLY AFTER INFRASTRUCTURE CHANGE** — not a safety blocker, an experimental-validity
one.

**68 — Persistent Host Verification.** Found three hosting mechanisms, all disabled; found a real
bug in `install_service.ps1` (`--mode loop` against an argparse that has no `--mode` flag); found
that all three target `api` mode with `VECTOR_API_RUN_LOOP=1` and `0.0.0.0` — a genuine parity gap
against what Task 60 actually audited. Formally recorded Segment 1 as terminated, not completed.

**69 — Segment 2 Launch Gate.** Phase-A verification only; deliberately handed the launch to the
owner's own terminal so the process lifetime would not be owned by the coordinating session — the
exact failure domain from 67. Segment 2 began 2026-09-03 12:28:06 IST, PID 37588. (Task 70 is not
present in the artifact set; the launch record lives in 69's successor reports.)

### Phase IV — Forensic analysis (71–83)

**71 — Offline Technical Audit.** 21 findings, 3 confirmed defects, nothing above S2. Two matter:
`obsidian_sync` logging an *expected* `asyncio.TimeoutError` as a warning **with full traceback**
roughly once per second (≈7,000 lines in Segment 1 alone), and OBS-02 — semantic memory's flat row
count hides real UPSERT activity, so "flat" must mean "row count", not "no writes". Also TEST-01:
`_episode_pattern_predictions` — the function Task 66's headline finding rests on — has zero direct
behavioural test coverage.

**72 — Learning Architecture V2.** The most architecturally important document in the series.
Established a **Level 0–7 ladder** (Storage → Retrieval → Influence → Internal learning →
Behavioural adaptation → Generalization → Correction → Meta-learning) with, for each level, the
necessary evidence, the *insufficient* evidence, and the false positives to guard against. Traced
six real persistence mechanisms and showed almost none of the write→read loops *close*. First to
fully trace the working `record_epistemic_belief()`/`_epistemic_penalty()` pair and to explain
precisely why it never fires for `analyze_progress`. Verdict: **nothing in VECTOR reaches Level 4.**
Proposed a V2 architecture (experience_id provenance, a single additive state-change log, bounded/
decaying policy updates, a first-seen-anchored counterfactual decay, a distinct `correction` event
type, a coarse `situation_class` fallback for generalization) and five falsifiable experiments —
all explicitly gated until after the experiment.
*Significance:* converted "no learning observed" from an intuition into a falsifiable claim against
an explicit ladder, and named the two highest-leverage fixes (counterfactual decay anchor; policy
update rule).

**73–77 — Frontend.** Memory Explorer, Cognition Panel, Experiment Observatory (73); Agent Atlas
(74); Command Center (75); HUD visual integration (76); live browser QA (77). Vanilla HTML/CSS/JS,
no framework, hand-rolled event bus. **All five tasks are purely observability: `git diff --name-only
-- '*.py'` stayed at 64 files throughout, and Task 77 ran against an isolated throwaway static
server, never Segment 2.** Nothing here changes backend cognition. The genuinely valuable
contribution is honest rendering of absent data: Agent Atlas shows `"NOT OBSERVED"` for per-agent
current task and `"UNKNOWN"` for capability reachability rather than fabricating them.

**78 — Digital Twin / Decision Simulation Lab.** ~2,900 lines, 21 modules, 28 tests, 4 replayable
scenarios, running the **real, unmodified** `DecisionEngine`, `PolicyMemory`, `GoalSystem`,
`EpisodicMemory`, `EpistemicTracker`, `CounterfactualMemory` against isolated SQLite via the
project's own pre-existing `VECTOR_DB_PATH` override. Flagship result: a genuine Level-4 chain —
two decisions across a real `close_db_connection()`/reopen, `reward=0.98` applied to one candidate
between them, winner flipped `check_calendar → search_web`, and a no-learning control that did not
flip. Sensitivity analysis quantified that `counterfactual_state` and `episodic recall` contribute
**exactly 0.0** to the score.
**What this does and does not prove — the distinction that matters most in this entire series:** it
proves VECTOR's existing wiring is *mechanically capable* of Level-4 adaptation given ≥2
close-scoring candidates and a strong unambiguous reward. It proves nothing about the real system,
which generates **one** candidate and whose only readable reward is a constant. A controlled
laboratory capability is not a demonstrated autonomous behaviour. The lab's own guard is exemplary:
`run_level4_experiment()` raises `ValueError` rather than returning a false positive on a
single-candidate scenario.

**79 — Segment-2 ~18h (actually 20.6h) checkpoint.** First large-scale live measurement:
1,753/1,753 identical winners; `avg_reward = 0.0499999999999745` over 29,140 samples; 1,746
counterfactual rejections, 100% `analyze_progress`; 3,799 inference calls, 98.2% autonomous; 39
gateway rows, 100% GREEN. Also the first observation of the *other* subsystem — 8,569
`governor_dispatch` episodic rows — initially framed as encouraging diversity.

**80 — Autonomous Agentic Learning Trace.** Static trace of the district/Hands subsystem. Found the
**PolicyMemory situation-hash mismatch** (three of four real writers unreadable by the only reader)
and the **`spawn_successor()` dict/attribute contract break**. Concluded: exactly one closed causal
loop exists in the entire subsystem — Agent HP → agent selection — and every memory-based mechanism
tops out at L3 with a broken or absent L1/L2 step.

**81 — Live Loop Health.** Corrected 79's optimism: the "diverse activity" is 318 dispatches per 50
minutes across 8 fixed pairs, 3 active agents, one script topic, and an APITester failure every ~63
seconds. Recorded the decision-cadence collapse (~11s → 1–4h) without explaining it. Coined the
right frame: **ACTIVITY ≠ PROGRESS.**

**82 — Content Pipeline + APITester Root Cause.** Static root-cause: district-keyed
`PUBLISH_EVENTS` discards `task_type`; `_fanout_handler` has zero dedup/cooldown/depth/cycle
detection; `ScriptGenerator` and `APITester` both silently substitute hardcoded defaults for the
task type they were given. Proved the two loops are one connected feedback loop. Predicted (from
source alone) that the "858 deaths" framing was likely wrong.

**83 — Current Checkpoint (106.7h).** Live-confirmed 82's predictions and **corrected its own
central one**: the registry bug fired exactly once; the 5,558 subsequent "deaths" are one orphaned
object. Also found that `agent_history`'s primary key on `agent_id` silently no-ops repeat inserts,
so the durable ghost table *undercounts real deaths and cannot be used to measure them*. Verdict:
healthy, safe, cognitively static; **no evidence of increasing adaptivity on any metric.**

---

## 8. Evolution timeline — Task → Discovery → Change → Verification → Residue

| # | Date | Discovery | Change | Verification | Residue |
|---|---|---|---|---|---|
| 51 | 09-01 | 5 integration defects; hypothesis loop never awaited; plan crash stall | none (audit) | 6 sub-audits + re-read | NOT READY, 2 blockers |
| 52 | 09-02 | — | `await` added; plan crash recovery | 39 tests; 2165/2173 | Governor↔gateway deferred |
| 55 | 09-02 | key mismatch + hardcoded confidence | consumer key; LLM-derived confidence | 7 tests, real engine | marker compliance |
| 56 | 09-02 | dict/str observation mismatch | `str(ctx)[:500]` | live unmocked run | RULE 1 gap |
| 53 | 09-02 | email real-send bypass; YELLOW==GREEN | 2 gates | 16 behavioural tests | device/fanout/subprocess unverified |
| 54 | 09-02 | RULE 1 violations; `validate_lesson` unwired | none (verification) | 203/203 targeted | **B — conditionally ready** |
| 57 | 09-02 | **3 confirmed bypasses (A,B,C)** | none (verification) | 10 diagnostic tests | **DO NOT START** |
| 58A | 09-02 | `_WIN_APP_ALIASES` contains cmd/powershell | media-player allowlist; token scope narrowed | behavioural | 2 real launches during testing, disclosed |
| 58B | 09-02 | `launch_terminal` untiered | RED + gate | 16 tests | — |
| 58C | 09-02 | `hf_train` untiered | RED + gate | 16 tests | `operation` key bug left unfixed |
| 59 | 09-02 | **Finding D** (autoresearch RCE) | none | 56/56 re-run | 4 uncertain surfaces |
| 58D | 09-02 | — | RED + gate | behavioural | sandbox not adopted |
| 58E | 09-02 | **ReAct tool-registry route found while fixing** | RED + gate on `vt_backtest` | behavioural | path mismatch left unfixed |
| 58G | 09-02 | tool composability (`write_file`+`backtest`) | gate inside shared `run_backtest()` | 3-call composition test | `os.environ.copy()` to subprocesses |
| 58F | 09-02 | a 4th destructive handler (`block_ip`) 59 missed | RED + gate | behavioural | dormant SIEM path covered |
| 60 | 09-02 | `mcp_server.py` fail-open, Class A | none | 113/113 | **A — READY** |
| 61 | 09-02 | H1–H10 protocol; baseline | none | smoke run | epistemic S2/S5 doc conflict |
| 62–65 | 09-03 | `analyze_progress` stall visible in minutes; 6 identical anticipation ticks | none | live queries | Windows SIGINT reality |
| 66 | 09-03 | anticipation "change" = clock artifact; **external kill** | none | source read | Segment 1 = 2h03m |
| 67 | 09-03 | session-level termination | none | Event Log, process forensics | mechanism unproven |
| 68 | 09-03 | 3 hosting mechanisms, all broken/misaligned | none | read-only | parity gap |
| 69 | 09-03 | — | none | Phase-A gate | owner-launched Segment 2 |
| 71 | 09-03 | 21 findings; 1-per-second traceback spam | none | static | all deferred |
| 72 | 09-03 | **L0–L7 ladder**; no mechanism reaches L4 | none (design) | source trace | V2 gated on experiment |
| 73–77 | 09-03 | frontend gaps | frontend only (0 `.py`) | live browser QA | observability only |
| 78 | 09-03 | **L4 achievable in isolation** | new isolated lab | 28 tests, 4 replays | ≠ real-system evidence |
| 79 | 09-04 | 29,140 samples, zero variance | none | read-only DB | second subsystem untraced |
| 80 | 09-04 | **hash mismatch**; **spawn_successor contract break** | none | static trace | 5 backlog items |
| 81 | 09-04 | activity ≠ progress; cadence collapse | none | live | collapse unexplained |
| 82 | 09-04 | fanout + hardcoded-default root causes | none | static | death-count framing challenged |
| 83 | 09-07 | 106.7h; 1,198/1,198 identical; APITester = 1 orphan | none | live logs + DB | stale-reference path unresolved |

**The shape of the arc:** broad architecture building → observability → cognitive-integration audit
→ an adversarial permission sweep that found *more* the harder it looked → a protocol-driven
experiment → an infrastructure failure and restart → forensic analysis that progressively replaced
optimistic framings with mechanistic ones. Each phase's central lesson was that the previous
phase's confidence was calibrated to what had been *looked at*, not to what was *there*.

---

## 9. [NEW] Findings from this session that are not in Tasks 51–83

### 9.1 The hypothesis pipeline is dead in Segment 2, and the reason is a missing timeout

`data/telemetry.db` records **exactly four** `hypothesis_engine` inference calls in its entire
history [VERIFIED-HERE]:

| id | provider | model | status | latency |
|---|---|---|---|---|
| 1 | mistral | ministral-3b-2512 | ok | 6.7 s |
| 2 | mistral | ministral-3b-2512 | ok | 6.4 s |
| 3 | mistral | ministral-3b-2512 | ok | 5.8 s |
| 13265 | *(empty)* | **gemma4:e4b** | **error** | **251,520,681 ms = 69.9 hours** |

Rows 1–3 are dated 2026-09-01 — they are Tasks 55/56's own live verification runs. Row 13265 is the
**only** hypothesis call in Segment 2's 107 hours.

`hypothesis_loop` fires every 4 h, so ~26 firings were due. One call was made, it hung for **69.9
hours**, and it errored. Working backwards from its recorded timestamp, that call began around
2026-09-03 11:20 UTC ≈ **16:50 IST — inside the 64-minute decision-cycle gap (16:03→17:08 IST) that
Task 83 identified as the boundary between Segment 2's burst phase and its sparse phase**, and
consistent with the loop's first scheduled firing (boot 12:28 + 4 h = 16:28 IST).

Mechanism [VERIFIED-HERE]: `hypothesis_loop` wraps its LLM call in **no timeout at all**, while its
sibling `think_loop` wraps `_think_tick()` in `asyncio.timeout(60)` and `observe_loop` uses
`asyncio.timeout(15)`. A hung provider call therefore parks the hypothesis coroutine indefinitely;
`_supervised()` cannot help, because the coroutine has not raised — it is simply awaiting.

Corroboration: `data/suggestion_queue.db` holds **195 rows, the newest dated 2026-09-02T17:07**
[VERIFIED-HERE] — nothing from Segment 2. Both hypothesis persistence paths are empty for the whole
experiment.

**Consequence for the experiment's own conclusions:** H10 (cognitive integration) and any claim
about proactive insight generation cannot be evaluated from Segment 2 — not because VECTOR chose not
to generate hypotheses, but because the mechanism made one attempt in 107 hours and that attempt
hung. This is the *exact* failure mode Task 51 §16.A warned about, recurring in a different form
after its original cause was fixed.

**Recommended (not applied):** wrap the call in `asyncio.timeout(...)` mirroring `think_loop`'s
pattern; and treat a `latency_ms` far above any plausible value as an alertable condition in
`InferenceObservability.alert_check()`.

### 9.2 ContinueGate is structurally inert for `think_loop`

`ContinueGate.evaluate()` is called with `step_number=self._tick_count` but **without
`last_checkpoint_step`**, which defaults to `0` [VERIFIED-HERE, `autonomous_loop.py:904-914`;
`guidance.py:1569-1580`]. Therefore `steps_since_ckpt = step_number - 0 = step_number`, always.
Once `step_number ≥ 100`, branch 2 (`step >= 100 and since_ckpt >= 25`) is **permanently true**, so
the verdict is always `"checkpoint"` and the branches that actually govern — coherence-`stop`,
budget-`stop`, rework-`pause`, slope-`throttle` — are unreachable.

Live confirmation across 25 consecutive gate evaluations spanning four days [VERIFIED-HERE]:
`step=23545 since_ckpt=23545` … `step=23648 since_ckpt=23648`. Every single one has
`since_ckpt == step`, and every one logs CHECKPOINT.

VECTOR has a step-level budget/coherence governor that is wired in, runs every decision, and can
never return anything but "continue as you were".

### 9.3 The perception loop has collapsed by ~1,000×, and the mechanism is not what the reports assumed

`_tick_count` is incremented **only** by `observe_loop`, only on a non-timeout iteration
(`autonomous_loop.py:653`), and is initialised to `0` at construction and never restored from
`loop_state` [VERIFIED-HERE]. So within this boot it is an exact, monotonic count of completed
observe ticks. Reading it out of the ContinueGate log lines gives a free instrument nobody has used:

| moment | `_tick_count` | elapsed since previous | s / tick |
|---|---|---|---|
| boot (09-03 12:28 IST) | 0 | — | — |
| 09-04 08:28 IST | 23,545 | ~20.0 h | **3.1 s** |
| 09-07 21:46 IST | 23,648 | ~85.3 h | **2,980 s (~50 min)** |

`observe_interval_sec` is `0.5` [VERIFIED-HERE, `config.py:60`], so the design cadence is 0.5 s and
the late-phase actual is ~50 minutes — a **~6,000× shortfall against design, ~1,000× against its own
first-day behaviour.**

Three explanations can be excluded with evidence:
- **Not timeouts.** `grep -c "observe] tick timed out"` across every Segment-2 log = **0**
  [VERIFIED-HERE]. (`_tick_count` only increments on the non-timeout path, so timeouts would have
  been the obvious explanation — and they simply are not happening.)
- **Not a slow tick body.** `AmbientListener.listen_tick()` returns immediately — it spawns a
  background wake task once and otherwise returns `None` [VERIFIED-HERE,
  `ambient_listener.py:156-177`]. `_observe_tick()` has no other blocking step.
- **Not the same cause as the think-loop's early returns.** `_think_tick` has exactly one
  unlogged early-return before `evaluate()` (the owner-coding backoff, which skips 2 of 3), which
  cannot account for the ~97% shortfall in decision cycles either.

What remains is that **both coroutines are being starved of event-loop turns**: `await
asyncio.sleep(0.5)` is taking ~50 minutes and `await asyncio.sleep(10)` is taking 1–4 hours, while
the district dispatch cascade continues at ~1 per 8.9 s. This is the mechanism behind the cadence
collapse that Tasks 81 and 83 both observed and explicitly left unexplained.

**Leading hypothesis for the starvation, with its evidence and its gaps:**

*For:* several hot paths call the **synchronous** `ollama_safe.chat()` directly from inside async
code, with no `asyncio.to_thread` — `Governor._llm_classify()` (`governor.py:1655`, reached from
`route_task()` inside `async def dispatch()`) and `AgentBase.vchat()` (`agent_base.py:335`, used by
district agents inside their `async def run()`) [VERIFIED-HERE]. Telemetry shows **8,223 Ollama
calls totalling 49.3 cumulative hours**, of which `script_generator → ollama` alone is **6,937 calls,
23.5 s average, 45.4 hours** [VERIFIED-HERE]. Any fraction of that executed on the event-loop thread
blocks every other coroutine for its full duration. Uninstrumented synchronous work compounds it:
SQLCipher writes into a 350 MB DB (64,043 episodic rows this boot), `memory_tree` ingestion, screen
OCR, Merkle audit hashing, and per-dispatch prompt-injection scanning are all synchronous and none
appear in `inference_calls`.

*Against / not yet established:* 49.3 h of Ollama over a 107 h boot is ~46% of wall clock, which by
itself would slow a `sleep(0.5)` to about 0.9 s, not 50 minutes. So either a much larger share of
in-thread blocking is uninstrumented, or a second mechanism (e.g. thread-pool exhaustion behind
`asyncio.to_thread`, or unbounded ready-queue growth from `_tracked_task`'s unbounded fire-and-forget
set) is contributing. **I am reporting this as the leading hypothesis, not as an established cause.**

*Exact next diagnostic (read-only, no code change):* run the process with
`PYTHONASYNCIODEBUG=1` / `loop.slow_callback_duration = 0.2` on a disposable instance, or trigger
the repository's own `core/loop/thread_dump.py` and read `data/logs/thread_dumps.log`, and measure
`loop.time()` drift against wall clock. That distinguishes "blocked in-thread" from "queued behind
`to_thread`" in one run.

### 9.4 Ollama *is* being used heavily — Task 83's inference framing is wrong

Task 83 states: *"Only 1 explicit `ollama` log mention was found in the entire 223,609-line boot log
— local-fallback usage is not visibly occurring at meaningful scale."* The telemetry table says
otherwise [VERIFIED-HERE, `data/telemetry.db`, 19,115 rows]:

| provider | calls | cumulative latency |
|---|---|---|
| mistral | 10,861 | 15.4 h |
| **ollama** | **8,223 (43%)** | **49.3 h** |
| cloudflare / zai / groq | 30 | ~0.1 h |

The inference is 43% local by call count and **76% local by time**. The conclusion was drawn from
log-line absence rather than from the telemetry table that exists precisely to answer this question
— a good illustration of Task 71's own OBS-02 lesson (absence in one instrument is not absence in
the system). Totals for the record: **9,968,674 input tokens, 21,867,226 output tokens, 25.4 s mean
latency, 5 errors in 19,115 calls (4 Ollama `ReadTimeout` + the hung hypothesis call).**

### 9.5 Task 83's "policy `last_updated` lags the decision cycles" is a timezone artifact

Task 83 flagged as unresolved that `policy_memory.last_updated = 2026-09-07 16:16:38` sat behind
decision cycles at 19:13, 20:14 and 21:46 [REPORTED]. Those cycle times are IST; the DB timestamp is
UTC. **16:16:38 UTC = 21:46:38 IST**, which is exactly the last decision cycle. Independent
confirmation from `epistemic.db` [VERIFIED-HERE]: `belief:presence:absent` and
`belief:goals:active_progress` both carry `last_seen_at = 2026-09-07T16:16:37Z`, one second before
the policy write — the same cycle, and `track_beliefs()` runs earlier in `_think_tick` than the
policy update. The veto-write path *is* firing on every occurrence. One less open question.

### 9.6 The counterfactual subsystem is a single-key blocklist, lifetime

See §4.4. 30,504 rejections, one distinct `decision_id`, spanning 81 days; `scenarios` and
`outcomes` both empty. This is stronger than any in-window figure previously reported: the
"counterfactual reasoning" subsystem has never, in its entire operational history, reasoned about
an alternative — it has only ever blocked one action.

### 9.7 The HP habituation asymmetry

See §5.2. The positive half of the only working learning signal decays to zero under repetition
(`repeat#10301 → ×0.000`), the negative half does not, and the dampener's own counter is in-memory
and resets each boot. In the current regime, "Darwinian selection" can only ratchet downward.

---

## 10. End-to-end cognitive loop — current status per transition

S0 nonexistent · S1 implemented but disconnected · S2 integrated · S3 runtime reachable ·
S4 test verified · S5 behaviourally verified (an observably different later outcome results).

| # | Transition | S | Basis |
|---|---|---|---|
| 1 | World/user/internal state → **Observation** | **S3** | `observe_loop` runs, but ~50 min/tick vs a 0.5 s design (§9.3). Reachable, not functioning as specified. |
| 2 | Observation → **Context** | **S5** | `get_world_state()` returns a real 16-key dict every cycle; six-plus consumers; live-verified in Task 56. |
| 3 | Context → **Memory retrieval** | **S5** | `recent_episodes` via `mem.recall()`; anticipation's episode matching is a genuine retrieval→behaviour link. |
| 4 | Memory → **Situation understanding** | **S3** | `track_beliefs()` writes 5 `belief:*` claims per cycle; **nothing that scores a decision reads them** (Task 78 proved this with a paired experiment). Information → belief happens; belief → decision does not. |
| 5 | Situation → **Goals** | **S3** | `generate_immediate_actions()` runs every cycle, but the goal set is frozen since 2026-07-10 and only the `progress == 0.0` exact-equality branch ever fires. |
| 6 | Goals → **Reasoning** | **S2** | `ReasoningBank.inject_past_reasoning()` writes `candidate.reasoning_steps`, which `total_score` never reads; `decision_engine.py:454`'s own comment admits it. Decorative. |
| 7 | Reasoning → **Hypotheses** | **S1** | Implemented, scheduled, three defects fixed — and **one inference call in 107 h, hung 69.9 h, errored** (§9.1). Zero hypotheses stored in Segment 2. |
| 8 | Goals → **Planning** | **S1 creation / S4 execution** | Execution machinery is real and test-verified incl. crash recovery; **`add_goal()`'s only production caller is an HTTP router** [VERIFIED-HERE], so nothing autonomous ever creates a plan. |
| 9 | Candidates → **Decision** | **S5** | `evaluate()` runs every cycle and its winner directly drives `_act_on()`. Behaviourally verified — and behaviourally verified to be *invariant*: 1,198/1,198 identical. |
| 10 | **Policy influence** | **S3** | `get_score()` is read before every score, so the mechanism is live — but three of five writers use an incompatible key (§4.5), so the value read is a constant. Mechanism S5, *signal* S1. |
| 11 | **Epistemic influence** | **S3** | `_epistemic_penalty()` reads every cycle; `action_domain:*` has had **zero writes in 107 h** and all three existing claims are stale (§4.3). Mechanism S5 (test-proven in Task 78), *signal* S0 for the live system. |
| 12 | **Counterfactual influence** | **S5** | Genuinely and repeatedly changes behaviour — 1,198/1,198 vetoes. The only S5 memory→behaviour link in the running system, and it points one way: block. |
| 13 | Decision → **Governance** | **S5** | `Governor.dispatch()` is real, routes 43,312 tasks, applies rate limiting/taint/injection-scan/audit. |
| 14 | Governance → **Permission** | **S3, partial by design** | 34 gateway actions vs 43,312 dispatches. Gating is decentralised at the point of effect; seven bypass classes closed and tested; ~40 subprocess files never traced. |
| 15 | Permission → **Action** | **S5** | 34/34 GREEN approved+executed; real nudges delivered. |
| 16 | Action → **Outcome observation** | **S5 (executed path) / S0 (vetoed path)** | The rich 5-factor reward exists and reads real owner feedback — but the vetoed branch `return`s before it, and the vetoed branch is the one that fires. |
| 17 | Outcome → **Attribution** | **S0** | No `experience_id`, no provenance field on any table, no state-change log. Task 72 §7 designs one; none exists. |
| 18 | Attribution → **Learning** | **S1** | `update_from_outcome()` and `record_epistemic_belief()` are real and correct; the first writes to an unreadable key, the second is never reached. |
| 19 | Learning → **Memory/policy update** | **S3** | Writes land durably: 29,164 policy samples, 30,504 rejections, 3,581 belief updates, 64,043 episodic rows this boot. |
| 20 | Update → **Future decision** | **S0 for the live system / S5 in isolation** | Task 78's lab demonstrated a real winner flip from a persisted reward across a genuine DB reopen. In production, across 1,198 cycles and 107 hours, the winner, every sub-score, and the total have not moved by one part in 10,000. |

**Aggregate:** the arc is complete and traceable from transition 1 to 19. It is broken at 17 and 20 —
attribution and influence-on-future-behaviour. Everything upstream of those works; nothing
downstream of them exists.

---

## 11. Writer → storage → reader → decision, for every learning mechanism

| Mechanism | Experience | Outcome | Attribution | Signal | Persistence | Retrieval | Decision influence | Future behaviour | **Closed?** |
|---|---|---|---|---|---|---|---|---|---|
| **Agent HP** | task ok/fail | `award/deduct_points` | direct | ±HP (positive habituated to ~0) | in-proc + `loop_state` | `max(agents, key=hp)` every dispatch | which agent runs | yes, in principle | **YES — the only one**, but saturated (§5.2) |
| **PolicyMemory** (veto writer) | "I was vetoed" | constant | direct | hardcoded 0.05 | SQLite | `get_score()` every score | yes | none — frozen at 0.05 × 29,164 | mechanically closed, informationally empty |
| **PolicyMemory** (5-factor writer) | real outcome + owner feedback | rich | direct | 0.0–1.0 | SQLite | **never — wrong key** | none | none | **NO — hash mismatch** |
| **PolicyMemory** (VectorCode / plan-step) | real outcome | 0.8/0.3, 0.7/0.3 | direct | real | SQLite | **never — wrong key** | none | none | **NO** |
| **PolicyMemory** (Hands) | hand ok/error | real | direct | real | SQLite | **never — no `Candidate` with that action_type is ever built** | none | none | **NO** |
| **CounterfactualMemory** | rejection | n/a | direct | proposal text | SQLite | `should_avoid()` every act | **yes — post-selection veto only** | blocks, forever | **YES, one-directional**; decay defeated by 30,504 same-key rows |
| **EpistemicTracker** `action_domain:*` | execution outcome | status+reward | direct | confidence 0–1 | SQLite | `_epistemic_penalty()` every score | yes, ×0.70–1.0 | **never exercised** — 0 writes in 107 h | mechanically closed, starved |
| **EpistemicTracker** `belief:*` | sense data | n/a | n/a | confidence | SQLite | monitoring endpoint only | **none** | none | **NO — disjoint keyspace** |
| **EpisodicMemory** | everything | n/a | n/a | raw event | SQLCipher | anticipation + `recent_episodes` | anticipation only | deterministic clock function | **NO** for 99.94% of writes |
| **SemanticMemory** | consolidation | n/a | n/a | facts | SQLite | `goals_v1` via `GoalSystem` | goal set (static since 07-10) | none | **NO** |
| **ReasoningMemory** (SQL) | hand outcome | reward | direct | 0.0/1.0 | SQLite | HTTP endpoint only | none | none | **NO** |
| **ReasoningBank** (file) | 57 fixed entries | n/a | n/a | text | JSON | every score | injected into an unread field | none | **NO** |
| **Ghost memory** | agent's life | final HP | direct | lessons/best_decisions | in-proc + `agent_history` | `get_system_prompt()` — **0 callers** | none | none | **NO** |
| **CorrectionLearner** | owner correction | n/a | n/a | lesson text | episodic | `session_hydration_prompt()` | prompt text only | unverifiable | **NO** — `validate_lesson()` has 0 callers |
| **SuggestionQueue** | hypothesis | n/a | n/a | text+confidence | SQLite | none found | none | none | **NO** — and 0 rows since 09-02 |

**One closed loop out of fourteen**, and it is currently pinned by its own habituation dampener.

---

## 12. What I would verify next, in priority order

1. **Instrument the event loop** (§9.3). One disposable run with `PYTHONASYNCIODEBUG=1` /
   `slow_callback_duration=0.2`, plus `loop.time()`-vs-wall-clock drift, would settle the starvation
   mechanism definitively. Everything else about Segment 2's cognitive silence is downstream of it.
2. **Trace the orphaned APITester reference** (Task 83's own open question). Something outside
   `AgentRegistry._agents` holds and dispatches a popped object every ~65 s. Likely candidates: a
   captured list from a prior `get_by_district()` call held in a closure, or a subscriber list in
   the event bus built at boot. This is a live object-lifetime bug, not a cosmetic one.
3. **Add an `asyncio.timeout` to `hypothesis_loop`** and an implausible-latency alert to
   `InferenceObservability` (§9.1) — a 69.9-hour recorded latency should never be silent.
4. **Fix the PolicyMemory hash** by centralising `_make_situation_hash` into one shared function
   imported by all writers and by `PolicyMemory` itself, so drift becomes impossible. Task 80 rates
   this the single highest-leverage change in the system, and I agree — it reconnects the only rich
   reward signal that exists.
5. **Then, and only then, re-run Task 78's Experiment B against the real system.** Note its stated
   precondition, which is not yet met: Level 4 requires ≥2 competing candidates, and production
   generates exactly one. Candidate diversification (Task 72 Stage 4) is a prerequisite for
   *measuring* learning, not just for having it.
6. **Do not "fix" `analyze_progress` first.** Task 71's LEARN-01 is right: it is the study object.
   With 29,164 samples of zero variance it is the most statistically unambiguous negative result the
   project has ever produced, and it should be preserved as a baseline against which any V2 change
   is measured.

---

## 13. Bottom line

VECTOR today is a **safe, stable, genuinely autonomous, and cognitively static** system.

- The safety architecture is materially stronger than it was two months ago, and stronger than my
  historical model of it. Seven confirmed bypass classes were found and closed with behavioural
  tests, and 107 hours of unattended operation produced zero unauthorized consequential actions.
- The autonomy is real: 43,312 dispatches, 19,115 LLM calls, 64,043 memory writes, 34 gated
  proactive actions, all with no human in the loop.
- The intelligence is not. Fourteen learning mechanisms are implemented, integrated and persisting
  data; **one** closes into behaviour, and that one is currently saturated. The system's largest and
  fastest-growing stores are the ones with no reader.
- The dominant failure mode is not broken code — almost every component works correctly in
  isolation, as Task 78's lab proved by making the real classes exhibit Level-4 adaptation on
  demand. The failure mode is **connective**: keys that don't match, namespaces that don't
  intersect, readers with no callers, timeouts on one coroutine but not its sibling, and events
  keyed by district when the information needed was the task type.

The most useful sentence in the whole 51–83 record is Task 81's: **activity is not progress.** The
most useful thing this reconstruction can add is that the same caution now applies one level up —
*a fixed architecture is not a learning architecture, and a system that has been made safe has not
thereby been made intelligent.* Those were separate problems all along, and only the first one has
been solved.

---

**Integrity statement.** Production source modified: **none**. Configuration modified: **none**.
Databases written: **none** (all connections `mode=ro`, and the two byte-copied databases were read
outside the repository and deleted afterwards). VECTOR process started/stopped/signaled/interacted
with: **none** — PID 37588 was running before this task and was still writing to
`data/logs/vector_loop.log` 14 seconds before my final read. Tests executed: **none**. Synthetic
stimulus introduced: **none**. Experiment steered: **no**. V3 not implemented; no architecture
redesigned; nothing fixed. Files created: exactly one — this document.
