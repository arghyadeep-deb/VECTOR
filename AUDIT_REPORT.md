# VECTOR Codebase Comprehensive Audit Report

**Date:** 2026-06-11
**Scope:** `vectorcode/src/` — 10+ directories, ~150K lines, 400+ .py files
**Auditor:** opencode (automated static analysis)

---

## Summary Statistics

| Directory | Files | Lines | Status |
|---|---|---|---|
| `tools/` | 124 | 56,796 | COMPLETE (with issues) |
| `vc_tools/` | 51 | 9,229 | COMPLETE (with issues) |
| `vector_cli/` | 123 | 76,624 | COMPLETE (with issues) |
| `channels/` | 41 | 5,352 | COMPLETE (with issues) |
| `system/` | 7 | 1,312 | COMPLETE (duplicate of vc_system) |
| `vc_system/` | 7 | 1,373 | COMPLETE (canonical) |
| `speech/` | 10 | 621 | COMPLETE |
| `workflow/` | 6 | 751 | COMPLETE |
| `transports/` | 6 | 1,470 | COMPLETE (fragile) |
| `utils/` | 9 | 866 | COMPLETE (with bugs) |
| `telemetry/` | 20 | 72 | RE-EXPORT SHIMS |
| `vector.py` | 1 | 22 | COMPLETE |
| **TOTAL** | **~400** | **~153K** | |

---

## CRITICAL Issues

### C1. `system/` is a near-duplicate of `vc_system/` — diverging copies
**Severity:** CRITICAL | **Files:** All 7 files in both dirs

Both directories contain identical file names (`builder.py`, `bundles.py`, `core.py`, `orchestrator.py`, `protocols.py`, `_channel_kwargs.py`, `__init__.py`) with **different content**. Key divergences:

- **`system/protocols.py`**: 2-line re-export (`from vectorcode.src.vc_system.protocols import OrchestratorDeps`)
- **`vc_system/protocols.py`**: Full 50-line `OrchestratorDeps` Protocol class definition
- **`system/builder.py`**: Uses `from vectorcode.src.mcp.server import MCPServer` and `from vectorcode.src.telemetry.store import TelemetryStore`
- **`vc_system/builder.py`**: Uses `from vectorcode.src.vc_mcp.server import MCPServer` and `from core.telemetry.store import TelemetryStore`
- **`system/bundles.py`**: Imports from `vectorcode.src.scheduler.*`
- **`vc_system/bundles.py`**: Imports from `core.scheduler.*`
- **`system/core.py`**: Imports from `vectorcode.src.skills.manager`, `vectorcode.src.comms._abc`
- **`vc_system/core.py`**: Imports from `vectorcode.src.vc_skills.manager`, `vector.channels._abc` (with bare try/except ImportError)

**Impact:** Which directory is actually used at runtime? Import paths scattered across the codebase reference both. Any bug fix applied to one copy will NOT be applied to the other.

---

### C2. Bare `core.*` imports — no `vectorcode.src.` prefix, will fail at runtime
**Severity:** CRITICAL | **Files:** Multiple

These imports use `core.X` instead of `vectorcode.src.core.X` or `vectorcode.src.vc_core.X`. They rely on `sys.path` manipulation to work:

| File | Bare Import |
|---|---|
| `vc_system/builder.py:__` | `from core.telemetry.store` |
| `vc_system/builder.py:__` | `from core.sandbox.runner` |
| `vc_system/builder.py:__` | `from core.scheduler.store` |
| `vc_system/builder.py:__` | `from core.scheduler.scheduler` |
| `vc_system/bundles.py:__` | `from core.scheduler.scheduler` |
| `vc_system/bundles.py:__` | `from core.scheduler.store` |
| `vc_system/bundles.py:__` | `from core.telemetry.gpu_monitor` |
| `vc_system/bundles.py:__` | `from core.telemetry.store` |
| `transports/__init__.py` | `sys.path` hack to strip own directory |
| `webhook.py:19` | `from core.engine.webhook.hmac_signer` |
| `vector_cli/doctor_cmd.py` | 2 bare core imports |
| `vector_cli/telemetry_cmd.py` | 1 bare core import |

**Impact:** Import resolution depends on `sys.path` state. Breaks if package installed differently or when Python path changes.

---

### C3. `vc_tools/shell_exec.py:139` — imports from `vector._rust_bridge` (wrong package)
**Severity:** CRITICAL

```python
from vector._rust_bridge import get_rust_module  # line 139
```

The canonical path is `vectorcode.src._rust_bridge`, not `vector._rust_bridge`. Same bug at `vc_tools/storage/sqlite.py:46,105`. The Rust extension `.pyd` doesn't exist in this repo (noted in `_rust_bridge.py`), but the import path is wrong regardless — if it ever does exist, this will fail.

---

### C4. `vc_tools/storage/sqlite.py:46-51` — Unreachable code after suppressed ImportError
**Severity:** CRITICAL

```python
try:
    from vector._rust_bridge import get_rust_module  # WRONG PATH
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

_rust = get_rust_module()  # NameError: get_rust_module not defined
self._rust_impl = _rust.SQLiteMemory(self._db_path)  # Never reached
```

The `except ImportError` block logs and continues, but then line 50 calls `get_rust_module()` which was never imported — **NameError at runtime**. The `except` block should `pass` into a pure-Python fallback, but instead falls through to code that requires the import.

---

### C5. `tools/skills_guard.py` — `eval()` + `exec()` on external skill code
**Severity:** CRITICAL | **File:** `tools/skills_guard.py` (932 lines)

This file uses `eval()` and `exec()` to inspect/execute skill code. While it's a security scanner (intended to detect bad patterns), the use of `eval`/`exec` on untrusted code is itself a security risk if the scanning is insufficient.

---

### C6. `vc_tools/templates/loader.py:92` — `eval()` on TOML-defined expressions
**Severity:** CRITICAL

```python
result = eval(expr, {"__builtins__": safe_builtins}, params)
```

`safe_builtins` includes `json` module (line 90), which provides access to `json.decoder`, `json.encoder`, etc. A crafted TOML template could exploit this. Also, `params` (user-controlled) is passed as `locals`, enabling attribute access chain exploits.

---

### C7. `vc_tools/templates/loader.py:116` — Insufficient shell injection protection
**Severity:** CRITICAL

```python
safe_val = str(val).replace(";", "").replace("&", "").replace("|", "").replace("`", "")
```

Blocklist-based sanitization is incomplete. Missing: `$()`, `>`, `<`, `>>`, `<<`, newline injection, `\x00`, etc. Since this constructs commands that are then `shlex.split()` and passed to `subprocess.run(shell=False)`, newlines in the value could still break the command.

---

## HIGH Issues

### H1. `utils/usage_pricing.py:13` — Timestamp never set, day filtering broken
**Severity:** HIGH

Sessions are recorded without a `timestamp` field at line 13, but `get_usage_summary()` at line 41 filters by `s.get("timestamp", 0)`. Since timestamp is never written, all sessions default to epoch 0, making day-based cost filtering completely non-functional.

---

### H2. `utils/usage_pricing.py` — No file locking on concurrent writes
**Severity:** HIGH

`_USAGE_FILE` is read/written with no locking (`fcntl`/`msvcrt`/filelock). If two VECTOR processes write simultaneously, data corruption or loss will occur.

---

### H3. `utils/time_utils.py:9` — Overwrites loguru `logger` with stdlib `logging.getLogger`
**Severity:** HIGH

```python
from loguru import logger  # line 3
...
logger = logging.getLogger(__name__)  # line 9 — shadows the import
```

All subsequent calls to `logger` in this file use stdlib logging instead of loguru, breaking VECTOR's logging convention.

---

### H4. `utils/time_utils.py:21` — Duplicate env var check `VECTOR_TIMEZONE`
**Severity:** HIGH

The `VECTOR_TIMEZONE` environment variable is checked twice: once in `time_utils.py` and again in `vector_time.py`. The two files have different resolution orders and fallback behavior, creating inconsistency.

---

### H5. `utils/__init__.py:28` — References `logger` before importing it
**Severity:** HIGH

The dynamic module loader at line 28 references `logger` before the loguru import, causing a potential `NameError` depending on execution order.

---

### H6. `tools/terminal_tool.py:3` — `from loguru import logger` inside docstring
**Severity:** HIGH

```python
"""
from loguru import logger
Terminal Tool Module
```

The `from loguru import logger` is inside the module docstring (triple-quoted), not actual code. This means the file has no `logger` import at the top level — any `logger.xxx()` calls in the file body will fail with `NameError`.

---

### H7. `tools/mcp_oauth.py:33` — Hardcoded OAuth `client_secret: "secret"`
**Severity:** HIGH

The docstring example shows `client_secret: "secret"` which could be copy-pasted as real config. While it's in a docstring, it normalizes insecure defaults.

---

### H8. `tools/terminal_tool.py` — Hardcoded `password = "SUDO_PASSWORD"`
**Severity:** HIGH

Placeholder password in code. If someone fills this in and commits, it's a leaked credential. Should use env var / config exclusively.

---

### H9. `channels/slack_daemon.py:52-55` — Wrong import paths
**Severity:** HIGH

```python
from vectorcode.src.agents.deep_research import DeepResearchAgent
from vectorcode.src.engine.ollama import OllamaEngine
from vectorcode.src.server.agent_manager_routes import _build_deep_research_tools
```

These import paths (`agents`, `engine`, `server`) don't match the actual package structure. The correct paths likely go through `vc_agents`, `vc_engine`, etc. Will fail at runtime.

---

### H10. `channels/slack_daemon.py:147-158` — Tokens passed as CLI arguments
**Severity:** HIGH

```python
subprocess.Popen([
    sys.executable, "-m", "openjarvis.channels.slack_daemon",
    "--bot-token", bot_token, "--app-token", app_token,
])
```

Bot tokens are visible in the process list (`ps aux`). Should use env vars or a file-based approach. Also references `openjarvis.channels.slack_daemon` (old package name).

---

### H11. `channels/webhook.py:13-14` — Wrong import paths for core modules
**Severity:** HIGH

```python
from vectorcode.src.core.events import EventBus, EventType
from vectorcode.src.core.registry import ChannelRegistry
```

These should likely be `vectorcode.src.vc_core.events` and `vectorcode.src.vc_core.registry`. Several other channel files use the same wrong path. Will fail at runtime if `vectorcode.src.core` doesn't exist as a package.

---

### H12. `transports/` — `sys.path` hack to avoid `types.py` shadowing stdlib
**Severity:** HIGH | **Files:** All 6 transport files

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path = [p for p in sys.path if p != os.path.dirname(os.path.abspath(__file__))]
```

The file `types.py` shadows the stdlib `types` module. Instead of renaming it, all transport files manipulate `sys.path` to strip their own directory. This is fragile and can break other modules' imports.

---

### H13. `vector_cli/webhook.py` — Hardcoded HMAC secret
**Severity:** HIGH

```python
secret: "your-global-hmac-secret"
```

Default HMAC secret in webhook configuration. If deployed without changing it, all webhook signatures are predictable.

---

## MEDIUM Issues

### M1. `vc_tools/code_interpreter.py` — Blocklist-based code security is bypassable
**Severity:** MEDIUM

The `_BLOCKED_PATTERNS` check is string-based (`if pattern in code`). Trivial bypasses:
- `__import__("os").system("rm -rf /")` — `__import__` is blocked but `__imp` + `ort__("os")` could bypass in concatenated strings
- `getattr(os, "system")` — not in blocklist
- `os.environ` — not blocked but can leak secrets

---

### M2. `vc_tools/repl.py` — Same blocklist bypass as code_interpreter
**Severity:** MEDIUM

`_BLOCKED_PATTERNS` is a substring match. `"open("` is blocked but `open\t(` or `builtins.open` bypass it. The restricted builtins approach is better but `json` in safe builtins still allows module traversal attacks.

---

### M3. `workflow/loader.py` — No path traversal protection
**Severity:** MEDIUM

`open(path, "rb")` is called without validating that `path` doesn't escape the intended directory. A crafted workflow definition could read arbitrary files.

---

### M4. `speech/openai_tts.py`, `speech/cartesia_tts.py` — No API key input validation
**Severity:** MEDIUM

API keys are passed via headers with no format validation. Empty or malformed keys will cause cryptic HTTP 401/403 errors rather than clear validation messages.

---

### M5. `utils/redact.py` — Regex-based redaction misses non-standard patterns
**Severity:** MEDIUM

The redaction regex only covers known key names. Custom key names (e.g., `my_api_token`, `x-custom-secret`) will not be redacted.

---

### M6. `telemetry/` — 20 files, all are 4-line re-export shims
**Severity:** MEDIUM

Every telemetry file is:
```python
from core.telemetry.X import *  # noqa: F401, F403
from core.telemetry.X import __all__  # noqa: F401
```

These use bare `core.*` imports and wildcard re-exports. If `core.telemetry` doesn't exist, all 20 files fail silently.

---

### M7. `channels/mastodon_channel.py` — 29 TODOs
**Severity:** MEDIUM

29 TODO/FIXME markers suggest the implementation is incomplete.

---

### M8. `channels/adapters/mastodon_adapter.py` — 14 TODOs
**Severity:** MEDIUM

14 TODOs indicate significant incomplete work.

---

### M9. `tools/todo_tool.py` — 39 TODOs (meta-ironic)
**Severity:** MEDIUM

The TODO tool itself has 39 TODOs.

---

### M10. `channels/adapters/__init__.py` — 7 TODOs
**Severity:** MEDIUM

Adapter registry incomplete.

---

### M11. `channels/imessage_daemon.py` — 9-line stub
**Severity:** MEDIUM

```python
try:
    from vectorcode.src.comms.imessage_daemon import *
except ImportError:
    def is_running() -> bool:
        return False
```

Always returns `False`. The `comms.imessage_daemon` module doesn't exist.

---

### M12. `vector.py:14-18` — Fragile dynamic import of CLI
**Severity:** MEDIUM

```python
_spec = importlib.util.spec_from_file_location("vectorcode._cli_main", _cli_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
```

If `src/cli.py` moves or is renamed, this breaks silently. No error handling.

---

### M13. `vc_tools/storage/sqlite.py:137` — `close()` is a no-op (`pass`)
**Severity:** MEDIUM

The SQLite `close()` method is `pass` — database connection is never properly closed, risking data loss on unclean shutdown.

---

## LOW Issues

### L1. `tools/storage/_abc.py` — 16-line stub with 3 NotImplementedError
**Severity:** LOW

`MemoryBackend` class has 3 abstract methods that just `raise NotImplementedError`. This is the `tools/` copy; the `vc_tools/storage/_abc.py` (50 lines) is the more complete version.

---

### L2. `vector_cli/auth_cmd.py` — `api_key = "{key}"` in f-string
**Severity:** LOW

Template string, not an actual leaked key. But confusing.

---

### L3. `vector_cli/model.py` — `api_key = "required"`
**Severity:** LOW

Placeholder, not a real key. Confusing naming.

---

### L4. `channels/whatsapp_business.py` — 1 TODO
**Severity:** LOW

---

### L5. `vc_tools/digest_collect.py` — 6 TODOs
**Severity:** LOW

---

### L6. `vector_cli/_bootstrap.py` — `api_key='{_REDACTED_PLACEHOLDER}'`
**Severity:** LOW

Placeholder, but the naming suggests a key was redacted rather than never existing.

---

## Duplicate Code Summary

| Pair | Common Files | Status |
|---|---|---|
| `system/` ↔ `vc_system/` | All 7 files | **DIVERGENT COPIES** — different import paths, different code |
| `tools/` ↔ `vc_tools/` | 8 files | **DIVERGENT COPIES** — different import paths (`core.*` vs `vectorcode.src.vc_core.*`) |
| `tools/storage/` ↔ `vc_tools/storage/` | `chunking.py`, `ingest.py` | **DIVERGENT COPIES** |
| `telemetry/` ↔ `core/telemetry/` | All 20 files | Re-export shims (no duplication, but bare imports) |

**Total duplicate/divergent files:** ~35

---

## Security Summary

| Category | Count |
|---|---|
| `eval()`/`exec()` usage | 4 files (skills_guard, repl, code_interpreter, templates/loader) |
| Subprocess spawning | ~30+ files across tools/, vector_cli/, channels/ |
| Hardcoded secrets (real) | 2 (terminal_tool SUDO_PASSWORD, webhook HMAC secret) |
| Hardcoded secrets (template) | 5 (mcp_oauth, auth_cmd, model, model_switch, _bootstrap) |
| Insufficient input sanitization | 3 (templates/loader shell injection, code_interpreter blocklist, repl blocklist) |
| Tokens in CLI args | 1 (slack_daemon) |
| Path traversal risk | 1 (workflow/loader) |
| Broken import paths (runtime crash) | 15+ files |

---

## Recommendations (Priority Order)

1. **Eliminate `system/` or `vc_system/`** — Pick one canonical location, delete the other. Fix all imports.
2. **Fix all bare `core.*` imports** — Replace with `vectorcode.src.vc_core.*` or `vectorcode.src.core.*` consistently.
3. **Fix `vector._rust_bridge` → `vectorcode.src._rust_bridge`** in shell_exec.py and sqlite.py.
4. **Fix sqlite.py unreachable code** — Add proper fallback when Rust module not available.
5. **Fix terminal_tool.py docstring logger import** — Move `from loguru import logger` out of the docstring.
6. **Fix `utils/usage_pricing.py` timestamp** — Add timestamp to session records.
7. **Fix `utils/time_utils.py` logger shadow** — Remove stdlib logger overwrite.
8. **Fix `channels/slack_daemon.py` wrong imports** — Update to correct package paths.
9. **Rename `transports/types.py`** — Eliminate the need for `sys.path` hacks.
10. **Replace blocklist-based code security** — Use AST-based allowlisting in repl/code_interpreter.
11. **Fix `templates/loader.py` shell sanitization** — Use `shlex.quote()` instead of character stripping.
12. **Add file locking to `usage_pricing.py`** — Prevent concurrent write corruption.
13. **Remove tokens from CLI args** in slack_daemon — Use env vars or file-based approach.
14. **Fix `channels/webhook.py` wrong core imports** — `vc_core` not `core`.
15. **Audit all 30+ subprocess calls** — Ensure no shell injection vectors.
