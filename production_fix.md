
  VECTOR — Production Hardening Plan (Complete)

  │ Author: Opus 4.7 (planner) · Executor: Claude Sonnet 4.6 (coder)
  │ Source: Honest reality check (2026-05-21) against BACKEND_GAP_AUDIT.md + live grep
  │ Goal: Move VECTOR from ~70% beta to ~90% production-grade across 7 phases.

  Instructions for Sonnet

  1. Execute phases in order — Phase 0 first, then 1, then 2&3 in parallel, then 4, 5, 6.
  2. Each task lists exact file paths, function names, and acceptance criteria. Do not improvise.
  3. After every task, run the listed acceptance check. If it fails, diagnose before moving on.
  4. Run pytest -q tests/<phase_dir>/ after each phase. Must stay green.
  5. Mark progress with [x] on each task as you complete it.
  6. Stop and ask if you hit a blocker that needs user input. Don't silently work around.
  7. Read docs/BACKEND_GAP_AUDIT.md and KNOWN_ISSUES.md before starting.
  8. If a task description conflicts with current code, read the current code first, then pick the smaller change that satisfies acceptance.
  9. Commit format: [phase-N task-X] short description.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 0 — Cleanup (1–2h, START HERE)

  Goal: Remove stale duplicates so subsequent phases work on the real codebase. Every other phase is faster on a clean tree.

  Task 0A — Delete the 3 stale .claude/worktrees/ clones

  Why: Three full codebase snapshots from old Claude Code worktree sessions, never cleaned up. Each contains an out-of-date core/loop/autonomous_loop.py (286 lines vs current
  1,413). ~3,000+ stale .py files, 5–10 GB of disk.

  Evidence:

  - core/loop/autonomous_loop.py: 1,413 lines (current main).
  - .claude/worktrees/agent-ab6214c2e6d2a3908/core/loop/autonomous_loop.py: 286 lines (May-16 snapshot).
  - .claude/worktrees/agent-acafa09e1315e0013/core/loop/autonomous_loop.py: 286 lines (May-14 snapshot).

  Steps:

  - [ ] Verify they're real git worktrees: cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"; git worktree list
  - [ ] If git tracks them, remove cleanly:

    git worktree remove --force .claude/worktrees/agent-ab29796a59d589a87
    git worktree remove --force .claude/worktrees/agent-ab6214c2e6d2a3908
    git worktree remove --force .claude/worktrees/agent-acafa09e1315e0013
    git worktree prune

  - [ ] If not tracked: Remove-Item -Recurse -Force ".claude/worktrees"
  - [ ] Add .claude/worktrees/ to .gitignore.

  Acceptance: Get-ChildItem -Path ".claude/worktrees" -ErrorAction SilentlyContinue returns nothing. Disk usage drops 5–10 GB.

  Task 0B — Consolidate core/mining/ underscore-prefixed duplicates

  Why: Public + private versions of same modules coexist (constants.py + _constants.py, stubs.py + _stubs.py, etc.). Likely incomplete refactor.

  Steps:

  - [ ] Read both constants.py and _constants.py. If _constants.py is real and constants.py re-exports → keep both, mark public as deprecated. If literal duplicates → delete
  older. If diverged → merge into public name.
  - [ ] Same for stubs.py / _stubs.py.
  - [ ] For lone _X.py files (no public twin), check what imports them: Get-ChildItem -Recurse -Include *.py | Select-String "from core\.mining\._" -List. If nothing imports →
  delete.
  - [ ] Run python -c "from core.mining import constants, stubs" to verify imports.

  Acceptance: find core/mining -name "*.py" | wc -l drops by 2–4 files; python -c "import core.mining" succeeds.

  Task 0C — Resolve monolith + package coexistence

  Why: Phase 6 task 6A is deferred. The empty stub packages I created (claims/, guidance/) cause import ambiguity.

  Steps:

  - [ ] Delete the stub package dirs:

    Remove-Item -Recurse "vectorcode/src/claims"
    Remove-Item -Recurse "vectorcode/src/guidance"

  - [ ] (They'll be recreated properly in Phase 6 task 6A during real decomposition.)

  Acceptance: python -c "from vectorcode.src import claims, guidance" still works (resolving to the .py files).

  Task 0D — Verify districts/investment/.../voice/tts.py is not a copy

  Steps:

  - [ ] Read both core/voice/tts.py and districts/investment/vector_finagent/voice/tts.py.
  - [ ] If literal copy → delete the finagent copy and redirect imports to from core.voice.tts import VoiceTTS.
  - [ ] If genuinely different → keep, add docstring explaining why.

  Acceptance: Either the finagent file is deleted with imports redirected, or it has a docstring explaining independence.

  Task 0E — Audit legacy_ported/ for canonical-test duplicates

  Steps:

  - [ ] List canonical test files: Get-ChildItem vectorcode/python/tests/*.py | Where-Object { $_.Name -ne "conftest.py" }
  - [ ] For each canonical test name, search legacy_ported/ for the same name. If literal duplicate → delete legacy_ported one. If diverged → keep the more thorough version.

  Acceptance: pytest -q vectorcode/python/tests/ runs without "duplicate test name" warnings.

  Task 0F — Snapshot baseline

  Steps:

  - [ ] git tag pre-phase-0-cleanup; git push --tags origin
  - [ ] python -m pytest -q tests/ vectorcode/python/tests/ --tb=no | Out-File baseline_test_results.txt

  Phase 0 final acceptance:

  - [ ] .claude/worktrees/ is gone.
  - [ ] find core/ vectorcode/ -name "*.py" | wc -l drops by ~3,000 files.
  - [ ] pytest -q tests/ matches baseline pass count.
  - [ ] Tagged for rollback safety.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 1 — Production hardening (6–8h)

  Goal: Make the existing code defensible. No new features, only correctness.

  Task 1A — Silent exception cleanup (829 → <100)

  Why: grep "except Exception:\s*$|except:\s*$|except.*:\s*pass$" returns 829 hits in core/.

  Steps:

  - [ ] Run grep -rn "except Exception:" core/ --include="*.py" -A1 | grep -B1 "pass\|return None\|return\s*$" to find offenders.
  - [ ] Replace each with one of:
    - A. Critical path: logger.error(f"[VECTOR][{module}] {operation} failed: {e}") + re-raise.
    - B. Retryable: raise typed ServiceUnavailableError from core.errors.
    - C. Optional feature: logger.debug(...) + return default.

  - [ ] Forbidden: except: pass and bare except Exception: pass outside destructors/shutdown handlers.
  - [ ] Priority files (highest hit counts):
    - core/research_engine/research_library/routes/rag_routes.py (17)
    - core/research_engine/research_library/services/download_service.py (14)
    - core/loop/autonomous_loop.py (11) — hot path, highest priority
    - core/research_engine/database/encrypted_db.py (11)
    - core/research_engine/web_search_engines/engines/parallel_search_engine.py (11)
    - core/loop/context_engine.py (7)
    - core/city/governor.py (8)

  Acceptance: grep -rcn "except Exception:\s*$\|except:\s*$" core/ --include="*.py" | awk -F: '{s+=$2}END{print s}' < 100.

  Task 1B — Fail-closed external task API

  File: core/api/routers/tasks.py _check_api_key().

  Steps:

  - [ ] If _TASK_API_KEY unset and VECTOR_ALLOW_OPEN_TASK_API != "1" → raise 503 with explanatory message.
  - [ ] Update .env.example with VECTOR_TASK_API_KEY= placeholder + comment.
  - [ ] Create docs/security.md documenting it.

  Acceptance: curl -X POST localhost:8000/api/v1/tasks -d '{"text":"x"}' returns 503 when env unset.

  Task 1C — Rate limit /api/v1/tasks

  Steps:

  - [ ] In tasks.py, add in-memory token bucket: 60 req/min/key (env VECTOR_TASK_RATE_PER_MIN).
  - [ ] Call _check_rate(authorization) after _check_api_key().
  - [ ] Add per-key request rate to core/monitoring/perf_contracts.py stats.

  Acceptance: 61 requests in 60s with same key → 61st returns 429.

  Task 1D — SQLite encryption (SQLCipher)

  Steps:

  - [ ] Add sqlcipher3-binary==0.5.4 to requirements.txt.
  - [ ] Patch _connect() in: core/memory/episodic.py, core/queue/retry_queue.py, core/memory/shared_facts.py, core/experiments/ab_testing.py, core/memory/multi_db_manager.py. Use
  sqlcipher3 if VECTOR_DB_KEY set; fall back to plain sqlite3 with warning.
  - [ ] Create scripts/migrate_to_encrypted.py (plain → encrypted).

  Acceptance: With VECTOR_DB_KEY=test, sqlite3 vector_memory.db .tables reports "file is not a database".

  Task 1E — Audit chain consultation

  Steps:

  - [ ] Add verify_chain() to core/audit/merkle_chain.py if missing.
  - [ ] Add GET /audit/verify endpoint.
  - [ ] Add daily 3 AM cron in core/loop/cron_jobs.py calling verify_chain().
  - [ ] On hash mismatch, publish EventType.SECURITY_ALERT.

  Acceptance: curl localhost:8000/audit/verify returns {"valid": true, "chain_length": N}.

  Task 1F — Retry queue observability

  Steps:

  - [ ] Create core/api/routers/queue.py with: GET /queue/retry/stats, /queue/retry/items, /queue/dlq/items, POST /queue/retry/{id}/replay.
  - [ ] Register in core/api/app.py.
  - [ ] New tests: tests/queue/test_retry_queue.py (push/pop/dlq/replay).

  Acceptance: Force a failure → GET /queue/retry/items shows the item.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 2 — Multi-agent activation (8–10h, biggest real gap)

  Goal: Make the 52 agents actually coordinate. Separates "city of agents" from "library of classes".

  Task 2A — Build event_fanout_loop

  Steps:

  - [ ] Add coroutine to core/loop/autonomous_loop.py:

    async def event_fanout_loop(self):
        bus = get_event_bus(); reg = self._get_agent_registry()
        while self._running:
            event = await bus.consume(timeout=1.0)
            if event is None: continue
            et = str(event.event_type) if hasattr(event, 'event_type') else event.get('type')
            targets = [a for a in reg.list_alive() if et in a.subscribed_events]
            await asyncio.gather(*(self._dispatch_event_to_agent(a, event) for a in targets), return_exceptions=True)

  - [ ] Add _dispatch_event_to_agent() with 5s timeout per agent.
  - [ ] Add list_alive() to AgentRegistry if missing.
  - [ ] Register in run_forever().

  Acceptance: Publish SECURITY_ALERT from a test → all subscribed agents receive handle_event within 1s.

  Task 2B — Add handle_event overrides to top 10 agents

  For each agent: subscribe in __init__ via self.subscribe_to(EventType.X), override handle_event to call super().handle_event(event) first, then take a real action (5s max):

  ┌───────────────────────────────────────────────┬─────────────────────────────────────────────┬───────────────────────────┐
  │ Agent file                                    │ Subscribes to                               │ Action                    │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/security/threat_scout.py            │ SYSTEM_ERROR, SECURITY_ALERT, LOGIN_ATTEMPT │ Run threat scan           │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/research/research_hub.py            │ KNOWLEDGE_GAP_DETECTED                      │ Auto-launch deep research │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/coding/bug_hunter.py                │ BUILD_FAILED, TEST_FAILED                   │ Investigate root cause    │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/health/fatigue_monitor.py           │ SCREEN_TIME_EXCEEDED                        │ Suggest break             │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/finance/budget_analyst.py           │ LARGE_TRANSACTION                           │ Flag for review           │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/governance/llm_council.py           │ HIGH_STAKES_DECISION_NEEDED                 │ Convene                   │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/memory_curator/consolidation_bot.py │ MEMORY_FULL                                 │ Run consolidation         │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/communications/email_agent.py       │ EMAIL_RECEIVED                              │ Triage                    │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/reflection/daily_reviewer.py        │ DAY_ENDED                                   │ Run review                │
  ├───────────────────────────────────────────────┼─────────────────────────────────────────────┼───────────────────────────┤
  │ districts/intelligence/vectorintel_agent.py   │ OSINT_ALERT                                 │ Cross-correlate           │
  └───────────────────────────────────────────────┴─────────────────────────────────────────────┴───────────────────────────┘

  Acceptance: tests/integration/test_agent_coordination.py passes (publish event → assert side effect).

  Task 2C — Wire request_agent_help end-to-end

  Steps:

  - [ ] In research_hub.handle_event for KNOWLEDGE_GAP_DETECTED, call await self.request_agent_help("memory_curator", {...}).
  - [ ] In architect_bot.review_spec, call await self.request_agent_help("research_hub", {...}) for complex specs.
  - [ ] Verify WorkflowRunner.trigger_workflow() actually executes the cross-agent call.

  Acceptance: Trigger architect_bot → research_hub.run() called within 2s.

  Task 2D — Cross-district workflow tests

  Steps:

  - [ ] Create tests/integration/test_cross_district.py with 4 tests:
    - test_security_alert_triggers_threat_scan
    - test_email_triage_chains_to_calendar
    - test_research_findings_persist_to_memory
    - test_council_convenes_on_high_stakes

  - [ ] Mark @pytest.mark.integration.

  Acceptance: All 4 pass.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 3 — VectorCode integration deepening (10–12h)

  Goal: Move VectorCode utilization from ~10% to ~50%.

  Task 3A — Wire VectorCode MessageBus as parallel event channel

  - [ ] In core/loop/autonomous_loop.py._publish_event(), also call vectorcode.src.message_bus.get_bus().publish(topic, payload, qos=1).
  - [ ] Subscribe vectorcode_bridge to selected topics so VectorCode tools can react.

  Acceptance: get_bus().get_stats() shows non-zero published count after running the loop.

  Task 3B — Activate Skills system

  - [ ] Before governor dispatch in _act_on, check vectorcode.src.skills.manager.SkillManager.match().
  - [ ] If confidence > 0.8, execute via sm.execute(skill, params) and skip governor.
  - [ ] Test with an existing skill in vectorcode/src/skills/builtin/.

  Acceptance: "search arxiv for transformers" triggers research/arxiv skill before falling through.

  Task 3C — Wire 30+ comms adapters into a CommsHub

  - [ ] Create core/communications/hub.py with CommsHub.send(channel, recipient, message) and CommsHub.listen(channel).
  - [ ] Wire listen() into the main loop: incoming messages → publish EventType.MESSAGE_RECEIVED → fanout → email_agent triage.
  - [ ] Document required env vars in docs/security.md: TELEGRAM_BOT_TOKEN, DISCORD_TOKEN, SLACK_BOT_TOKEN.

  Acceptance: Send a Telegram message → shows up in EventBus within 5s.

  Task 3D — Use Queen for multi-model RED-action consensus

  - [ ] In core/loop/permission_gateway.py._request_humanlayer_approval(), when 2+ Ollama models loaded, replace HumanLayer with
  vectorcode.src.queen.QueenCoordinator.deliberate().
  - [ ] Models: ["vector-chairman", "vector-reasoning", "qwen3:30b-a3b"].
  - [ ] If verdict.consensus and verdict.confidence > 0.75 → auto-approve. Else → fall through to HumanLayer.

  Acceptance: Trigger send_email (RED) → Queen deliberates; if consensus auto-approve, else HumanLayer.

  Task 3E — Activate Claims work-stealing

  - [ ] When loop has > 5 pending tasks, hand them to vectorcode.src.claims.ClaimsManager for distribution.
  - [ ] Each agent worker periodically claims tasks; failures re-queue.

  Acceptance: Submit 20 tasks via /api/v1/tasks → claims distributes them; throughput beats single-worker baseline.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 4 — Self-improvement validation (4–6h)

  Task 4A — End-to-end test of SelfImprovementCycle.run_weekly()

  - [ ] Seed 1000 high-reward chains via tests/fixtures/seed_training_data.py.
  - [ ] Run cycle with qwen2.5:0.5b (small enough for CI).
  - [ ] Verify: collect writes JSONL ≥ 800 entries → train produces LoRA adapter, val_loss < initial → evaluate score > baseline → deploy registers Ollama model.

  Acceptance: pytest -q tests/training/test_self_improvement_e2e.py passes < 5 min.

  Task 4B — Validate LoRA produces a usable model

  - [ ] Add evaluate() to core/training/openmythos/trainer.py. Run on 50 held-out prompts. Compute: coherence (LLM-judge), action accuracy, latency.
  - [ ] If any metric worse than base → abort deploy.

  Acceptance: Train on garbage data → eval rejects → deploy skipped.

  Task 4C — Add eval gates

  - [ ] Reject runs where val_loss > 1.5x initial, action accuracy drops > 5pp, or latency increases > 50%.
  - [ ] On rejection, push training data to data/rejected_runs/ with reason.

  Acceptance: Force a regression → run_weekly() returns {"status": "rejected", "reason": "..."}.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 5 — Voice quality (3–5h)

  Task 5A — Fix Kokoro or replace

  - [ ] Try pip install onnxruntime==1.19.2 kokoro-onnx. If still INVALID_PROTOBUF, switch to Piper TTS (piper-tts + en_US-ryan-high.onnx).
  - [ ] Update core/voice/tts.py priority: Piper > Kokoro > pyttsx3.
  - [ ] Benchmark: 10-word sentence < 600ms.

  Acceptance: python -c "from core.voice.tts import VoiceTTS; VoiceTTS().speak('Hello sir')" produces audio < 800ms with no pyttsx3 fallback.

  Task 5B — Train custom hey_vector wake word

  - [ ] Run await WakeWordDetector().train_wake_word(15) to record + train.
  - [ ] Validate false-positive rate < 1/hour.

  Acceptance: _init_model() log says openWakeWord ready (phrase='hey_vector'), NOT Whisper KWS fallback.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase 6 — Cleanup (6–10h)

  Task 6A — Decompose 5 monolithic files

  For vectorcode/src/{cli.py, claims.py, guidance.py, neural_training.py, repl.py}:

  - [ ] Split by natural boundaries (top-level classes / functional groups).
  - [ ] Move groups to sibling modules in package dirs (recreate the dirs deleted in Phase 0 task 0C, but with real content this time).
  - [ ] Monolith re-exports from package for backward compat.
  - [ ] Run full test suite after each — must stay green.
  - Order (least → most risky): neural_training.py → repl.py → cli.py → claims.py → guidance.py.

  Acceptance: Each monolith < 10K chars; tests still pass.

  Task 6B — Eliminate _stubs.py files

  For each of 11 _stubs.py:

  - A. ABC base → rename _abc.py.
  - B. Optional fallback → rename _fallback.py with docstring.
  - C. Genuine stub → implement or delete.
  - [ ] Add tests/integration/test_no_stubs.py that fails on any _stubs.py.

  Acceptance: find . -name "_stubs.py" | wc -l = 0; _abc.py + _fallback.py count = 11.

  Task 6C — TODO/FIXME triage

  - [ ] Run grep -rn "TODO\|FIXME\|XXX\|HACK" core/ --include="*.py".
  - [ ] Classify each: real bug (file issue, link in comment), future feature (move to docs/ROADMAP.md), obsolete (delete comment + workaround).

  Acceptance: grep -c "TODO\|FIXME" core/**/*.py | awk -F: '{s+=$2}END{print s}' < 20.

  ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

  Phase ordering

  Phase 0 (cleanup, 1–2h)
      ↓
  Phase 1 (hardening, 6–8h)
      ↓
      ├──→ Phase 2 (multi-agent, 8–10h) ──┐
      │                                    ├──→ Phase 4 (training, 4–6h) ──→ Phase 5 (voice, 3–5h) ──→ Phase 6 (cleanup, 6–10h)
      └──→ Phase 3 (VectorCode, 10–12h) ──┘

  Effort estimate

  ┌───────┬─────────────┬─────────────────────────────────────────┐
  │ Phase │ Hours       │ Risk                                    │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 0     │ 1–2         │ Low (deletions of confirmed stale code) │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 1     │ 6–8         │ Low                                     │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 2     │ 8–10        │ Medium                                  │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 3     │ 10–12       │ Medium-high                             │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 4     │ 4–6         │ Low (training takes GPU time)           │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 5     │ 3–5         │ Low (Kokoro fix may not work)           │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ 6     │ 6–10        │ Low                                     │
  ├───────┼─────────────┼─────────────────────────────────────────┤
  │ Total │ 38–53 hours │ ~1 focused work-week, ~3 weeks calendar │
  └───────┴─────────────┴─────────────────────────────────────────┘

  Final acceptance — full system smoke

  After all 7 phases:

  - [ ] pytest -q passes all unit + integration.
  - [ ] Backend + frontend + Ollama up → DEMO.md walkthrough runs end-to-end.
  - [ ] grep -rcn "except Exception:\s*$" core/ --include="*.py" | awk -F: '{s+=$2}END{print s}' < 100.
  - [ ] find core/ vectorcode/ -name "_stubs.py" | wc -l = 0.
  - [ ] find . -path "./.claude/worktrees" -prune -o -name "*.py" -print | wc -l reasonable (no stale clones).
  - [ ] python -m core.api.app runs 4 hours without crashes.
  - [ ] All 7 questions in the honest reality check answered ≥ 90%.

