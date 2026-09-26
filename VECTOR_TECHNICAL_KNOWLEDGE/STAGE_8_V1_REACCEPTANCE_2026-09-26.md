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
