# VECTOR Codebase — Deduplication & Hardening Plan

**Scope:** Fix Everything | Implement All Stubs | Refactor Absorbed Subsystems  
**Strategy:** Sequential phases, each self-contained and testable  
**Estimated effort:** 12–16 weeks (single developer, part-time on VECTOR)  
**Status:** Phase 0 — COMPLETE | Phase 1 — COMPLETE | Phase 2 — COMPLETE | Phase 3 — COMPLETE (adapter pattern) | Phase 4 — Pending | Phase 5 — Pending

---

## Phase 0 — Safety & Diagnostics *(1–2 days, HIGHEST priority)*

**Goal:** Stop silent failures before touching anything else.

| Task | Files | Risk |
|------|-------|------|
| Replace all bare `except Exception: pass` (50+ sites) with logged, typed exceptions using `core/errors.py` hierarchy | governor.py, autonomous_loop.py, event_bus, vectorcode_bridge, all district swarms | **None** — logging only, no behavior change |
| Set `VECTOR_DEBUG = False` in `core/config.py:345` | config.py | **None** — prod-safe default |
| Add `sys.excepthook` + `asyncio` exception handler in `run_vector.py` | run_vector.py | **None** — global safety net |
| Consolidate 6 `ConfigurationError` classes into `core/errors.py`; re-import in all 6 files | errors.py, mining/docker.py, vectorcode/src/mining/_docker.py, coding_assistant/acp/exceptions.py, vector_finagent/Analytics/quant/exceptions.py, vectorcode/src/learning/distillation/storage/paths.py | **Low** — pure import change |

**Verification:** `python run_vector.py smoke` passes; `python -m pytest tests/` passes; no new log warnings.

---

## Phase 1 — Consolidate Duplicate Infrastructure *(1–2 weeks)*

**Goal:** Single canonical version of every framework class.

### Task 1.1 — EventBus unification

| Step | Detail |
|------|--------|
| Rename `core/event_bus/redis_bus.py` → `core/event_bus/bus.py` (it's in-memory, not Redis) | Single rename + update imports |
| Merge `vectorcode/src/vc_core/events.py` EventBus → delegate to `core/event_bus/bus.py` | Adaptor in vectorcode, not copy |
| Remove EventBus from `vector_backtest/src/session/events.py` (unused test artifact) | Delete dead code |
| Remove test EventBus in `legacy_ported/gateway/test_matrix.py` | Clean up legacy tests |

### Task 1.2 — MemoryProvider & MemoryManager unification

| Step | Detail |
|------|--------|
| Keep `vectorcode/src/memory/provider.py` as canonical ABC | This is the more complete version |
| Make `vectorcode/src/agent/memory_provider.py` delegate to it | Same ABC, no code copy |
| Same for `manager.py` vs `memory_manager.py` | Pick one, re-export from the other |

### Task 1.3 — ToolRegistry, WorkflowEngine, SkillManager, PluginManager

| Step | Detail |
|------|--------|
| For each duplicated class: pick the canonical file, make others thin re-exports | Pure import redirection |
| Remove `vectorcode/src/agents/_stubs.py` and `vectorcode/src/vc_agents/_stubs.py` `BaseAgent` if truly dead | Delete dead stubs |

### Task 1.4 — EventType enum consolidation

| Step | Detail |
|------|--------|
| `core/event_bus/types.py` is canonical | Already the most complete (33 event types) |
| `vectorcode/src/vc_core/events.py` → import from `core/event_bus/types.py` | Avoid enum value drift |

**Verification:** All imports work; `core/event_bus/types.py` EventType has 33+ members; no duplicate class definitions remain at runtime.

---

## Phase 2 — Deduplicate core/ vs vectorcode/ Forks *(2–3 weeks)*

**Goal:** One canonical version of each module shared between core and vectorcode.

### Task 2.1 — Telemetry (18 file pairs)

| Step | Detail |
|------|--------|
| Choose `core/telemetry/` as canonical | It's the VECTOR-native version, slightly larger (more features) |
| Make `vectorcode/src/telemetry/` thin re-imports from `core/telemetry/` | Every function re-exported, no code copy |
| Remove `instrumented_engine.py` from vectorcode side (418 bytes vs 19KB — clearly stale) | Delete |

### Task 2.2 — Mining (11 file pairs)

| Step | Detail |
|------|--------|
| Choose `core/mining/` as canonical | Already documented as "ported from VectorCode and trimmed" |
| Make `vectorcode/src/mining/` re-import from `core/mining/` where functions overlap | GPU detection, Docker orchestration |
| Keep unique mining loop files only in vectorcode | `_miner_loop_main.py`, `_mps_miner_loop_main.py` |

### Task 2.3 — Sandbox (3 file pairs)

| Step | Detail |
|------|--------|
| Choose `core/sandbox/` as canonical | Larger, more complete |
| `vectorcode/src/sandbox/` → re-import | mount_security, runner, wasm_runner |

**Verification:** `python -m pytest tests/` passes; all imports from both `core.telemetry` and `vectorcode.src.telemetry` work and return identical objects.

---

## Phase 3 — Refactor Absorbed Subsystems into Core *(6–8 weeks)*

**Goal:** research_engine (454 files), coding_assistant (177 files), engine (27 files) use VECTOR's core infrastructure.

### Task 3.1 — research_engine → core integration

| Sub-step | Files | Change |
|----------|-------|--------|
| 3.1a Config | `research_engine/settings/` (entire package) | Replace with `from core.config import CONFIG`; remove own settings manager |
| 3.1b Database | `research_engine/database/` (24+ models, 9 Alembic migrations, encrypted_db.py, backup.py) | Migrate to `core/memory/` SQLite patterns; remove own DB engine |
| 3.1c Utilities | `research_engine/utilities/` (db_utils, llm_utils, log_utils) | Replace with `core/` equivalents; remove duplicates |
| 3.1d Web search | `research_engine/web_search_engines/` (25+ engines) | Keep as-is, it's unique value — just rewire config to `core.config` |
| 3.1e Models | `research_engine/database/models/` | Keep models but inherit from `core/memory/` base instead of own SQLAlchemy base |

**Verdict on whether to keep research_engine:** YES — it provides real value (25+ web search engines, encrypted DB, research pipeline). It just needs to share core's config and database instead of owning its own.

### Task 3.2 — coding_assistant → core integration

| Sub-step | Files | Change |
|----------|-------|--------|
| 3.2a LLM backends | `core/coding_assistant/core/llm/backend/` (anthropic.py, openai_responses.py, mistral.py, vertex.py, generic.py) | Replace with `core/inference/vectorcode_llm.py` router; remove own backends |
| 3.2b Config | `core/coding_assistant/core/config/` (entire package) | Replace with `from core.config import CONFIG` |
| 3.2c Tools | `core/coding_assistant/core/tools/` (13+ builtins) | Keep as coding-specific tools; no core overlap |
| 3.2d Skills | `core/coding_assistant/core/skills/` | `SkillManager` already duplicated — consolidate into one |

**Important note:** After this refactor, `core/coding_assistant/` remains valuable for its MCP tool integration and TTS subsystem. It's just no longer a standalone island.

### Task 3.3 — engine (OpenHuman remnant) → core merge

| Sub-step | Change |
|----------|--------|
| `core/engine/agents/` (16 roles) | Move role prompts to `districts/` as `.md` files; remove AgentBase duplicate |
| `core/engine/channels/runtime.py` | Merge into `core/communications/hub.py` |
| `core/engine/providers/model_router.py` | Replace with `core/inference/vectorcode_llm.py` |
| `core/engine/memory_tree/` | Keep as-is — unique wiki/memory-tree builder, no core duplicate |
| `core/engine/research/parallel_researcher.py` | Keep as-is — unique parallel research capability |

**Verification:** All research_engine, coding_assistant, and engine functionality still works. Smoke test passes. No duplicate config or database instances.

---

## Phase 4 — Implement Stubs *(4–6 weeks)*

**Goal:** All 10 district agents and 300 MCP tools fully functional.

### Task 4.1 — 10 stub district agents

| District | Suggested Implementation |
|----------|------------------------|
| `academic` | Course material search, paper summarization, citation management |
| `core` | System-level diagnostics, health checks, debug tools — NOT a stub of VECTOR core |
| `game_development` | Unity/Unreal project scaffolding, asset generation prompts |
| `paid_media` | Ad campaign management, budget tracking, performance reporting |
| `project_management` | Jira/Trello integration, task breakdown, status tracking |
| `sales` | CRM integration, lead scoring, pipeline management |
| `spatial_computing` | AR/VR environment setup, 3D model generation |
| `specialized` | Catch-all for domain-specific tasks; route to GenericSwarm |
| `strategy` | Competitive analysis, OKR tracking, decision frameworks |
| `support` | Ticket triage, FAQ generation, escalation routing |

**Implementation pattern for each:** `SwarmAgent` subclass with 3–5 `.md` prompt agents + 1–2 `AgentBase` subclass with real logic. Each gets a `__main__` smoke test.

### Task 4.2 — 300 stub MCP tools

| Tool group | Files affected | Approach |
|------------|---------------|----------|
| `agent_*` (50 tools) | `core/mcp_server.py` | Wire to AgentRegistry: spawn, kill, list, inspect, HP query |
| `swarm_*` (30 tools) | `core/mcp_server.py` | Wire to SwarmOrchestrator: create, dispatch, query swarms |
| `memory_*` (30 tools) | `core/mcp_server.py` | Wire to episodic/semantic/policy/reasoning memory |
| `hook_*` (20 tools) | `core/mcp_server.py` | Wire to event bus subscriptions |
| `task_*` (30 tools) | `core/mcp_server.py` | Wire to Governor dispatch queue |
| `security_*` (20 tools) | `core/mcp_server.py` | Wire to permission gateway, SSRF guard, taint tracker |
| `neural_*` (20 tools) | `core/mcp_server.py` | Wire to policy memory / RL system |
| `file_*`, `git_*`, `test_*`, `doc_*`, `browser_*`, `graph_*`, `perf_*`, `worker_*`, `config_*` (remaining ~100) | `core/mcp_server.py` | Wire to existing `core/` modules for each domain |

**Reality check:** Most of these tools already have backend implementations in `core/` — they just aren't exposed via MCP. The wiring is mechanical: define tool schema → call existing function → format response.

**Verification:** Every MCP tool returns a real result, not "not yet wired". All 10 district agents return meaningful responses.

---

## Phase 5 — Polish & Security *(2–3 weeks)*

**Goal:** Address remaining quality issues.

| Task | Detail | Files |
|------|--------|-------|
| Remove 79 empty `__init__.py` | Delete files (Python 3.3+ doesn't need them) | All across tree |
| Consolidate `utils.py` (13 files) | Extract shared utility to `core/utils.py`; keep domain-specific ones | vectorcode/src/utils.py, coding_assistant/*/utils.py, research_engine/*/utils.py, etc. |
| Fix subprocess `shell=True` risks | Replace with `subprocess.run(cmd_list, shell=False)` | `core/api/routers/sensing.py:72`, `vector_backtest/src/tools/background_tools.py:46`, `core/resilience/injectors/network_chaos.py:37-79` |
| Add websocket auth | Token-based auth check on connect | `core/api/routers/websocket.py` |
| Add SQLite connection pooling | Wrap `sqlite3.connect` with `sqlite3.ConnectionPool` or `psycopg2.pool` equivalent | `core/memory/episodic.py` |
| Remove mirrored markdown | Pick canonical location (`.claude/` for skills, `districts/` for ads references), remove copies | `brain/.claude/skills/`, `vectorcode/skills/`, `districts/marketing/ads/references/` |
| Consolidate routes (3 routing tables → 1) | Merge Governor DISTRICT_TASK_MAP, TaskRouter, SwarmOrchestrator into `core/routing/` | governor.py, TaskRouter, SwarmOrchestrator |
| Add root LICENSE, CONTRIBUTING.md | Based on absorbed Apache 2.0 code origin | Root |

**Verification:** Full test suite passes. No `shell=True` with user-controlled strings. Websocket requires auth token. 79 fewer empty files.

---

## Execution Order & Dependencies

```
Phase 0 ──────────────────────────────────────────────────────┐
  (Safety, done first; no deps)                                │
                                                               ▼
Phase 1 ─── Phase 2 ─── Phase 3 ─── Phase 4 ─── Phase 5
(no deps)   (no deps)   (needs P1,P2)  (no deps)   (needs all)
```

- **Phase 0** can start immediately — pure logging/error handling changes
- **Phase 1 & 2** are independent of each other; could be parallel but sequential chosen
- **Phase 3** should wait until Phase 1 & 2 are done (so core infrastructure is stable)
- **Phase 4** is independent and could run in parallel if desired
- **Phase 5** must be last (many changes depend on earlier consolidation)

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Phase 3 breaks research_engine functionality | Medium | Run research_engine tests (check if they exist) before/after each sub-step |
| Phase 3.2 LLM backend swap changes code assistant behavior | Medium | Keep old backends as fallback; switch default gradually |
| Phase 2 changes break vectorcode/src imports | Medium | Phase 1 ensures all core infrastructure stable first |
| 300 MCP tools is a grind | High | Automate with code generation: template → inject → register |
| This is too much work in one session | Certain | Each phase is a separate commit |

---

## Duplication Audit Summary

### Byte-for-Byte Identical Files

| Group | Count | Paths |
|-------|-------|-------|
| Empty `__init__.py` (0 bytes) | **79 files** | Scattered across `vectorcode/tests/`, `core/`, `districts/` |
| `__init__.py` with just `#` (36 bytes) | **33 files** | Entirely within `districts/investment/vector_finagent/` |
| District `agent.py` stubs (999 bytes) | **10 files** | `academic`, `core`, `game_development`, `paid_media`, `project_management`, `sales`, `spatial_computing`, `specialized`, `strategy`, `support` |
| `__init__.py` (34 bytes) | **8 files** | `core/trading/` subdirectories |
| `ffn_analysis.py` (14,326 bytes) | **2 files** | Same file in two locations within `vector_finagent` |
| `digest_store.py` | **2 files** | `vectorcode/src/agents/` and `vectorcode/src/vc_agents/` |

### Near-Identical Code Forks

| Module Pair | File Count | Size Diff |
|-------------|-----------|-----------|
| `core/telemetry/` vs `vectorcode/src/telemetry/` | **18 pairs** | 96-151 bytes each |
| `core/mining/` vs `vectorcode/src/mining/` | **11 pairs** | 15-8,119 bytes |
| `core/sandbox/` vs `vectorcode/src/sandbox/` | **3 pairs** | 279-330 bytes |
| `cli/` vs `vector_cli/` (inside vectorcode) | **4 near-identical pairs** | `mine_cmd`, `registry_cmd`, `scheduler_cmd`, `skill_cmd` |
| `channels/` vs `comms/` (inside vectorcode) | **3 pairs** | Twitter, Twilio SMS, Teams |

### Duplicate Classes

| Class | Count | Files |
|-------|-------|-------|
| `class EventBus` | **4** | `core/event_bus/base.py`, `vectorcode/src/vc_core/events.py`, `vector_backtest/src/session/events.py`, test stub |
| `class MemoryProvider` | **2** | `vectorcode/src/memory/provider.py`, `vectorcode/src/agent/memory_provider.py` |
| `class MemoryManager` | **2** | `vectorcode/src/memory/manager.py`, `vectorcode/src/agent/memory_manager.py` |
| `class BaseAgent` | **3** | `vc_agents/_stubs.py`, `agents/_stubs.py`, `vector_finagent/agno_trading/core/base_agent.py` |
| `class ToolRegistry` | **3** | `vc_core/registry.py`, `tools/registry.py`, `vector_backtest/src/agent/tools.py` |
| `class WorkflowEngine` | **4** | `core/loop/workflow_runner.py`, `vectorcode/src/workflow/engine.py`, `vectorcode/src/agents/workflow_engine.py`, `vector_finagent/agno_trading/core/workflow_engine.py` |
| `class SkillManager` | **3** | `vc_skills/manager.py`, `skills/manager.py`, `core/coding_assistant/core/skills/manager.py` |
| `class PluginManager` | **2** | `vector_cli/plugins.py`, `plugins/plugin.py` |
| `class ConfigurationError` | **6** | Different parent classes across 6 files |
| `class EventType(str, Enum)` | **4** | `core/event_bus/types.py`, `vc_core/events.py`, `evals/core/event_recorder.py`, test stub |

### Absorbed Project Remnants

| Module | Files | Size | Problem |
|--------|-------|------|---------|
| `core/research_engine/` | **454 files** | **4.5 MB** | Complete standalone project: owns its own database, settings, utilities. Zero imports from `core.config`. |
| `core/coding_assistant/` | **177 files** | **921 KB** | Full standalone AI coding assistant: own LLM backends, tools, config, version 2.9.6. |
| `core/engine/` (OpenHuman) | **27 files** | **161 KB** | Rust-to-Python port. Agent roles overlap with `core/city/agent_base.py`. |

### Skill Mirroring

**~92 duplicate skill directories** — same skills in both `.claude/skills/` and `vectorcode/skills/`.

---

*Plan created: 2026-05-21*
