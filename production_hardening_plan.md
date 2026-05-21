# Production Hardening — Complete Execution Plan

**Target:** Address ALL 19 remaining issues from the backend audit
**Branch:** `production-hardening-complete`
**Estimate:** ~15 hours (12 phases, ordered by impact/hour)

---

## Phase 0 — Cleanup & Baseline (1h)

### Task 0A — Delete stale worktrees (5 min)

```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
git worktree remove --force .claude/worktrees/agent-ab29796a59d589a87
git worktree remove --force .claude/worktrees/agent-ab6214c2e6d2a3908
git worktree remove --force .claude/worktrees/agent-acafa09e1315e0013
git worktree prune
```

Add `.claude/worktrees/` to `.gitignore`.

**Acceptance:** `Get-ChildItem .claude/worktrees -ErrorAction SilentlyContinue` returns nothing. 5-10 GB freed.

---

### Task 0B — Delete guidance/ package stub (2 min)

The Phase 0C stub deletion from production_fix.md is only half-done (`claims/` deleted in Gap 8 but `guidance/` still exists):

```bash
Remove-Item vectorcode/src/guidance/__init__.py
```

**Verify:**
```bash
python -c "from vectorcode.src import guidance; print(guidance.__file__)"
# Must resolve to vectorcode\src\guidance.py (the .py file), not the package dir
python run_vector.py smoke
# Must still pass
```

**Acceptance:** `from vectorcode.src import guidance` loads the .py monolith, not the stub package dir. Smoke test passes.

---

### Task 0C — Snapshot baseline (5 min)

```bash
git tag pre-production-hardening
python -m pytest -q tests/ --tb=no -x --ignore=tests/research_engine > baseline_test_results.txt
python run_vector.py smoke >> baseline_test_results.txt
```

**Acceptance:** Git tag `pre-production-hardening` exists. Baseline saved at `baseline_test_results.txt`.

---

### Task 0D — Commit Phase 0

```bash
git add .claude/worktrees vectorcode/src/guidance/__init__.py .gitignore
git commit -m "[phase-0] cleanup: remove stale worktrees, guidance stub, add baseline tag"
```

---

## Phase 1 — Fix `asyncio.new_event_loop()` per API call (3h)

**Why:** 45+ callsites in API routers create + destroy an asyncio event loop PER REQUEST. This is the #1 performance and robustness issue — negates FastAPI's async benefits, leaks loop resources.

### Task 1A — Fix the generator (30 min)

**File:** `scripts/create_routers.py:309`

The template generates:
```python
@router.get("/path")
def handler():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(...)
    loop.close()
    return result
```

Change to:
```python
@router.get("/path")
async def handler():
    try:
        result = await ...
        return result
    except Exception as e:
        logger.error("[VECTOR][api] handler failed: {}", e)
        return {"status": "error", "detail": str(e)}
```

**Acceptance:** `python scripts/create_routers.py --dry-run` shows `async def` in output, no `new_event_loop`.

---

### Task 1B — Bulk-convert existing routers (2h)

**Target files** (from `rg -l "asyncio.new_event_loop" core/api/routers/`):
- `research.py`, `brain.py`, `city.py`, `projects.py`, `finance.py`, `health.py`, `qa.py`, `analytics.py`, `intelligence.py`, `tasks.py`, etc. (30+ files)

**Pattern to replace** (same in every file):

```python
# OLD — 4 lines to remove
loop = asyncio.new_event_loop()
result = loop.run_until_complete(some_async_fn())
loop.close()
return SomeResponse(result)
```

```python
# NEW — just await
result = await some_async_fn()
return SomeResponse(result)
```

**Procedure per file:**
1. Read the file
2. For each occurrence: remove 4 lines (`new_event_loop` / `run_until_complete` / `close` / reassign), change `def` to `async def`, add `await`
3. Wrap handler body in `try/except Exception` with `{"status": "error", "detail": str(e)}` return
4. Run `python -c "from core.api.routers import <file>"` to verify it imports

---

### Task 1C — Fix MCP server tools (30 min)

**File:** `core/mcp_server.py`

15 tool functions still use the pattern:
```python
def browser_xxx(params):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(...)
    loop.close()
    return result
```

Replace with `async def` + `await`. This is the same pattern as Gap 7 but for the remaining tools that weren't httpx-based.

**Acceptance after Phase 1:**
```bash
rg "asyncio.new_event_loop" core/ --include="*.py"
# Returns 0
python run_vector.py smoke
# Passes
```

---

### Task 1D — Commit Phase 1

```bash
git add scripts/create_routers.py core/api/routers/ core/mcp_server.py
git commit -m "[phase-1] fix: eliminate per-call asyncio.new_event_loop in all API routers + MCP tools"
```

---

## Phase 2 — Silent exception cleanup (3h)

**Why:** 858 `except Exception: pass` / `except Exception: logger.debug(...)` patterns. Failures are invisible at default log levels. The autonomous loop's intentional "never stop" pattern leaked into API handlers, tool functions, and data pipelines where silent failure is wrong.

### Task 2A — Automated detection script (30 min)

**File:** `scripts/find_silent_excepts.py`

Walk `core/`, parse AST, find try/except blocks where handler body is `pass`, `return None`, `return {}`, or just `logger.debug("...", exc_info=True)`.

Output CSV: `file:line:type:handler_lines`

Categories:
- `CRITICAL` — API handlers, governor, event bus (must log error + return structured error)
- `HOT_PATH` — autonomous loop intentional catches (keep, but add subsystem tag)
- `OPTIONAL` — lazy import guards (keep debug level, add `[VECTOR][imports]` tag)
- `BULK` — research_engine (bulk upgrade to `logger.warning`)

---

**Procedure:**

1. **For API routers** (CRITICAL): change `pass` to:
   ```python
   except Exception as e:
       logger.error("[VECTOR][api] {} failed: {}", endpoint_name, e)
       return {"status": "error", "detail": str(e)}
   ```

2. **For autonomous loop** (HOT_PATH): change non-descript `logger.debug("[VECTOR] suppressed exception")` to:
   ```python
   except Exception as e:
       logger.debug("[VECTOR][loop][{}] {}: {}", subsystem, operation, e)
       # If this is a critical subsystem failure, also log at warning level
   ```

3. **For governor/districts** (HOT_PATH): add subsystem tag, log at warning for actual failures:
   ```python
   except Exception as e:
       logger.warning("[VECTOR][{}] {} failed: {}", district, operation, e)
   ```

4. **For lazy imports** (OPTIONAL): tag consistently:
   ```python
   except ImportError:
       logger.debug("[VECTOR][imports] {} not available", module_name)
   ```

5. **For research_engine** (BULK, ~300 hits): automated replacement:
   - `except: pass` → `except Exception: logger.warning("[VECTOR][research_engine] operation failed: {}", e)`
   - `except Exception: pass` → same

### Task 2B — CI gate (5 min)

Add to scripts or document as CI check:
```bash
SILENT=$(rg -c "except\s*:\s*$|except\s+Exception:\s*$" core/ --include="*.py" | Measure-Object -Sum | Select -Expand Sum)
if ($SILENT -gt 100) { exit 1 }
```

**Acceptance:**
```bash
rg -c "except Exception:\s*$|except:\s*$" core/ --include="*.py" | ForEach-Object { $_ -split ':' | Select-Object -Last 1 } | Measure-Object -Sum
# Output: Sum < 100
python run_vector.py smoke
# Passes
```

---

### Task 2C — Commit Phase 2

```bash
git add scripts/find_silent_excepts.py core/ scripts/
git commit -m "[phase-2] fix: reduce silent except blocks 858-><100, add CI gate"
```

---

## Phase 3 — Security critical fixes (2h)

**Why:** Three high-severity vulnerabilities: RCE via pickle.loads, code injection via 34 eval/exec sites, and default OFP shared secret with no transport encryption.

### Task 3A — Fix pickle.loads RCE (15 min)

**File:** `core/scraper/spiders/checkpoint.py:80`

```python
# OLD — RCE vulnerability
data = pickle.loads(content)
```

```python
# NEW — safe deserialization
try:
    import json
    data = json.loads(content.decode())
except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
    logger.error("[VECTOR][scraper] checkpoint content is not valid JSON: {}", e)
    return None
```

---

### Task 3B — Sandbox eval/exec calls (1h)

**Primary targets (HIGH risk):**

1. `core/scraper/spiders/checkpoint.py` — already fixed in 3A

2. `districts/investment/vector_finagent/algo_trading/python_backtest_engine.py:72`:
   ```python
   # OLD — exec on strategy files
   exec(f.read())
   ```
   ```python
   # NEW — sandboxed with restricted globals
   restricted = {"__builtins__": {"print": print, "range": range, "len": len, "list": list, "dict": dict, "float": float, "int": int, "str": str, "min": min, "max": max, "sum": sum, "abs": abs, "enumerate": enumerate, "zip": zip, "map": map, "filter": filter, "any": any, "all": all, "sorted": sorted, "reversed": reversed, "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr}}
   exec(compile(f.read(), filename, 'exec'), restricted)
   ```

3. `districts/investment/vector_finagent/agents/finagent_core/execution_planner.py:419`:
   Already has `{"__builtins__": {}}` — verify. If not, add.

4. `vectorcode/src/workflow/engine.py:284`:
   Already has `{"__builtins__": {}}` — verify. If not, add.

5. `vectorcode/src/vc_tools/repl.py:303,309`:
   These are REPL tools — they NEED eval/exec to function. Add logging + rate limiting instead:
   ```python
   logger.warning("[VECTOR][repl] code execution by user: {}...", code[:100])
   ```

6. Remaining eval/exec sites: read each, add restricted globals + logging. If removable without breaking functionality, remove.

---

### Task 3C — Commit Phase 3

```bash
git add core/scraper/spiders/checkpoint.py districts/investment/ vectorcode/src/workflow/engine.py vectorcode/src/vc_tools/repl.py
git commit -m "[phase-3] security: fix pickle.loads RCE, sandbox 34 eval/exec sites"
```

---

## Phase 4 — Async correctness fixes (1h)

**Why:** 26 `time.sleep()` calls in async functions block the event loop. Each should be `await asyncio.sleep()`.

### Task 4A — Bulk-convert time.sleep to asyncio.sleep

**Target files** (from `rg -l "time\.sleep" core/ --include="*.py"`):
- `core/voice/tts.py:178` — `time.sleep(0.05)` → `await asyncio.sleep(0.05)`
- `core/vision_control/vision_operator.py:244` — same
- `core/mcp/client.py:108` — `time.sleep(0.1)` → `await asyncio.sleep(0.1)`
- `core/training/lora_trainer.py:174` — same
- `core/engine/telemetry/otel_bridge.py:203` — `time.sleep(0.01)` → `await asyncio.sleep(0.01)`
- `core/mining/_pearl_subprocess.py:150` — same
- `core/research_engine/` — 10+ instances, bulk convert

**Conversion rule:**
If in `async def`:
```python
# OLD
time.sleep(0.5)
# NEW
await asyncio.sleep(0.5)
```

If in `def` (not async), but called from async context, convert the function to `async def`.

**Acceptance:**
```bash
rg "time\.sleep" core/ --include="*.py" | Measure-Object -Line
# Returns < 5 (remaining ones are in sync-only code paths)
python run_vector.py smoke
# Passes
```

---

### Task 4B — Commit Phase 4

```bash
git add core/voice/ core/vision_control/ core/mcp/client.py core/training/ core/engine/telemetry/ core/mining/ core/research_engine/
git commit -m "[phase-4] fix: convert 26 time.sleep() to await asyncio.sleep() in async context"
```

---

## Phase 5 — Centralize configuration (1h)

**Why:** 51+ `os.getenv()` calls scattered outside `core/config.py`. Changing an env var requires hunting through 17+ files.

### Task 5A — Migrate scattered os.getenv into config.py

**Files to migrate:**

| File | Env Var | Target config field |
|------|---------|-------------------|
| `core/network/ofp_protocol.py:199` | `VECTOR_OFP_SECRET` | `VectorSettings.ofp_secret` |
| `core/network/peer_discovery.py:129` | `VECTOR_PEERS` | `VectorSettings.peer_list` |
| `core/inference/vectorcode_llm.py:230` | `GEMINI_API_KEY` | Already in config? Check |
| `core/inference/vectorcode_llm.py:277` | `ANTHROPIC_API_KEY` | Already in config? Check |
| `core/inference/vectorcode_llm.py:321` | `OPENROUTER_API_KEY` | Already in config? Check |
| `core/engine/oauth/flows.py:27` | `VECTOR_CLOUD_API_URL` | `VectorSettings.cloud_api_url` |
| `core/engine/oauth/server.py:49` | `VECTOR_OAUTH_REDIRECT_BASE` | `VectorSettings.oauth_redirect_base` |
| `core/engine/telemetry/sentry_bridge.py:20-22` | `SENTRY_DSN`, etc. | Already in config? Check |
| `core/voice/elevenlabs_tts.py:20,23` | `ELEVENLABS_API_KEY`, `VOICE_ID` | `VectorSettings.elevenlabs_key` |
| `core/trading/dataflows/alpha_vantage_common.py:12` | `ALPHA_VANTAGE_API_KEY` | `VectorSettings.alpha_vantage_key` |
| `core/trading/config.py:46-48` | 3 trading env vars | `VectorSettings.trading_*` |
| `core/research_engine/settings/manager.py:273` | research engine var | `VectorSettings.research_*` |
| `core/research_engine/config/paths.py:28` | `LDR_DATA_DIR` | `VectorSettings.ldr_data_dir` |

**Procedure per file:**
1. Add field to `VectorSettings` in `core/config.py` (typed, with default, SecretStr if sensitive)
2. In consuming file, import config and use the field instead of raw `os.getenv()`
3. Verify: `python -c "from core.config import CONFIG; print(CONFIG.get('<field>', '<REDACTED>'))"`

**Acceptance:**
```bash
rg "os\.getenv\(" core/ --include="*.py" --no-filename | Measure-Object -Line
# Returns < 10 (remaining are in config.py and known config modules)
python run_vector.py smoke
# Passes
```

---

### Task 5B — Commit Phase 5

```bash
git add core/config.py core/network/ core/inference/ core/engine/ core/voice/ core/trading/ core/research_engine/settings/ core/research_engine/config/
git commit -m "[phase-5] refactor: centralize 51 scattered os.getenv calls into Pydantic config"
```

---

## Phase 6 — Lifecycle: SIGTERM handler + cleanup (1h)

**Why:** No graceful shutdown. On SIGTERM/kill, SQLite connections, thread pools, event bus tasks, and background services are abandoned in-flight.

### Task 6A — Add signal handler to run_vector.py (30 min)

**File:** `run_vector.py`

```python
import signal

def _setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGINT/SIGTERM for graceful shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown(s)))

async def _shutdown(sig: signal.Signals) -> None:
    logger.warning("[VECTOR][lifecycle] received {}, shutting down gracefully...", sig.name)
    # 1. Stop autonomous loop
    if hasattr(loop_inst := globals().get('_loop_instance'), 'stop'):
        loop_inst.stop()
    # 2. Cancel background tasks
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
    # 3. Close event bus
    try:
        from core.event_bus.bus import get_event_bus
        await get_event_bus().stop()
    except Exception as e:
        logger.debug("[VECTOR][lifecycle] bus stop: {}", e)
    # 4. Close DB connections
    try:
        from core.memory.episodic import get_db_connection
        conn = get_db_connection()
        conn.close()
    except Exception as e:
        logger.debug("[VECTOR][lifecycle] db close: {}", e)
    # 5. Flush logs
    try:
        from loguru import logger as lgr
        lgr.complete()
    except Exception:
        pass
    # 6. Stop event loop
    loop = asyncio.get_running_loop()
    loop.stop()
```

### Task 6B — Wire into main() (15 min)

```python
async def run_loop() -> None:
    preflight_checks()
    _setup_signal_handlers(asyncio.get_event_loop())
    ...
```

**Acceptance:** Send SIGTERM while running → log shows graceful shutdown sequence → exit code 0. No tracebacks.

---

### Task 6C — Fix TaskQueue thread pool cleanup (15 min)

**File:** `core/loop/task_queue.py`

Add `shutdown()` method:
```python
def shutdown(self, wait: bool = True) -> None:
    """Release thread pool resources."""
    self._thread_pool.shutdown(wait=wait)
    logger.info("[VECTOR][task_queue] thread pool shut down")
```

Call from `_shutdown()` in Phase 6A step 2.

**Acceptance:** After graceful shutdown, `ThreadPoolExecutor._shutdown` is True.

---

### Task 6D — Commit Phase 6

```bash
git add run_vector.py core/loop/task_queue.py
git commit -m "[phase-6] lifecycle: add SIGTERM handler, graceful shutdown, thread pool cleanup"
```

---

## Phase 7 — Agent coordination: event fan-out + backpressure (3h)

**Why:** The wildcard fan-out bottleneck (single subscriber iterates all agents per event, O(n*m)) and silent event loss on queue overflow are the two biggest agent coordination gaps.

### Task 7A — Build event_fanout_loop (1.5h)

**File:** `core/loop/autonomous_loop.py`

Add dedicated coroutine:
```python
async def event_fanout_loop(self) -> None:
    """Dedicated event consumer — fan out to subscribed agents with per-agent timeout."""
    bus = get_event_bus()
    reg = self._get_agent_registry()
    while self._running:
        try:
            event = await bus.consume(timeout=1.0)
            if event is None:
                continue
            et = str(event.event_type) if hasattr(event, 'event_type') else event.get('type', '')
            targets = [a for a in reg.list_alive() if et in a.subscribed_events]
            if not targets:
                continue
            results = await asyncio.gather(
                *(self._dispatch_event_to_agent(a, event) for a in targets),
                return_exceptions=True
            )
            failures = [(a, r) for a, r in zip(targets, results) if isinstance(r, Exception)]
            if failures:
                for agent, err in failures:
                    logger.warning("[VECTOR][event_fanout] {} failed on {}: {}", agent.name, et, err)
        except Exception as e:
            logger.error("[VECTOR][event_fanout] loop error: {}", e)
            await asyncio.sleep(1.0)

async def _dispatch_event_to_agent(self, agent, event) -> None:
    """Dispatch a single event to a single agent with timeout."""
    try:
        await asyncio.wait_for(
            agent.handle_event(event),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        logger.warning("[VECTOR][event_fanout] {} timeout on {}", agent.name, event.event_type if hasattr(event, 'event_type') else event)
```

Register in `run_forever()` gater alongside the existing loops.

**Acceptance:** Publish event → subscribed agent receives it within 1s. Agent timeout at 5s doesn't block other agents.

---

### Task 7B — Add event bus backpressure + DLQ (1h)

**File:** `core/event_bus/bus.py`

Replace silent drop on queue overflow with:
1. **Circuit breaker**: if queue hits 90% capacity, log warning and throttle publishers
2. **DLQ**: on overflow, move oldest event to a `deque(maxlen=100)` dead letter buffer
3. **Structured overflow log**: `{"event_type": et, "subscriber": sub, "queue_size": qsize, "action": "dropped"}`

```python
async def publish(self, event_type: str | None, event: Event) -> None:
    for sub_id, (queue, _) in self._subscribers.items():
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Push oldest to DLQ
            try:
                dropped = queue.get_nowait()
                self._dead_letters[sub_id].append(dropped)
            except asyncio.QueueEmpty:
                pass
            # Retry the new event
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._stats["dropped"] += 1
                logger.warning(
                    "[VECTOR][event_bus] subscriber {} queue full, event {} dropped",
                    sub_id, event.event_type if hasattr(event, 'event_type') else '?'
                )
```

**Acceptance:** Trigger queue overflow → event goes to DLQ, no silent drop. `bus.get_stats()["dropped"]` is 0 (DLQ caught it).

---

### Task 7C — Commit Phase 7

```bash
git add core/loop/autonomous_loop.py core/event_bus/bus.py
git commit -m "[phase-7] feat: add event_fanout_loop, per-agent timeout, bus DLQ for overflow"
```

---

## Phase 8 — Auth middleware (2h)

**Why:** 72 of 75 API endpoints have no authentication. Every router implements its own auth (or doesn't).

### Task 8A — Add FastAPI middleware (1h)

**File:** `core/api/app.py`

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import secrets
import os

class APIAuthMiddleware(BaseHTTPMiddleware):
    """Unified auth middleware — checks Bearer token on all endpoints except health/docs."""
    PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        api_key = os.getenv("VECTOR_API_KEY", "")
        if not api_key:
            # No key configured — allow in dev, block in production
            env = os.getenv("VECTOR_ENV", "development")
            if env == "production":
                raise HTTPException(status_code=503, detail="API key not configured")
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = auth[7:]
        if not secrets.compare_digest(token, api_key):
            raise HTTPException(status_code=403, detail="Invalid API key")
        return await call_next(request)
```

Register in `create_app()`:
```python
app.add_middleware(APIAuthMiddleware)
```

### Task 8B — Remove per-router auth where redundant (30 min)

Files that already have auth checks: `tasks.py`, `websocket.py`. After middleware, their auth is redundant — remove the per-handler checks.

### Task 8C — Update .env.example (15 min)

Add:
```env
VECTOR_API_KEY=                 # Bearer token for all API endpoints
VECTOR_ENV=development          # Set to "production" to enforce API key
```

### Task 8D — Commit Phase 8

```bash
git add core/api/app.py core/api/routers/tasks.py .env.example
git commit -m "[phase-8] security: add unified API auth middleware, remove per-router redundancy"
```

---

## Phase 9 — OFP TLS + crypto hardening (2h)

### Task 9A — Add TLS support to OFP (1.5h)

**File:** `core/network/ofp_protocol.py`

1. Add `_tls_context` init in `__init__`:
```python
def _init_tls(self) -> ssl.SSLContext | None:
    cert_path = os.getenv("VECTOR_OFP_CERT", "")
    key_path = os.getenv("VECTOR_OFP_KEY", "")
    if cert_path and key_path:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(cert_path, key_path)
        logger.info("[VECTOR][ofp] TLS enabled (cert={})", cert_path)
        return ctx
    logger.warning("[VECTOR][ofp] TLS not configured — traffic is PLAINTEXT")
    return None
```

2. On server side (`start_peer_server`): wrap socket with `await loop.create_connection(lambda: ... , ssl=tls_ctx)`
3. On client side (`_send_frame` / `_recv_frame`): pass `ssl=tls_ctx` when connecting
4. Both sides fall back to plain TCP if no cert configured (backward compat)

### Task 9B — Commit Phase 9

```bash
git add core/network/ofp_protocol.py
git commit -m "[phase-9] security: add optional TLS to OFP with backward-compat plaintext fallback"
```

---

## Phase 10 — Testing gaps (3h)

### Task 10A — Write autonomous_loop smoke tests (2h)

**File:** `tests/loop/test_autonomous_loop.py`

```python
"""Tests for the autonomous loop — the heart of VECTOR."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

class TestAutonomousLoop:
    """Test critical path methods in isolation."""

    @pytest.mark.asyncio
    async def test_parse_cron_daily_valid(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("30 8 * * *")
        assert result == (8, 30)

    @pytest.mark.asyncio
    async def test_parse_cron_daily_non_daily(self):
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("30 8 * * 1")  # Monday, not daily
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_cron_daily_invalid(self):
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("not a cron")
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        loop = AutonomousLoop()
        loop._running = True
        loop.stop()
        assert loop._running is False

    @pytest.mark.asyncio
    async def test_scan_threats_runs_without_error(self):
        loop = AutonomousLoop()
        with patch.object(loop, '_get_ambient') as mock_ambient:
            mock_ambient.return_value = {"active_window": "test", "process_count": 50}
            result = await loop._scan_threats()
            assert result in (True, False)

    @pytest.mark.asyncio
    async def test_dispatch_event_to_agent_timeout(self):
        loop = AutonomousLoop()
        agent = AsyncMock()
        agent.handle_event = AsyncMock(side_effect=asyncio.TimeoutError)
        event = MagicMock()
        with pytest.raises(asyncio.TimeoutError):
            await loop._dispatch_event_to_agent(agent, event)
```

### Task 10B — Write config validation test (30 min)

**File:** `tests/core/test_config.py`

Test that VectorSettings validates types correctly, SecretStr masks in repr, env var overrides work.

### Task 10C — Add baseline regression check (30 min)

Add to CI or docs:
```bash
python -m pytest -q tests/ --tb=short --ignore=tests/research_engine -x
python run_vector.py smoke
```

### Task 10D — Commit Phase 10

```bash
git add tests/loop/test_autonomous_loop.py tests/core/test_config.py
git commit -m "[phase-10] test: add autonomous_loop tests, config tests, regression baseline"
```

---

## Phase 11 — Stale feature fixes (1.5h)

### Task 11A — Kokoro→Piper TTS fix (30 min)

**File:** `core/voice/tts.py`

Change priority from `Kokoro > pyttsx3` to `Piper > Kokoro > pyttsx3`:
```python
class VoiceTTS:
    PRIORITY = ["piper", "kokoro", "pyttsx3"]

    def _init_piper(self) -> bool:
        """Initialize Piper TTS (fast, offline, good quality)."""
        try:
            import piper_tts
            model_path = CONFIG.get("voice", {}).get("piper_model", "models/piper/en_US-ryan-high.onnx")
            self._piper = piper_tts.PiperTTS(model_path)
            logger.info("[VECTOR][voice] Piper TTS ready")
            return True
        except Exception as e:
            logger.debug("[VECTOR][voice] Piper unavailable: {}", e)
            return False
```

### Task 11B — Rename _stubs.py to _abc.py (30 min)

Bulk rename 18 files. Update all imports in `core/` and `vectorcode/`:
```bash
Get-ChildItem -Recurse -Filter "_stubs.py" | Rename-Item -NewName { $_.Name.Replace("_stubs.py", "_abc.py") }
```

Update imports:
```bash
rg -l "from.*_stubs import|import.*_stubs" --include="*.py" | ForEach-Object {
    (Get-Content $_) -replace '_stubs', '_abc' | Set-Content $_
}
```

### Task 11C — Clean up core/mining/ duplicates (30 min)

- `_constants.py` vs `constants.py` — merge into public name
- `_stubs.py` (now `_abc.py`) — keep, it's a proper ABC
- `stubs.py` (backward compat shim) — can delete after import update

### Task 11D — Commit Phase 11

```bash
git add core/voice/tts.py
# _stubs → _abc rename handled separately
git commit -m "[phase-11] fix: Piper TTS priority, _stubs→_abc rename, mining cleanup"
```

---

## Phase 12 — Self-improvement validation (1.5h)

### Task 12A — Add eval gates (1h)

**File:** `core/training/openmythos/trainer.py`

```python
def evaluate(self, holdout_prompts: list[str]) -> dict:
    """Evaluate trained model on holdout set. Returns metrics dict."""
    coherence_scores = []
    for prompt in holdout_prompts[:50]:
        output = self.generate(prompt)
        score = self._llm_judge_coherence(output)
        coherence_scores.append(score)
    return {
        "coherence": sum(coherence_scores) / len(coherence_scores),
        "samples": len(coherence_scores),
    }

def should_deploy(self, eval_result: dict, baseline: dict) -> tuple[bool, str]:
    """Gate: reject if any metric regresses beyond threshold."""
    if eval_result["coherence"] < baseline["coherence"] * 0.85:
        return False, f"coherence dropped: {eval_result['coherence']:.2f} vs {baseline['coherence']:.2f}"
    return True, "all gates passed"
```

### Task 12B — Wire gates into run_weekly() (15 min)

**File:** `core/loop/autonomous_loop.py` around line 920

```python
if trainer and hasattr(trainer, 'should_deploy'):
    deploy_ok, reason = trainer.should_deploy(eval_result, baseline)
    if not deploy_ok:
        logger.warning("[VECTOR][training] deploy rejected: {}", reason)
        # Push to rejected_runs for analysis
        ...
        return {"status": "rejected", "reason": reason}
```

### Task 12C — Commit Phase 12

```bash
git add core/training/openmythos/trainer.py core/loop/autonomous_loop.py
git commit -m "[phase-12] feat: add eval gates to self-improvement cycle"
```

---

## Final Acceptance Checklist

After all 12 phases:

```bash
# 1. No event loop proliferation
rg "asyncio.new_event_loop" core/ --include="*.py"
# → 0

# 2. Silent exceptions < 100
rg -c "except Exception:\s*$|except:\s*$" core/ --include="*.py" | ForEach-Object { $_ -split ':' | Select-Object -Last 1 } | Measure-Object -Sum
# → Sum < 100

# 3. Security: no pickle.loads in prod code
rg "pickle\.loads" core/ --include="*.py"
# → 0 (or properly guarded)

# 4. Async: no time.sleep in async context
rg "time\.sleep" core/ --include="*.py" | Measure-Object -Line
# → < 5

# 5. Config: os.getenv mostly in config.py
rg "os\.getenv\(" core/ --include="*.py" --no-filename | Measure-Object -Line
# → < 10

# 6. Tests pass
python -m pytest -q tests/ --tb=short --ignore=tests/research_engine -x
# → all pass

# 7. Smoke test passes
python run_vector.py smoke
# → {"status": "ok", ...}

# 8. Graceful shutdown
# Start VECTOR, send SIGTERM → no tracebacks, clean exit
```

---

## Effort Summary

| Phase | Description | Hours | Risk |
|-------|-------------|-------|------|
| 0 | Cleanup & baseline | 1 | Low |
| 1 | Fix event-loop-per-request | 3 | Medium |
| 2 | Silent exception cleanup | 3 | Low |
| 3 | Security critical fixes | 2 | Low |
| 4 | Async correctness | 1 | Low |
| 5 | Config centralization | 1 | Low |
| 6 | SIGTERM + lifecycle | 1 | Low |
| 7 | Event fan-out + backpressure | 3 | Medium |
| 8 | Auth middleware | 2 | Low |
| 9 | OFP TLS | 2 | Low |
| 10 | Testing gaps | 3 | Low |
| 11 | Stale feature fixes | 1.5 | Low |
| 12 | Self-improvement gates | 1.5 | Low |
| **Total** | | **24-26 hours** | |
