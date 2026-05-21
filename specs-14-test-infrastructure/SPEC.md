# SPEC-014: Test Infrastructure — 80% Coverage with CI Gate

**Status:** Draft  
**Owner:** Arghyadeep Deb  
**Phase:** 1  
**Priority:** P0  
**Target Branch:** `specs-14-test-infrastructure`  
**Estimate:** 5 days (3 parallel agents + 1 buffer)  
**Deps:** `pytest.ini`, `.github/workflows/test.yml` (existing)

---

## 1. Problem Statement

VECTOR has 7,926 Python source files and 27 test files — a **0.34% test-to-source ratio** and estimated **~0.3% line coverage**. There is no CI coverage gate, no shared test fixtures, and no regression protection.

This is a production autonomous AI system that executes real OS/filesystem/network commands. The permission gateway approves or denies destructive actions (file delete, shell exec, package uninstall). The autonomous loop runs 11 concurrent asyncio tasks that never stop. 49 district agents operate with HP and can be terminated by the governor. A single bug in permission classification or loop crash recovery could cause silent data loss or allow destructive commands to execute with no warning.

### 1.1 Specific Risks

**Permission gateway** (42 action types classed GREEN/YELLOW/RED). A missing RED entry, off-by-one in severity classification, or race condition in the rate limiter could approve `shell.exec("rm -rf /")` when it should block. Zero tests for 37 of 42 action types. No rate limit edge case tests. No audit log capacity tests.

**Autonomous loop** (958 lines, 11 concurrent asyncio tasks). Tasks: sensor_poll, context_build, decision, permission_check, execution, memory_write, health_monitor, reflect_trigger, cron_scheduler, heartbeat, cleanup. Any silent crash degrades the system undetected. No crash-recovery tests, no circuit-breaker tests, no task-liveness tests.

**Decision engine** (397 lines, 5-factor scoring + A2C neural trainer). No unit tests for tie scores, negative costs, zero-utility actions, NaN/Inf inputs, or degenerate policy convergence (always-pick-first). The A2C trainer has zero tests — actor shape, critic shape, experience buffer, training trigger, entropy collapse are all untrusted.

**Context engine** (358 lines, 14 domains). A single domain crash (e.g., filesystem permission error) fails the entire context build silently. TokenJuice compression has no tests. Session prompt format and token counting are untested.

**Memory** (8+ types). Episodic memory uses SQLite FTS5 with AES-256 — no encryption verification test. Semantic memory uses ChromaDB — no 768-dim vector test, no threshold search test. Knowledge graph uses NetworkX — no subgraph extraction, merge, path-finding, or cycle-detection tests. Causal graph — no acyclic enforcement test, no do-calculus test. Policy memory stores PyTorch tensors — no corrupted-file detection test.

**MCP server** (300+ tools). No tool registration verification. No param validation tests (valid, invalid types, missing required, empty optional). No fuzz testing.

**Config** (555 lines, Pydantic V2). No env override tests. No secret redaction tests. No validation tests (port range, negative timeout, unknown fields). No sub-config loading tests for all 50+ sub-configs.

**49 districts.** All inherit AgentBase HP/state logic. None have instantiation or run-response tests. Evolution engine HP decay, death triggers, and ghost memory propagation are completely untested.

### 1.2 Cost of Delay

Without tests: bugs discovered manually in production, fix cost 3-8 hours each, refactoring impossible without breaking things, onboarding dangerous, CI provides near-zero protection.

At 80% coverage: bugs caught in <30 seconds via `pytest --test-only` on the affected module, fix cost 15-60 minutes (repro in test, patch, verify with same test), refactoring confidence high, CI blocks regressions before merge.

---

## 2. Current State Assessment

### 2.1 Existing Test Inventory

| Test File | Lines | Covers | Quality | Gaps |
|-----------|-------|--------|---------|------|
| `test_agent_base.py` | ~40 | HP init, state transitions | Smoke only | No edge case HP bounds, no concurrent action, no dead-agent act |
| `test_decision_engine.py` | ~60 | Basic scoring, ranking | Happy path | Only 1 of 5 factors tested, no A2C, no NaN/Inf, no temperature |
| `test_permission_gateway.py` | ~50 | GREEN/YELLOW/RED, 5 types | Partial | 5 of 42 types tested, no rate limit, no audit log, no config modes |
| `test_governor.py` | ~35 | Routing smoke | Minimal | One scenario only, no fallback chain, no concurrent, no unknown intent |
| `test_llm_council.py` | ~45 | Council session | Basic | Single session type, no edge cases |
| `test_episodic.py` | ~55 | Basic CRUD | Adequate | No FTS5 scoring, no encryption verify, no concurrent write, no batch |
| `test_memory_curator.py` | ~30 | Consolidation trigger | Thin | Single trigger path, no config variations |
| `test_obsidian_sync.py` | ~40 | Sync roundtrip | Good | Covers main flow |
| `test_point_system.py` | ~30 | HP math | Thin | No negative, no overflow, no multiplier edge cases |
| `test_research_district.py` | ~25 | Output format | Adequate | One district only |
| `test_web_search_tool.py` | ~20 | Tool format | Thin | No error response testing |
| `test_dashboard_api.py` | ~20 | One endpoint | Incomplete | 1 of ~10 endpoints |
| `test_config.py` | ~30 | Partial config load | Thin | No env override, no secret redaction, no validation |
| `test_chroma_memory.py` | ~35 | Vector insert/query | Basic | No threshold, no high-dim, no metadata |
| `test_causal_graph.py` | ~25 | Graph construction | Happy path | No acyclic enforcement, no do-calculus |
| `test_counterfactual.py` | ~25 | What-if generation | Basic | No similarity search, no prune |
| `test_knowledge_graph.py` | ~30 | Triple insert/query | Basic | No subgraph, no merge, no path finding |
| `test_reasoning_memory.py` | ~30 | Prompt templates | Basic | No missing var error, no compose chain |
| `test_semantic_memory.py` | ~30 | Embedding store/retrieve | Basic | No threshold, no high-dim, no delete |
| `test_skill_memory.py` | ~25 | Skill record/replay | Basic | No generalization, no prune |
| `test_camera.py` | ~20 | Frame capture | Mock only | No error modes tested |
| `test_screen_observer.py` | ~25 | Screen diff | Basic | Single diff scenario |
| `test_stt.py` | ~15 | Transcription | Basic | No silence, no timeout |
| `test_tts.py` | ~15 | Output format | Basic | No empty, no rate limit |
| `test_wake_word.py` | ~20 | Detection | Basic | No confidence threshold |
| `test_adb_bridge.py` | ~15 | Connectivity | Basic | No shell timeout, no file push/pull |
| `test_ambient_listener.py` | ~20 | Wake word orchestration | Basic | No stop, no consecutive cycles |

**Total:** 27 files, ~750 lines of test code, estimated ~0.3% coverage of 7,926 source files.

### 2.2 Coverage Gaps

| Module | Lines | Est. Coverage | What's Missing |
|--------|-------|--------------|----------------|
| `core/loop/autonomous_loop.py` | 958 | 0% | Everything — 11-task lifecycle, crash detection, circuit breaker, heartbeat, cron, reflect, cleanup |
| `core/loop/decision_engine.py` | 397 | ~10% | 4 of 5 scoring factors untested, A2C entirely untested, edge cases (NaN, Inf, negative, ties) |
| `core/loop/context_engine.py` | 358 | 0% | Everything — 14 domains, TokenJuice, session prompt format, incremental update |
| `core/loop/permission_gateway.py` | ~200 | ~15% | 37 of 42 action types untested, rate limit duration/overflow, config reload, audit log rotation |
| `core/memory/episodic.py` | 404 | ~6% | Encryption verification, FTS5 BM25 scoring, concurrent writes, batch stores, large content (>10K) |
| `core/memory/semantic.py` | ~150 | ~10% | Threshold-filtered search, 768-dim embeddings, delete by ID, collection stats |
| `core/memory/policy.py` | ~120 | 0% | Everything — tensor store/load, versioning, corrupted file detection, nonexistent load |
| `core/memory/reasoning_memory.py` | ~100 | ~15% | Missing variable error handling, compose with extra vars, template chain verification |
| `core/memory/knowledge_graph.py` | ~200 | ~7% | Subgraph extraction by depth, graph merging, path finding (BFS), cycle detection, JSON import/export |
| `core/memory/causal_graph.py` | ~180 | ~5% | Acyclic enforcement (CycleError), do-calculus intervention simulation, confounding detection, backdoor adjustment sets |
| `core/memory/counterfactual.py` | ~160 | ~6% | Embedding similarity search, time-based pruning of outdated entries |
| `core/city/agent_base.py` | ~250 | ~8% | State machine edge cases (busy→busy rejection), dead→idle raises, concurrent action blocking, log rotation |
| `core/city/governor.py` | ~350 | ~4% | Full fallback chain execution, all-fallbacks-exhausted path, concurrent request handling, priority queue, dead-agent routing |
| `core/city/evolution_engine.py` | ~200 | 0% | Everything — HP decay rate, decay stops at zero, death trigger, ghost memory tags, resurrection HP restore |
| `core/city/agent_registry.py` | ~80 | 0% | Everything — register, unregister, lookup by name/capability, duplicate registration handling |
| `core/city/point_system.py` | ~100 | ~15% | Negative point edge cases, overflow protection, configurable multipliers |
| `core/inference/ollama_safe.py` | ~180 | ~5% | Retry logic, exponential backoff, max-retries-exceeded, connection-refused, model-not-found |
| `core/config.py` | 555 | ~3% | Environment variable overrides, config file precedence, secret redaction in repr/str, type validation, port range, 50+ sub-configs |
| `core/mcp_server.py` | ~500 | 0% | Everything — 300+ tool registration, param schemas, execution, error handling, fuzz testing |
| `core/voice/stt.py` | ~120 | ~4% | Empty audio, silence-detection path, timeout error, concurrent requests |
| `core/voice/tts.py` | ~100 | ~5% | Empty text handling, rate limit enforcement, streaming vs non-streaming |
| `core/voice/wake_word.py` | ~80 | ~6% | Sub-threshold confidence, noise rejection, model loading failure |
| `core/voice/ambient_listener.py` | ~150 | ~3% | Listen cycle orchestration, clean stop, consecutive cycles, wake-word→STT pipeline |
| `core/sensing/camera.py` | ~90 | ~5% | Device not found, permission denied, timeout during capture |
| `core/sensing/screen_observer.py` | ~120 | ~4% | No-display environment, resolution change handling |
| `phone_node/ambient_server.py` | ~150 | 0% | Everything — heartbeat, battery reporting, low-battery alert, disconnect/reconnect |
| `phone_node/adb_bridge.py` | ~100 | ~5% | Connection failure, command timeout, file push/pull error modes |
| `dashboard/` | ~400 | ~2% | All endpoints beyond health check, CORS headers, request validation, error responses |
| 49 districts (~80 avg) | ~3,920 | ~1% | Instantiation, run method, HP init, fallback definitions, empty input handling |

**Estimated total uncovered lines:** ~10,500

### 2.3 What Works

- pytest is used consistently (not unittest) — consistent with target
- Some tests use `pytest.mark.asyncio` — correct async pattern to extend
- Episodic memory test uses in-memory SQLite — correct approach for memory tests
- Permission gateway test covers GREEN/YELLOW/RED concept — needs expansion to all 42 types
- Existing tests are standalone (no shared state) — easy to repurpose as smoke tests

### 2.4 What's Missing

- **No conftest.py** — fixture factories duplicated across every test file
- **No coverage configuration** — pytest-cov not set up, no fail-under threshold
- **No CI coverage gate** — workflow runs tests but enforces nothing on PRs
- **No mock factory** — real Ollama/network calls could leak into CI, causing flaky failures
- **No edge case coverage** — all 27 tests are happy-path only (zero boundary/exhaustion/error tests)
- **No cleanup assertions** — tests don't verify they cleaned up temp files, DB connections, etc.
- **No stress tests** — no concurrent access tests, no batch operation tests, no long-running tests
- **No test organization** — 27 files flat in a single `tests/` directory; no grouping by module

---

## 3. Target State

### 3.1 Coverage Targets

| Area | Current | Target | CI Gate Command |
|------|---------|--------|-----------------|
| Overall line coverage | ~0.3% | >= 80% | `--cov=core --cov-fail-under=80` |
| Core loop modules | 0-10% | >= 90% | `--cov=core.loop --cov-fail-under=90` |
| Memory modules | 0-15% | >= 85% | `--cov=core.memory --cov-fail-under=85` |
| City modules | 0-8% | >= 85% | `--cov=core.city --cov-fail-under=85` |
| Config | 3% | >= 90% | `--cov=core.config --cov-fail-under=90` |
| MCP server | 0% | >= 70% | `--cov=core.mcp_server --cov-fail-under=70` |
| Voice modules | 0-6% | >= 75% | `--cov=core.voice --cov-fail-under=75` |
| Phone node | 0-5% | >= 70% | `--cov=phone_node --cov-fail-under=70` |
| Dashboard | 2% | >= 60% | `--cov=dashboard --cov-fail-under=60` |
| 49 districts | 1% | >= 80% | `--cov=districts --cov-fail-under=80` |
| New code (diff) | — | >= 85% | `--cov=diff` |

### 3.2 CI Performance Targets

| Suite | Target Runtime | Parallelism |
|-------|---------------|-------------|
| Full suite | < 5 min | 7-way matrix (unit, memory, mcp, districts, voice, phone, dashboard) |
| Unit tests | < 2 min | Single job |
| Memory roundtrips | < 1 min | Single job |
| MCP fuzz + districts | < 30s | Single job |
| Voice + phone + dashboard | < 30s | Single job |
| Coverage report generation | < 10s | Summary job after matrix |

### 3.3 Quality Gates

| Gate | Threshold | Behavior on Failure |
|------|-----------|---------------------|
| Overall line coverage | >= 80% | GitHub check fails, PR blocked |
| Core module coverage | >= 90% | GitHub check fails, PR blocked |
| New code (diff) coverage | >= 85% | GitHub check fails, PR blocked |
| Test pass rate | 100% | GitHub check fails, PR blocked |
| Flaky test tolerance | 0 flags | Allowed 1 retry; 2nd failure = hard fail |

### 3.4 Test Directory Structure

```
tests/
├── __init__.py                    — package marker
├── conftest.py                    — all shared fixtures (mock_ollama, mock_memory, etc.)
├── mock_factory.py                — MockWorldState, MockMemory, MockOllama, MockPermissionGateway
├── fixtures/                      — pre-built sample data
│   ├── __init__.py
│   ├── sample_world_states.py     — minimal, complete, with_sensors, with_errors, empty
│   ├── sample_actions.py          — all 42 action types + edge cases
│   ├── sample_decisions.py        — tie scores, zero-cost, negative, single, empty
│   └── sample_memories.py         — pre-built entries for all 8 memory types
├── unit/
│   ├── __init__.py
│   ├── test_autonomous_loop.py    — 20 tests
│   ├── test_decision_engine.py    — 30 tests
│   ├── test_context_engine.py     — 25 tests
│   ├── test_permission_gateway.py — 40 tests
│   ├── test_agent_base.py         — 15 tests
│   ├── test_governor.py           — 15 tests
│   ├── test_evolution_engine.py   — 10 tests
│   ├── test_point_system.py       — 5 tests
│   ├── test_agent_registry.py     — 5 tests
│   ├── test_config.py             — 25 tests
│   └── test_ollama_safe.py        — 10 tests
├── memory/
│   ├── __init__.py
│   ├── test_episodic.py           — 15 tests
│   ├── test_semantic.py           — 10 tests
│   ├── test_policy.py             — 8 tests
│   ├── test_reasoning_memory.py   — 8 tests
│   ├── test_knowledge_graph.py    — 12 tests
│   ├── test_causal_graph.py       — 10 tests
│   ├── test_counterfactual.py     — 6 tests
│   ├── test_skill_memory.py       — 6 tests
│   ├── test_agent_history.py      — 4 tests
│   └── test_memory_roundtrip.py   — 4 tests
├── mcp/
│   ├── __init__.py
│   ├── test_mcp_server.py         — 10 tests (parametrized across 300+ tools)
│   └── test_mcp_fuzz.py           — 2 tests (100 fuzz calls)
├── districts/
│   ├── __init__.py
│   └── test_all_districts.py      — 10 tests × 49 districts (parametrized)
├── voice/
│   ├── __init__.py
│   ├── test_stt.py                — 5 tests
│   ├── test_tts.py                — 3 tests
│   ├── test_wake_word.py          — 3 tests
│   └── test_ambient_listener.py   — 4 tests
├── phone/
│   ├── __init__.py
│   ├── test_ambient_server.py     — 6 tests
│   └── test_adb_bridge.py         — 4 tests
├── dashboard/
│   ├── __init__.py
│   └── test_dashboard_api.py      — 5 tests
├── integration/
│   ├── __init__.py
│   ├── test_loop_integration.py   — 3 tests (sensor→context→decide→act)
│   ├── test_memory_integration.py — 3 tests (episodic→semantic consolidation)
│   └── test_governor_council.py   — 3 tests (governor→council→response)
└── performance/
    ├── __init__.py
    └── test_loop_latency.py       — 2 tests (measure loop iteration time)
```

---

## 4. Component Breakdown

### 4.1 TestAutonomousLoop

**File:** `tests/unit/test_autonomous_loop.py` | **Source:** `core/loop/autonomous_loop.py` (958 lines)

**Scope:** 11 concurrent asyncio tasks lifecycle, crash detection/recovery, circuit breaker, heartbeat, cron scheduler, reflect trigger, context window consolidation, sensor polling, memory write latency, cleanup on stop.

**Fixtures:**

```python
@pytest.fixture
def loop(self, mock_world_state, mock_memory, mock_ollama, mock_permission_gateway):
    """AutonomousLoop with all dependencies mocked."""
```

**Tests (20):**

| # | Test Name | What It Verifies |
|---|-----------|------------------|
| 1 | `test_start_creates_all_11_tasks` | After `start()`, `loop.tasks` length == 11, all are not done |
| 2 | `test_start_creates_correct_task_names` | Task names match the known 11: sensor_poll, context_build, decision, permission_check, execution, memory_write, health_monitor, reflect_trigger, cron_scheduler, heartbeat, cleanup |
| 3 | `test_stop_cancels_all_tasks` | After `stop()`, all tasks are cancelled within timeout (5s) |
| 4 | `test_stop_handles_sigterm` | Sending SIGTERM signal triggers graceful stop sequence |
| 5 | `test_supervisor_detects_task_failure` | Manually cancel one task, supervisor detects within 1 second |
| 6 | `test_supervisor_restarts_dead_task` | Supervisor creates a new task to replace the dead one |
| 7 | `test_circuit_breaker_triggers_after_3_rapid_crashes` | Task crashes 3 times in 60s → circuit breaker permanently stops that task |
| 8 | `test_circuit_breaker_does_not_trigger_for_slow_crashes` | 3 crashes spread over 120s does NOT trigger circuit breaker |
| 9 | `test_iteration_count_increments` | After N loop iterations, `loop.iteration == N` |
| 10 | `test_heartbeat_updates_timestamp` | `loop.last_heartbeat` is updated after heartbeat interval |
| 11 | `test_health_monitor_reports_healthy` | All tasks running → health status = 'healthy' |
| 12 | `test_health_monitor_reports_degraded` | Missing/crashed tasks → health status = 'degraded' |
| 13 | `test_reflect_trigger_fires_at_interval` | Freeze time, advance past reflect interval, verify reflect callback was called |
| 14 | `test_cron_scheduler_fires_registered_task` | Register cron task with 30s interval, advance time, verify execution |
| 15 | `test_cron_scheduler_handles_multiple_tasks` | 5 registered cron tasks all fire at correct intervals |
| 16 | `test_context_window_triggers_consolidation` | When context token count exceeds limit, consolidation callback is triggered |
| 17 | `test_sensor_poll_adds_data_to_world_state` | After one sensor poll cycle, world state contains new keys |
| 18 | `test_memory_write_is_nonblocking` | Memory write completes within 10ms and doesn't delay next iteration |
| 19 | `test_loop_handles_empty_sensor_data` | Sensor poll returning None doesn't crash the loop |
| 20 | `test_loop_handles_ollama_timeout` | Decision engine timeout → degraded response, loop continues |

### 4.2 TestDecisionEngine

**File:** `tests/unit/test_decision_engine.py` | **Source:** `core/loop/decision_engine.py` (397 lines)

**Scope:** 5 scoring factors, total score calculation, weight adjustment, candidate ranking, temperature-based selection, A2C neural trainer (actor/critic forward shapes, train step, loss convergence, experience buffer, training triggers), edge cases (NaN, Inf, negative, missing factors, zero-dim state, high-dim state).

**Scoring factors:** urgency (0.0-1.0), impact (0.0-1.0), cost (inverted 0.0-1.0), confidence (0.0-1.0), novelty (0.0-1.0).

**Tests (30):**

| # | Group | Tests |
|---|-------|-------|
| 1-3 | Urgency | `test_score_urgency_high` (deadline imminent → ~1.0), `test_score_urgency_zero` (no deadline → 0.0), `test_score_urgency_mid` (moderate → 0.5) |
| 4-6 | Impact | `test_score_impact_high`, `test_score_impact_zero`, `test_score_impact_mid` |
| 7-9 | Cost | `test_score_cost_low` (cheap → ~1.0 inverted), `test_score_cost_high` (expensive → ~0.0), `test_score_cost_zero` (free → 1.0) |
| 10-12 | Confidence | `test_score_confidence_high`, `test_score_confidence_low`, `test_score_confidence_mid` |
| 13-15 | Novelty | `test_score_novelty_high` (not in history → ~1.0), `test_score_novelty_zero` (just executed → 0.0), `test_score_novelty_mid` |
| 16 | Combination | `test_total_score_is_weighted_sum` — total = w1*u + w2*i + w3*c + w4*conf + w5*n |
| 17 | Weights | `test_weight_adjustment_changes_score` — changing urgency weight alters total appropriately |
| 18-21 | Ranking | `test_rank_orders_by_score_descending`, `test_rank_tie_scores` (stable sort), `test_rank_empty_list`, `test_rank_single_candidate` |
| 22-25 | Selection | `test_select_top_candidate`, `test_select_with_temperature_above_zero` (stochastic), `test_select_with_temperature_zero` (deterministic), `test_select_with_temperature_one` (samples distribution) |
| 26-30 | A2C | `test_actor_forward_shape` (outputs = n_actions), `test_critic_forward_shape` (scalar), `test_train_step_updates_weights` (weights change after step), `test_experience_buffer_capacity` (oldest dropped at max), `test_training_trigger_by_buffer_full` |
| 31-35 | Edge cases | `test_negative_cost_clamped_to_zero`, `test_nan_score_replaced_with_zero`, `test_inf_score_clamped_to_one`, `test_missing_factor_defaults_to_0_5`, `test_all_factors_max_equals_max_score` |
| 36-37 | A2C convergence | `test_entropy_bonus_prevents_collapse`, `test_degenerate_policy_detection` |

### 4.3 TestContextEngine

**File:** `tests/unit/test_context_engine.py` | **Source:** `core/loop/context_engine.py` (358 lines)

**Scope:** 14 domains hydrate correctly, full context build contains all domains, empty domain produces placeholder, domain crash isolation (one crash doesn't take down others), session prompt format and token count, TokenJuice compression preserves critical sections, incremental single-domain update, build latency under 100ms.

**14 domains:** time, system, filesystem, network, process, user, memory, state, permissions, sensors, inference, phone, districts, errors.

**Tests (25):**

| # | Group | Tests |
|---|-------|-------|
| 1-14 | Per-domain | `test_time_domain`, `test_system_domain`, `test_filesystem_domain`, `test_network_domain`, `test_process_domain`, `test_user_domain`, `test_memory_domain`, `test_state_domain`, `test_permissions_domain`, `test_sensors_domain`, `test_inference_domain`, `test_phone_domain`, `test_districts_domain`, `test_errors_domain` — each verifies the returned dict has expected keys and non-null values |
| 15 | Full build | `test_full_context_contains_all_14_domains` — `build()` dict has all 14 keys |
| 16 | Completeness | `test_full_context_has_no_empty_domains` — no domain is None or empty unless expected |
| 17 | Empty handling | `test_empty_domain_returns_placeholder` — sensor domain with no data returns 'no data' |
| 18 | Crash isolation | `test_domain_crash_does_not_affect_others` — one domain raising doesn't affect other 13 |
| 19 | Session prompt | `test_session_prompt_format` — returns formatted string containing all domain sections |
| 20 | Token count | `test_session_prompt_token_count` — rough token estimate is returned and positive |
| 21 | TokenJuice compression | `test_token_juice_compression` — compresses prompt below token budget |
| 22 | Critical sections | `test_token_juice_preserves_critical_sections` — permissions, errors sections survive compression |
| 23 | Incremental update | `test_incremental_update` — `update_domain('system', data)` updates single domain |
| 24 | Latency | `test_build_latency_under_100ms` — full context build completes in < 100ms |
| 25 | Concurrent | `test_concurrent_builds` — 5 concurrent `build()` calls all complete |

### 4.4 TestPermissionGateway

**File:** `tests/unit/test_permission_gateway.py` | **Source:** `core/loop/permission_gateway.py`

**Scope:** All 42 action types individually parametrized across GREEN (20 auto-approve), YELLOW (15 confirm), RED (7 block). Unknown/empty/None action handling. Parameter edge cases (None params, empty dict, unexpected keys). Rate limiting (default window, exceeded resets, per-type buckets, config override). Config modes (disabled auto-approves all, strict mode rejects YELLOW, permissive mode approves YELLOW, reload). Audit logging (approval, denial, retrieval, rotation).

**Tests (40):**

| # | Group | Tests |
|---|-------|-------|
| 1-20 | GREEN parametrized | `test_green_action_{action}` — each of 20 GREEN types returns `(True, 'auto_approved')` |
| 21-35 | YELLOW parametrized | `test_yellow_action_{action}` — each of 15 YELLOW types returns `(False, 'requires_confirmation')` |
| 36-42 | RED parametrized | `test_red_action_{action}` — each of 7 RED types returns `(False, 'blocked')` |
| 43 | Unknown action | `test_unknown_action_rejected` — returns `(False, 'unknown_action')` |
| 44 | Empty string | `test_empty_action_string_raises` — raises ValueError |
| 45 | None action | `test_none_action_raises` — raises TypeError |
| 46 | Case sensitivity | `test_case_sensitivity` — 'File.Read' ≠ 'file.read' |
| 47-49 | Parameter edge cases | `test_none_params`, `test_empty_params`, `test_unexpected_params` — no crash |
| 50-54 | Rate limiting | `test_rate_limit_default_window`, `test_rate_limit_exceeded`, `test_rate_limit_resets_after_window`, `test_rate_limit_per_action_type`, `test_rate_limit_config_override` |
| 55-58 | Config modes | `test_disabled_gateway_auto_approves_all`, `test_strict_mode_rejects_yellow`, `test_permissive_mode_approves_yellow`, `test_config_reload_updates_classification` |
| 59-62 | Audit logging | `test_approval_logged_with_timestamp`, `test_denial_logged_with_reason`, `test_audit_log_retrieval`, `test_audit_log_rotation` |

### 4.5 TestMemory All

**Files:** `tests/memory/test_*.py` (10 files) | **Source:** `core/memory/*`

**Scope:** All 8+ memory types with roundtrip (write→read→verify), search (exact, fuzzy, semantic, time-range), edge cases (empty store, nonexistent query, large content, concurrent access, corrupted data), cross-type consistency via memory_roundtrip.

#### TestEpisodicMemory — `core/memory/episodic.py` (404 lines)

| Test | What It Verifies |
|------|------------------|
| `test_store_and_retrieve_by_id` | Store episode, retrieve by UUID, all fields match |
| `test_fts5_search_returns_relevant_results` | Full-text search returns episodes with matching content |
| `test_search_by_time_range` | Time-filtered search returns only episodes within window |
| `test_search_nonexistent_content_returns_empty_list` | Search for unique string returns [] |
| `test_delete_removes_episode` | Delete then retrieve returns None |
| `test_delete_nonexistent_id_does_not_raise` | Deleting already-deleted ID is idempotent |
| `test_encryption_at_rest` | Raw SQLite file does not contain plaintext content |
| `test_large_content_10k_chars` | 10,000 character content stores and retrieves byte-identical |
| `test_batch_store_100_episodes_under_1s` | 100 sequential stores complete within 1 second |
| `test_5_concurrent_writes_all_succeed` | 5 concurrent writes all return successfully |
| `test_fts5_bm25_scores_non_negative` | Search results have BM25 relevance scores >= 0 |
| `test_count_returns_correct_total` | After storing N episodes, count() == N |
| `test_clear_removes_all_episodes` | clear() empties the store, count() == 0 |
| `test_search_limit_and_offset` | search(limit=5, offset=10) returns correct window |
| `test_episode_with_no_content` | Empty content episode stores and retrieves |

#### TestSemanticMemory — `core/memory/semantic.py`

| Test | What It Verifies |
|------|------------------|
| `test_store_text_with_embedding` | Store text + embedding vector |
| `test_similarity_search_returns_most_similar_first` | Nearest-neighbor returns highest cosine similarity first |
| `test_search_with_score_threshold` | threshold=0.9 filters out below-threshold results |
| `test_search_on_empty_store_returns_empty_list` | No data → [] |
| `test_768_dimension_embeddings` | 768-dim vectors store and match correctly |
| `test_delete_by_id_removes_vector` | Delete followed by search excludes deleted item |
| `test_store_and_retrieve_metadata` | Metadata dict (source, timestamp, tags) stored alongside embedding |
| `test_collection_stats` | Stats returns correct count and dimension |
| `test_duplicate_content_handling` | Same content stored twice → two entries |
| `test_search_with_top_k` | top_k=3 returns at most 3 results |

#### TestPolicyMemory — `core/memory/policy.py`

| Test | What It Verifies |
|------|------------------|
| `test_store_policy_weights_returns_path` | state_dict saved to disk, path returned |
| `test_load_policy_weights_shapes_match` | Loaded weights have same tensor shapes as stored |
| `test_load_nonexistent_policy_returns_none` | policy_name not found returns None |
| `test_list_policies_returns_all_names` | list() includes all stored policy names |
| `test_delete_policy_removes_files` | Delete removes weight files from disk |
| `test_version_tracking_increments` | Each store() increments version counter |
| `test_corrupted_file_raises_descriptive_error` | Invalid .pt file raises PolicyError with helpful message |
| `test_same_name_overwrites_previous_version` | store() with existing name overwrites, version increments |

#### TestReasoningMemory — `core/memory/reasoning_memory.py`

| Test | What It Verifies |
|------|------------------|
| `test_store_named_template` | Template stored with name, retrievable by name |
| `test_retrieve_existing_template` | Retrieved template content matches stored |
| `test_compose_fills_variables` | `compose("greeting", name="World")` → "Hello World" |
| `test_compose_missing_variable_raises_keyerror` | Unfilled variable raises KeyError with variable name |
| `test_compose_extra_variables_ignored` | `compose("greeting", name="A", unused="B")` — no error, "B" not inserted |
| `test_list_templates_returns_all` | After storing 3 templates, list() returns 3 names |
| `test_delete_template_removes_it` | Delete then retrieve returns None |
| `test_template_chain_store_compose_verify` | Store → retrieve → compose → output matches expected |

#### TestKnowledgeGraph — `core/memory/knowledge_graph.py`

| Test | What It Verifies |
|------|------------------|
| `test_insert_triple_adds_edge` | (S, P, O) creates graph edge |
| `test_query_by_subject_returns_triples` | All triples with matching subject |
| `test_query_by_object_returns_triples` | All triples with matching object |
| `test_query_by_predicate_returns_triples` | All triples with matching predicate |
| `test_query_nonexistent_subject_returns_empty_list` | No results → [] |
| `test_delete_removes_specific_triple` | Delete then query excludes triple |
| `test_stats_returns_node_and_edge_count` | After N inserts, stats matches |
| `test_import_from_json_ld` | Import JSON-LD format, verify graph built |
| `test_export_to_json_ld_roundtrip` | Export → re-import → same graph |
| `test_subgraph_extraction_by_depth` | subgraph(node, depth=2) returns connected nodes within 2 hops |
| `test_merge_two_graphs` | Merge combines nodes and edges from both |
| `test_bfs_path_finding` | Path exists between connected nodes |
| `test_cycle_detection` | detect_cycles() returns True for cyclic graph |

#### TestCausalGraph — `core/memory/causal_graph.py`

| Test | What It Verifies |
|------|------------------|
| `test_add_causal_edge` | cause → effect edge created |
| `test_add_causal_edge_with_confidence_weight` | Edge has confidence weight attribute |
| `test_query_causes_returns_all_causes` | All causes of an effect node |
| `test_query_effects_returns_all_effects` | All effects of a cause node |
| `test_acyclic_enforcement_raises_on_cycle` | Adding edge that creates cycle raises CycleError |
| `test_do_calculus_intervention` | `do(node, value)` simulates intervention, updates downstream nodes |
| `test_counterfactual_query` | What-if: cause had been different → different effect |
| `test_confounding_detection` | Returns confounders (common cause) between two nodes |
| `test_backdoor_adjustment_set` | Calculates minimal adjustment set for causal effect estimation |
| `test_empty_graph_queries_return_empty` | Query on empty graph returns [] |

#### TestCounterfactual — `core/memory/counterfactual.py`

| Test | What It Verifies |
|------|------------------|
| `test_generate_counterfactual` | Create what-if from cause-effect pair |
| `test_store_and_retrieve_counterfactual` | Store then retrieve by original action ID |
| `test_similarity_search` | Find similar counterfactuals by embedding distance |
| `test_prune_outdated_older_than_threshold` | Remove counterfactuals older than TTL |
| `test_retrieve_nonexistent_returns_none` | Unknown ID returns None |
| `test_counterfactual_contains_expected_fields` | Original action, alternative, predicted outcome, confidence |

#### TestSkillMemory — `core/memory/skill_memory.py`

| Test | What It Verifies |
|------|------------------|
| `test_record_skill_sequence` | Record [action1, action2, action3] as a named skill |
| `test_retrieve_skill_by_name` | Retrieve returns same action sequence |
| `test_replay_produces_same_actions` | Replay produces identical action sequence |
| `test_skill_generalization` | Generalize to similar context (parameterized action values) |
| `test_skill_frequency_tracking` | Each execution increments frequency counter |
| `test_skill_pruning_removes_least_used` | Over capacity, least-used skill is removed |

#### TestAgentHistory — `core/memory/agent_history.py`

| Test | What It Verifies |
|------|------------------|
| `test_add_conversation_turn` | Add entry with role, content, timestamp |
| `test_get_full_history` | Returns all entries in order |
| `test_get_recent_n_entries` | last(5) returns most recent 5 |
| `test_truncate_to_max_length` | Over max, oldest entries removed |
| `test_search_history_by_text` | Full-text search returns matching entries |

#### TestMemoryRoundtrip — cross-type consistency

| Test | What It Verifies |
|------|------------------|
| `test_episodic_to_semantic_consolidation` | Episodic entry → semantic embedding preserves key content and ID |
| `test_repeated_actions_become_skills` | Same action sequence repeated N times → skill created |
| `test_knowledge_graph_to_causal_derivation` | KG triples (A→B, B→C) can derive causal edge (A→C) |
| `test_all_memory_types_use_uuid_format` | All memory IDs are valid UUIDv4 |

### 4.6 TestAgentBase

**File:** `tests/unit/test_agent_base.py` | **Source:** `core/city/agent_base.py`

**Scope:** HP bounds [0, max_hp], negative clamped to 0, over-max clamped to max_hp, take_damage decrements correctly, heal increments correctly (capped at max), HP=0 triggers death state, dead agent raises AgentDeadError on act(), state machine transitions (idle→busy→idle, idle→busy→dead), dead→idle raises (resurrection required), resurrection sets state to idle, concurrent action while busy is blocked, action logging includes timestamp and result, error logging includes traceback, log rotation at max entries, log query returns entries in order.

**Tests (15):** test_initial_hp_matches_config, test_hp_bounds_range, test_hp_negative_clamped, test_hp_over_max_clamped, test_take_damage_reduces_hp, test_heal_increases_hp, test_hp_zero_triggers_death, test_dead_agent_cannot_act, test_initial_state_is_idle, test_idle_transitions_to_busy_on_act, test_busy_blocks_concurrent_action, test_busy_transitions_to_dead_on_fatal_error, test_dead_to_idle_requires_resurrection, test_resurrection_sets_state_to_idle, test_action_logged_with_timestamp_and_result.

### 4.7 TestGovernor

**File:** `tests/unit/test_governor.py` | **Source:** `core/city/governor.py`

**Scope:** Intent routing to correct district, ambiguous intents routed to council session, unknown intents fall back to default handler, fallback chain executes in order (primary → fallback_1 → fallback_2), all fallbacks exhausted returns error, route to named agent, route to nonexistent agent uses fallback, successful action increases agent HP (+1), denied action decreases agent HP (-1), dead agents skipped during routing, governor can resurrect dead agents, concurrent requests (5) all receive responses, queue overflow blocks when full, high-priority requests jump the queue.

**Tests (15):** test_route_to_correct_district, test_ambiguous_intent_routes_to_council, test_unknown_intent_uses_fallback, test_fallback_chain_execution, test_all_fallbacks_exhausted, test_route_to_named_agent, test_route_to_nonexistent_agent_uses_fallback, test_successful_action_increases_hp, test_denied_action_decreases_hp, test_dead_agent_skipped_in_routing, test_governor_can_resurrect_agent, test_concurrent_routes_all_succeed, test_queue_blocked_when_full, test_priority_queue_bypasses_blocked_normal, test_no_registered_districts_returns_error.

### 4.8 TestEvolutionEngine

**File:** `tests/unit/test_evolution_engine.py` | **Source:** `core/city/evolution_engine.py`

**Scope:** HP decays by configured rate per time interval, decay stops at 0 (never negative), HP=0 triggers death state, dead agent's memory preserved as ghost (tagged with agent_id + 'ghost' flag), active agents are not ghosted, resurrect restores HP to configured starting value, successful action increases HP by configured gain, failed action decreases HP by configured penalty, high-cost action incurs extra HP penalty, critical success grants bonus HP, cumulative stats tracked (total_actions, successes, failures, timeouts).

**Tests (10):** test_hp_decays_by_rate_per_interval, test_hp_decay_stops_at_zero, test_death_trigger_at_zero_hp, test_ghost_memory_preserved_on_death, test_ghost_memory_tagged_with_agent_id_and_flag, test_active_agents_not_ghosted, test_resurrect_restores_hp_to_start, test_successful_action_increases_hp, test_failed_action_decreases_hp, test_stats_accumulation_tracks_all_events.

### 4.9 TestConfig

**File:** `tests/unit/test_config.py` | **Source:** `core/config.py` (555 lines)

**Scope:** Default values for all fields, VECTOR_-prefixed env vars override config values, config file overrides defaults, env vars take precedence over file values, API keys redacted in __repr__ and __str__ (never leaked), missing required env var raises ConfigError, invalid type raises Pydantic ValidationError, port values outside 1-65535 raise ValidationError, negative timeout raises ValidationError, log level case-insensitive (DEBUG=debug), unknown config keys ignored with warning, nested config accessible via double-underscore (VECTOR_OLLAMA__HOST), reload() returns diff dict, API key not present in `caplog` output, masked secrets in repr show only first 4 chars, all 10+ sub-configs have all required fields non-None.

**Tests (25):** test_loads_with_defaults, test_env_var_override, test_env_prefix_vector, test_config_file_override, test_env_takes_precedence_over_file, test_secret_redacted_in_repr, test_secret_not_in_str, test_missing_required_raises_config_error, test_invalid_type_raises_validation_error, test_port_range_validation, test_negative_timeout_raises, test_level_case_insensitive, test_unknown_field_ignored_with_warning, test_nested_double_underscore_env_var, test_reload_returns_diff, test_api_key_not_in_logs, test_repr_shows_only_first_4_secret_chars, test_ollama_sub_config, test_memory_sub_config, test_loop_sub_config, test_permission_sub_config, test_voice_sub_config, test_phone_sub_config, test_dashboard_sub_config, test_logging_sub_config.

### 4.10 TestMcpServer

**Files:** `tests/mcp/test_mcp_server.py` + `test_mcp_fuzz.py` | **Source:** `core/mcp_server.py` (300+ tools)

**Scope:** All 300+ tools register without error, no duplicate tool names, every tool has non-empty description and input_schema, every tool has return type annotation, valid parameters produce successful execution, missing required params raise ValidationError, invalid param types raise ValidationError, empty optional params accepted or handled gracefully, tool execution returns dict, error during execution caught and returned as error dict, timeout returns descriptive error message.

**Fuzz:** 100 random tool calls with random parameters complete without server crash, high-risk tools (file.write, shell.exec, network.connect, process.start) tested with deliberately malformed params.

| Test | What It Verifies |
|------|------------------|
| `test_all_tools_registered` | `server.list_tools()` returns >= 300 entries |
| `test_no_duplicate_tool_names` | All tool names are unique |
| `test_all_tools_have_descriptions` | Every tool.description is non-empty |
| `test_all_tools_have_input_schema` | Every tool.input_schema is defined |
| `test_all_tools_have_return_annotation` | Every tool has return type annotation |
| `test_valid_params_succeed` | Each tool with valid params returns success |
| `test_missing_required_params_raise` | Required param omitted → ValidationError |
| `test_invalid_param_types_raise` | Wrong type for param → ValidationError |
| `test_empty_optional_params_accepted` | Empty string/None for optional is allowed |
| `test_execution_error_returns_error_dict` | Runtime error in tool → {"error": "..."} dict |
| `test_timeout_returns_descriptive_error` | Tool timeout → error dict with "timeout" |
| `test_fuzz_100_random_calls` | 100 calls with random params → server still running |
| `test_fuzz_high_risk_tool_params` | file.write with None path, shell.exec with empty cmd → graceful handling |

### 4.11 TestDistricts

**File:** `tests/districts/test_all_districts.py` | **Source:** all 49 districts

**Scope:** Every district can be instantiated with default constructor, has non-empty `name` and `description` attributes, has async `run()` method, inherits from AgentBase (checked via `isinstance` or `__mro__`), run() with mock input returns dict containing 'result' key, run() with empty/None input returns graceful error dict, HP initialized to configured value (verified via agent_base HP fixture), fallback district defined (or None for leaf districts), capabilities list is non-empty.

**Tests (10 parametrized × 49 districts = 490 test cases):** test_instantiation, test_has_name, test_has_description, test_has_run_method, test_inherits_agent_base, test_run_returns_dict, test_run_has_result_key, test_run_handles_empty_input, test_hp_initialized, test_capabilities_defined.

### 4.12 TestVoicePipeline

**Files:** `tests/voice/test_stt.py`, `test_tts.py`, `test_wake_word.py`, `test_ambient_listener.py` | **Source:** `core/voice/*`

**Tests (15):**

| File | Tests |
|------|-------|
| `test_stt.py` (5) | `test_transcribe_returns_text` (audio→string), `test_transcribe_empty_audio_returns_empty_string`, `test_transcribe_silence_returns_none`, `test_transcribe_ollama_timeout_returns_error`, `test_transcribe_concurrent_calls` |
| `test_tts.py` (3) | `test_synthesize_returns_audio_bytes`, `test_synthesize_empty_text_returns_none`, `test_synthesize_rate_limited` (rate limit blocks within window) |
| `test_wake_word.py` (3) | `test_detects_wake_word` (known phrase → detected=True), `test_ignores_noise_without_wake_word` (random noise → detected=False), `test_below_confidence_threshold_ignored` (low-confidence match → ignored) |
| `test_ambient_listener.py` (4) | `test_listen_cycle_orchestrates_pipeline` (audio→wake word→STT→result), `test_no_wake_word_skips_stt` (wake word false → STT not called), `test_10_consecutive_listen_cycles` (all complete without error), `test_stop_halts_listen_loop` (stop() → listen loop exits) |

### 4.13 TestPhoneNode

**Files:** `tests/phone/test_ambient_server.py`, `test_adb_bridge.py` | **Source:** `phone_node/*`

**Tests (10):**

| File | Tests |
|------|-------|
| `test_ambient_server.py` (6) | `test_heartbeat_returns_status_dict`, `test_battery_level_reported_correctly`, `test_low_battery_triggers_alert`, `test_alert_pushed_to_memory`, `test_connection_lost_returns_error_status`, `test_reconnect_restores_heartbeat` |
| `test_adb_bridge.py` (4) | `test_connect_success_returns_true`, `test_connect_failure_returns_false`, `test_shell_command_returns_stdout`, `test_shell_timeout_returns_error` |

### 4.14 Fixture Factories

**File:** `tests/mock_factory.py`

| Factory | Methods | Purpose |
|---------|---------|---------|
| **MockWorldState** | `minimal()` — required fields only. `complete()` — all 14 domains populated. `with_sensors(has_camera, has_mic)` — camera frame + mic signal. `with_errors(count)` — N recent error entries. `empty()` — no domains, edge case. | Provides deterministic world state for context_engine, decision_engine, autonomous_loop tests |
| **MockMemory** | In-memory dicts/lists for all 8 types. Methods: `store_episode()`, `search_episodes()`, `store_policy()`, `load_policy()`, `insert_triple()`, `add_causal_edge()`, `store_skill()`, `add_history()`, etc. | Zero-side-effect memory backend for all tests |
| **MockOllama** | Wraps `pytest_httpx` to intercept `http://127.0.0.1:11434/api/*`. Methods: `set_generate_response(text)`, `set_embed_response(vector)`, `set_list_response(models)`, `set_timeout()`, `set_error(status, msg)`. | Makes Ollama deterministic — no real inference in tests |
| **MockPermissionGateway** | Three modes: `approve_all()` (permissive), `deny_all()` (locked), `deny_specific(actions)`. Method: `check(action, params)` returns `(bool, str, timestamp)`. | Isolates permission tests from real gateway logic |
| **MockHTTPServer** | Class method `create(routes)` starts real localhost HTTP server. `stop()` terminates. `.url` property returns base URL. | Used by integration tests for realistic HTTP roundtrips |

---

## 5. Mock Strategy

### 5.1 Principles

1. **Every external call is mocked at the network boundary.** No real Ollama, SQLite (except `:memory:`), ChromaDB, camera, microphone, or ADB calls in unit tests.
2. **Mock factories produce predictable, configurable responses.** Tests never depend on real hardware state or network latency.
3. **Integration tests use `:memory:` databases and localhost servers.** Real in-process databases but no outbound network.
4. **Fixture scoping matches usage.** Module-scoped for slow initialization (MockHTTPServer), function-scoped for mutable state (MockMemory).
5. **Autouse fixture blocks unmocked HTTP.** Any test that makes an un-mocked HTTP request fails immediately with a clear error message.
6. **Time is always frozen** for cron, reflect interval, and HP decay tests. No real wall-clock dependency.

### 5.2 Dependency Mocking Details

| Dependency | Mock Strategy | Tool | Implementation Details |
|------------|---------------|------|----------------------|
| **Ollama REST API** | Intercept httpx at `http://127.0.0.1:11434/api/*` | `pytest-httpx` | `MockOllama` class sets canned responses for generate, embed, list, chat, pull, delete endpoints. Timeout mode raises `httpx.ReadTimeout`. Error mode returns configurable status code + message. Default mode returns realistic fake responses (e.g., generate returns '{"response": "Mock response"}') |
| **SQLite** | In-memory `:memory:` database | `sqlite3` built-in | Fresh database per test. AES-256 encryption replaced with `cryptography.fernet.Fernet` using test key `"testing-key-must-be-32-bytes-long!"`. DB cleaned up automatically when fixture goes out of scope. |
| **ChromaDB** | Ephemeral in-memory client | `chromadb.Client(Settings(is_persistent=False))` | Created per `test_episodic` module. `reset()` called between tests. No disk I/O. |
| **FastAPI** | `TestClient` wrapping async ASGI transport | `httpx.AsyncClient(app=app, base_url="http://test")` | In-process request/response, no network. CORS headers present in response. |
| **Camera** | Mock numpy array (640×480×3, uint8 gradient) | `unittest.mock.patch` | `Camera.capture()` returns fixed gradient frame. No-camera mode returns `None`. Permission error raises `CameraError`. |
| **Microphone** | Mock numpy array (16,000 samples, float32) | `unittest.mock.patch` | `Microphone.listen()` returns silence (all zeros), known wake word (pattern match), or noise (random). Duration configurable. |
| **Network (all HTTP)** | Intercept with callback that fails on unmocked | `pytest-httpx` | Autouse fixture `_block_network` registers catch-all callback that calls `pytest.fail("Unexpected HTTP: {method} {url}")`. Per-test code registers allowed routes via `httpx_mock.add_response()`. |
| **psutil** | Mock all function return values | `unittest.mock.patch` | `MockPsutil` fixture patches: `cpu_percent()` → 45.0, `virtual_memory().percent` → 62.0, `virtual_memory().available` → 8GB, `disk_usage('/').percent` → 55.0, `disk_usage('/').free` → 100GB, `net_connections()` → [(TCP, ESTABLISHED, ...)] |
| **GPU (pynvml)** | Mock nvidia-smi wrapper | `unittest.mock.patch` | `get_gpu_stats()` → `{"gpu_usage": 30.0, "vram_used": 4096, "vram_total": 12288, "temperature": 65.0}` |
| **ADB** | Mock `subprocess.run()` | `pytest-mock` | `subprocess.run()` returns `CompletedProcess(args, returncode=0, stdout=b"device", stderr=b"")`. Timeout mode raises `subprocess.TimeoutExpired`. Fail mode returns returncode=1. |
| **Audio playback** | No-op replacement | `unittest.mock.patch` | `AudioPlayer.play()` returns immediately without calling any audio device. |
| **Time** | Freeze at known UTC timestamp | `time-machine` | `freezer` fixture freezes at `2026-05-20 10:00:00+00:00` with `tick=False`. Advance time via `traveller.shift(seconds=N)`. Essential for cron, reflect interval, HP decay, rate limit reset tests. |
| **File system** | Temp directory per test | `pytest tmp_path` fixture | Auto-created per function, deleted after test. Symlinks, permissions, empty dir all available. |
| **Environment variables** | Per-test override with restore | `monkeypatch` (built-in) | `monkeypatch.setenv()` / `delenv()` restored after test. Use `monkeypatch.setattr(os, 'environ', {})` for full env isolation. |
| **Random/seed** | Fixed seed for reproducibility | `random.seed(42)` in conftest | All tests using random numbers get deterministic sequences. A2C weight initialization, temperature sampling, noise generation all reproducible. |

### 5.3 conftest.py Shared Fixtures

```python
# All shared fixtures, available to every test file under tests/

@pytest.fixture
def mock_ollama(httpx_mock):
    """Intercept http://127.0.0.1:11434/api/* with canned responses."""
    mock = MockOllama(httpx_mock)
    mock.set_generate_response("Mock response text")
    mock.set_embed_response([0.1] * 768)
    return mock

@pytest.fixture
def mock_world_state():
    """Return MockWorldState factory class."""
    return MockWorldState

@pytest.fixture
def mock_memory():
    """Return fresh in-memory MockMemory instance."""
    memory = MockMemory()
    yield memory

@pytest.fixture
def mock_permission_gateway():
    """Return MockPermissionGateway in normal mode."""
    return MockPermissionGateway(mode="normal")

@pytest.fixture(autouse=True)
def _block_network(httpx_mock):
    """Fail any test that makes an unmocked HTTP request."""
    httpx_mock.add_callback(
        lambda request: pytest.fail(
            f"Unmocked HTTP request: {request.method} {request.url}"
        )
    )

@pytest.fixture
def mock_psutil(mocker):
    """Mock system statistics."""
    mock = {}

@pytest.fixture
def mock_sensors(mocker):
    """Mock camera + microphone inputs."""

@pytest.fixture
def mock_phone(mocker):
    """Mock phone node heartbeat."""

@pytest.fixture
def mock_audio():
    """Return numpy zeros array (16kHz, 1s, float32)."""

@pytest.fixture
def mock_noise():
    """Return numpy random array (16kHz, 1s, float32)."""

@pytest.fixture
def freezer():
    """Freeze time at 2026-05-20T10:00:00Z using time-machine."""
```

---

## 6. Agent Dispatch Plan

Three agents running in parallel worktrees, each with isolated scope and no file overlap.

### 6.1 Agent A — Core Unit Tests (2 days, ~170 tests + fixture factories)

**Focus:** 7 highest-impact modules + all fixture factories + conftest + sample data.

| Day | Work | Deliverables |
|-----|------|-------------|
| 1 AM | Fixture infrastructure | `tests/mock_factory.py` (5 factory classes), `tests/fixtures/*.py` (4 sample data files), `tests/conftest.py` (15 fixtures including autouse) |
| 1 PM | Core loop tests | `test_autonomous_loop.py` (20 tests), `test_permission_gateway.py` (40 tests) |
| 2 AM | Decision + context | `test_decision_engine.py` (30 tests), `test_context_engine.py` (25 tests) |
| 2 PM | City + config | `test_agent_base.py` (15), `test_governor.py` (15), `test_evolution_engine.py` (10), `test_config.py` (25), `test_ollama_safe.py` (10) |

**Verification checkpoint:** Agent A deliverables must be merged before Agent C's CI work can proceed (coverage gate needs the tests).

### 6.2 Agent B — Memory + MCP + Districts + Voice + Phone + Dashboard (2 days, ~125 tests)

**Focus:** All 8 memory types, MCP server validation, district parametrized tests, voice/phone/dashboard.

| Day | Work | Deliverables |
|-----|------|-------------|
| 1 AM | Episodic + semantic + policy + reasoning | `test_episodic.py` (15), `test_semantic.py` (10), `test_policy.py` (8), `test_reasoning_memory.py` (8) |
| 1 PM | KG + causal + counterfactual + skill + history + roundtrip | `test_knowledge_graph.py` (12), `test_causal_graph.py` (10), `test_counterfactual.py` (6), `test_skill_memory.py` (6), `test_agent_history.py` (4), `test_memory_roundtrip.py` (4) |
| 2 AM | MCP + districts | `test_mcp_server.py` (10 parametrized across 300+ tools), `test_mcp_fuzz.py` (2 tests, 100 calls), `test_all_districts.py` (10×49 parametrized) |
| 2 PM | Voice + phone + dashboard | `test_stt.py` (5), `test_tts.py` (3), `test_wake_word.py` (3), `test_ambient_listener.py` (4), `test_ambient_server.py` (6), `test_adb_bridge.py` (4), `test_dashboard_api.py` (5) |

**Verification checkpoint:** Agent B can verify independently using conftest from Agent A (no circular dependency — both agents' tests use the same shared fixtures).

### 6.3 Agent C — CI Infrastructure + Test Harness + Integration Tests (1 day)

**Focus:** CI pipeline, coverage gate, tools, integration tests, performance baselines.

| Time | Work | Deliverables |
|------|------|-------------|
| AM | CI pipeline | `.github/workflows/test.yml` — parallel matrix (7 jobs), coverage gate (overall 80% + per-module), diff coverage job, artifact upload, notification |
| AM | Coverage config | `pyproject.toml` — `[tool.coverage.run]` (source, omit), `[tool.coverage.report]` (fail_under, exclude_lines). `pytest.ini` — 11 markers, asyncio_mode, filterwarnings |
| AM | Tools | `scripts/pretest_smoke.py` — validates 16 module imports + 8 packages. `scripts/check_coverage.py` — reads XML, enforces per-module thresholds, prints table |
| PM | Integration tests | `test_loop_integration.py` (3), `test_memory_integration.py` (3), `test_governor_council.py` (3) |
| PM | Performance + docs | `test_loop_latency.py` (2), `tests/README.md` — test conventions, run instructions, marker reference |

---

## 7. Implementation Steps

### 7.1 Fixtures & Infrastructure (Steps 1-8)

1. **Create `tests/__init__.py`** — empty package marker
2. **Create `tests/mock_factory.py`** — implement MockWorldState (5 methods), MockMemory (15+ methods mirroring all memory types), MockOllama (6 methods: generate, embed, list, set_timeout, set_error, _setup_defaults), MockPermissionGateway (4 modes + check method), MockHTTPServer (class+static for async create/stop)
3. **Verify mock factory** — `python -c "from tests.mock_factory import MockWorldState, MockMemory, MockOllama; print('MockFactory OK')"`
4. **Create `tests/fixtures/`** — `__init__.py`, `sample_world_states.py` (5 dicts: minimal, complete, with_sensors, with_errors, empty), `sample_actions.py` (dict mapping action name → {type, params, expected_classification}), `sample_decisions.py` (list of candidate dicts with varied scores), `sample_memories.py` (pre-built entries for all 8 types)
5. **Create `tests/conftest.py`** — all 15 shared fixtures: mock_ollama, mock_world_state, mock_memory, mock_permission_gateway, _block_network (autouse), mock_psutil, mock_sensors, mock_phone, mock_audio, mock_noise, freezer, mock_gpu_stats
6. **Create package markers** — `tests/unit/__init__.py`, `tests/memory/__init__.py`, `tests/mcp/__init__.py`, `tests/districts/__init__.py`, `tests/voice/__init__.py`, `tests/phone/__init__.py`, `tests/dashboard/__init__.py`, `tests/integration/__init__.py`, `tests/performance/__init__.py`
7. **Run fixture smoke test** — `pytest tests/conftest.py --collect-only` — verify all fixtures are discovered
8. **Verify existing tests still pass** — `pytest tests/` — all 27 existing tests pass with new conftest

### 7.2 Agent A: Core Unit Tests (Steps 9-17)

9. **`tests/unit/test_autonomous_loop.py`** — 20 tests using loop fixture, mock_ollama, freezer
10. **`tests/unit/test_decision_engine.py`** — 37 tests using engine fixture, mock_ollama, mock_world_state, mock_memory
11. **`tests/unit/test_context_engine.py`** — 25 tests using engine fixture, mock_world_state, mock_memory, mock_sensors, mock_psutil, freezer
12. **`tests/unit/test_permission_gateway.py`** — 62 tests parametrized across 42 action types + edge cases
13. **`tests/unit/test_agent_base.py`** — 15 tests using agent fixture, various state transitions
14. **`tests/unit/test_governor.py`** — 15 tests using governor fixture, registry, mock_ollama, mock_memory
15. **`tests/unit/test_evolution_engine.py`** — 10 tests using engine fixture, registry, mock_memory, freezer
16. **`tests/unit/test_config.py`** — 25 tests using monkeypatch, tmp_path
17. **`tests/unit/test_ollama_safe.py`** — 10 tests using mock_ollama, httpx_mock

### 7.3 Agent B: Memory, MCP, Districts, Voice, Phone, Dashboard (Steps 18-28)

18. **`tests/memory/test_episodic.py`** — 15 tests, use `tmp_path` for SQLite file, `cryptography` for AES verify
19. **`tests/memory/test_semantic.py`** — 10 tests, use ephemeral ChromaDB fixture
20. **`tests/memory/test_policy.py`** — 8 tests, use `tmp_path` for tensor storage
21. **`tests/memory/test_reasoning_memory.py`** — 8 tests, pure dict-based
22. **`tests/memory/test_knowledge_graph.py`** — 13 tests, use NetworkX in-memory
23. **`tests/memory/test_causal_graph.py`** — 10 tests, use NetworkX DAG
24. **`tests/memory/test_counterfactual.py`** — 6 tests, dict-based
25. **`tests/memory/test_skill_memory.py`** + **`test_agent_history.py`** — 6 + 4 tests
26. **`tests/memory/test_memory_roundtrip.py`** — 4 tests using all memory fixtures
27. **`tests/mcp/test_mcp_server.py`** + **`test_mcp_fuzz.py`** — 10 + 2 tests, use server fixture with all mocked backends
28. **`tests/districts/test_all_districts.py`** — parametrized fixture loading all 49 modules dynamically via `importlib`
29. **Voice/phone/dashboard tests** — 30 tests across 7 files using mock_ollama, mock_audio, mock_phone

### 7.4 Agent C: CI + Harness (Steps 30-34)

30. **Update `.github/workflows/test.yml`** — parallel matrix (unit, memory, mcp, districts, voice, phone, dashboard), coverage-gate job (`--cov-fail-under=80`, per-module sub-gates `--cov-fail-under=90/85/85/70`), diff-coverage job, upload coverage artifacts, failure notification
31. **Update `pyproject.toml`** — `[tool.coverage.run]` source=core,phone_node,dashboard,districts; omit=test_*,__init__,_version.py; `[tool.coverage.report]` fail_under=80, show_missing=true, precision=1; exclude_lines for pragma, __repr__, NotImplementedError, __main__
32. **Update `pytest.ini`** — testpaths = tests, asyncio_mode = auto, 11 markers (unit,memory,mcp,districts,voice,phone,dashboard,integration,performance,slow,flaky), filterwarnings for DeprecationWarning
33. **Create `scripts/pretest_smoke.py`** — validates 16 module imports, 8 package imports, prints PASS/FAIL, exits 0/1
34. **Create `scripts/check_coverage.py`** — reads `coverage.xml`, enforces per-module thresholds from `pyproject.toml`, prints formatted table with module/actual/target/pass-fail columns
35. **Integration + performance tests** — 9 tests across 4 files using MockHTTPServer and loop fixture
36. **Update dev dependencies** — add `pytest-cov`, `pytest-httpx`, `time-machine` to `[project.optional-dependencies] dev`
37. **Final verification** — `python scripts/pretest_smoke.py && pytest tests/ --cov=core --cov-report=term`

---

## 8. Files to Create/Modify

### 8.1 New Files (52 total)

| Dir | Count | Files |
|-----|-------|-------|
| `tests/` | 4 | `__init__.py`, `conftest.py`, `mock_factory.py`, `README.md` |
| `tests/fixtures/` | 5 | `__init__.py`, `sample_world_states.py`, `sample_actions.py`, `sample_decisions.py`, `sample_memories.py` |
| `tests/unit/` | 10 | `__init__.py`, `test_autonomous_loop.py`, `test_decision_engine.py`, `test_context_engine.py`, `test_permission_gateway.py`, `test_agent_base.py`, `test_governor.py`, `test_evolution_engine.py`, `test_config.py`, `test_ollama_safe.py` |
| `tests/memory/` | 11 | `__init__.py`, `test_episodic.py`, `test_semantic.py`, `test_policy.py`, `test_reasoning_memory.py`, `test_knowledge_graph.py`, `test_causal_graph.py`, `test_counterfactual.py`, `test_skill_memory.py`, `test_agent_history.py`, `test_memory_roundtrip.py` |
| `tests/mcp/` | 3 | `__init__.py`, `test_mcp_server.py`, `test_mcp_fuzz.py` |
| `tests/districts/` | 2 | `__init__.py`, `test_all_districts.py` |
| `tests/voice/` | 5 | `__init__.py`, `test_stt.py`, `test_tts.py`, `test_wake_word.py`, `test_ambient_listener.py` |
| `tests/phone/` | 3 | `__init__.py`, `test_ambient_server.py`, `test_adb_bridge.py` |
| `tests/dashboard/` | 2 | `__init__.py`, `test_dashboard_api.py` |
| `tests/integration/` | 4 | `__init__.py`, `test_loop_integration.py`, `test_memory_integration.py`, `test_governor_council.py` |
| `tests/performance/` | 2 | `__init__.py`, `test_loop_latency.py` |
| `scripts/` | 2 | `pretest_smoke.py`, `check_coverage.py` |

### 8.2 Modified Files (4)

| File | Changes Required | Owner |
|------|-----------------|-------|
| `.github/workflows/test.yml` | Add 7-job parallel matrix, coverage gate (overall + per-module), diff coverage, artifact upload | C |
| `pyproject.toml` | Add `[tool.coverage.run]`, `[tool.coverage.report]` sections | C |
| `pytest.ini` | Add 11 markers, `asyncio_mode=auto`, `filterwarnings`, `testpaths` | C |
| `setup.py` / `pyproject.toml` deps | Add `pytest-cov`, `pytest-httpx`, `time-machine` to dev deps | C |

---

## 9. Success Criteria

### 9.1 Quantitative Gates

| # | Criterion | Target | Verification Method |
|---|-----------|--------|-------------------|
| 1 | Overall line coverage | >= 80% | `pytest --cov=core --cov-report=term --cov-fail-under=80` |
| 2 | Core loop coverage | >= 90% | `pytest tests/unit/ --cov=core.loop --cov-fail-under=90` |
| 3 | Memory coverage | >= 85% | `pytest tests/memory/ --cov=core.memory --cov-fail-under=85` |
| 4 | City coverage | >= 85% | `pytest tests/unit/ --cov=core.city --cov-fail-under=85` |
| 5 | Config coverage | >= 90% | `pytest tests/unit/test_config.py --cov=core.config --cov-fail-under=90` |
| 6 | MCP coverage | >= 70% | `pytest tests/mcp/ --cov=core.mcp_server --cov-fail-under=70` |
| 7 | Full CI runtime | < 5 min | GitHub Actions job wall clock |
| 8 | PR coverage gate | Blocks < 80% | Push below-threshold branch → CI check red |
| 9 | Zero regressions | All 27 old tests pass | `pytest tests/ -k "$(27 test names)"` |
| 10 | Flaky rate | < 1% | Full suite 3× consecutively, any failure logs are flagged |
| 11 | New test count | >= 295 | `pytest --collect-only --quiet | grep "test_" | Measure-Object -Line` |
| 12 | Tested modules | >= 25 distinct modules | Coverage report shows green for all target modules |

### 9.2 Qualitative Gates

- Mock factories are reusable: a new test file can pull in `mock_ollama`, `mock_memory`, and `mock_world_state` from conftest.py without writing any new fixture code.
- Test organization is navigable: each subdirectory in `tests/` corresponds to exactly one module group.
- CI output is actionable: when coverage drops below threshold, the CI log prints which modules are below target and by how much.
- Fixtures are well-scoped: no state leaks between tests (verified by running `pytest tests/ --random-order`).
- All tests are deterministic: running the same test 10 times produces the same result (verified by `pytest tests/ --count=10`).

### 9.3 Non-Goals

- **100% coverage.** 80% overall is the target. Rarely-triggered error handlers, CLI entry points, and platform-specific code remain uncovered.
- **Real hardware tests.** No real camera, microphone, Ollama, or ADB in CI. Covered by the mock strategy.
- **Property-based testing (Hypothesis).** Future enhancement.
- **Mutation testing (mutmut/cosmic-ray).** Future enhancement.
- **Performance regression baselines.** Latency measurements exist but no cross-build comparison. Future enhancement.

### 9.4 Rollback Conditions

The branch is rolled back if any of the following occur:
1. Any of the existing 27 tests fail with the new infrastructure in place (regression)
2. Full CI runtime exceeds 10 minutes (2× target)
3. Coverage measurement is incorrect due to config bugs (verified by manually checking 3 module coverage reports against source file line counts)
4. Mock leaks cause test interference (detected by `pytest --random-order` flakiness)

---

## 10. Dependencies

### 10.1 Python Packages

| Package | Min Version | Purpose | Status |
|---------|-------------|---------|--------|
| pytest | >= 8.0 | Test runner with fixture/parametrize/mark support | Installed |
| pytest-asyncio | >= 0.23 | `@pytest.mark.asyncio` for async test functions | Installed |
| pytest-cov | >= 5.0 | Coverage measurement, `--cov-fail-under`, XML report | **Not installed** |
| pytest-httpx | >= 0.30 | Intercept httpx requests; `httpx_mock` fixture | **Not installed** |
| time-machine | >= 2.14 | Fast `datetime`/`time` freezing; 8× faster than freezegun | **Not installed** |
| numpy | >= 1.24 | Mock camera frames (640×480×3), audio (16kHz×1s) | Installed |
| httpx | >= 0.27 | `TestClient` for FastAPI, `AsyncClient` for integration tests | Installed |
| psutil | >= 5.9 | System stats (CPU, RAM, disk) — mocked in tests | Installed |

### 10.2 System Requirements

- **Python >= 3.11** (already in use by VECTOR)
- **SQLite 3.37+** with FTS5 enabled — verify with `PRAGMA compile_options` returning `FTS5`
- **Ollama** at `127.0.0.1:11434` — needed only for local manual testing; fully mocked in CI

### 10.3 CI Services

- **GitHub Actions** — `ubuntu-latest`, Python 3.11, pip cache
- **Codecov** (optional) — `codecov/codecov-action@v4` for coverage dashboard

### 10.4 Installation Commands

```bash
# Install required packages
pip install pytest-cov pytest-httpx time-machine

# Or via pyproject.toml (after updating dev deps)
pip install -e ".[dev]"

# Verify installation
python -c "import pytest_cov; import pytest_httpx; import time_machine; print('All test deps installed')"
```

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **HP** | Hit Points — VECTOR's agent health metric. Decremented on failure, incremented on success. Zero = death. |
| **A2C** | Advantage Actor-Critic — RL algorithm in decision_engine for learning action selection policy. Actor outputs action probabilities, critic estimates state value. |
| **FTS5** | Full-Text Search version 5 — SQLite extension for fast content search with BM25 ranking. |
| **GREEN/YELLOW/RED** | Permission classification: GREEN = auto-approve, YELLOW = requires confirmation, RED = always blocked. |
| **TokenJuice** | Context compression system that reduces token count while preserving critical sections (permissions, errors). |
| **Ghost memory** | Memory of a deceased district agent, preserved with agent_id + 'ghost' flag for post-mortem analysis. |
| **MockFactory** | Pattern for creating configurable mock objects with sensible defaults and per-test overrides. |
| **AES-256** | Encryption used by episodic memory at rest. Tested via verify that plaintext is not in raw SQLite file. |

## Appendix B: Test Writing Conventions

| Rule | Standard |
|------|----------|
| File naming | `test_<module_or_group>.py` |
| Class naming | `Test<Module><Category>` (e.g., `TestPermissionGatewayRateLimit`) |
| Method naming | `test_<behavior>_<condition>` (e.g., `test_score_urgency_high`) |
| Assertions | Plain `assert` (not self.\*). `pytest.raises()` for exceptions. `pytest.warns()` for warnings. |
| Fixture scope | Most local possible (function scope default). Module scope only for expensive setup (ChromaDB client). |
| Mock boundary | Network boundary (httpx, subprocess). Never mock internal functions unless testing error recovery. |
| Parametrization | `@pytest.mark.parametrize` for input variations. `@pytest.fixture(params=...)` for module variants (districts). |
| Async tests | `async def` with `asyncio_mode=auto` in pytest.ini. Use `pytest.mark.asyncio` only for custom event loop config. |
| Cleanup | Fixture teardown via `yield`. Verify `tmp_path` is empty after test (no leaked files). |
| Coverage | Every new function: minimum 1 happy-path test + 1 error-path test. |
| Determinism | No random values without fixed seed. No wall-clock time without frozen time. |
| Isolation | No shared mutable state between tests. Each test gets fresh fixtures. |

## Appendix C: Priority Order for Test Writing

**P0 — Safety-critical (blocks CI gate, must be first):**
1. Permission gateway — 42 action types, rate limits, audit log
2. Autonomous loop — 11 tasks, crash recovery, circuit breaker
3. Decision engine — 5 factors, A2C, edge cases
4. Config — env override, secret redaction, validation
5. Agent base — HP bounds, state transitions, death
6. Governor — routing, fallback chain, unknown intent
7. MCP server — tool registration, param validation, fuzz
8. Episodic memory — FTS5, encryption, roundtrip

**P1 — Core functionality (high correctness requirement):**
9. Semantic memory — embedding, similarity, ChromaDB
10. Knowledge graph — triples, path finding, merge
11. Causal graph — acyclic enforcement, do-calculus
12. Policy memory — tensor store/load, versioning
13. Reasoning memory — template composition, variables
14. Context engine — 14 domains, TokenJuice, compression
15. Evolution engine — HP decay, death trigger, ghost

**P2 — Correctness (medium priority):**
16. Counterfactual — generate, store, prune
17. Skill memory — record, replay, generalization
18. Agent history — add, get, truncate, search
19. Memory roundtrip — cross-type consistency
20. District smoke — instantiation, run, HP (49× parametrized)
21. Voice pipeline — STT, TTS, wake word, listener
22. Phone node — heartbeat, battery, ADB
23. Dashboard API — endpoints, CORS, validation

**P3 — Nice to have (lowest priority):**
24. Integration tests — end-to-end, multi-module
25. Performance baselines — loop latency
26. Ollama safe wrapper — retry, backoff, timeout

---

**End of SPEC-014**
