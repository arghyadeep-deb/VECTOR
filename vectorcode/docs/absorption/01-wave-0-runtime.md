# Wave 0 — Runtime Foundation

**Goal:** Port Hermes's agent execution loop, tool router, state schema, and base utilities. After this wave, VectorCode is a functioning agent (calls model → executes tools → iterates).

**Dependencies:** None. This is the root of the DAG.

**Est effort:** 2–3 sessions (~15,000 lines ported).

---

## Read before coding

1. `vectorcode/docs/absorption/00-MASTER-PLAN.md`
2. `vectorcode/python/vectorcode/engine/agent_loop.py` (existing skeleton)
3. `vectorcode/python/vectorcode/tools/registry.py` (existing skeleton)
4. `vectorcode/python/vectorcode/session_db.py` (existing v1 schema)
5. `GitHub/NousResearch_hermes-agent/repo/run_agent.py` (the master source)

---

## File mappings

| # | Source | Lines | Target | Notes |
|---|--------|------:|--------|-------|
| 0.1 | `run_agent.py` | 12,229 | `engine/agent_loop.py` (rewrite) | Split into submodules if >2000 lines |
| 0.2 | `model_tools.py` | ~800 | `tools/registry.py` (rewrite) | Merge with existing registry skeleton |
| 0.3 | `hermes_state.py` | ~2,500 | `session_db.py` (extend) | Migrate to SCHEMA_VERSION 10 |
| 0.4 | `hermes_logging.py` | ~450 | `utils/logging.py` (extend) | File rotation, JSON, per-subsystem levels |
| 0.5 | `hermes_time.py` | ~100 | `utils/time_utils.py` (new) | `HermesTime`, `format_duration`, `parse_relative_time` |
| 0.6 | `hermes_constants.py` | ~350 | `vector_constants.py` (extend) | Copy missing constants |
| 0.7 | `utils.py` | ~300 | `utils/core.py` (new) | `atomic_json_write`, `env_var_enabled`, `safe_json_loads`, URL utils |
| 0.8 | `toolsets.py` + `toolset_distributions.py` | ~1,100 | `tools/toolset.py` (extend) | Toolset grouping + platform distributions |

---

## Step-by-step

### Step 0.1 — Split `run_agent.py` (CRITICAL, 12,229 lines)

Source file is a single monolith. Split into these submodules under `vectorcode/python/vectorcode/engine/`:

| Submodule | Responsibility | Source lines (approx) |
|-----------|----------------|----------------------:|
| `engine/budget.py` | `IterationBudget` (thread-safe, parent/subagent) | 1–200 |
| `engine/agent.py` | `AIAgent` class (main entry, init, config) | 200–1500 |
| `engine/conversation.py` | `run_conversation()` main loop | 1500–3500 |
| `engine/tool_exec.py` | `_execute_tool_calls_sequential/_concurrent()`, parallel detection | 3500–5500 |
| `engine/prompt.py` | `_build_system_prompt()`, soul injection | 5500–7000 |
| `engine/compression.py` | `_compress_context()`, focus topic, mid-session compaction | 7000–8500 |
| `engine/recovery.py` | `_recover_with_credential_pool()`, error fallback | 8500–9500 |
| `engine/safety.py` | `_SafeWriter`, `_sanitize_surrogates`, `_is_destructive_command` | 9500–10500 |
| `engine/subagent.py` | Subagent spawn via `delegate_tool` | 10500–11500 |
| `engine/max_iter.py` | `_handle_max_iterations()` graceful exhaustion | 11500–12229 |

`engine/agent_loop.py` becomes a thin facade that re-exports the public API.

**CHECKPOINT 0.1:** `python -c "from vectorcode.engine import AIAgent; a = AIAgent(); print(a)"` succeeds.

### Step 0.2 — Rewrite `tools/registry.py`

Port `model_tools.py` verbatim. Functions needed:
- `handle_function_call(name, args, context)` — central dispatcher
- `get_tool_definitions(toolset: str)` — returns JSON schemas per model family
- `check_toolset_requirements(toolset)` — env var / binary presence checks
- `register_tool(name, fn, schema, risk_level)` — runtime registration (used by plugins later)
- `_PARALLEL_SAFE_TOOLS`, `_NEVER_PARALLEL_TOOLS`, `_PATH_SCOPED_TOOLS` frozensets

**CHECKPOINT 0.2:** Integration test — `AIAgent` with dummy provider receives tool_call, `registry.handle_function_call()` executes a `read_file` stub, result flows back into the loop for iteration 2.

### Step 0.3 — Extend `session_db.py` to SCHEMA_VERSION 10

Port `hermes_state.py`. Add columns/tables:
- `parent_session_id` (subagent chain)
- `billing_provider`, `billing_mode`, `estimated_cost_usd`, `actual_cost_usd`, `cost_status`
- `api_call_count`
- `is_training_data` per turn (RULE 8)
- `focus_topic` (for compression)
- Migration script `migrations/v1_to_v10.py`

**CHECKPOINT 0.3:** `session_db.migrate_up()` transforms an existing v1 DB to v10 without data loss.

### Step 0.4 — `utils/logging.py`

Port `hermes_logging.py`:
- Rotating file handler at `~/.vectorcode/logs/vector.log` (10 MB × 5)
- JSON structured log option (`VECTOR_LOG_JSON=1`)
- Per-subsystem log levels via `VECTOR_LOG_LEVEL_<SUBSYSTEM>`
- `redact_sensitive_text()` hook (uses Wave 2's redact.py later, stub for now)

**CHECKPOINT 0.4:** `loguru` output matches Hermes format. Sensitive data is not leaked (stub passes through for now).

### Step 0.5 — `utils/time_utils.py`

Small file. Port `hermes_time.py` directly: `HermesTime` → `VectorTime`, rename class but keep method signatures.

### Step 0.6 — `vector_constants.py`

Merge `hermes_constants.py` into existing `vector_constants.py`. Rename `HERMES_*` → `VECTOR_*`. Add backwards-compat aliases `HERMES_HOME = VECTOR_HOME` for copy-pasted code paths.

### Step 0.7 — `utils/core.py`

Port `utils.py`:
- `atomic_json_write(path, data)` — temp + rename
- `base_url_host_matches(a, b)`, `base_url_hostname(url)`
- `env_var_enabled(name, default=False)`
- `normalize_proxy_url(url)`
- `safe_json_loads(s, default=None)`

### Step 0.8 — `tools/toolset.py`

Merge `toolsets.py` + `toolset_distributions.py` into existing `tools/toolset.py`. Toolsets:
- `coding` (default — file_ops, terminal, git, search)
- `research` (web, browser, extract, vision)
- `communication` (messenger, email, telegram, discord)
- `full` (all above)
- `minimal` (read-only)

Each has a platform distribution manifest (which tools need which binaries).

---

## Wiring (after all 8 steps)

Wire the new engine into `repl.py`:

```python
# repl.py — replace direct _ask_model() call
from vectorcode.engine import AIAgent

agent = AIAgent(
    provider=model_router,
    session_db=_db,
    permission_gateway=_perm,
    memory_manager=_mem,
    toolset="coding",
)

async def handle_user_input(text: str):
    result = await agent.run_conversation(text)
    return result
```

Apply `expand_context_references()` BEFORE `agent.run_conversation()` receives the text.

Apply `memory.prefetch_all(text)` before; `memory.sync_all()` after.

`_db.add_message()` called by `agent.run_conversation()` directly after each turn.

---

## Acceptance tests (must all pass before Wave 1)

Create `tests/test_wave0.py`:

1. `test_agent_single_tool_call` — agent receives prompt "read README.md and summarize", calls `read_file` tool, returns a non-empty summary
2. `test_agent_iteration_budget` — parent budget=5, subagent spawned with its own budget=3, parent still has 5 left
3. `test_tool_registry_dispatch` — registering a fake tool, calling via `handle_function_call`, result flows back
4. `test_session_migration_v1_to_v10` — test fixture v1 DB migrates cleanly
5. `test_compression_triggers` — conversation that exceeds 90% context triggers `_compress_context()` with focus_topic
6. `test_recovery_on_429` — stubbed 429 from provider, credential pool rotates, call retries
7. `test_safe_writer_daemon_mode` — writes to broken pipe don't crash (OSError/ValueError caught)
8. `test_surrogate_sanitization` — paste with surrogate codepoints doesn't break JSON encode

**Run:** `pytest tests/test_wave0.py -v --tb=short`

All 8 must pass. If any fail, fix before Wave 1.

---

## Rollback

If Wave 0 breaks existing functionality:

```bash
git checkout HEAD~1 -- vectorcode/python/vectorcode/engine/
git checkout HEAD~1 -- vectorcode/python/vectorcode/tools/registry.py
git checkout HEAD~1 -- vectorcode/python/vectorcode/session_db.py
git checkout HEAD~1 -- vectorcode/python/vectorcode/repl.py
```

Keep original `run_agent.py` copied to `vectorcode/docs/absorption/reference/run_agent.py.txt` for consultation (rename to .txt to avoid import).

---

## Handoff to Wave 1

After Wave 0 is green:

1. Tag commit: `git tag absorption-wave-0-complete`
2. Update `00-MASTER-PLAN.md` wave status table: `0 → [DONE]`
3. Open Wave 1 session with the Sonnet 4.6 prompt template + pointer to `02-wave-1-tools.md`
