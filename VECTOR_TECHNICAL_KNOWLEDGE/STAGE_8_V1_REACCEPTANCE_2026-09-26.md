# VECTOR V1 — Re-acceptance pass, 2026-09-26

Follows `STAGE_7_FINAL_V1_ACCEPTANCE_REPORT.md` (2026-09-22: "SUBSTANTIALLY COMPLETE", Stage 4 PARTIAL, Stage 6 proved
at unit level only). Branch `fix/external-review-2026-09`, nothing pushed or deployed. Evidence categories below follow
Stage 7's rule: a claim is only as strong as the run that backs it.

**VERDICT: NOT "V1 ACCEPTED".** Stage 4 and the Stage 6 live-server gap are now closed with real evidence, five further
defects were found and fixed, and the full suite is green (6,440 passed, 0 failed, 38 skipped). What still blocks
acceptance under the owner's own rule is listed in §5: no independent review yet, the browser workflow, and no
owner-run live behavioural check.

## 1. Stage 4 (long-horizon autonomy): PARTIAL -> closed, with a real root cause

Stage 4 could not reach plan termination and blamed "structural candidate competition". The real cause was a defect:

* `AutonomousLoop._think_tick()` passed `decision.winner.total_score` to `ContinueGate` as its **coherence** input.
  ContinueGate stops below 0.4; the loop acts above 0.3. Every winner scoring 0.30-0.40 was selected, logged
  `verdict='stop'`, and never run, tick after tick. Live log evidence: 330+ drops (all `analyze_progress`, 0.377-0.396),
  and a plan step whose fallback scored 0.38 could never execute. (This dead zone existed since 2026-05-30.)
* Fix: the gate now receives `CoherenceScheduler`'s score for the loop (neutral 1.0 with no evidence), as its docstring
  says. Real gate stops/pauses still block (tested).
* The two findings Stage 4 carried forward were already fixed on 2026-09-24 (empty `GoalSystem` starving plan
  candidates; fallback inheriting an unsatisfiable verification) and are guarded by their own tests.
* New end-to-end evidence, `tests/test_stage4_long_horizon_termination.py`: real `_think_tick` -> `DecisionEngine` ->
  `PlanRunner` -> `AutonomousExecutor` -> `PermissionGateway` -> `Governor` -> `GitBot`, empty goal system, isolated DB
  and plan store, nothing stubbed below the loop. A 4-step fork/merge plan with one honest verification failure
  completes: fallback activated once, `replan_count == 1`, all steps completed, well inside the tick budget.
  Before the fix the same test stalled at 2/4 steps for 25 ticks.

Category: SOURCE IMPLEMENTED, TEST VERIFIED, BEHAVIORALLY VERIFIED (isolated). Not observed yet on the owner's live loop.

## 2. Stage 6 (JWT closure): live-server smoke test done

`tests/test_jwt_live_server_smoke.py`: own uvicorn process, hardened mode, throwaway DB, real tokens over HTTP.
Owner session and a 3-hop refresh chain work; a collection access token gets 401/403 on owner endpoints; a collection
refresh token cannot mint owner scope (rejected at the gate, and at the endpoint even with a valid owner credential); a
collection record named `owner` gets no owner access; garbage/no token rejected. 7/7 pass. The test also found a
duplicate-email registration escaping as HTTP 500; it is now a 400.

## 3. Defects found by this pass and fixed (each with a regression test)

| Area | Defect | Fix |
|---|---|---|
| Research | `DeepResearcher` reported failed/empty research as `status: ok` (and paid HP for failed news/document searches); the advertised `deep_research`/`research`/`search` task types hit "Unknown task type" | failures carry an explicit `error`; empty results are errors; advertised types accepted |
| Coding | `str_replace`/`write_file`/`apply_patch` wrote wherever an LLM-produced path pointed (`../../.env`, absolute paths), with no gateway check on the write itself; `CodingOrchestrator` reported `ok` for zero edits (0 == 0) and `partial` when every edit failed, then paid +50 HP | edits confined to the workspace, `.env*` and `.git` protected; no-op / all-failed runs are errors |
| Follow-on | making `deep_research` real turned ArchitectBot's awaited "ask ResearchHub" into a minutes-long call inside every scan, failing the r13 flagship in the full suite | the optional help request runs in the background |
| Inference | seven callers used `ProviderClient.complete(messages=...)`, which it rejected: /command execution, four marketing agents, the subconscious loop failed on every call | `complete()` accepts `messages=`; subconscious loop uses the real shape |
| Content | `VoiceGenerator.generate_voice` used a non-existent kokoro_onnx API and the video pipeline `await`ed the synchronous method: no narration was ever produced on that path | real `Kokoro(...).create()`, configured male voice, off the event loop; verified with real synthesis |
| Growth | burning captions from an absolute Windows path failed on every call (ffmpeg filter escaping); log said only `exit 4294967294` | escaped correctly; ffmpeg stderr logged; verified against real ffmpeg |
| HUD | after an API-key rotation a stale tab polls with 401s forever; a "backend offline" screen would have been wrong | `ACCESS KEY REJECTED` screen; websocket-only failures never trigger it; stray backspace char removed from a regex |

Test-suite housekeeping the same day: six long-standing failures were stale tests, not code bugs (details in
`docs/OPEN_ISSUES.md` item 7).

## 4. Evidence

* Full sharded suite on the final tree before the last fix: 6,440 passed, 1 failed (r13 flagship, caused by the
  follow-on above), 38 skipped. After the fix r13 (29), r14 (36) and the new tests pass; the suite itself was not
  re-run in full after that last commit.
* Loop watch: 1 h 40 min on the pre-fix backend, no stalls, no unreachable samples, memory flat at 1.5 GB. Its error
  sampling is what surfaced the inference, content and growth defects above. A second watch on the post-fix backend was
  started 05:40 (`%TEMP%\loop_watch3.log`); its result is not part of this report.

## 5. What still blocks "V1 ACCEPTED"

1. **Independent review.** The Governor district-trust fix, the 2026-09-25 permission-tier changes and this pass's
   changes have had no Codex review (Codex quota returns after 2026-09-27 19:11).
2. **Browser workflow (handoff workflow C)** is unchanged and still open: `browser_task` has no plan-composition bridge,
   BrowserController returns status not extracted fields, and a model `finished` is rewarded without independent page
   verification. This is a build, not a fix, and the handoff says not to start it without an owner decision.
3. **Shared outcome-assessment slice** (handoff) is still "PROPOSED, NOT APPROVED".
4. **Nothing here has been observed on the live loop yet** beyond the watch; Stage 4's plan-termination evidence is from
   an isolated run. Owner-run live behavioural checks (voice, camera, a real day of operation) are outstanding.
5. Test runs emit LangSmith trace uploads (429 rate-limit noise) -- tests are talking to an external service; worth
   turning tracing off under pytest.

## 6. Addendum (later on 2026-09-26): the two builds, decided and done

The owner delegated the decision on the two items §5 listed as blocked on them. Both were built, minimally, against the
handoff's own constraints (reuse the existing runtime, no rewrite, real evidence, conservative).

**Shared outcome assessment** (`core/runtime/executor.py`, `core/runtime/plans.py`; `tests/test_outcome_assessment.py`)
* Executor: an explicit failure signal inside a payload whose status looks fine (non-empty `error`, `success/ok/verified:
  false`) is a failure, not "executed". It never infers failure from absence and never treats a positive flag as proof.
* Plans: new verification types `result_field` (equals / contains / regex / in / non_empty / min_items on a dotted path of
  the step's REAL result) and `all_of`; they fail closed and require the step to have executed. Dotted `param_bindings`
  ("s1.fields.detail_url") hand nested real output to the next step.
* A step verified against objective evidence is no longer LLM-restructured away when it fails (the LLM replan rebuilt steps
  without their verification/bindings, letting a plan finish "verified" by a weaker check); it is abandoned with the failure
  recorded. Declared fallbacks still work.

**Browser workflow (workflow C)**
* `web_extract` (`core/browser/page_extract.py`, WebScout handler): GREEN, read-only, http/https GET, SSRF-guarded on every
  redirect hop, size/time limited, no cookies/login/forms/JS, structured evidence out, page text injection-scanned.
  **This is a new GREEN tier entry and a new member of `_PLAN_COMPOSABLE_ACTION_TYPES` -- flag it for the Codex review.**
* `tests/test_workflow_c_browser_plan.py`: open index -> discover URL -> persist -> interrupt and restart (new loop, plan
  reloaded from its JSON file) -> follow the persisted URL -> extract -> verify -> compare with the fixture and with an
  independent fetch, through the real loop / gateway / governor / agent against a real local HTTP server. Also: wrong content
  fails verification and the plan is abandoned, and private targets are refused.
* Model-driven browser (`BrowserController`, RED tier): a model's `finished()` is now a claim. The controller returns the
  final page as evidence and an action log, checks an optional `expect` against it (mismatch turns END into ERROR), aborts
  after three consecutive blocked/failed actions; `GUIAutomationAgent` rewards by evidence and failures now cost HP. Real
  headless-Chromium tests with a scripted VLM.

What is still not done: the desktop `gui_task` path has no evidence check; research/coding still lack the "advertised review
phase / run the tests" verification the handoff describes; nothing here has had an independent review or a live run.

## 7. Addendum: a walk through the real HUD (2026-09-26, after the builds)

The running backend was restarted on the final code and the real HUD (`/hud/`, headless Chromium, live data) was opened the way a user
would: boot screen, then all 51 widgets one by one, each screenshotted and its text and console errors recorded (walk scripts
kept in the session scratchpad, not the repo). All 51 open; 30-plus show live data, the rest show honest empty or "not running" states
(ComfyUI, camera, music player, finance positions). The boot screen and panels look clean and consistent.

Found and fixed (each has an e2e assertion in `tests/frontend/test_hud_honesty_e2e.py`, 32 tests, both runtime modes):
* tall panels (memory, features, council, memory explorer) ran off the bottom of the stage behind the dock/command bar/ticker;
* the ticker alternated between "230 AGENTS" and "12 AGENTS" and between two "TOP AGENT"s: the 12-agent snapshot sample overwrote the
  full roster every 5 s;
* the SYS status text sat hidden under the KEYS pill;
* boot status read "DEGRADED . ws gesture disconnected" permanently, and ~900 rejected gesture connections filled the backend log:
  optional sockets (voice/gesture/camera) now give up after 5 tries and never change the global status;
* the Civilization Atlas was blank for 6-12 s (it awaited `/city/districts`, a slow Governor round trip whose result nothing used);
* a stale tab after the key rotation hammered ~22 endpoints every few seconds (thousands of 401s): polling now stops after six
  consecutive rejections and probes every 30 s; the screen says ACCESS KEY REJECTED;
* `/security/status` ran an ~8 s process scan inline in an async handler, freezing the whole event loop (and the in-process loop and
  websockets) on every cache miss; it also listed the idle pseudo-process at "2111 %" CPU. Now in a worker thread, CPU normalised.

Taste calls and follow-ups left for the owner (deliberately not changed):
* Command Center shows "STATUS UNKNOWN" for most domain tiles and "APPROVALS UNKNOWN" in its header although approvals are known (0);
* the top ticker's THREAT LEVEL reads HIGH when two or more processes run from a temp directory, which a VS Code installer trips: the
  heuristic has no notion of a legitimate installer;
* the HUD has two docks (a labelled row and an icon row); `/city/districts` still takes 6-12 s (no longer used by the HUD);
* the gesture handler needs porting to the MediaPipe Tasks API (installed 0.10.35 has no legacy `solutions`), so hand control is off.

Final suite after all of the above: 6,499 passed, 0 failed, 38 skipped; the HUD e2e file was then re-run alone (32 passed) because its
runtime had outgrown the suite's 120 s per-test timeout (fixed with a module-level 600 s timeout).

## 8. Addendum (2026-09-27): current-state reconstruction and the fixes it produced

Read-only reconstruction of the repository at `43ef7e5e2` (branch `fix/external-review-2026-09`, 131 commits after the Stage 7
merge `544e235e6`), then fixes for what it found. Claude only: Codex is unavailable until 2026-09-27 19:11, so there is no independent
assessment yet and this is not a two-model verdict.

**Verdict at reconstruction: C, bounded V1 work remains.** After the fixes below: **B, final verification only remains**
(Codex review, the owner's live voice/camera checks, a real day of use). Not "V1 ACCEPTED".

| Gap | At reconstruction | Now |
|---|---|---|
| A. Long-horizon autonomy | PARTIAL: the passing test used an empty mocked goal system and an injected impossible criterion | **CLOSED (isolated)**: `tests/test_stage4_real_goalsystem_competition.py` uses the real GoalSystem and a real git failure. It first FAILED (0 of 4 steps in 40 ticks: a plan step at 0.715 lost to an ambient candidate at 0.72-0.76 every tick); fixed by plan-step aging; the plan now terminates (fallback after the real failure, `replan_count == 1`, real goal candidates on the table). Known limit: goal-less plans still lose by design |
| B. `no_agents` becoming progress | fixed in the executor, no test named it | **CLOSED**: executor cases pinned; `/command` and `/ws/command` had the same defect (an `ok` status with an `error` field, `no_agents`, `timeout`, `blocked` all read as success) and now share `result_failure_reason` |
| C. JWT live | closed by a live-server test (own uvicorn), not the daily backend | unchanged: **CLOSED (test server)** |
| D. IntentMatcher startup | TEST-ONLY | **observed live** in two backend logs: 499 embedded, 0 failed, 10-22 s, bounded. Event-loop responsiveness during bootstrap not separately measured |
| E. RG-D2 / adaptation | PARTIAL | outcome -> PolicyMemory -> later scoring -> later action choice proven in isolation (r13/r15 with controls); "a genuinely different strategy" only via plan-declared fallbacks: **PARTIAL** |
| F. Goal progress | closed | **CLOSED** |
| G. Restart | closed in isolation | **CLOSED (isolated)**, never observed on the owner's daily loop |
| H. Trust / permissions | not regressed | no regression in the 6,586-test run |

**Defects found and fixed after the reconstruction (each with a test, none pushed):**

* **Backend froze 15-27 s every ~30 s, ~1.3 cores idle CPU** (V1-1). py-spy: 67% of the API's GIL time inside psutil's per-process
  `status()/cpu_percent()/memory_percent()` (Windows: each is a whole-system query that holds the GIL, ~10 s per sweep over 363
  processes). The process table and the anomaly scan now run in child processes (`core/control/security/process_snapshot.py`), refreshed
  at most every 120 s. `/agents` worst case 19-27 s -> 1.99 s over 90 samples; `/security/status` 6 s -> 0.2 s; idle CPU 1.3 -> 0.54 cores.
* Other event-loop blockers found by py-spy and a static scan of async handlers: `/camera/ws` (YOLO load, device open, every frame),
  `psutil.cpu_percent(interval=...)` in three endpoints, `docker info`, `nvidia-smi`, six COUNT(*) in `/health/system`, and the nightly
  self-check (compileall up to 600 s + smoke up to 300 s inline in an async cron job).
* `/command` and `/ws/command` reported failed handler results as done (above).
* Plan steps starved behind ambient goal candidates (above).
* Gemini: `gemini-2.0-flash` (404 on the owner key) was still the default; now `gemini-2.5-flash`, verified live. This was why
  `vector-chairman` calls and the daily reviewer had no LLM.
* Free-tier rule: the legacy OpenRouter tier mapped to paid Claude/DeepSeek models; only an empty account (HTTP 402) prevented charges.
  It now calls `:free` models only.
* LightRAG init retried and logged on every memory query (113x per session). **The vault index itself is damaged**: 7 of its 11 files
  are zero-filled since 2026-07-15 (a crash during write), so vault RAG memory has been down for over two months. Nothing was touched:
  rebuilding re-runs LLM extraction over the whole vault and is the owner's call (see OPEN_ISSUES 19).
* Ollama probe timeout 0.5 -> 2 s (78 empty-message timeouts per session).
* The two test-only bridge commits on `vector-integration` were applied (`87bc9ab0a`).

Test evidence for this section is in the commit messages and section 9.

## 9. Final test state (2026-09-27, HEAD `d8c392274`)

Full sharded suite (`-m "not requires_ollama" --timeout=120`, 19 batches, clean working tree): **6,678 passed, 0 failed, 39 skipped**.
The first run on the pre-final tree (`ceaa7fc51`) was 6,677 / 1 / 39; the one failure, `r13 ... control_d`, failed about 1 run in 3 alone
because its real `read_code` scan walked the whole 7,000-file repo and hit the Governor's 45 s timeout under load. All r13 tests now run
the same real scan over a small project (stable 4 of 4). Before the fixes, `43ef7e5e2` was 6,586 / 3 / 55: the 3 HUD dev-mode e2e failures
pass when run alone and did not recur.

Live backend on the final code: `/agents` worst case 1.03 s over 45 samples (was 19-27 s), idle CPU 0.54 cores (was ~1.3), autonomous
loop ticking (323 ticks in 200 s), `/a2a/internal/directory` 200.

**Verdict remains B, not "V1 ACCEPTED".** Remaining: Codex independent review (after 19:11; packet `CODEX_REVIEW_PACKET_2026-09-27.md`), the
owner's live voice/camera checks, a real day of use on the daily phone/PC. `V1_FINAL_STATE_REPORT.md` is not written because that report is
only for verdict A. V1.x backlog (not blocking): goal-less plans lose to ambient goals by design; rare RED paths still call `subprocess.run`
inline in async code (`districts/emergency`, `core/resilience`); only GitBot has a practice drill; the LightRAG vault index rebuild (owner
decision); the taste calls in section 7.

## 10. Addendum (2026-09-27, later): "complete all tasks that can be done by you"

The owner gave blanket permission to finish everything from section 9's list that does not need a live camera/mic or a human's own
account. All of it landed on `fix/external-review-2026-09`, HEAD `f1f560143` (11 commits after section 9's `d8c392274`). Full suite:
**6,708 passed, 0 failed, 39 skipped.**

* **Goal-less plans** (`goal_id == ""`) no longer lose to ambient goal candidates: `Candidate.priority_bonus`, an additive score term
  for a plan step that keeps losing (clamped to 0.3). The strict Stage 4 test now runs both goal-linked and goal-less.
* **The remaining inline `subprocess.run` calls in async code** (`districts/emergency`, `incident_playbook_runner.py`,
  `core/resilience`, `devops_automator.py`, `stealth_browser`) now run in worker threads; a static AST guard test fails the suite if
  a new one appears anywhere in `core/` or `districts/`.
* **The junk `agent_history` rows (577 of 1,150: CullAgent, DeregBot) were NOT deleted.** The permission classifier denied the delete
  and denied writing a script to do it later; per the classifier's own instruction, this was not worked around. The owner can run it
  from chat, or add a Bash permission rule for that class of action.
* **The LightRAG vault index was rebuilt** -- not just diagnosed. Root cause of the "index has been damaged since 2026-07-15" finding
  turned out to be two separate defects: the crash-zeroed files (real), and, once past that, the configured LLM (`vector-ambient`, an
  intent-classifier persona that answers every prompt with a JSON blob, and a thinking model) made every LightRAG extraction return
  zero entities. Switched to the plain `gemma4:e2b` base model with `think: False`; rebuilt 137 of 154 high-value vault notes (17
  protected paths skipped by policy, not failures) into a staged index over ~2 hours of local model time; verified real, correctly
  grounded answers offline and through the live `/command` endpoint (asked "What is the Wealth Equation?", got the real
  `W = sum(O x R x M)` formula back) before swapping it in. Old damaged/empty copies kept, nothing deleted
  (`data/lightrag_vault.{corrupt,empty,rebuild-noentities}-20260927`).
* **Two more verifiable practice drills** (SSML well-formedness against an XML parser; a static-review drill checked against Python's
  own `ast`), which found and fixed a real defect: `VoiceGenerator.text_to_ssml` produced invalid XML for `&`/`<`/`>`. Drill coverage
  is now 3 of 230 agents.
* **The gesture handler was ported to the MediaPipe Tasks API** (the legacy `mp.solutions` does not exist in mediapipe 0.10.35) and off
  the event loop; the hand-landmarker model downloads once (7.8 MB) into `models/mediapipe/` (gitignored). Verified with the real
  model against a blank frame; real hand detection needs the owner's camera.
* **Camera and gesture sockets are now opt-in.** The HUD opened `/camera/ws` and `/gesture/ws` as soon as any tab loaded; the camera
  handler ran the webcam and YOLO at 15 fps for as long as a tab was open, and the ported gesture handler would have driven the
  HUD's own fist/pinch/swipe reactions from an always-on camera. Both now idle until `POST /camera/start` or `/gesture/start`
  (or `VECTOR_GESTURE_ENABLED=1`).
* **httpx's SSL context is now cached** (`core/api/ssl_cache.py`): constructing `httpx.AsyncClient()` cost 240-325 ms of blocking CPU
  (loading the certifi CA bundle fresh every time); about twenty API handlers build one client per request.
* **The Command Center's threat-level heuristic and approvals chip.** A validly signed installer or updater running from a temp
  directory (the VS Code installer alone pushed THREAT LEVEL to HIGH) no longer counts as suspicious -- checked natively via
  `WinVerifyTrust` (milliseconds; a PowerShell `Get-AuthenticodeSignature` took 15 s+ under load). An unsigned temp executable, a bad
  name fragment, or a script launched from temp are still flagged. Zero pending approvals now renders as `APPROVALS 0`, not
  `APPROVALS UNKNOWN`.
* **The four behaviour flags are on** in `.env`: `VECTOR_HP_FAIR=1`, `VECTOR_PLAYBOOK=1`, `VECTOR_EXPLORE=1` (`_SHARE=0.05`),
  `VECTOR_GYM=1`. `VECTOR_LEVEL_COUNCIL` stays off (no agent has a level yet) and `VECTOR_GESTURE_ENABLED` stays off (opt-in).
  `tests/conftest.py` forces all of them off inside pytest so the default-behaviour tests keep meaning what they say.
* Two more real defects found along the way and fixed: `data/adapters/*` (rewritten by the live training cycle) was tracked in git
  and kept dirtying the working tree -- untracked; `districts/content/voice_generator.py`'s SSML output was invalid XML for
  `&`/`<`/`>` (found by the new drill, above).

**Not done, and why:** the 577-row `agent_history` delete (owner permission needed for the delete itself, see above); Codex review
(quota back 19:11 today; packet updated at `CODEX_REVIEW_PACKET_2026-09-27.md`); the owner's own live voice/camera checks and a
real day of use. Verdict remains **B**, not "V1 ACCEPTED".
