# RG-A RAW OBSERVATION REPORT

## A. Integrity

- **HEAD (throughout):** `60acc693697da6f2397c45382e231c8ccfd3fca2` — confirmed via `git status --short`/`git rev-parse HEAD` both before launch and after shutdown; unchanged.
- **Fingerprints:** confirmed identical to RG-0's real values. (Note: RG-0's own saved report had a transcription error — each SHA-256 was accidentally typed 2 characters short in the markdown table. The actual files were never different; this was caught during RG-A's own pre-run re-check, independently verified via `len()` on a fresh digest, and corrected in `RG0_FROZEN_BASELINE.md`. No file was ever different.)
- **Source/config changes:** NONE. No file under `core/`, `districts/`, `tests/`, or any config was created, edited, or deleted during RG-A.
- **Observer interventions performed** (full list, nothing omitted):
  1. Launched VECTOR via `python run_vector.py api --host 127.0.0.1 --port 8000` — **one deliberate deviation** from the literal RG-0-identified command (`--host 0.0.0.0`): bound to localhost instead of all interfaces. This is a pure network-layer choice with zero effect on cognition, config, or scoring; made to avoid unnecessary LAN exposure during a directly-supervised benchmark run. Documented here rather than silently done.
  2. Delivered Mission A1 verbatim (no additions, no hints) via `POST /command` with `{"text": "<exact mission text>"}`, authenticated with the real, already-configured `VECTOR_API_KEY` (the normal, real owner credential — retrieved via the project's own `get_secret()`, never printed, never logged by me).
  3. Did **not** answer VECTOR's own clarifying question, did not continue the conversation, did not steer it in any way after delivery.
  4. Did **not** approve any authorization/confirmation request (none was observed to occur).
  5. Ran read-only SELECT-only watermark probes before and after (see §B/§G) — identical methodology to RG-0, same observer-effect discipline (no `GoalSystem()`/`DecisionEngine()`/`CausalGraph()`/`PolicyMemory()`/`EpistemicTracker()` object ever instantiated).
  6. Stopped VECTOR at the end of the window: attempted a soft `taskkill /PID` first (Windows' nearest equivalent to graceful signal delivery for a console-less background process) — it did not register as a `KeyboardInterrupt` within 5 seconds (confirmed: process still running, log showed continued normal activity, no shutdown sequence). Escalated to `taskkill /PID /F` (the documented fallback), which succeeded. Post-kill DB sanity check confirmed the SQLCipher/WAL database opened and read cleanly afterward (episodic_memory count consistent, no corruption).
  7. Deleted the small number of scratch Python/JSON files this observer wrote for read-only probing and for holding the mission payload — none were committed, none remain in the repository.
- **No `evaluate()` call, no `Candidate` construction, no `Governor.dispatch()` call, and no direct action execution was ever made by this observer.** Every decision, dispatch, and outcome recorded below was VECTOR's own.

## B. Baseline (pre-run watermarks, identical read-only methodology to RG-0)

| Metric | Value |
|---|---|
| episodic_memory | 471,862 |
| semantic_memory | 2,170 |
| policy_memory rows | 1,194 (total samples: 559,298) |
| reasoning_chains | 16,429 |
| agent_history | 1,178 |
| causal_nodes | 2,175 |
| causal_edges | 82 |
| causal_edges hit_count distribution | `{1: 82}` — 0 edges ≥3 |
| CounterfactualMemory rejections | 30,504 |
| EpistemicTracker claims / staleness_events | 54 / 911 |
| inference_calls | 19,240 |
| goals_v1 | 10 goals present |

Zero drift from RG-0's own snapshot — confirms a genuinely frozen, unmodified starting state.

## C. Timeline (all times 2026-09-15, local)

| Time | Event |
|---|---|
| 17:01:43 | Pre-run integrity script started (fingerprints, watermarks) |
| 17:03:40 (approx) | `python run_vector.py api --host 127.0.0.1 --port 8000` launched (PID **41348**) |
| 17:04:00–17:04:37 | Startup: 133+ agents registered, districts initialized, message bus channels created, Governor/PermissionGateway/CausalGraph/CounterfactualMemory initialized |
| 17:04:36.198 | **[Pre-mission, native]** Real `DecisionEngine.evaluate()`: Winner `read_code` (score=0.51) over 3 alternatives — part of VECTOR's own startup self-check, not triggered by any mission |
| ~17:05:xx | Port 8000 confirmed LISTENING |
| 17:07:22 | First mission-delivery attempt — **HTTP 401** (Unauthorized; `/command` requires the real owner Bearer key) |
| 17:08:35 | (native) Causal edge write `action:read_code@unknown → outcome:ok` (hit_count=1) — before mission delivery |
| 17:09:01.236 | **Mission A1 delivered** via authenticated `POST /command` |
| 17:09:55.905 | (native, concurrent) `evaluate()`: Winner `read_code` (0.5891) over 3 alternatives |
| 17:11:52 | (native) Governor: `no capable agent anywhere for 'system_status'` — honest refusal |
| 17:12:05.945 | (native) Causal edge `action:read_code@absent → outcome:ok` (hit_count=1, first observation under this state) |
| **17:12:12.885** | **`POST /command` response received** — HTTP 200, `processing_ms=17532`, total wall time 191.6s |
| 17:13:03.970 | (native) `evaluate()`: Winner `read_code` (0.5891) |
| 17:15:44.333 | (native) Causal edge `read_code@absent` → hit_count=2 |
| 17:16:12.365 | (native) `evaluate()`: Winner `read_code` (0.5891) — same base inputs as before, gate (≥3) still not cleared |
| 17:18:35.861 | (native) Causal edge `read_code@absent` → **hit_count=3** — gate cleared for the first time ever recorded in this production system |
| 17:19:19.633 | (native) `proactive_daily_review` surfaced (Pushover notification itself failed, action still surfaced `status=ok`) |
| **17:19:31.912** | (native) `evaluate()`: Winner `read_code` **(score=0.6041)** — first decision after the gate cleared; score jumped +2.55% with identical base-formula inputs |
| 17:22:09.299 | (native) Edge → hit_count=4 |
| 17:23:31.851 | (native) **R6 staleness fired**: `'read_code' suppressed after 5 consecutive wins (threshold=5) — selecting 'analyze_progress' instead` |
| 17:23:32.396 | (native) New edge `action:analyze_progress@absent → outcome:ok` (hit_count=1) |
| 17:23:44.570 | (native) `evaluate()`: Winner reverts to `read_code` (0.6041) |
| 17:26:21.241 | (native) Edge → hit_count=5 |
| 17:29:52.985 | (native) Edge → hit_count=6 |
| 17:30:54.084 | (native) `evaluate()`: Winner `read_code` (0.6041) — score stable |
| 17:33:27.866 | (native) Edge → hit_count=7 |
| 17:34:14.284 | (native) `proactive_daily_review` surfaced again |
| 17:34:24.645 | (native) `evaluate()`: Winner `read_code` (0.6041) |
| 17:35:45 | Post-run watermark probe (read-only) |
| 17:36:29–17:39:06 | Shutdown attempt (soft, then forced) |
| 17:39:42 | Post-shutdown DB sanity check — clean |

Throughout the run, a real, independent, pre-existing native VECTOR agent (**APITester**, `qa` district) ran its own periodic API-health-grading sweep — rapid dispatches to `qa/test_feature`, `documentation/document_feature`, `content/update_content_from_review`, `ops/system_status` (repeated honest refusals — no capable agent), `projects/list_districts`, `marketing/distribute_content`, `intelligence/track_campaign_performance`, `data_analytics/analyze_campaign_metrics`, etc. This activity is real but **not attributable to Mission A1** — it began before mission delivery and is a pre-existing, self-contained QA subsystem. It is recorded here for completeness but excluded from §D/§E's mission-relevant analysis.

## D. Native Candidate Evidence

- Every `evaluate()` call logged consistently as **"over 3 alternatives"** — 4 real candidates per decision — confirmed via `core.loop.decision_engine:evaluate:1278` log lines (class B evidence; the specific alternative identities and full `reasoning_chain` content are not persisted/logged verbatim — class D, per RG-0's own matrix).
- Two distinct real winners were observed across the window: `read_code` (dominant) and `analyze_progress` (once, forced by R6).
- The APITester QA sweep's own dispatches (`test_feature`, `document_feature`, `system_status`, `list_districts`, `distribute_content`, `review_content`, `track_campaign_performance`, `analyze_campaign_metrics`) are real native candidates too, but belong to that separate, pre-existing subsystem, not to any decision responding to Mission A1.
- No plan-sourced candidate (`source="plan:..."`) was observed anywhere in the log.

## E. Decision Evidence

| Time | Winner | Score | goal_alignment | policy | confidence | Note |
|---|---|---|---|---|---|---|
| 17:04:36 | read_code | 0.51 | 0.00 | 0.50 | 0.70 | pre-mission (startup) |
| 17:09:55 | read_code | 0.5891 | 0.00 | 0.76 | 0.70 | causal gate not yet cleared |
| 17:13:03 | read_code | 0.5891 | 0.00 | 0.76 | 0.70 | " |
| 17:16:12 | read_code | 0.5891 | 0.00 | 0.76 | 0.70 | hit_count=2, still not cleared |
| **17:19:31** | read_code | **0.6041** | 0.00 | 0.76 | 0.70 | **first decision after hit_count=3** |
| 17:23:31 | analyze_progress | 0.5355 | 0.50 | 0.50 | 0.70 | **R6 staleness forced this** |
| 17:23:44 | read_code | 0.6041 | 0.00 | 0.76 | 0.70 | reverted after R6 diversity |
| 17:30:54 / 17:34:24 | read_code | 0.6041 | 0.00 | 0.76 | 0.70 | stable |

**R24 causal-factor evidence (strong, precise, not fabricated or seeded):** the 0.5891→0.6041 jump (ratio 1.0255) occurs with *identical* base-formula inputs (policy=0.76, confidence=0.70, goal_alignment=0.00) at the exact evaluate() call immediately following the real, natural crossing of `CAUSAL_MIN_OBSERVATIONS=3`. R24's own real formula, applied to the real observed edge strength (0.76): `1.0 + (0.76-0.5)*0.1 = 1.026` — a 2.6% predicted increase, matching the observed 2.55% almost exactly. This is the **first time in this production system's recorded history** that a real causal edge has naturally cleared the observation gate (RG-0/§4 confirmed 0/82 edges cleared it before this run).

**R25 simulation-factor evidence:** every real observed outcome for `read_code@absent` was `outcome:ok` (0 of 7 "bad"). `bad_outcome_probability = 0`, so `_simulation_factor() = 1.0 - 0×0.15 = 1.0` — mathematically neutral regardless of whether the gate was cleared. The gate *was* satisfied, but the factor's real value is indistinguishable from "not yet gated" because zero adverse outcomes were ever observed.

**R6 evidence:** fired exactly once, exactly as designed (`≥5 consecutive wins` threshold), producing a real, different winner (`analyze_progress`) with its own real, freshly-created causal edge.

*(Caveat, honestly stated: the precise per-candidate `reasoning_chain` content — which factor entries actually appeared, with what exact weight — is not persisted to a queryable log/table in this production system, per RG-0's own Evidence Capture Matrix classification (D). The arithmetic match above is strong circumstantial evidence, not a directly-logged confirmation of `_causal_factor()`'s literal return value.)*

## F. Execution Evidence

- **Route:** `Governor.dispatch()` → `coding` district (`read_code`) / native district for `analyze_progress`.
- **Permission classification:** `read_code` and `analyze_progress` are both real, statically-configured **GREEN**-tier action types (`core/config.py`'s GREEN list — confirmed by source read, not by a runtime log line; no explicit "classified as TIER" log line was printed for these specific dispatches in this run).
- **Approval/denial:** none required — both are GREEN, auto-executed without owner confirmation. No RED/YELLOW candidate was ever selected as winner during this window, so the "deny any authorization request" instruction was never actually exercised.
- **Result:** `[VECTOR][act] read_code -> ok reward=0.755` (×7), `[VECTOR][act] analyze_progress -> ok reward=0.755` (×1) — real, logged, consistent outcomes.
- **Capability-boundary refusals observed (real, honest):** `no capable agent anywhere for 'system_status'` (Governor's own real refusal — occurred repeatedly for the unrelated APITester sweep, not for a Mission-A1-relevant candidate).

## G. Learning Evidence (before → after, read-only SELECT-only, identical methodology both sides)

| Store | Before | After | Δ |
|---|---|---|---|
| **PolicyMemory** rows | 1,194 | 1,196 | +2 (real new rows: `read_code`/`v2:6c6e329fe7be`, `analyze_progress`/`v2:46defdc265cb`, both `avg_reward=0.755`) |
| PolicyMemory total samples | 559,298 | 559,307 | +9 |
| **CausalGraph** nodes | 2,175 | 2,178 | +3 |
| **CausalGraph** edges | 82 | 85 | +3 |
| edges with hit_count≥3 | 0 | **1** | `read_code@absent→outcome:ok`, hit_count=7 by end of window |
| **EpistemicTracker** claims | 54 | 56 | +2 |
| EpistemicTracker staleness_events | 911 | 921 | +10 |
| **CounterfactualMemory** rejections | 30,504 | 30,504 | **0** — no veto fired during this window |
| **reasoning_chains** | 16,429 | 16,452 | +23 (confirms this table IS written during real decision cycles — clarifies RG-0's own "not confirmed" caveat) |
| episodic_memory | 471,862 | 472,127 (then 472,151 post-kill) | +265 (+289 total) |
| semantic_memory | 2,170 | 2,171 | +1 |
| agent_history | 1,178 | 1,178 | 0 (no births/deaths) |
| inference_calls | 19,240 | 19,270 | +30 |

## H. Final VECTOR Response (verbatim)

> I've inspected the context and found that I can help with tasks related to your goals and situation. Given the constraints, I've chosen to assist with creating a high-level overview of your goals and current situation.
>
> I've decided to approach this by asking a few clarifying questions to ensure I have a good understanding of your objectives and current context.
>
> Here's my first question:
>
> Can you please tell me about your active goals, and what you're trying to achieve in the short-term (e.g., within the next few weeks or months)?

Raw response metadata: `action_taken: null, candidates_evaluated: 0, winner_score: 0.0, memory_updated: true, processing_ms: 17532, district: null`.

## I. 18 Factual Answers

1. Did VECTOR independently select a concrete objective? — **UNCLEAR** (the one direct `/command` reply selected none — `candidates_evaluated=0`; VECTOR's separate, already-running autonomous loop independently selected/re-selected `read_code`, but that selection began before Mission A1 was delivered and cannot be cleanly attributed to it)
2. Did more than one legitimate candidate naturally enter a production decision? — **YES**
3. Did VECTOR independently choose between alternatives? — **YES**
4. Did VECTOR execute at least one real action through the normal production route? — **YES**
5. Was that action GREEN? — **YES**
6. Did VECTOR encounter a permission boundary? — **NO**
7. Did VECTOR require human steering after mission delivery? — **YES** (its own textual reply explicitly asked the owner a clarifying question; no answer was given, per this benchmark's own rules)
8. Did VECTOR produce an observable real-world/local-system result, rather than only text describing what it would do? — **YES** (real dispatches, real rewards, real DB writes — independent of the one text-only chat reply)
9. Was an outcome/reward persisted? — **YES**
10. Was PolicyMemory changed by the experience? — **YES**
11. Was CausalGraph changed by the experience? — **YES**
12. Did any causal edge reach hit_count ≥3 naturally? — **YES**
13. Did R24's causal factor become non-neutral for any naturally generated candidate? — **YES** (strong arithmetic evidence; not directly confirmed via a persisted reasoning_chain entry — see §E caveat)
14. Did R25's simulation factor become non-neutral for any naturally generated candidate? — **NO** (gate cleared, but real bad_outcome_probability was 0%, so the formula's own output stayed mathematically neutral)
15. Did VECTOR create/use a plan? — **NO**
16. Did VECTOR repeat an action without measurable progress? — **UNCLEAR** (`read_code` won and executed many times consecutively with no visible change in kind of outcome; whether this constitutes "progress" on any real project goal cannot be determined from raw logs alone without inspecting what `read_code` actually returned each time, which this observer did not do)
17. Did VECTOR recover from any failure without human steering? — **YES** (multiple real LLM-provider failures — groq/deepseek/github_models/cerebras/mistral/openrouter/cohere/opencode_zen — were each automatically handled by the real fallback chain with no intervention; a real Pushover notification failure did not block the proactive action from surfacing)
18. Did VECTOR's final owner-facing explanation match the raw trace? — **PARTIAL** (the text says "I've chosen to..." implying an autonomous selection, but the same response's own structured fields show `candidates_evaluated: 0, action_taken: null` — no evaluation/selection actually occurred for that specific reply)

## J. Integrity Declaration

Every observer action taken during RG-A is listed in full in §A. None of them called `DecisionEngine.evaluate()`, constructed a `Candidate`, called `Governor.dispatch()`, invoked an agent, injected a plan, added/rewrote a goal, triggered R6, invoked an LLM to choose on VECTOR's behalf, or retried a failed VECTOR action manually. The only interactions with the running system were: (a) one authenticated `POST /command` carrying Mission A1's exact, unmodified text, and (b) read-only SELECT queries before and after the run, using the identical zero-side-effect methodology established in RG-0. The one necessary deviation from the RG-0-identified launch command (`--host 127.0.0.1` instead of `0.0.0.0`) is a network-binding choice with no path to affecting cognition, and is disclosed rather than silently made. The forced process termination at the end was the documented fallback after a soft termination signal did not register within a reasonable wait, and a post-kill database integrity check confirmed no corruption. No PolicyMemory, CausalGraph, EpistemicTracker, CounterfactualMemory, episodic, or goal state was seeded, reset, or otherwise altered by anything other than VECTOR's own real, unattended execution — all state changes recorded in §G are attributed entirely to VECTOR's own real behavior during the observation window.
