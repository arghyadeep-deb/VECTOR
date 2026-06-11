# VECTOR core/ Line-by-Line Code Audit Report

**Date**: 2026-06-11  
**Scope**: `core/loop/`, `core/city/`, `core/memory/`, `core/` root `.py` files, `run_vector.py`  
**Total LOC in core/**: 238,315  
**LOC in audited scope**: 17,957 (loop: 5,449 | city: 2,959 | memory: 3,426 | core/ root: 5,670 | run_vector.py: 453)  

---

## File Inventory

| File | Lines | Status |
|------|-------|--------|
| `core/loop/autonomous_loop.py` | 1,963 | PARTIAL |
| `core/loop/permission_gateway.py` | 1,030 | PARTIAL |
| `core/loop/decision_engine.py` | 361 | PARTIAL |
| `core/loop/context_engine.py` | ~270 | PARTIAL |
| `core/loop/planner.py` | 83 | STUB |
| `core/loop/workflow_runner.py` | ~390 | PARTIAL |
| `core/loop/task_queue.py` | ~340 | PARTIAL |
| `core/loop/nudge_engine.py` | ~190 | PARTIAL |
| `core/loop/loop_guard.py` | ~110 | COMPLETE |
| `core/loop/loop_state.py` | ~100 | PARTIAL |
| `core/loop/cron_jobs.py` | ~520 | PARTIAL |
| `core/loop/presence.py` | ~60 | COMPLETE |
| `core/loop/__init__.py` | 7 | COMPLETE |
| `core/city/governor.py` | ~1,200 | PARTIAL |
| `core/city/agent_base.py` | ~260 | PARTIAL |
| `core/city/agent_registry.py` | ~160 | PARTIAL |
| `core/city/evolution_engine.py` | ~220 | PARTIAL |
| `core/city/point_system.py` | 62 | PARTIAL |
| `core/city/meta_cognition.py` | ~150 | PARTIAL |
| `core/city/task_router.py` | 74 | PARTIAL |
| `core/city/prompt_agent.py` | ~130 | PARTIAL |
| `core/city/declarative_manifest.py` | ~180 | PARTIAL |
| `core/city/__init__.py` | 10 | COMPLETE |
| `core/memory/episodic.py` | ~900 | PARTIAL |
| `core/memory/policy.py` | ~130 | PARTIAL |
| `core/memory/semantic.py` | ~60 | STUB |
| `core/memory/counterfactual.py` | ~100 | PARTIAL |
| `core/memory/causal_graph.py` | ~200 | PARTIAL |
| `core/memory/reasoning_memory.py` | ~80 | STUB |
| `core/memory/shared_facts.py` | ~130 | PARTIAL |
| `core/memory/knowledge_graph.py` | ~250 | PARTIAL |
| `core/memory/obsidian_sync.py` | ~280 | PARTIAL |
| `core/memory/unified.py` | ~180 | PARTIAL |
| `core/memory/db_registry.py` | ~180 | PARTIAL |
| `core/memory/multi_db_manager.py` | ~700 | PARTIAL |
| `core/memory/__init__.py` | 15 | COMPLETE |
| `core/mcp_server.py` | 3,920 | PARTIAL |
| `core/mcp_server_stdio.py` | 217 | PARTIAL |
| `core/config.py` | 990 | COMPLETE |
| `core/errors.py` | 139 | PARTIAL |
| `core/__init__.py` | 18 | COMPLETE |
| `core/runtime_paths.py` | 24 | COMPLETE |
| `core/breaker_registry.py` | 45 | PARTIAL |
| `core/api_manager.py` | ~400 | PARTIAL |
| `core/repo_hygiene.py` | 74 | COMPLETE |
| `core/frontend_bundle.py` | 46 | COMPLETE |
| `run_vector.py` | 453 | PARTIAL |

**Status Summary**: 8 COMPLETE | 34 PARTIAL | 3 STUB

---

## CRITICAL Issues

### C1. Path Traversal in `memory_export` and `memory_import`
- **File**: `core/mcp_server.py:1052-1066`
- **Severity**: CRITICAL
- **Detail**: `memory_export(path)` and `memory_import(path)` accept arbitrary filesystem paths from MCP callers with zero sanitization. An LLM or external client can write/read any file the process has access to (`../../etc/passwd`, `~/.ssh/authorized_keys`, etc.). The `open(out, "w")` at line 1061 and `open(path)` at line 1073 are direct user-supplied paths.

### C2. Unauthenticated Destructive `memory_clear`
- **File**: `core/mcp_server.py:1039-1049`
- **Severity**: CRITICAL
- **Detail**: `memory_clear()` executes `DELETE FROM episodic_memory` with no confirmation, no authorization beyond MCP layer, and no undo. Any MCP client can wipe the entire episodic memory store in one call.

### C3. Ephemeral HMAC Secret on Every Restart
- **File**: `core/mcp_server_stdio.py:37`
- **Severity**: CRITICAL
- **Detail**: `KERNEL_SECRET = os.environ.get("MCP_KERNEL_SECRET", str(uuid.uuid4()))` — if the env var is unset, a random secret is generated per-process. In multi-process deployments, each process gets a different secret, making HMAC verification impossible across processes. Also, restart invalidates all existing signed requests. No persistence or shared-secret mechanism.

### C4. `TimeoutError` Shadows Python Builtin
- **File**: `core/errors.py:56`
- **Severity**: CRITICAL
- **Detail**: `class TimeoutError(VectorError)` shadows the Python builtin `TimeoutError`. Any code that catches `TimeoutError` (e.g., `asyncio.wait_for`) will catch the wrong type if `core.errors` is imported with `from core.errors import *` or if the import shadows the builtin in scope. This is a silent logic bomb.

### C5. Thread-Unsafe Module-Level Mutable State
- **File**: `core/loop/context_engine.py:9` (`_SENSE_CACHE` dict)
- **Severity**: CRITICAL
- **Detail**: `_SENSE_CACHE` is a module-level plain dict accessed from async coroutines without any locking. In the autonomous loop where multiple coroutines may call `session_hydration_prompt()` concurrently, this is a data race. Dict mutation during iteration will raise `RuntimeError: dictionary changed size during iteration`.

### C6. Unbounded In-Memory Lists
- **Files**: `core/city/point_system.py` (`_logs` list), `core/loop/loop_guard.py` (`_recent_calls` list)
- **Severity**: CRITICAL
- **Detail**: Both are plain lists that grow without bounds. `_logs` records every HP change event; `_recent_calls` records every action. Over 24/7 operation, these become memory leaks that will eventually OOM the process.

---

## HIGH Issues

### H1. `sys.path.insert(0, ...)` Hack (3 instances)
- **Files**: `core/loop/context_engine.py:4`, `core/loop/decision_engine.py:8`, `core/city/agent_base.py:4`
- **Severity**: HIGH
- **Detail**: Forces the project root to index 0 of `sys.path`, overriding any installed packages with the same name. Creates import-order-dependent behavior, breaks virtualenv isolation, and can shadow stdlib or site-packages modules.

### H2. `check_same_thread=False` Without Serialization
- **Files**: `core/memory/episodic.py:126,146,303`, `core/memory/causal_graph.py:50`, `core/memory/counterfactual.py:41`, `core/memory/db_registry.py:158,174`
- **Severity**: HIGH
- **Detail**: All SQLite connections use `check_same_thread=False` but none implement connection-level serialization (e.g., thread-local connections, queue-based access, or `aiosqlite`). SQLite's default journal mode is not safe for concurrent writes from multiple threads. This will cause `OperationalError: database is locked` or silent data corruption under load.

### H3. Divergent DB Path for `shared_facts`
- **File**: `core/memory/shared_facts.py:20`
- **Severity**: HIGH
- **Detail**: Hardcodes `_DB_PATH = Path.home() / ".vector_ca" / "shared_facts.db"` instead of using `data_path()` from `core.runtime_paths` like the rest of the codebase. This creates two separate data directories, and `shared_facts` data will be lost if `VECTOR_DATA_DIR` is overridden (which `runtime_paths.py:16-18` explicitly supports).

### H4. Knowledge Graph Uses Separate DB at Hardcoded Path
- **File**: `core/memory/knowledge_graph.py`
- **Severity**: HIGH
- **Detail**: Uses `Path.home() / ".vector_ca" / "knowledge_graph.db"` — same problem as H3. Ignores `VECTOR_DATA_DIR`.

### H5. Bare `except Exception` — 544 Occurrences
- **Files**: All audited directories
- **Severity**: HIGH
- **Detail**: 544 instances of `except Exception` (many with swallowed errors, many bare without `as e`). The autonomous loop's "must never die" pattern is correctly defensive, but the vast majority of these are in non-loop code where specific exceptions should be caught. This masks `KeyboardInterrupt` (no, that's `BaseException`), `SystemExit`, and critically, makes debugging impossible because errors disappear silently.

### H6. `datetime.datetime.utcnow()` — Deprecated (100+ instances)
- **Files**: `core/city/agent_base.py:43,166,200,205`, `core/loop/decision_engine.py:38`, `core/memory/semantic.py:28,48`, and many more across core/
- **Severity**: HIGH
- **Detail**: `utcnow()` was deprecated in Python 3.12. Returns naive datetime (no tzinfo), which causes silent bugs when comparing with timezone-aware datetimes. Should be `datetime.now(timezone.utc)`.

### H7. `breaker_registry._lazy_load()` Not Thread-Safe
- **File**: `core/breaker_registry.py:11-12`
- **Severity**: HIGH
- **Detail**: `_Registry` and `_CircuitBreakerConfig` type variables are set as module globals in `_lazy_load()`. The `_instance` lock only protects singleton creation, not the type reassignment. Two threads calling `_lazy_load()` simultaneously can race on the global type variables.

### H8. `api_manager.py` Assumes `.get()` on Pydantic Model
- **File**: `core/api_manager.py:64`
- **Severity**: HIGH
- **Detail**: `CONFIG.get("api_base_url", ...)` — if `CONFIG` is a pydantic model (which `core/config.py` defines), it doesn't have a `.get()` method. This will `AttributeError` at runtime. Pydantic models use `model.__getitem__` or attribute access, not dict-style `.get()`.

### H9. `declarative_manifest.py` Imports Potentially Unresolvable Path
- **File**: `core/city/declarative_manifest.py:24`
- **Severity**: HIGH
- **Detail**: `from vectorcode.src.agents.registry import AgentRegistry` — if `vectorcode` is not installed or not on `sys.path`, this will `ImportError` at module import time, preventing the entire `declarative_manifest` module from loading.

### H10. `mcp_server.py` — 3,920-Line Monolith
- **File**: `core/mcp_server.py`
- **Severity**: HIGH
- **Detail**: Single file with 80+ `@mcp.tool` definitions, no logical grouping, no sub-modules. Violates SRP, makes the file unmaintainable, and causes long import times. Each tool's error handler is the identical `except Exception as e: return _safe_json({"error": str(e)})` pattern copy-pasted 80+ times.

---

## MEDIUM Issues

### M1. `core/__init__.py:16-17` — Unsafe `sys.modules` Access
- **Severity**: MEDIUM
- **Detail**: Checks `"mcp" in sys.modules` then accesses `sys.modules["mcp"]`. Between the check and access, another thread could remove the key (unlikely but possible). Should use `sys.modules.get("mcp")`.

### M2. CausalGraph Dual-Mode (JSON/SQLite) Complexity
- **File**: `core/memory/causal_graph.py`
- **Severity**: MEDIUM
- **Detail**: Supports both JSON file and SQLite backends, selected by `use_sql` flag. The JSON mode is not thread-safe (no file locking), and the mode switch happens at `__init__` time with no validation. If the JSON file is corrupted, the entire causal graph fails.

### M3. `permission_gateway.py:21-33` — Bare `except Exception` After `except ImportError`
- **Severity**: MEDIUM
- **Detail**: The import fallback chain catches `ImportError` then immediately has a second `except Exception` that swallows any other import-time error (e.g., `SyntaxError` in the imported module).

### M4. `loop_state.py` — 6 Bare `except Exception` Blocks
- **File**: `core/loop/loop_state.py`
- **Severity**: MEDIUM
- **Detail**: All six `except Exception` blocks in this 100-line file silently swallow errors from checkpoint save/load operations. A corrupted checkpoint will be silently ignored and the loop restarts from scratch with no indication.

### M5. `nudge_engine.py` — Nudge Logging Without Throttle
- **File**: `core/loop/nudge_engine.py`
- **Severity**: MEDIUM
- **Detail**: Nudge events are logged but not throttled. A flood of nudge events can overwhelm the episodic memory store.

### M6. `governor.py` — LLM Council Quorum Not Enforced
- **File**: `core/city/governor.py`
- **Severity**: MEDIUM
- **Detail**: Council sessions can proceed with fewer than the required HP>700 members. If only 1 agent qualifies, the "council" is a single voice, defeating the purpose of deliberation.

### M7. `evolution_engine.py` — Ghost Memory Injection Without Validation
- **File**: `core/city/evolution_engine.py`
- **Severity**: MEDIUM
- **Detail**: Ghost memory from dead agents is injected into new agents without schema validation. A corrupted or malicious ghost memory entry could inject arbitrary text into the new agent's context.

### M8. `multi_db_manager.py` — 4-Backend Sync With No Conflict Resolution
- **File**: `core/memory/multi_db_manager.py`
- **Severity**: MEDIUM
- **Detail**: Supports SQLite, PostgreSQL, MongoDB, and Redis backends but has no conflict resolution for concurrent writes to different backends. Last-write-wins silently.

### M9. `obsidian_sync.py` — File-Level Locking May Deadlock
- **File**: `core/memory/obsidian_sync.py`
- **Severity**: MEDIUM
- **Detail**: Uses file-level locking for vault sync. If the process crashes while holding a lock, the lock file persists and blocks all future syncs until manually removed.

### M10. `episodic.py` — SQLCipher Fallback to Plain SQLite
- **File**: `core/memory/episodic.py:126-146`
- **Severity**: MEDIUM
- **Detail**: If `pysqlcipher3` import fails, falls back to plain `sqlite3` with no warning to the user. Sensitive episodic memories (API keys, personal data) are then stored unencrypted.

### M11. `mcp_server_stdio.py:51` — `hmac.new()` vs `hmac.new()`
- **File**: `core/mcp_server_stdio.py:51`
- **Severity**: MEDIUM
- **Detail**: Uses `hmac.new()` which is correct (it's `hmac.new(key, msg, digestmod)`). However, the signing does not include the `kernelId` in the signed data, so a replay from a different process with the same secret would verify.

### M12. `run_vector.py` — Global Excepthook Not Restored on Shutdown
- **File**: `run_vector.py`
- **Severity**: MEDIUM
- **Detail**: Installs a custom `sys.excepthook` at startup but never restores the original on graceful shutdown. If VECTOR is imported as a library, the host process's excepthook is permanently overridden.

---

## LOW Issues

### L1. `core/config.py` — Uses `Optional` from `typing` (Not Modern Syntax)
- **Severity**: LOW
- **Detail**: Uses `Optional[X]` instead of `X | None`. Works but is outdated style since Python 3.10+.

### L2. `core/loop/presence.py` — Trigger Modes Not Validated
- **Severity**: LOW
- **Detail**: Accepts any string for trigger mode without validation against known modes.

### L3. `core/loop/loop_guard.py` — `_recent_calls` Uses `list.pop(0)` (O(n))
- **Severity**: LOW
- **Detail**: `pop(0)` on a list is O(n). Should use `collections.deque` with `maxlen`.

### L4. `core/city/task_router.py` — Keyword Matching Is Case-Sensitive
- **Severity**: LOW
- **Detail**: Keyword-to-district mapping is case-sensitive. "Finance" and "finance" route differently.

### L5. `core/memory/policy.py` — Online Averaging Has No Decay
- **Severity**: LOW
- **Detail**: Policy scores use simple online averaging `(old * n + new) / (n + 1)` with no decay. Old outcomes dominate forever, making adaptation slow.

### L6. `core/memory/reasoning_memory.py` — STUB
- **Severity**: LOW
- **Detail**: Barely implemented. Only stores, never retrieves for decision-making.

### L7. `core/memory/semantic.py` — STUB
- **Severity**: LOW
- **Detail**: Has `store()` and `search()` but search returns empty list always (placeholder).

### L8. `core/loop/planner.py` — STUB (83 lines)
- **Severity**: LOW
- **Detail**: Goal-driven planner is mostly scaffold. No actual planning logic beyond template methods.

### L9. `core/mcp_server.py` — `_safe_json()` Pattern Repeated 80+ Times
- **Severity**: LOW
- **Detail**: Every tool has identical `try: ... except Exception as e: return _safe_json({"error": str(e)})`. Should be a decorator.

### L10. `core/frontend_bundle.py` — Dev Scripts Check in Production
- **Severity**: LOW
- **Detail**: Only checks for dev-only scripts in production but doesn't enforce their removal.

### L11. `core/runtime_paths.py` — No `VECTOR_DATA_DIR` Creation
- **Severity**: LOW
- **Detail**: Resolves the data directory but doesn't create it if it doesn't exist. First write will fail.

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| **Total LOC in core/** | 238,315 |
| **LOC in audited scope** | 17,957 |
| **CRITICAL issues** | 6 |
| **HIGH issues** | 10 |
| **MEDIUM issues** | 12 |
| **LOW issues** | 11 |
| **`except Exception` occurrences** | 544 |
| **`utcnow()` occurrences** | 100+ |
| **`sys.path.insert` hacks** | 3 |
| **STUB files** | 3 (planner, semantic, reasoning_memory) |
| **PARTIAL files** | 34 |
| **COMPLETE files** | 8 |

## Top 5 Priorities

1. **C1 — Path traversal in mcp_server.py**: Sanitize `memory_export`/`memory_import` paths, restrict to `ROOT` directory, reject `..` components
2. **C4 — `TimeoutError` shadowing**: Rename to `VectorTimeoutError` or `OperationTimeoutError`
3. **C5 + C6 — Thread safety + unbounded memory**: Add `asyncio.Lock` to `_SENSE_CACHE`, cap `_logs` and `_recent_calls` with `deque(maxlen=N)`
4. **H2 — SQLite thread safety**: Migrate to `aiosqlite` or use `db_registry` with per-thread connections
5. **H3 + H4 — Divergent DB paths**: Migrate `shared_facts` and `knowledge_graph` to use `data_path()` from `runtime_paths`
