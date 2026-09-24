# POST-RGC2 REPAIR — Owner-Command Reliability + Learning Identity + Demonstrated Vocabulary Seam

## 1. Executive verdict

**POST-RGC2 REPAIR PASS — DEMONSTRATED OWNER-COGNITION SEAMS CLOSED.** All three
concrete defects RG-C2 behaviorally demonstrated are closed with PRE-FIX FAIL /
POST-FIX PASS proof, zero regressions, and independent live-production
re-confirmation: (1) `classify_chat_intent()`'s 12s timeout — the primary cause
of 4/5 RG-C2 objectives collapsing to conversation — is now 45s, matching an
already-precedented sibling function; (2) a classifier infrastructure failure
is now explicitly distinguishable from a genuine conversational classification,
and `/command` routes the former to an honest, deterministic message instead of
the fabrication-prone LLM fallback that produced RG-C2 O1's 5 fabricated arXiv
citations; (3) `/command`'s own non-canonical situation-hash helper — which
silently orphaned every real reward from ever informing a future decision — is
replaced with the canonical `PolicyMemory.make_situation_hash()`, with a closed-
loop write-then-later-read proof both in an isolated test and independently
re-confirmed live in production. The one demonstrated seam NOT repaired
(`personal_strategy_recommendation`, reflection vocabulary) was traced and
proven to have no real implementation or alias match — correctly left blocked,
per the mission's own explicit branch for this exact case. Two new,
out-of-mission-scope findings were discovered during live validation and are
reported, not fixed. Final HEAD: `dfc4b4ce7`. VECTOR confirmed stopped.

## 2. Starting integrity

```
git rev-parse HEAD    -> f8a166ee45e90ec62f3c573c01f1b0e67eb43ee9  (MATCH)
git branch --show-current -> production-hardening-complete  (MATCH)
```
Working tree at mission start: `data/models/neural_policy.meta.json`/`.pt`
modified (EXPECTED RUNTIME STATE — RL checkpoint churn from prior sessions'
live runs); a set of untracked prior-mission `.md` reports (REPORT, the
established uncommitted-report pattern) and unrelated pre-existing untracked
files (`docs/*.md`, `tools/vector_dev_orchestrator/`,
`.claude/settings.local.backup-2026-09-14.json`). No production source/config
mismatch. VECTOR confirmed stopped (`tasklist`: no VECTOR process; no
listener on port 8000). **Startup integrity: PASS.**

## 3. Accepted RG-C2 evidence

Not re-audited. Accepted as the reason this mission exists: RG-C2 PARTIAL
(16/60): O1=2/12 (classifier timeout x2, fallback fabricated 5 citations),
O2=10/12 (proven positive control: natural language → `check_attendance` →
Candidate → DecisionEngine → PermissionGateway GREEN → real KIITScraper
execution), O3=1/12 (classifier timeout, composition never attempted),
O4=3/12 (correct classification, `personal_strategy_recommendation` never
registered, UNKNOWN block), O5=0/12 (classifier timeout). F-C2-1 through
F-C2-4 as summarized in the mission prompt's Section 2, taken as given.

## 4. Scope controls

No DecisionEngine/PolicyMemory/EpistemicTracker/CausalGraph/Governor
redesign. No reward-formula, goal-progress, or neural-RL change. No mass
DISTRICT_TASK_MAP edits or mass UNKNOWN-action registration. No
background-stagnation fix. No JWT fix or re-test. No RG-C2R or RG-D2 started.
Two new issues surfaced during live validation (Sections 29) were classified
BACKLOG, not DIRECT BLOCKER, and were not fixed — reasoning given inline at
point of discovery and repeated in Section 29.

## 5. Pre-fix reproductions

Each of the three repaired defects was independently reproduced with focused,
mocked tests BEFORE any production change, per Phase A:

- **F-C2-1**: `tests/test_postrgc2_classifier_reliability.py` — mocked
  `provider_client.get_client()` to return a genuine `TimeoutError` (via
  mocking `asyncio.wait_for` itself, the standard technique for testing
  timeout behavior without a real wait), unparseable output, and a
  provider-layer exception. Pre-fix: all three silently returned the same
  bare `{"type": "answer_question"}` as a genuine conversational
  classification — indistinguishable, confirmed by 4 failing assertions.
- **F-C2-2**: `tests/test_postrgc2_situation_hash_identity.py` — drove a real
  `/command` execution through `command_endpoint()` for a synthetic
  action_type, then read back via the canonical
  `PolicyMemory.make_situation_hash(action_type, real_params)`. Pre-fix:
  `get_score()` returned `DEFAULT_SCORE` (0.5) despite the log confirming a
  real write occurred — proving the write landed under a different,
  unreadable hash.
- **F-C2-4**: `tests/test_postrgc2_fallback_fabrication_guard.py` — mocked
  `classify_chat_intent` to report `classification_failed=True` for a
  paraphrased research request. Pre-fix: `_llm_answer()` was still called
  (confirmed via mock call count), reward was still 0.8 (identical to a
  genuine success).

All three pre-fix runs are recorded with their exact failure output in
Sections 8/12/10 below (not merely asserted here).

## 6. Classifier timeout architecture

Full latency layering, traced via direct source read (`core/city/governor.py`,
`core/inference/provider_client.py`) before any change:

```
/command (commands.py)
  -> classify_chat_intent()                         [OUTER ceiling: was 12.0s, now 45.0s]
      -> provider_client.chat()
          -> route_policy.decide_route() orders providers (observed live: up
             to 13 providers, e.g. cohere/cloudflare/cerebras/nvidia/llm7/
             github_models/zai/opencode_zen/groq/deepseek/mistral/openrouter/
             ollama)
          -> for each provider (loop):
              -> provider_health.can_try() gate (may skip immediately on an
                 open circuit-breaker — observed live: a real
                 "skipped by provider health circuit" event)
              -> _call_with_retry() [max_retries=3 per provider]
                  -> _call() -> httpx per-attempt ceiling: self._timeout=60.0s
                     (ReliableProvider.__init__, reduced from 120s in the
                     2026-07-23 "JARVIS-parity latency pass")
                  -> on failure: exponential backoff 1.0s -> 2.0s -> ... capped 30s
              -> on total provider failure: continue to next provider
```

The SAME 2026-07-23 pass that reduced the per-attempt ceiling to 60s also
added an outer `asyncio.wait_for(..., timeout=45.0)` around
`_answer_conversationally()`'s own single `get_client().chat(tier="fast", ...)`
call — its own comment explicitly documents why: *"a single provider hanging
inside provider_client's own 120s-per-attempt HTTP timeout, across up to 3
retries and several providers in the fallback chain, had no ceiling here."*
`classify_chat_intent()`'s own `asyncio.wait_for(..., timeout=12.0)` was added
TWO DAYS EARLIER (2026-07-21, per its own comment) — predating the pass that
properly characterized this exact call shape's real worst-case latency, and
never received the same fix.

## 7. Classifier root cause

Not a mysterious defect: `classify_chat_intent()`'s 12s ceiling was a
reasonable-at-the-time estimate ("12s is generous for a 'fast' tier call",
per its own original comment) that was never revisited after a *sibling*
function facing the *identical* downstream call shape was given a
properly-characterized 45s ceiling two days later. RG-C2 behaviorally
confirmed the real-world consequence: 4/5 objectives (O1 x2 attempts, O3, O5)
independently hit `verdict='TIMEOUT (12s)'`, including one case with a real,
observed provider-health circuit-breaker event contributing to the delay.

## 8. Classifier repair

`core/city/governor.py::classify_chat_intent()`:
- `timeout=12.0` → `timeout=45.0` (aligned to the sibling
  `_answer_conversationally()`'s own already-validated value — no new timeout
  mechanism introduced, per the mission's explicit preference for reuse).
- A new small helper, `_classifier_failed(reason)`, returns
  `{"type": "answer_question", "classification_failed": True,
  "failure_reason": reason}` — additive to the existing dict shape, so every
  existing caller that only checks `.get("type")` (including `/ws/command`,
  never touched by this mission) sees byte-identical behavior.
- Applied at all three genuine infrastructure-failure exit points:
  `asyncio.TimeoutError` (`failure_reason="timeout"`), unparseable LLM output
  / `NO_JSON_MATCH` (`failure_reason="invalid_output"`), and the outer
  catch-all `except Exception` covering provider-layer failures
  (`failure_reason="provider_error"`).
- The low-confidence/wrong-district "REJECTED" branch and a genuine
  successfully-parsed `is_action=false` classification are explicitly
  **unchanged** — both are completed, valid classifications, not
  infrastructure failures, and must not be conflated with them (mission
  Section 6's core distinction).

Pre-fix vs post-fix proof: `tests/test_postrgc2_classifier_reliability.py`,
8 tests — 4 failed pre-fix (timeout ceiling assertion, timeout/invalid-
output/provider-error `classification_failed` markers), all 8 pass post-fix,
including the 4 unchanged-behavior tests which passed in BOTH runs (proving
no regression to the REJECTED/genuine-conversation paths).

## 9. Timeout/failure fallback semantics

`core/api/routers/commands.py::command_endpoint()`: a new branch, inserted
immediately after `classify_chat_intent()` returns and before the existing
`"respond"`-intent branch, checks `gov_intent.get("classification_failed")`.
If true: returns a deterministic, honest message (*"I wasn't able to work
out how to handle that request in time (classification did not complete) —
could you try again or rephrase it?"*) with **zero LLM call**, records the
outcome via `store_reasoning_chain`/`episodic_mem.store` with an honest
`outcome="classification_failed"` tag and `reward=0.2` (not the 0.8 a genuine
success gets), and returns immediately — `action_taken=None,
candidates_evaluated=0`, matching the existing `CommandResponse` shape.
Genuine conversation (no `classification_failed`) and genuine successful
action classification are both completely unaffected — verified by
regression (Section 21).

## 10. Retrieval-grounding/fabrication repair

Same code change as Section 9 — the fabrication vector (RG-C2 O1: a
research request hit the classifier timeout, fell through to `_llm_answer()`
with no signal that classification never completed, and the LLM confidently
fabricated 5 specific, independently-verified-wrong arXiv citations) is
closed by construction: the honest-failure branch never calls `_llm_answer()`
or any other LLM at all, so there is no generative step that could invent
retrieved-looking content. This is scoped exactly to the demonstrated
seam (classifier-infrastructure-failure → fallback), not a general
hallucination fix — a genuine conversational classification still calls
`_llm_answer()` exactly as before, and general LLM-conversational-fabrication
risk outside this specific seam is explicitly out of this mission's scope.

Deterministic fabrication test (Section 24 detail):
`test_classification_failure_response_is_honest_not_fabricated` — asserts the
response contains none of `"arxiv"`, `"i found"`, `"here's a"/"here is a"`,
and does contain an honest failure phrase (`"couldn't"/"could not"/"unable"/
...`). Pre-fix: FAILED (response was the mocked `_llm_answer()` return value
verbatim, i.e. exactly what would happen with real fabrication). Post-fix:
PASSED.

## 11. Situation-hash root cause

`core/api/routers/commands.py` defined its own module-level
`_make_situation_hash(params: dict) -> str` (line 44-46): `hashlib.md5(
json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:12]`
— params-only, MD5, no `action_type` folded into the identity at all. This
is a *completely different* function from `PolicyMemory.make_situation_hash(
action_type, params)` (`core/memory/policy.py`), the canonical, "v2:"-
prefixed SHA-256 identity `DecisionEngine._score_candidate()`'s own
`get_score()` call reads when scoring a new candidate for the same
`(action_type, params)` pair. `commands.py`'s Step 6 write
(`update_policy(action_type, situation_hash, reward)`) and the
`/command/feedback` endpoint's fallback both used the local, non-canonical
function. RG-C2 confirmed live: a real `check_attendance` reward (0.8, 13
samples) was durably persisted in `policy_memory`, but under a hash
`DecisionEngine`'s own reader could never address — a genuine identity
mismatch, not a data-loss bug.

## 12. Canonical hash repair

- Removed `commands.py`'s local `_make_situation_hash()` entirely (confirmed
  unused elsewhere via repo-wide grep before removal; its only two call
  sites are the two below). Removed the now-dead `hashlib`/`json` imports.
- `command_endpoint()` Step 6: `situation_hash = PolicyMemory
  .make_situation_hash(decision.winner.action_type, decision.winner.params)`.
- `feedback_endpoint()`: `situation_hash = body.get("situation_hash") or
  PolicyMemory.make_situation_hash(action_type, {})` — the canonical
  function's own documented empty-params convention when no caller-supplied
  hash exists, replacing a THIRD, differently-shaped non-canonical call
  (`_make_situation_hash({"action": action_type})`) that did not even match
  the OTHER local call site's own shape.

Pre-fix vs post-fix proof: `tests/test_postrgc2_situation_hash_identity.py`,
6 tests — 4 failed pre-fix (helper-removed guard, source-uses-canonical
guard, the closed-loop proof, and the feedback-endpoint canonical-identity
check), all 6 pass post-fix. Two identity-differentiation tests (different
action_type, different params) passed in both runs, confirming
`PolicyMemory.make_situation_hash()` itself (untouched) remains correct.

## 13. Legacy owner-command PolicyMemory rows

Per Section 9's explicit instruction, no broad migration was performed.
Confirmed by direct query: the pre-existing RG-C2-era rows
(`check_attendance` under legacy hash `99914b932bd3`, `personal_strategy_
recommendation` under `ae382000b97d`, three `respond` rows from 2026-07-14)
remain intact, untouched, under their original non-canonical hashes — they
are legacy/orphaned historical data, documented here, not fabricated or
silently discarded. Every **new** write from this point forward (confirmed
live, Section 22 P4) uses the canonical identity.

## 14. Closed-loop learning proof

Required by Section 10 of the mission — proven twice, independently:

1. **Isolated test** (`test_closed_loop_write_then_later_read`, isolated temp
   DB): `Candidate(action_type="postrgc2_synth_action_a", params=P)` executed
   through the real `/command` pipeline (real `DecisionEngine`, real
   `PermissionGateway.execute` mocked only at the GREEN-approval boundary) →
   `get_score()` on the canonical hash reads back the updated value (not
   `DEFAULT_SCORE`) → a **fresh** `DecisionEngine().evaluate()` call for the
   identical `(action_type, params)` reads `policy_score` exactly equal to
   that updated value — not merely comparing two hash strings, but proving a
   later real scoring call is actually influenced by the earlier real write.
2. **Live production** (Section 22, P2+P4): `check_weather` executed twice
   via real `/command` HTTP requests. First execution: real row created
   under `v2:081ac8c32131` (avg_reward=0.8, sample_count=1) — confirmed via
   direct DB query, a genuine "v2:"-prefixed canonical hash, unlike RG-C2's
   orphaned `check_attendance` row. Second, identical request: `winner_score`
   rose from 0.569 to 0.6225 (a real, measurable, attributable increase from
   the first execution's reward being correctly read back), and the DB row
   updated to `sample_count=2` under the *same* hash. This is independent,
   live, unmocked confirmation that the fix works in production, not only
   under test.

## 15. Reflection capability trace

Per Section 11's six explicit questions, answered via direct source read
(`districts/reflection/*.py`, `core/city/governor.py::_snap_to_known_task_type`,
`_DISTRICT_KEYS`):

1. Is `personal_strategy_recommendation` itself implemented? **No.** No
   reflection-district agent (`DailyReviewer`, `GrowthAnalyst`,
   `JournalWriter`) declares or handles this exact task_type string.
2. Is it an alias for an already-implemented action? **No.**
   `_DISTRICT_KEYS["reflection"] = ["daily_review", "reflect", "journal"]`
   (derived from `DISTRICT_TASK_MAP`). `_snap_to_known_task_type()`'s own
   word-overlap matching requires at least one shared underscore-separated
   word; `{"personal","strategy","recommendation"}` shares zero words with
   any of the three real keys — confirmed by the live log itself: RG-C2 O4's
   own `verdict='ACCEPTED type=personal_strategy_recommendation ...'` (i.e.
   `_snap_to_known_task_type()` ran and correctly found no match, returning
   the invented string unchanged — not a bug in that function).
3. Which concrete agent handles the intended behavior? None exactly;
   `GrowthAnalyst.run()`'s `task_type="analyse"` (capabilities include
   "growth"/"progress"/"reflect") is the closest conceptual match, but is
   never lexically triggered by this invented string.
4. Does adding it to a tier make it executable? Only nominally — dispatch
   would reach the `reflection` district but match no real handler branch,
   falling to that agent's generic `"<Agent> ready. Use task_type='X'..."`
   stub response.
5. Would registration cause a later `not_implemented`-shaped failure?
   Effectively yes — a misleading "looks executed, HTTP 200, status=ok"
   response containing no real reflection content, which is **worse** than
   the current honest, safe UNKNOWN block.
6. What permission tier is justified? None — no real handler exists for this
   exact string, so no tier assignment would be meaningful.

## 16. Reflection repair or proven non-implementation

**Option B taken, per the mission's own explicit branch: proven
non-implemented, left safely blocked.** No production code changed for this
seam. `personal_strategy_recommendation` (and, per Section 18's live
re-observation, at least one other invented-but-unregistered task_type,
`goal_setting`) continue to reach real `DecisionEngine` scoring and then
correctly, safely fail closed as UNKNOWN at `PermissionGateway` — confirmed
unchanged behavior, live, in Section 22 (P3).

## 17. Composition smoke result

**CLASSIFICATION STILL FAILS** (via a distinct mechanism from RG-C2's own
timeout-driven collapse — see Section 22, P5): a paraphrased draft+schedule
request's classifier call actually *succeeded* this time (no timeout at all)
with `task_type="generate_report", district="communication", confidence=1.0`
— but was correctly REJECTED because `"communication"` (singular) is not a
real district name (the real one is `"communications"`, plural). This is a
genuine, new, out-of-mission-scope finding (an LLM district-name-guessing
error, not one of F-C2-1/2/3) — documented in Section 29, not fixed. The
real `script`→`schedule_post` composition machinery was never reached; the
fallback response was honest (correctly stated it lacked context to draft
anything), not fabricated.

## 18. Policy-conflict/code-status smoke result

**NOT OBSERVED**, again — but for a *third*, different reason than either
RG-C2's O5 (pure timeout) or a genuine habit-vs-semantics conflict. A
paraphrased "any notable code changes recently" probe's classifier call
again succeeded (`task_type="check_code_changes", district="development",
confidence=0.95`) but was REJECTED because `"development"` is not a real
district name either (the real one is `"coding"`) — the same class of
district-name-guessing error as Section 17, a third independent instance.
H (`commit_code`) vs C (`git_status`) never competed; the response was
honest and grounded in real session context, not fabricated.

## 19. Test matrix

| Category | File | Tests | Pre-fix | Post-fix |
|---|---|---|---|---|
| Classifier reliability | `test_postrgc2_classifier_reliability.py` | 8 | 4 failed | 8 passed |
| Fallback fabrication guard | `test_postrgc2_fallback_fabrication_guard.py` | 5 | 3 failed | 5 passed |
| Situation-hash identity | `test_postrgc2_situation_hash_identity.py` | 6 | 4 failed | 6 passed |
| **Total new tests** | | **19** | **11 failed** | **19 passed** |

## 20. Pre-fix vs post-fix evidence

Recorded exhaustively in Sections 5/8/10/12 above with exact assertion
failures and their root cause; not repeated here. Every claimed repair has
a real, reproduced PRE-FIX FAIL captured in this session's own tool output
before the corresponding production edit was made — no repair was applied
speculatively.

## 21. Regression results

Targeted (not exhaustive — matching this mission's bounded scope, per the
established discipline from prior missions that a full 354-file suite is
frequently blocked by unrelated system memory pressure):
- `test_rr1_command_integration.py` (9 tests) + `test_rr1_5_permission_
  vocabulary.py` (16 tests): all pass — the canonical `/command` pipeline
  RR-1 established is fully intact.
- `test_rr3_6_authorization_boundary.py` (16), `test_red_interactive_tools_
  bypass.py` (29), `test_agency_run_wiring.py` (10), `test_coding_reviewers_
  run_wiring.py` (11), `test_email_agent_permission_gate.py` (9), `test_
  command_websocket_parity.py` (12): all pass in isolation. One
  cross-file-only hang was observed when 4 of these files ran back-to-back
  in one pytest invocation; isolated re-runs of each file confirmed it
  is a pre-existing test-isolation artifact (a lingering resource from an
  earlier file's test), not a regression — none of these files' production
  code was touched by this mission.
- `test_permission_gateway.py`/`test_permission_gateway_extra.py`/`test_
  skill_gateway.py`: 3 pre-existing failures found, all independently
  confirmed via `git stash` to fail identically against the unmodified
  pre-fix code (Section 25 detail) — zero regressions caused by this
  mission.
- `test_regression_governor_capability_routing.py`: excluded from this
  pass — its tests reach a real, unmocked `IntentMatcher._embed()` →
  `ollama.Client()` → local SSL context creation that stalls in this
  environment; a pre-existing environmental dependency, unrelated to
  `classify_chat_intent`'s own timeout logic (confirmed: the stall occurs
  inside pure local certificate loading, before any network call).

**Zero regressions attributable to this mission's changes.**

## 22. Production validation P1-P5 (+ Section 14/17 smoke probes)

VECTOR started via `python run_vector.py api`. All 6 live probes below used
paraphrased text, never RG-C2's frozen wording.

- **P1 (executable/retrieval)**: *"Would you mind pulling together a short
  overview of any notable recent findings on this general topic?"* — took
  139.45s total, but **not** due to my fix: the log shows a one-time
  `IntentMatcher` cold-start ("Embedding 499 examples...") on this fresh
  process consumed nearly all of that time; the request never even reached
  the LLM-classification stage `classify_chat_intent()`'s 45s ceiling
  guards — Stage 2 (embedding similarity) matched it directly to
  `create_overview`, which reached real `DecisionEngine` scoring
  (score=0.542) and was then correctly, safely blocked as UNKNOWN at
  `PermissionGateway`. **Result: honest failure, zero fabrication** — the
  fabrication-guard branch wasn't even needed this time because a different,
  also-safe path (real UNKNOWN block) was taken.
- **P2 (ordinary executable, GREEN)**: *"Can you tell me the current weather
  conditions right now?"* — 4369ms, `check_weather` → real Candidate →
  DecisionEngine (score 0.569) → PermissionGateway GREEN → real execution.
  Confirms fast paths are completely unaffected by this mission's changes.
- **P3 (reflection)**: *"Thinking about how things have gone recently, what
  would you say I should prioritize next?"* — 20911ms, classifier succeeded
  (`task_type="goal_setting", district="reflection", confidence=0.8"`),
  reached real `DecisionEngine` (score 0.5419), correctly failed closed as
  UNKNOWN with the same honest message RG-C2 O4 observed. **Confirms Section
  16's decision (no repair) produces stable, unchanged, safe behavior live.**
- **P4 (learning identity closed loop)**: see Section 14 — fully proven live.
- **P5 (composition smoke)**: see Section 17.
- **Section 14 policy-conflict smoke**: see Section 18.

Post-probe goal-store snapshot: bit-for-bit identical to the pre-probe
baseline across all 7 active goals — **NO IMPACT OBSERVED** (Section 27).

## 23. Latency table

| Probe | Total /command latency | Classifier outcome | Candidates evaluated |
|---|---|---|---|
| P1 | 139,450ms | Embedding-matcher match (cold-start bootstrap dominated; classify_chat_intent's own LLM path never reached) | 1 (UNKNOWN, blocked) |
| P2 | 4,369ms | N/A (Stage-0 keyword match, "weather") | 1 (GREEN, executed) |
| P3 | 20,911ms | Real LLM success (0.8 conf) | 1 (UNKNOWN, blocked) |
| P4 (repeat of P2) | 3,530ms | N/A (Stage-0 keyword match) | 1 (GREEN, executed) |
| P5 | 15,578ms | Real LLM success but REJECTED (bad district name) | 0 (fast-path) |
| Sec.18 smoke | 49,942ms | Real LLM success but REJECTED (bad district name) | 0 (fast-path) |

**Assessment**: once the one-time embedding-cache cold-start (P1) is
excluded, steady-state latency (P2-Sec.18: 3.5s-50s) is bounded and
reasonable — no case exceeded the 45s classifier ceiling plus a bounded
downstream step. The repair achieves **more reliable** classification
(timeout no longer silently masks genuine executable requests) **while
remaining bounded** — not every command now takes 45+ seconds; the two
slower cases (P3, Sec.18 smoke) reflect real LLM round-trip time for a
successful classification, not a timeout.

## 24. Fabrication test

Mandatory, deterministic, mocked (per Section 19 of the mission — not
"asking the real LLM to hallucinate and hoping it does"):
`test_classification_failure_response_is_honest_not_fabricated`. Asserts:
no `"arxiv"`, no `"i found"`, no `"here's a"/"here is a"`, no leakage of the
mocked (never-should-be-called) `_llm_answer()` return value, and an honest
failure phrase present. **Pre-fix: FAILED** (the mocked fabrication-shaped
text passed straight through, exactly reproducing the RG-C2 O1 mechanism).
**Post-fix: PASSED.**

## 25. PermissionGateway regression check

Confirmed intact: `test_permission_gateway.py`'s core GREEN/YELLOW/RED
auto-execute and UNKNOWN-fail-closed tests all pass. The one PermissionGateway-
file failure (`test_red_action_times_out_without_confirmation`) is a
test-side signature mismatch (`fast_timeout()`'s mock doesn't accept a
`pending_id` kwarg the real code now passes) — **independently confirmed
via `git stash` to fail identically on the unmodified pre-fix code**, and the
real production behavior visible in that same test's log
(`Council verdict=defer conf=0.00 for action=send_email`) shows the actual
RED-tier deferral logic working correctly; only the test's own mock crashed
afterward. The two `test_skill_gateway.py` failures are the exact same
already-diagnosed false-positive (a naive substring-search helper confused by
an unrelated later comment) documented in this session's own prior RR-4
report — re-confirmed here as still present, still not a real regression,
and still not caused by anything in this mission's diff (which never touches
`autonomous_loop.py`). **PermissionGateway's fail-closed behavior is
unweakened.**

## 26. Owner/background coherence observation

**UNCHANGED.** As in RG-C2, the background `analyze_progress` autonomous
cycle continued running on its own ~11-13s cadence throughout all 6 live
probes, visibly interleaved in the log, with no observable cross-influence
in either direction. This mission did not touch, and did not need to touch,
this relationship.

## 27. Goal-progress observation

**NO IMPACT OBSERVED.** All 7 active goals' `progress` values are bit-for-bit
identical before and after all 6 live probes. Fully consistent with Task
89C's established finding (no production path auto-advances goal progress
from reward) — unaffected by any change in this mission.

## 28. Known pre-V1 JWT backlog

RR-4's previously-identified JWT type-confusion finding (a regular
collections-engine user's own login token can be accepted as full
VECTOR-owner API access, via `core/api/middleware.py`) was **not** touched,
tested, or re-verified in this mission, per explicit instruction. Remains
open, documented, carried forward as **KNOWN PRE-V1 SECURITY BACKLOG** —
requires its own, separately-scoped, owner-approved mission.

## 29. New findings (discovered during this mission, not fixed)

Both classified **BACKLOG** (not DIRECT BLOCKER — neither prevented
completing this mission's own required validation, once understood):

1. **`IntentMatcher._embed()`'s one-time embedding bootstrap has no timeout
   at all.** On a fresh VECTOR process with no cached embeddings, the first
   real `classify_chat_intent()` call triggers a real, unbounded "embed 499
   examples" step (observed live: ~139s) BEFORE ever reaching the
   LLM-classification stage this mission's 45s fix guards. This is a
   one-time cold-start cost (confirmed: all subsequent probes in the same
   process were fast), not a per-call/systemic issue, and was never part of
   RG-C2's own demonstrated evidence (RG-C2's session had a warm cache
   throughout). Out of this mission's explicit scope (`intent_matcher.py`
   is not one of the named repair surfaces); flagged for a future,
   narrowly-scoped fix (e.g. an outer timeout around the bootstrap, or a
   pre-warmed cache at process startup).
2. **The classifier LLM frequently invents plausible-but-wrong district
   names** (`"communication"` instead of `"communications"`;
   `"development"` instead of `"coding"`) — observed independently in both
   P5 and the Section 18 smoke probe. `_snap_to_known_task_type()`'s own
   word-overlap correction only fixes `task_type` mismatches within an
   already-valid district, not a wrong district name itself, so these cases
   correctly, safely fall through to conversational REJECTED — not a
   security issue, but a real, reproducible capability-selection gap
   distinct from all three of F-C2-1/2/3. Not fixed (would require either
   prompt changes or a district-name fuzzy-correction step, neither in this
   mission's scope); flagged for a future RG-C2R-informed repair pass.

## 30. Production diff audit

```
git status --short (final):
  M data/models/neural_policy.meta.json   -> EXPECTED RUNTIME STATE
  M data/models/neural_policy.pt          -> EXPECTED RUNTIME STATE
  (all committed files below no longer show as modified)
  ?? [17 pre-existing untracked report/doc files]  -> PRE-EXISTING / REPORT
  ?? VECTOR_TECHNICAL_KNOWLEDGE/POST_RGC2_OWNER_COGNITION_REPAIR_REPORT.md -> REPORT (this file)

git show --stat dfc4b4ce7:
  core/api/routers/commands.py        | +71 -6   -> F-C2-2 + F-C2-4 (Sections 9,10,12)
  core/city/governor.py               | +47 -6   -> F-C2-1 (Sections 7,8)
  tests/test_postrgc2_classifier_reliability.py       | new, 233 lines -> F-C2-1 proof
  tests/test_postrgc2_fallback_fabrication_guard.py   | new, 168 lines -> F-C2-4 proof
  tests/test_postrgc2_situation_hash_identity.py      | new, 196 lines -> F-C2-2 proof
```

Every production hunk in the commit traces to exactly one of the three
demonstrated RG-C2 findings, cited inline by its own comment. No hunk alters
unrelated semantics — confirmed by the full regression pass (Section 21) and
by direct diff review before commit. **Zero unexplained production hunks.**
Commit `dfc4b4ce7` created; RL-checkpoint runtime churn and pre-existing
untracked reports/docs deliberately left uncommitted, per this repo's
established convention throughout this whole mission series.

**Final HEAD: `dfc4b4ce7`.**

## 31. RG-C2R readiness

**RG-C2R READY.** All three demonstrated seams are closed and independently
re-confirmed live; the one seam correctly left unrepaired (reflection
vocabulary) is honestly, safely blocked, unchanged from RG-C2. RG-C2R should
be a focused behavioral recheck using new natural-language probes across:
executable research/retrieval, composition, context/reflection, code-status
semantic selection, and canonical owner-learning carry-forward — not another
full five-objective benchmark. It should specifically also probe whether the
two new Section 29 findings (embedding cold-start, district-name-guessing
errors) meaningfully affect real owner-command reliability at scale, since
this mission's own live validation could not fully characterize either given
their newly-discovered, out-of-scope nature.

## 32. RG-D2 impact

**RG-D2 READY AFTER RG-C2R.** The specific concern RR-4/RG-C2 raised for
RG-D2 (that `/command`'s own reward writes were orphaned from ever informing
a later decision, which would make an RG-D2 failure-adaptation test via
`/command` produce a false negative) is now closed and proven both in
isolation and live production (Section 14). RG-D2's own prior evidence via
the autonomous-loop path (RR-4's R13/RR-3-Overnight winner-flip proofs, which
already used the canonical hash correctly) remains valid and unaffected.
Preferred sequence, unchanged from the mission's own stated preference:
POST-RGC2 REPAIR (this mission, complete) → RG-C2R → RG-D2. No RR-5.

## 33. Verdict

**POST-RGC2 REPAIR PASS — DEMONSTRATED OWNER-COGNITION SEAMS CLOSED.**

Checked against Section 23's 18 PASS criteria: all applicable items hold.
(9) is satisfied via branch B (proven non-implemented, honestly left
blocked) exactly as the mission's own criteria anticipates. No criterion
was weakened or reinterpreted to force this verdict — Section 29's two new
findings are real, disclosed in full, and explicitly out of this mission's
scope rather than swept aside.

## 34. Hard Stop

VECTOR confirmed stopped (`tasklist`: no VECTOR process; no port-8000
listener). No repair was made for the reflection vocabulary gap (proven
non-implemented, correctly left blocked). RG-C2R was not started. RG-D2 was
not started. The JWT backlog item was not touched. Background stagnation and
goal-progress semantics were not touched. Awaiting independent review.

**Required return summary:**
- Verdict: **POST-RGC2 REPAIR PASS — DEMONSTRATED OWNER-COGNITION SEAMS
  CLOSED**
- Starting HEAD: `f8a166ee45e90ec62f3c573c01f1b0e67eb43ee9`
- Final HEAD: `dfc4b4ce7`
- Production files changed: `core/api/routers/commands.py`,
  `core/city/governor.py` (+ 3 new test files)
- F-C2-1 classifier result: **CLOSED** — timeout 12.0s → 45.0s, aligned to
  precedented sibling
- Timeout before/after: 12.0s → 45.0s
- Timeout/failure fallback result: **CLOSED** — infrastructure failure now
  distinguishable from genuine conversation; honest deterministic message,
  zero LLM call
- F-C2-2 hash identity result: **CLOSED** — canonical
  `PolicyMemory.make_situation_hash()` used at both call sites
- Canonical closed-loop learning result: **PROVEN** — isolated test +
  independent live-production re-confirmation
- Legacy policy-row treatment: left intact, undocumented rows documented,
  not migrated or fabricated
- F-C2-3 reflection result: **PROVEN NON-IMPLEMENTED, LEFT SAFELY BLOCKED**
  (Option B)
- F-C2-4 fabrication/grounding result: **CLOSED** for the demonstrated seam
  — deterministic fabrication test passes
- Composition smoke result: CLASSIFICATION STILL FAILS (new, unrelated
  district-name-guessing error — Section 29 finding #2)
- Code-status/policy-conflict smoke result: NOT OBSERVED (same new
  district-name-guessing error)
- PermissionGateway regression result: **INTACT** — 3 pre-existing,
  independently-confirmed-unrelated failures, zero regressions
- Test count/result: 19 new tests, 19/19 pass post-fix (11/19 correctly
  failed pre-fix)
- Pre-fix proof result: **CONFIRMED for all 3 repairs**
- Regression result: **ZERO regressions** across all targeted suites
- P1 result: honest failure, zero fabrication (via a different, also-safe
  path — real UNKNOWN block, not the fabrication-guard branch)
- P2 result: PASS — full real pipeline, GREEN, executed
- P3 result: PASS (as expected) — correct classification, correctly blocked
  UNKNOWN, unchanged from RG-C2
- P4 result: **PROVEN LIVE** — closed-loop write-then-later-read confirmed
  in production
- P5 result: classification succeeded but REJECTED (new finding, not one of
  F-C2-1/2/3)
- Latency summary: steady-state 3.5s-50s once one-time embedding cold-start
  excluded; bounded, not degraded to universal 45+s
- Owner/background coherence observation: UNCHANGED
- Goal-progress observation: NO IMPACT OBSERVED
- Known JWT backlog status: untouched, remains KNOWN PRE-V1 SECURITY
  BACKLOG
- New bounded findings: (1) `IntentMatcher` embedding-bootstrap has no
  timeout (one-time cold-start cost); (2) classifier frequently invents
  wrong-but-plausible district names — both BACKLOG, not fixed
- RG-C2R: **READY**
- RG-D2 status: **READY AFTER RG-C2R**
- Report path:
  `VECTOR_TECHNICAL_KNOWLEDGE/POST_RGC2_OWNER_COGNITION_REPAIR_REPORT.md`
- Confirmation VECTOR stopped: **YES**

**NO NEXT MISSION STARTED. NO SELF-APPROVAL. Awaiting independent review.**
