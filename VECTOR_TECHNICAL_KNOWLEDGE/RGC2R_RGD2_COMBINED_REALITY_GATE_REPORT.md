# RG-C2R Owner-Cognition Recheck + RG-D2 Grounded Self-Correction — Combined Reality Gate

## 1. Executive verdict

**RG-C2R: FAIL — OWNER COGNITION REMAINS UNRELIABLE.**
**RG-D2: NOT RUN — RG-C2R BLOCKER MAKES ADAPTATION TEST INVALID.**

Four fresh, independently-designed, novel-phrasing owner probes (retrieval,
composition, reflection, code/project status — none using benchmark or
internal-capability vocabulary) were sent to a genuinely fresh VECTOR
process built from the POST-RGC2 REPAIR baseline (`dfc4b4ce7`). All four
FAILED. Three (C1, C2, C4) were classified by the LLM with high confidence
(0.95-1.0) and a task_type a human would recognize as correct, but each was
rejected solely because the classifier emitted a district string that does
not exist in `DISTRICT_TASK_MAP` — three different fabricated labels
(`knowledge_engineering`, `communication`, `project_management`) across
three probes, one of which (`communication`) reproduces an exact
near-miss pattern already documented in the accepted baseline. The fourth
(C3) failed earlier still: the classifier declared the request not an
action at all (`is_action=false`) despite a real, GREEN-tier reflection
capability existing for it. Zero of four probes reached
Candidate→DecisionEngine. No fabrication occurred in any case — every
failure surfaced as an honest "I can't do that / don't have that
information" response, confirming the POST-RGC2 REPAIR fabrication-guard
repair held under fresh adversarial-shaped input. The previously-observed
`IntentMatcher` cold-start bootstrap (N1) was reconfirmed: 103.90s,
unbounded, one-time per process, dominating C1's latency but not
recurring on C2-C4. Given 0/4 reach into the Candidate/DecisionEngine
machinery — the exact machinery RG-D2 needs to test grounded
self-correction — Phase B (RG-D2) was not started; continuing it would
have produced an uninterpretable result built on a path already shown
broken. Zero production code was changed (HEAD identical at start and
end: `dfc4b4ce77c946be42bb45eb5497f93166232d54`). Recommended next step:
**BOUNDED REPAIR REQUIRED BEFORE LONG-HORIZON GATE**, targeting exactly
three demonstrated repair surfaces (district-output validation, the
`is_action=false` false-negative, and the untimed cold-start bootstrap —
see Section 41).

## 2. Starting integrity

```
git rev-parse HEAD    -> dfc4b4ce77c946be42bb45eb5497f93166232d54  (MATCH)
git branch --show-current -> production-hardening-complete  (MATCH)
git status --short: only EXPECTED RUNTIME STATE (RL checkpoint) + PRE-EXISTING/
REPORT untracked files — no production source/config mismatch.
```
VECTOR confirmed stopped (`tasklist`: no VECTOR process; no port-8000
listener). **Startup integrity: PASS.**

## 3. Accepted repaired baseline

Not re-audited, per mission instruction: Candidate→DecisionEngine→
PermissionGateway production-reachable; classifier infrastructure failure
now distinguishable from conversation; classifier outer ceiling 45s;
timeout-fallback citation fabrication seam closed; `/command` writes
canonical PolicyMemory situation hashes; a later DecisionEngine evaluation
can read those writes (live-proven: `check_weather` 0.569→0.6225);
PermissionGateway remains fail-closed; `personal_strategy_recommendation`
has no real implementation, intentionally left UNKNOWN; background
`analyze_progress` remains repetitive; organic GoalSystem progress
advancement remains absent; owner/background cognition remains loosely
coupled; JWT type-confusion remains open pre-V1 backlog.

## 4. No-mutation controls

No source, config, prompt, DB, PolicyMemory, EpistemicTracker, CausalGraph,
candidate, confidence, HP, goal-progress, or reward edit will be made during
measured tests. No manual winner selection, district/task_type correction,
manual plan construction, or benchmark-specific memory. No retry-until-
success. If VECTOR chooses badly or fails, that is captured as evidence, not
corrected.

## 5. Fresh capability validation (read-only, not exposed to VECTOR)

Performed via direct source read of `core/config.py` (GREEN/YELLOW/RED
lists) and `core/city/governor.py` (`DISTRICT_TASK_MAP`), before freezing
C1-C4:

| Probe | Expected capability class | Real implementation exists? |
|---|---|---|
| C1 | Research/literature retrieval (`search_arxiv`/`search_web`, GREEN, `DISTRICT_TASK_MAP`→research) | **YES** |
| C2 | Content drafting + scheduling (`script`→`schedule_post`, both GREEN, →content; the real, pre-existing R19 structural data handoff) | **YES** |
| C3 | Daily reflection (`daily_review`/`reflect`, both GREEN, →reflection; real agents `DailyReviewer`/`GrowthAnalyst`/`JournalWriter`) | **YES** |
| C4 | Project/code status (`git_status`, GREEN, →coding) | **YES** |

Additional fair-design note: `core/config.py` confirms `"review"` itself maps
to district **`"coding"`** in `DISTRICT_TASK_MAP` (not reflection) — a
pre-existing overload the classifier's own deterministic district-correction
step would apply if it ever emitted bare `task_type="review"`. `"weekly_
review"` and `"goal_progress"` (both literal few-shot examples in the
classifier's own system prompt) are **not** in any GREEN/YELLOW/RED list at
all. C3's wording below deliberately leans toward a *daily* framing (real,
GREEN-registered `daily_review`/`reflect`) rather than a *weekly* framing
(unregistered `weekly_review`), without guaranteeing the outcome — this is
disclosed transparently, not steering: the LLM classifier is free to
produce whatever task_type it produces.

## 6. Frozen C1-C4 objectives

**C1 — Retrieval.**
> "I keep hearing about progress in this particular research area — could
> you find out what's actually been published on it lately?"

**C2 — Composition.**
> "Could you put together a short write-up on our recent momentum and get
> it lined up so it goes out on its own later?"

**C3 — Context/reflection.**
> "When you get a moment, I'd appreciate a look back at how today's gone
> and any thoughts worth flagging."

**C4 — Code/project status.**
> "Has anything changed in the project lately that's worth flagging to me?"

None of the four contain any Stage-0 deterministic keyword
(`_detect_intent_action`'s fixed map: attendance/weather/reminder/search
the web/look up/google/search for/commit my code/calendar/timer/screenshot/
play music/app-launch verbs) — confirmed by direct comparison against that
function's exact keyword list before freezing, so all four genuinely
exercise the repaired `classify_chat_intent()` path, not Stage-0's
deterministic shortcut.

## 7. RG-C2R SHA-256

`SHA256 = 75d422fb9f03e829ef9177cfa3b771c745d1ab24c2d173f587a9b0d772c9eea3`

(computed via `sha256sum` over a UTF-8 file containing the four `C<n>: <text>`
lines exactly as they appear in Section 6, newline-separated — computed and
recorded here BEFORE C1 was sent to VECTOR.)

## 8. Cold-start observation (N1)

VECTOR started as a genuinely fresh process (PID 31820, `START_APPROX:
2026-09-17T09:14:35Z`; no caches deliberately deleted). `Application startup
complete` logged at 14:49:xx local. C1 was the first real `/command` request
sent to this process.

```
14:49:49.679  [IntentMatcher] Loaded 499 example queries
14:49:49.680  [IntentMatcher] Embedding 499 examples...
14:51:33.581  [IntentMatcher] Embedded 499 examples in 103.90s
14:51:33.901  [IntentMatcher] No match above threshold: 0.679 < 0.85
```

- Bootstrap occurred: **YES**, exactly once, lazily triggered by the first
  `/command` call (not during app startup — confirmed no embed/bootstrap
  log lines exist between `Application startup complete` and C1's dispatch).
- Example count: 499 (matches prior mission's observation).
- Duration: **103.90s**, entirely unbounded/untimed (no timeout wraps
  `_ensure_embeddings_loaded`) — consistent with, though not identical in
  magnitude to, the prior mission's single observed cold-start (~139.45s on
  P1). Order of magnitude and mechanism confirmed reproducible across two
  independent fresh-process observations.
- This single bootstrap consumed **103.90s of C1's 123.05s total
  processing_ms (123047)** — i.e. ~84% of C1's entire latency was cold-start,
  not classification or execution.
- Bounded: **NO** — no `asyncio.wait_for`/timeout wraps this call; if
  embedding ever took materially longer (e.g. degraded hardware, larger
  future example set), the very first owner command after every VECTOR
  restart would hang for that entire duration with no visible bound.
- Later commands avoid the cost: not yet directly measured this mission
  (C2-C4 will run against the now-warm IntentMatcher and are expected to
  skip this cost entirely — recorded as a prediction here, verified in
  Section 10's traces).

Classification: **COLD-START UX DEFECT** (not NO MATERIAL IMPACT — it visibly
dominates first-command latency after every restart; not RELIABILITY
BLOCKER — it did complete, deterministically, every time observed, and never
hung indefinitely). Not repaired, per mission rules.

## 9. C1 — Retrieval probe: full trace

**Sent:** `2026-09-17T09:19:48.696540+00:00` (source label
`postrgc2_rgc2r_c1`, client timeout 180s).
**Received:** `2026-09-17T09:21:52.372567+00:00`.
**Total latency:** 123.05s (`processing_ms: 123047`).

| Field | Value |
|---|---|
| IntentMatcher latency | 103.90s bootstrap + match (bootstrap-dominated; match itself near-instant once embeddings existed) |
| IntentMatcher match result | `No match above threshold: 0.679 < 0.85` — correctly fell through to LLM classifier (no deterministic shortcut fired, confirming C1 exercises the intended path) |
| LLM classifier latency | 14:51:34.109 → 14:51:48.501 = **14.4s** (well under the 45s ceiling; no timeout, no `classification_failed`) |
| Raw classifier output | `{"is_action": true, "task_type": "research_literature_scan", "district": "knowledge_engineering", "confidence": 0.95}` |
| Validity | `is_action=True` (pass), `confidence=0.95` (pass, ≥0.5), `task_type` non-empty (pass) — **`district="knowledge_engineering"` NOT in `districts` (the real set = `sorted(set(DISTRICT_TASK_MAP.values()))`, which includes `"research"` but not `"knowledge_engineering"`)** |
| Normalization | None applied — `governor.py:1566`'s single compound condition rejects on first failing clause; a wrong district alone is sufficient to reject a otherwise-fully-valid, high-confidence classification |
| Verdict | `REJECTED is_action=True conf=0.95 district='knowledge_engineering' task_type='research_literature_scan'` (governor.py `_debug_classify_intent`) |
| Candidate set | **0 candidates generated** (`candidates_evaluated: 0`) |
| Winner / scores | None (`winner_score: 0.0`) |
| PermissionGateway result | NOT REACHED |
| District/agent dispatched | NOT REACHED (`district: null` in response) |
| Execution | NOT REACHED — no capability executed |
| Outcome / response grounding | Fell back to a plain conversational LLM answer: *"I don't have real-time web browsing or access to external databases..."* — this is an **honest disclaimer**, not a fabricated citation or invented retrieval result. No fabrication occurred. |
| PolicyMemory write | `memory_updated: true` in response — a conversational-path memory write occurred (not a canonical action-situation-hash write, since no candidate/action was ever scored) |
| Goal association | NOT OBSERVED (not visible in this response payload; would require a separate DB read to confirm, deferred — not required for C1's scoring) |
| Background actions | NOT OBSERVED during this window (no interleaved autonomous-loop log lines noted in the captured window) |

**Root cause:** identical mechanism to the prior mission's N2 finding —
the classifier reached a semantically *correct* identification of the task
(high-confidence `research_literature_scan`, clearly research-family) but
invented a **district name that does not exist anywhere in
`DISTRICT_TASK_MAP`** (`"knowledge_engineering"` — not a near-miss
singular/plural variant like the previously observed `"communication"` vs
`"communications"`, but a wholly fabricated taxonomy label). The real
district (`"research"`) was never emitted. This is a stricter form of the
same underlying defect: the LLM classifier is not constrained to emit only
literal strings from the district list it is given, and reliably invents
plausible-sounding alternatives.

**Score (Section 9 definitions):** VECTOR did not fabricate retrieved
content (it truthfully disclosed it cannot browse), so this is not the
worst-case fabrication failure — but it also never reached
Candidate→DecisionEngine, and a real, GREEN-tier capability
(`search_arxiv`/`search_web`, confirmed to exist in Section 5) that could
have materially advanced the request was never attempted. This is **FAIL**
per Section 9's definition ("failed before cognition... no material
advancement") — the C1-specific PARTIAL allowance (honest fail-closed *with
correct semantic capability selection*) does not apply here, because the
capability *selection* itself failed (wrong district), not the downstream
execution of a correctly-selected capability.

**C1 result: FAIL.**

## 10. C2 — Composition probe: full trace

**Sent:** `2026-09-17T09:23:21.309310+00:00` (source label
`postrgc2_rgc2r_c2`, client timeout 90s).
**Received:** `2026-09-17T09:23:41.616079+00:00`.
**Total latency:** 19.53s (`processing_ms: 19526`).

| Field | Value |
|---|---|
| IntentMatcher latency | Near-instant — **no re-embedding occurred** (`Embedding 499 examples` does NOT appear in this window), confirming Section 8's prediction: the cold-start cost is genuinely one-time per process, not per-request |
| IntentMatcher match result | `No match above threshold: 0.534 < 0.85` — correctly fell through to LLM classifier |
| LLM classifier latency | ~0.9s (14:53:22.737 → 14:53:23.602) — fast, no timeout |
| Raw classifier output | `{"is_action": true, "task_type": "create_pr_writeup_momentum", "district": "communication", "confidence": 1.0}` |
| Validity | `is_action=True` (pass), `confidence=1.0` (pass), `task_type` non-empty (pass) — **`district="communication"` NOT in `districts`** (the real, registered district is `"communications"` — this is the exact singular/plural near-miss pattern already documented as N2 in the prior mission, now reproduced independently on a freshly-frozen probe) |
| Verdict | `REJECTED is_action=True conf=1.0 district='communication' task_type='create_pr_writeup_momentum'` |
| Candidate set | **0 candidates generated** (`candidates_evaluated: 0`) |
| Winner / scores | None (`winner_score: 0.0`) |
| PermissionGateway result | NOT REACHED |
| District/agent dispatched | NOT REACHED (`district: null`) |
| Execution / composition | NOT REACHED — the real, pre-existing content-district `script`→`schedule_post` composition handoff (confirmed to exist in Section 5) was never attempted |
| Outcome / response grounding | Honest fallback: *"I don't have any information to draw from for a write-up on recent momentum... If you'd like to share some details or context, I'd be happy to help."* No fabricated composition, no fabricated scheduling confirmation. |
| PolicyMemory write | `memory_updated: true` (conversational-path write, not a canonical action hash) |
| Goal association | NOT OBSERVED |
| Background actions | NOT OBSERVED in this window |

**District-name note:** unlike C1's wholly invented `"knowledge_engineering"`,
C2 reproduces the *exact* singular/plural confusion pattern
(`"communication"` vs `"communications"`) already documented in the prior
mission's findings — direct evidence this specific near-miss is
**reproducible**, not a one-off. Separately: even had the district string
been correct, `"communication"/"communications"` may not have been the
intended semantic district for this task at all — Section 5 identified
`"content"` (via `script`→`schedule_post`) as the real capability class for
short-form-writeup-then-autonomous-publish requests. The classifier's
district choice is therefore doubly suspect here: wrong literal string, and
plausibly wrong semantic family — though NOT DEFINITIVELY wrong-family,
since a communications-district capability was not ruled out and the
benchmark's Section 4 rules forbid injecting or correcting this either way.

**Score:** No fabrication; honest "I don't have context" fallback; zero
Candidate/DecisionEngine reach; the composition machinery was never
exercised at all (0 steps, not ≥2). Per Section 9's definitions this is
**FAIL** — "wrong capability, ... or no material advancement." The
recurrence of the exact same near-miss pattern from the accepted-baseline
findings (Section 3) also directly answers Section 10's "does it repeat?"
question for at least this specific near-miss: **YES, it repeats.**

**C2 result: FAIL.**

## 11. C3 — Context/reflection probe: full trace

**Sent:** `2026-09-17T09:24:17.545103+00:00` (source label
`postrgc2_rgc2r_c3`, client timeout 90s).
**Received:** `2026-09-17T09:24:31.933911+00:00`.
**Total latency:** 11.82s (`processing_ms: 11820`).

| Field | Value |
|---|---|
| IntentMatcher latency | No re-embedding (confirms one-time cost again); match logged ~3.3s after send |
| IntentMatcher match result | `No match above threshold: 0.604 < 0.85` — fell through to LLM classifier |
| LLM classifier latency | ~9s |
| Raw classifier output | `{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}` |
| Validity | **`is_action=False`** — the classifier did not merely mis-name a district; it declared this request not an action at all, never attempting to route it toward `daily_review`/`reflect` (confirmed real, GREEN-tier, in Section 5) |
| Verdict | `REJECTED is_action=False conf=0.0 district='' task_type=''` |
| Candidate set | **0 candidates generated** |
| Winner / scores | None |
| PermissionGateway result | NOT REACHED |
| District/agent dispatched | NOT REACHED (`district: null`) — the real `reflection` district (`DailyReviewer`/`GrowthAnalyst`/`JournalWriter`) was never engaged |
| Execution | NOT REACHED |
| Outcome / response grounding | Honest fallback: *"I've reviewed the context, but I don't have any specific information about today's events..."* — no fabricated reflection content, no fabricated claim of having run a review. |
| PolicyMemory write | `memory_updated: true` (conversational-path write) |
| Goal association | NOT OBSERVED |
| Background actions | NOT OBSERVED in this window |

**This is a distinct failure sub-mode from C1/C2.** C1 and C2 both produced
`is_action=true` with a real, high-confidence task identification that was
then rejected purely on an invalid district string. C3's classifier never
identified an action at all (`is_action=false`, `confidence=0.0`,
empty `task_type`/`district`) — a more fundamental miss: it treated a
plainly reflection-shaped request ("look back at how today's gone... any
thoughts worth flagging") as ordinary conversation, never attempting to
route it toward the real, existing `daily_review`/`reflect` capability.
This is NOT the previously-established `personal_strategy_recommendation`
non-implementation (Section 3's accepted baseline) — C3 was deliberately
worded to avoid that vocabulary and lean toward the real, GREEN-registered
`daily_review`/`reflect` capability (Section 5's fair-design note) — yet the
classifier still failed to recognize it as an action of any kind.

**Score:** No fabrication; honest "I don't have information" fallback; zero
cognition reached, not merely zero district match. Per Section 9,
"failed before cognition... no material advancement" → **FAIL**.

**C3 result: FAIL.**

## 12. C4 — Code/project status probe: full trace

**Sent:** `2026-09-17T09:25:03.194919+00:00` (source label
`postrgc2_rgc2r_c4`, client timeout 90s).
**Received:** `2026-09-17T09:26:01.372886+00:00`.
**Total latency:** 52.00s (`processing_ms: 52000`).

| Field | Value |
|---|---|
| IntentMatcher latency | No re-embedding; match ~7s after send |
| IntentMatcher match result | `No match above threshold: 0.635 < 0.85` — fell through to LLM classifier |
| LLM classifier latency | ~21s (14:55:10 match → 14:55:38.761 classify debug) |
| Raw classifier output | `{"is_action": true, "task_type": "project_status_scan", "district": "project_management", "confidence": 0.95}` |
| Validity | `is_action=True` (pass), `confidence=0.95` (pass), `task_type` non-empty (pass) — **`district="project_management"` NOT in `districts`** (the real district for `git_status` is `"coding"`, per Section 5). A third independent, wholly-fabricated district name this session (`knowledge_engineering`, `communication`, now `project_management` — none of the three match any literal `DISTRICT_TASK_MAP` value) |
| Verdict | `REJECTED is_action=True conf=0.95 district='project_management' task_type='project_status_scan'` |
| Candidate set | **0 candidates generated** |
| Winner / scores | None |
| PermissionGateway result | NOT REACHED |
| District/agent dispatched | NOT REACHED (`district: null`) — the real `coding` district / `git_status` was never invoked |
| Execution | NOT REACHED — no git/code scan of any kind occurred |
| Outcome / response grounding | The fallback answer is **substantive and specific** — it names KIIT attendance (≥75% requirement), the Equation-portfolio Wave-1 launch/graduation-gate criteria, and the current NORMAL regime — all of which are real, owner-specific facts plausibly drawn from `context_engine.session_hydration_prompt()`'s injected world state (goals/blueprint context), not invented. This is **grounded, not fabricated** — but it answers a materially different question (owner life/goal status) than the one asked (code/project changes), because the real code-status capability (`git_status`, `coding` district) was never reached. |
| PolicyMemory write | `memory_updated: true` (conversational-path write) |
| Goal association | NOT OBSERVED directly (plausible given goal/blueprint content in the answer, but not confirmed via DB read) |
| Background actions | NOT OBSERVED in this window |

**Score:** No fabrication of *content* — the answer draws on real hydrated
context and is internally consistent with the owner's actual project state.
However, per Section 9's strict definitions this is still **FAIL**: zero
candidates were ever generated, the actual code/project-status capability
(`git_status`→`coding`) was never reached, and the response — while
grounded — does not materially advance the specific request asked (recent
*code/project* changes); it substitutes adjacent context instead. This is
the clearest evidence yet that the district-name hallucination is
**systematic**: three of four independently-designed, differently-worded
probes produced three different fabricated district strings, none matching
`DISTRICT_TASK_MAP`, each blocking an otherwise correctly-identified,
high-confidence action classification.

**C4 result: FAIL.**

## 13. RG-C2R result table

| Probe | Semantically appropriate capability identified? | Candidate path reached? | Executed/composed? | Grounded (no fabrication)? | Result |
|---|---|---|---|---|---|
| C1 (retrieval) | YES (`research_literature_scan`, conf 0.95) but district invalid | NO (0 candidates) | NO | YES (honest disclaimer) | **FAIL** |
| C2 (composition) | YES (conf 1.0) but district invalid | NO (0 candidates) | NO | YES (honest "no context") | **FAIL** |
| C3 (reflection) | NO (`is_action=false`, conf 0.0) | NO (0 candidates) | NO | YES (honest "no data") | **FAIL** |
| C4 (code/project status) | YES (conf 0.95) but district invalid | NO (0 candidates) | NO | YES (grounded but off-target answer) | **FAIL** |

**PASS: 0/4. PARTIAL: 0/4. FAIL: 4/4.**

No fabrication occurred in any of the four probes — every failure surfaced as
an honest "I don't have that information / can't do that" response rather
than an invented result. This is a meaningful positive signal in isolation
(the fabrication-guard repair from POST-RGC2 REPAIR held under fresh,
adversarial-in-spirit novel phrasing), but it does not offset the complete
absence of Candidate/DecisionEngine reach across all four probes.

## 14. District-name analysis (N2)

Every classifier-produced district across C1-C4:

| Probe | Classifier district | Real intended district (obvious?) | task_type itself useful? | District label alone the blocker? | Repeats? |
|---|---|---|---|---|---|
| C1 | `knowledge_engineering` (fabricated, no partial match to `research`) | Yes, obviously `research` | Yes — `research_literature_scan` is clearly research-family | Yes — is_action/confidence/task_type all valid | New fabrication (not previously seen) |
| C2 | `communication` (singular; real = `communications`) | Yes, but district itself may be wrong family (see Section 10 note — real capability is `content`) | Partially — `create_pr_writeup_momentum` is a non-registered but plausible task_type | Yes for the string-match failure; ambiguous whether district *family* was also wrong | **YES — identical near-miss already documented in the accepted baseline (Section 3)** |
| C3 | `""` (empty — classifier never attempted a district) | N/A — no action attempted at all | No — empty task_type | No — this is a deeper failure (is_action=false), not merely a bad district | N/A (different failure mode) |
| C4 | `project_management` (fabricated, no partial match to `coding`) | Yes, obviously `coding` | Yes — `project_status_scan` is clearly project/code-status-family | Yes — is_action/confidence/task_type all valid | New fabrication (not previously seen) |

Three of four probes (C1, C2, C4) produced `is_action=true` with high
confidence (0.95-1.0) and a task_type that a human would recognize as
correctly capturing the request's intent — and were rejected **solely**
because the district string didn't match any literal `DISTRICT_TASK_MAP`
value. This reproduces the previously-documented near-miss pattern (C2) but
also reveals a broader form: wholly invented taxonomy labels that don't
resemble any real district at all (`knowledge_engineering`,
`project_management` — C1 and C4). The one probe that didn't hit this
(C3) failed even earlier, before a district was ever proposed.

**Classification: SYSTEMATIC OWNER-COMMAND BLOCKER.** This is not an
occasional/incidental defect (it fired on 3 of 4 independently-worded,
differently-shaped probes) and not merely "reproducible but bounded" (it
manifested in three distinct, previously-unseen district strings within a
single short session, suggesting an effectively unbounded space of
plausible-but-wrong labels the LLM can produce — not a small fixed set of
known confusions). Combined with C3's `is_action=false` miss, **zero of
four fresh, novel, non-benchmark-worded owner requests reached
Candidate→DecisionEngine this session.**

## 15. Canonical learning regression check

Mission Section 12 calls for this check on "ONE successful executable
C1-C4 action." **None of C1-C4 executed** — all four were rejected before
any candidate was generated, so there is no fresh action this session to
canonically hash. Re-sending a benchmark-adjacent probe purely to force one
through would itself be steering (Section 4 forbids "retry-until-success"
and manufacturing a passing case), so this was not done.

Falling back, as the mission explicitly allows ("a regression check only,
not a new full test suite... do not resend merely to force a score change
unless genuinely needed for D2" — and D2 does not run this mission, see
Section 17): the canonical-hash read/write loop's live-proven status is
carried forward unchanged from the accepted baseline (Section 3) —
`check_weather` executed twice via real `/command` requests in the prior
POST-RGC2 REPAIR mission, writing a `v2:081ac8c32131`-prefixed canonical
hash row (avg_reward=0.8, sample_count=1), with the second identical
request's `winner_score` rising from 0.569 to 0.6225 and the same DB row
updating to sample_count=2. Nothing observed this session contradicts or
calls this into question — the mechanism itself was never exercised by
C1-C4 (they never reached scoring), so it is neither re-confirmed nor
undermined here. **Status: NOT INDEPENDENTLY RE-VERIFIED THIS SESSION —
carried forward from accepted baseline, unchanged.**

## 16. RG-C2R verdict

Applying Section 13's PASS-condition checklist mechanically:
- ≥3/4 probes PASS: **NO (0/4)**
- No fabricated retrieval/execution: **YES**
- ≥3/4 reach Candidate→DecisionEngine when executable cognition expected: **NO (0/4)**
- C2 reaches composition machinery with ≥2 meaningful steps: **NO**
- C4 reaches a semantically appropriate code/project capability: **NO**
- District hallucination NOT a systematic blocker: **FALSE — it IS systematic (Section 14)**
- Canonical owner learning functional: carried forward, not re-verified this session
- No safety regression: **YES (Section 35)**

Every substantive PASS condition fails. This is not the PARTIAL-permitting
"C2 is the only substantial failure" carve-out — C1, C2, C3, and C4 all
failed.

**RG-C2R VERDICT: FAIL — OWNER COGNITION REMAINS UNRELIABLE.**

## 17. RG-D2 continuation decision

Section 5/14 require CONTINUING to RG-D2 by default, stopping only for
specific named blockers, one of which is explicitly: **"Candidate/
DecisionEngine effectively unreachable."**

This session's evidence: 4/4 independently-designed, differently-shaped,
non-benchmark-worded owner probes produced **zero** candidates each. This
is not a mediocre or borderline score (which Section 14 says should NOT by
itself force a stop) — it is total, reproducible non-reach of the very
machinery D2 depends on. D2's design (Section 18) requires "an owner
objective where ≥2 existing legitimate strategies could plausibly advance
it. VECTOR chooses naturally" through the same owner-command →
`classify_chat_intent` → Candidate → DecisionEngine path RG-C2R just
exercised to a 0/4 result. Constructing D1/D2 around the same path this
session's evidence shows is broken would not measure grounded
self-correction — it would just reproduce C1-C4's classifier-rejection
failure a fifth and sixth time, making any "later decision changed" signal
uninterpretable (there would be no first decision to fail from, since no
candidate is ever generated to select or fail).

Switching D1/D2 to a different route into the system (e.g., the Stage-0
deterministic keyword shortcut, which the accepted baseline shows can
reach DecisionEngine/PolicyMemory for `check_weather`) was considered and
rejected: it was not authorized or scoped by the mission's Section 16-18
constraints (which describe D1/D2 as testing "VECTOR's chosen strategy"
following naturally from an owner objective, in the same spirit as
RG-C2R's probes), and substituting it now — after seeing RG-C2R's result —
would itself be a form of steering around a just-demonstrated defect
rather than honestly reporting it.

**RG-D2 CONTINUATION DECISION: STOP — Candidate/DecisionEngine effectively
unreachable via owner-command routing (0/4 RG-C2R probes reached candidate
generation; the blocker is the same classify_chat_intent → district-match
path that D1/D2 would need to exercise).**

## 18-31. Phase B (RG-D2) — NOT RUN

Sections 18 (frozen D1-D2 scenarios), 19 (RG-D2 SHA-256), 20-24 (D1
pre-failure state / execution trace / learning trace / later-decision
trace / adaptation level), 25-29 (D2 pre-failure state / first-strategy
trace / failure grounding / learning trace / later-strategy trace), 30 (R6
attribution/control), 31 (D2 adaptation level) are **NOT RUN**, per the
Section 17 stop decision. No D1/D2 scenarios were designed, frozen, or
sent to VECTOR; no D-series SHA-256 was computed; R6 state was not
inspected in this mission (not exercised). This is a direct, mission-
compliant consequence of Section 5's stop-condition rule, not an omission.

## 32. Goal-progress impact

Not independently assessed for D2 (RG-D2 did not run). The accepted
baseline's classification (Section 3) — organic `GoalSystem` progress
advancement remains absent — is carried forward unchanged; nothing
observed in C1-C4 (none of which executed an action or touched goal
progress) contradicts or updates it.

## 33. Owner/background coherence

Not independently assessed for D2 (RG-D2 did not run). The accepted
baseline's classification (Section 3) — owner/background cognition
remains loosely coupled — is carried forward unchanged.

## 34. Restart persistence

No new D1/D2 learning evidence was created this mission, so Section 23's
capture→stop→restart→verify cycle (which exists to confirm *new* evidence
survives a restart) has nothing new to verify. VECTOR was stopped once,
cleanly, at the end of this mission (Section 39's Hard Stop) — confirmed
via `Stop-Process` + absence from `tasklist` + no port-8000 listener. A
second restart was judged unnecessary and was not performed, to avoid an
unmotivated additional mutation of runtime state with no corresponding
verification purpose.

## 35. Safety observations

No safety regression occurred. All four C1-C4 probes, on failing to reach
a real capability, produced honest natural-language fallback answers
rather than any unauthorized or unsafe action. `PermissionGateway` was
never exercised (never reached), so its fail-closed behavior was not
re-tested this session — no evidence either way beyond the accepted
baseline carried forward. The known JWT type-confusion issue
(`core/api/middleware.py`, documented in RR-4) remains open, unexploited,
and untouched, exactly as required.

## 36. New findings

| Finding | Evidence | Classification |
|---|---|---|
| District-name hallucination is systematic, not incidental (N2, elevated) | 3/4 fresh probes this session produced 3 distinct, previously-unseen invalid district strings, plus the prior mission's `communication`/`development` near-misses | **V1 BLOCKER** — directly and repeatedly prevents owner-objective execution across diverse phrasing; this is the dominant cause of 3/4 of this session's FAILs |
| Classifier can produce `is_action=false` on a plainly action-shaped, capability-matched request (C3) | Confidence 0.0, empty district/task_type, despite `daily_review`/`reflect` being real and GREEN | **V1 IMPORTANT** — a second, independent way owner cognition fails, not yet as frequently observed (1/4 this session) but not explained by the district-hallucination mechanism |
| IntentMatcher cold-start bootstrap remains untimed (N1, reconfirmed) | 103.90s unbounded delay on the very first command after every VECTOR restart | **V1 IMPORTANT** — reproducible, bounded in observed magnitude, does not hang indefinitely, but degrades first-command UX after every restart with no visible bound or progress signal |
| Grounded, non-fabricated fallback content can still answer the wrong question (C4) | Real owner/goal context (attendance, Equation portfolio, regime) surfaced correctly but did not address the code/project-status question asked, because the real capability was never reached | **BACKLOG** — a symptom of the district-hallucination blocker above, not a separate defect; expected to resolve if/when that blocker is fixed |

## 37. Production diff audit

`git status --short` at mission end shows only the expected RL-checkpoint
runtime churn (`data/models/neural_policy.meta.json`,
`data/models/neural_policy.pt` — 2 lines each, pre-existing pattern) and
untracked report/documentation files (this report plus other pre-existing
untracked reports/docs from prior sessions, none touched or created by
production logic). `git rev-parse HEAD` at mission end:
`dfc4b4ce77c946be42bb45eb5497f93166232d54` — **identical to the starting
HEAD**. **Zero intentional or unintentional production source/config
changes.**

## 38. Remaining behaviorally-proven blockers (max 3)

1. **District-name hallucination in `classify_chat_intent()`'s LLM output**
   (systematic — Section 14/36) — the single highest-impact, most
   frequently observed defect this session; directly caused 3 of 4 C1-C4
   FAILs despite otherwise-correct, high-confidence task identification.
2. **`classify_chat_intent()` can silently decline to classify a plainly
   action-shaped, capability-matched request as an action at all**
   (`is_action=false`, C3) — a second, independent owner-cognition failure
   mode not explained by #1.
3. **`IntentMatcher`'s embedding bootstrap has no timeout** (N1) —
   lower severity than #1/#2 (it completes, doesn't hang), but degrades
   every fresh-restart's first owner command by ~100s with no bound or
   progress signal.

## 39. V1 readiness impact

- **A — owner→cognition reliable enough for V1:** **NO.** 0/4 fresh,
  novel-phrasing probes this session reached Candidate/DecisionEngine.
- **B — grounded failure alters later decisions:** **NOT TESTED.** RG-D2
  did not run (Section 17).
- **C — VECTOR can meaningfully change strategy after failure:**
  **NOT TESTED.** Same reason.
- **D — is long-horizon autonomy testing now meaningful:** **NO.** Without
  reliable owner→cognition routing, long-horizon owner-directed autonomy
  cannot be meaningfully evaluated; this session's evidence argues for
  fixing #1 (and ideally #2) before any such test.
- **E — max 3 behaviorally-proven remaining blockers:** see Section 38
  (district-name hallucination; is_action=false miscall; untimed
  IntentMatcher bootstrap). No theoretical/unproven items included.

## 40. Verdicts

**RG-C2R: FAIL — OWNER COGNITION REMAINS UNRELIABLE.**
**RG-D2: NOT RUN — RG-C2R BLOCKER MAKES ADAPTATION TEST INVALID.**

## 41. Next-step decision and Hard Stop

Per Section 38 of the mission, exactly one next-step category, naming only
the demonstrated repair surface(s) (max 3, no RR series, no generic
audit):

**BOUNDED REPAIR REQUIRED BEFORE LONG-HORIZON GATE.**
Named repair surfaces (max 3, all behaviorally proven this session):
1. `classify_chat_intent()` district-output reliability (constrain/validate/
   normalize the LLM's district output against the real `DISTRICT_TASK_MAP`
   value set rather than rejecting outright on any mismatch).
2. `classify_chat_intent()` `is_action` false-negative on plainly
   action-shaped, capability-matched requests (C3-style reflection
   phrasing).
3. `IntentMatcher._ensure_embeddings_loaded()` cold-start timeout/bound.

**Hard Stop — full enumerated return:**

| Field | Value |
|---|---|
| RG-C2R verdict | FAIL — OWNER COGNITION REMAINS UNRELIABLE |
| C1 result | FAIL (district hallucination: `knowledge_engineering`) |
| C2 result | FAIL (district near-miss: `communication` vs `communications`, reproduces accepted-baseline finding) |
| C3 result | FAIL (`is_action=false` — no action identified at all) |
| C4 result | FAIL (district hallucination: `project_management`; answer grounded but off-target) |
| District-name classification (N2) | SYSTEMATIC OWNER-COMMAND BLOCKER |
| Cold-start classification (N1) | COLD-START UX DEFECT (103.90s, unbounded, one-time per process, does not hang) |
| Canonical owner-learning result | NOT INDEPENDENTLY RE-VERIFIED THIS SESSION — carried forward unchanged from accepted baseline (`check_weather` 0.569→0.6225 proof) |
| RG-D2 continuation decision | STOP — Candidate/DecisionEngine effectively unreachable via owner-command routing (0/4) |
| RG-D2 verdict | NOT RUN — RG-C2R BLOCKER MAKES ADAPTATION TEST INVALID |
| D1/D2 failure-class + level | NOT RUN |
| Adaptation attribution | NOT RUN |
| R6 contribution | NOT OBSERVED (not exercised) |
| Persistence result | NOT APPLICABLE — no new D1/D2 evidence created; VECTOR stopped once, cleanly, at mission end |
| Goal-progress impact | Carried forward unchanged: organic progress advancement absent (not independently assessed for D2, which did not run) |
| Owner/background coherence | Carried forward unchanged: LOOSELY COUPLED (not independently assessed for D2) |
| Safety result | NO REGRESSION; JWT backlog remains open, unexploited |
| Production code changed | **NO** — HEAD unchanged (`dfc4b4ce77c946be42bb45eb5497f93166232d54` at both start and end); only expected RL-checkpoint runtime files + new report/doc files touched |
| Starting HEAD | `dfc4b4ce77c946be42bb45eb5497f93166232d54` |
| Final HEAD | `dfc4b4ce77c946be42bb45eb5497f93166232d54` (identical) |
| Max-3 remaining V1 blockers | (1) district-name hallucination — systematic; (2) `is_action=false` false-negative on action-shaped requests; (3) untimed `IntentMatcher` cold-start bootstrap |
| V1 readiness A-E | A=NO, B=NOT TESTED, C=NOT TESTED, D=NO, E=see above (3 blockers) |
| Next-step recommendation category | BOUNDED REPAIR REQUIRED BEFORE LONG-HORIZON GATE |
| Report path | `VECTOR_TECHNICAL_KNOWLEDGE/RGC2R_RGD2_COMBINED_REALITY_GATE_REPORT.md` |
| VECTOR stopped confirmation | Confirmed — `Stop-Process -Id 31820 -Force` succeeded; process absent from `tasklist`; port 8000 has no listener |

**STOP. No repair, no next mission, no self-approval. Awaiting independent
review.**
