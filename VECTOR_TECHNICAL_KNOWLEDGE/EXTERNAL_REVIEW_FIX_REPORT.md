# External Review Fix Report — 2026-09-24

Branch: `fix/external-review-2026-09`. Each finding verified against real source before fixing (never trusted as fact). Baseline for comparison: Task 90 (5,012 passed / 13 failed / 36 skipped).

## Phase 1 — Broken imports (HIGH) — DONE

| # | Finding | Verified? | Fix commit | Tests added |
|---|---------|-----------|------------|-------------|
| 1 | `db_guardian.py` → `core.cloud.notify.notify_owner` missing | TRUE | (this branch) | `test_notify_owner_paths.py` |
| 2 | `content_arm.py` → `core.notify.pushover` missing | TRUE (also found: called without `await` even after import fixed) | (this branch) | `test_notify_owner_paths.py` |
| 3 | `simulation.py` → `vector_social_sim_agent.SocialSimAgent` missing | TRUE | (this branch) | `test_simulation_router_dispatch.py` |
| 4 | `research.py` → `core.loop.llm_interface.LLMInterface` missing | TRUE (pure status flag, no functional dependency) | (this branch) | covered by import checker |
| 5 | `core/mining/stubs.py` missing (breaks `mining.py` router) | TRUE — `MiningCapabilities` moved to `core/mining/_abc.py` | (this branch) | `test_mining_import_fix.py` |

**New finding beyond Opus's list, same root cause as #3:** fixing the import alone would have left the feature silently broken in a different way — `SocialSimAgent.run()` only read `params["action"]` (which the router never sets), so `/simulation/run`, `/interview`, `/report` all silently executed `build_ontology()` regardless of what was requested. `/interview` and `/report` also used entirely wrong action-name strings (`interview_agent`/`generate_report` vs the agent's real `agent_interview`/`simulation_report`). Fixed both: agent now prefers `task["type"]` (matching the pattern already used correctly in `hedgebot_agent.py`/`trading_conductor_agent.py`), router now uses the real action names.

**`core/mining/vllm_pearl.py`'s `_discovery`/`_docker` imports** and **`districts/investment/vector_hedgebot/cli.py`'s `core.vector_hedge` import** (found by the new checker, not in Opus's list): both confirmed genuinely dead — standalone `__main__` entry points never imported anywhere in the live codebase. `vllm_pearl.py` is for the Docker/distributed mining path the package's own docstring says was deliberately excluded (VECTOR runs fully local). Not fixed (no real target to fix to); added to the checker's documented allowlist pending an owner deletion decision (Phase 6).

**Item 6 — CI import checker:** `scripts/check_first_party_imports.py` written, wired into `tools/ci_gate.py`. Catches exactly this bug class (a typo'd/stale first-party import silently swallowed by a broad `except`). Confirmed clean on the current tree (0 unallowlisted broken imports).

**Item 7 — Highest-risk silent catch-all handlers** (report only, not mass-edited — reviewed 47 `except Exception: pass`/`logger.debug`-only handlers across `core/loop`, `core/memory`, `core/city/governor.py`, `core/api/routers`, `core/cloud`, `core/security`; most are appropriate, already-intentional graceful-degradation code matching this codebase's own "never crash" convention. These are the ones that are genuinely high-risk):

| File:line | What silently fails | Real consequence | Recommendation |
|-----------|---------------------|-------------------|-----------------|
| `permission_gateway.py:452` | `pending_approvals` table init | RED-tier approvals can't survive a process restart | `logger.warning`, not debug |
| `permission_gateway.py:469` | pending approval persist | An in-flight RED-tier approval is lost on restart before the owner responds | `logger.warning` + retry once |
| `permission_gateway.py:528` | `gateway_audit` table init | Whole audit trail silently never starts | `logger.error` — this is a security-relevant table |
| `permission_gateway.py:543` | audit persist | Individual audit log entries vanish silently | `logger.warning`, consider a fallback write to episodic memory |
| `multi_db_manager.py:323,346` | Supabase/Turso push failure | Owner believes data is cloud-backed when it silently isn't | `logger.warning`, and surface a periodic "N rows failed to sync" summary rather than per-row debug spam |
| `multi_db_manager.py:576,611` | Supabase/Turso pull failure | Same — silent data-recovery gap, only discovered during an actual disaster recovery | same as above |
| `db_guardian.py` (fixed this phase) | owner alert on auto-quarantine | Owner never knew a security quarantine happened | fixed |
| `content_arm.py` (fixed this phase) | owner alert on content ready | Owner never knew content was ready to post | fixed |

Lower-risk, reviewed and NOT flagged (appropriate graceful degradation, left as-is): `permission_gateway.py:477,837,910,1592`, `governor.py:2217,2840,2865`, `episodic.py`'s 3 VACUUM-related bare-pass sites, `social_safety.py`'s file-stat fallback, `notifications.py`'s websocket push/unsub, `secrets_providers.py`'s keyring fallback (part of an intentional multi-provider fallback chain), `session_buffer.py`, `reasoning_memory.py`, `correction_learner.py`'s 4 sites, `commands.py`'s 2 sites, `voice.py`/`voice_ws.py`'s 5 sites.

**Test results after Phase 1:** full suite run in progress (see Phase 2 section — Phase 1 and Phase 2 work landed together before the first full-suite comparison completed).

## Phase 2 — LLM Council non-functional (HIGH) — DONE, pending final full-suite confirmation

All 3 claims verified true against real code/data before fixing:
- `ollama.Client(timeout=5.0)`: confirmed at `core/brain/council.py:37` (original).
- `data/council_log.jsonl`: measured **57.7%** timeout rate (1075/1863) — matches Opus's ~58% exactly.
- `sorted(stage1_responses, key=len, reverse=True)` "ranking" and hardcoded `"confidence": 0.75`: both confirmed. Since `permission_gateway.py`'s auto-proceed gate is `confidence >= 0.75`, the gate **never actually filtered anything** — every "proceed" verdict passed it by construction.

**Fix (Strategy 2 of Opus's 3 options — one model, multiple perspectives):**
- Root cause of the 58% timeout rate: 3 *different* local models called sequentially under `OLLAMA_MAX_LOADED_MODELS=1` forced a cold swap on nearly every member call. Now all 3 members use `CONFIG["models"]["reasoning"]` with different role-framing system prompts; the chairman model is only invoked on a genuine split (saves a call+swap on the common case).
- Each member is now asked for and gives a real structured PROCEED/REJECT/DEFER vote (extracted via regex, fail-closed to `defer` if ambiguous) — real majority tally, chairman tiebreak only on a split.
- Confidence now computed from real vote agreement (unanimous=1.0, 2/3 majority≈0.83, chairman-broken split=0.5) instead of a hardcoded constant.
- Timeout moved to `CONFIG["council"]["deliberation_timeout"]` (default 30.0s, was hardcoded 5.0s).
- Both `ollama.Client()` calls now run inside `asyncio.to_thread()` — **new finding, not in Opus's list**: the original code called these synchronously from `async def deliberate()`, which is reached from the live autonomous-loop/API event loop via `permission_gateway.py`'s RED-tier path; a 5-30s blocking call inline would freeze the whole event loop for every other in-flight request/dispatch. Directly relevant to Phase 3 finding #1 below.

**Tests:** `tests/test_council_brain_rewrite.py` (17 tests: vote parsing, majority/tie logic, confidence computation, configurable timeout, failure-safety fallback, `permission_gateway.py` contract preservation) — all pass.

**Regressions found and fixed while verifying no breakage:**
1. `tests/integration/test_phase_a7_council_red_tier.py`'s `_patched_council()` stub mocked the OLD contract (`deliberate()` returning raw text under `"verdict"`); updated to match the new contract (parsed verdict + raw text under `"verdict_text"`). After the fix: same 1 pre-existing failure as baseline (`test_proceed_high_confidence_returns_proceed`, `push_github` not in `COUNCIL_AUTO_PROCEED_ALLOWED` — a Phase 3 "known failing test" item, not caused by this change; confirmed via `git stash` on the original code).
2. `tests/unit/test_permission_gateway.py::test_red_allows_with_manual_confirmation` — genuine regression, confirmed via `git stash` (passed before, failed after). Root cause on inspection: unrelated to the council rewrite's correctness — the test's own polling loop checked for the literal string `"send_email"` as a `_pending_events` key, which never actually matches the real randomized pending-id scheme (2026-09-23 security fix); it only ever "worked" by timing coincidence with the OLD council path's ~5s real delay lining up against the test's own 5s polling budget and a pre-existing `_red_timeout = 1 if "pytest" in sys.modules else 300` fast-path. With council now resolving instantly, that coincidence broke. Fixed the test to poll real state (`_pending_actions` values) instead of a key that was never right.

## Phase 3 — Autonomous loop reliability (HIGH) — IN PROGRESS

**#1 loop thread freeze — ROOT CAUSE FOUND AND FIXED**, from `data/logs/thread_dumps.log`: a real thread dump caught the MAIN event loop thread (the one running `run_api`/uvicorn/`governor.dispatch()`) blocked for 60+ real seconds inside `districts/content/script_generator.py`'s `_llm()`, which — like the council bug — spun up its own `ThreadPoolExecutor` + nested `asyncio.run()` and blocked on `Future.result(timeout=120)` from a function that is *already* called from inside an async context (`ScriptGenerator.run()` and `video_pipeline.py`'s `_generate_script()` both call it as a plain synchronous call, no `await`, no `to_thread`). Fixed: `_llm()` is now `async def` and awaits `ProviderClient.chat()` directly (already async, no reason for the nested thread+loop dance at all); `generate_script`/`generate_hook`/`generate_cta`/`expand_script`/`run()` converted to async accordingly; `video_pipeline.py`'s caller and the file's own `__main__` smoke test updated to await. This directly connects to Opus's own Phase 3 #4 (the ~1,300×/day script regeneration) — this exact code path was almost certainly freezing the whole event loop on every one of those calls.

Remaining Phase 3 items (#2 known failing tests, #3 the 7 hanging files, #4 repetition/dedup + APITester respawn, #5 Stage 4 findings) — investigation continuing.
