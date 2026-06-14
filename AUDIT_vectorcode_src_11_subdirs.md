# VECTOR Code Audit — vectorcode/src/ 11 Subdirectories

**Date:** 2026-06-11  
**Scope:** vc_agents, vc_engine, vc_core, vc_security, vc_tools, vc_mcp, vc_sessions, vc_skills, vc_system, vc_templates, vc_traces  
**Total files:** 147 Python files  
**Total lines:** 26,636

---

## Subdirectory Summary

| Subdir | Files | Lines | Issues |
|--------|-------|-------|--------|
| vc_agents | 34 | 6,811 | 8 |
| vc_engine | 13 | 2,904 | 7 |
| vc_core | 6 | 2,327 | 0 |
| vc_security | 18 | 1,953 | 7 |
| vc_tools | 51 | 9,229 | 5 |
| vc_mcp | 5 | 689 | 0 |
| vc_sessions | 4 | 481 | 2 |
| vc_skills | 3 | 15 | 2 |
| vc_system | 7 | 1,373 | 1 |
| vc_templates | 2 | 94 | 0 |
| vc_traces | 4 | 760 | 1 |

**Total issues: 33**

---

## CRITICAL Issues (6)

### C1. `vc_engine/nexa_shim.py:31-35` — `sys.exit(1)` at module import time
**Status:** COMPLETE (but dangerous)  
**Category:** Process termination  
If `nexaai` is not installed, `sys.exit(1)` kills the entire VECTOR process — not just the module. This is catastrophic when imported as a dependency (e.g., by `_discovery.py` or `multi.py`). Should `raise ImportError` instead.

### C2. `vc_engine/apple_fm_shim.py:26-28` — `raise ImportError` at module level for non-macOS
**Status:** COMPLETE (but dangerous)  
**Category:** Process termination / portability  
Unconditionally raises `ImportError` on non-macOS platforms at import time. Any code that does `import vectorcode.src.vc_engine.apple_fm_shim` on Linux/Windows will crash. Should be guarded behind a try/except at the call site.

### C3. `vc_security/scanner.py:30` — `SecretScanner.__init__` calls `get_rust_module()` unconditionally
**Status:** COMPLETE (Rust-dependent)  
**Category:** Crash on missing Rust module  
The top-level `try/except ImportError` at line 13-16 catches the import failure, but `get_rust_module()` is still called unconditionally in `__init__` at line 30. If the Rust bridge is not installed, instantiating `SecretScanner` will `NameError`. Same issue at line 104 for `PIIScanner.__init__`. No Python fallback exists — the `PATTERNS` dict is defined but never used.

### C4. `vc_tools/repl.py` — Sandbox bypass via pattern-blocklist approach
**Status:** COMPLETE  
**Category:** Security  
The 3-layer sandbox (pattern blocklist, restricted builtins, safe import allowlist) is bypassable. Pattern blocklists can be evaded with encoding tricks, string concatenation, `getattr()`, `__import__`, `exec`/`eval` via obfuscated strings, and attribute access on allowed objects.

### C5. `vc_tools/code_interpreter.py` — Pattern-based sandbox, bypassable
**Status:** COMPLETE  
**Category:** Security  
Same class of issue as repl.py. Pattern-matching sandboxes are fundamentally bypassable. The Docker variant (`code_interpreter_docker.py`) is the safer option.

### C6. `vc_security/file_policy.py:42` — Wrong package prefix in Rust bridge import
**Status:** COMPLETE (but broken)  
**Category:** Broken import  
Imports `from vector._rust_bridge import get_rust_module` — uses `vector.` prefix instead of `vectorcode.src._rust_bridge`. Every other file in the 11 subdirs uses `vectorcode.src._rust_bridge`. This import will always fail, falling through to the Python fallback (which works, but the Rust path is dead code).

---

## HIGH Issues (11)

### H1. `vc_engine/_openai_compat.py:119-141` — Sync `httpx.Client` in `async def stream()`
**Status:** COMPLETE (but blocks event loop)  
**Category:** Concurrency  
`stream()` is declared `async` and returns `AsyncIterator[str]`, but uses `self._client.stream()` which is a **synchronous** `httpx.Client` method. This will block the entire asyncio event loop during streaming. Should use `httpx.AsyncClient` for the streaming path.

### H2. `vc_engine/ollama.py:181-201` — Same sync/async mismatch
**Status:** COMPLETE (but blocks event loop)  
**Category:** Concurrency  
Identical issue to H1. `OllamaEngine` uses `httpx.Client` (sync) in `async def stream()`. Both `generate()` and `stream()` are blocking calls disguised as async.

### H3. `vc_agents/tool_agent.py:14` — Broken import `from core.config import CONFIG`
**Status:** PARTIAL  
**Category:** Broken import  
Uses bare `core.config` instead of `vectorcode.src.vc_core.config`. Will fail at import time unless `core` happens to be on `sys.path`.

### H4. `vc_agents/skill_agent.py:15` — Broken import `from core.config import CONFIG`
**Status:** PARTIAL  
**Category:** Broken import  
Same issue as H3.

### H5. `vc_agents/routing_agent.py:12` — Broken import `from core.config import CONFIG`
**Status:** PARTIAL  
**Category:** Broken import  
Same issue as H3.

### H6. `vc_agents/memory_agent.py:45` — Broken import `from core.memory.episodic import EpisodicMemory`
**Status:** PARTIAL  
**Category:** Broken import  
Uses `core.memory.episodic` — non-existent package path. Will fail at import time.

### H7. `vc_agents/insight_agent.py:39` — Broken import `from core.memory.episodic import EpisodicMemory`
**Status:** PARTIAL  
**Category:** Broken import  
Same issue as H6.

### H8. `vc_security/audit.py:46` — SQLite `check_same_thread=False` without thread safety
**Status:** COMPLETE  
**Category:** Concurrency  
`sqlite3.connect(str(self._db_path), check_same_thread=False)` allows cross-thread access but `AuditLogger` has no locking mechanism. Concurrent writes will corrupt the database. Need a `threading.Lock` or connection-per-thread pattern.

### H9. `vc_agents/digest_store.py:33` — SQLite `check_same_thread=False` without thread safety
**Status:** COMPLETE  
**Category:** Concurrency  
Same pattern as H8. No locking around the shared connection.

### H10. `vc_agents/manager.py:100` — SQLite `check_same_thread=False` without thread safety
**Status:** COMPLETE  
**Category:** Concurrency  
Same pattern as H8.

### H11. `vc_tools/agent_tools.py:32` — Module-level `_SPAWNED_AGENTS` dict not thread-safe
**Status:** COMPLETE  
**Category:** Concurrency  
`_SPAWNED_AGENTS: Dict[str, Dict[str, Any]] = {}` is accessed from multiple tools (`agent_spawn`, `agent_list`, `agent_kill`, `agent_send`) without any synchronization. In an async context, concurrent agent operations can corrupt this dict.

---

## MEDIUM Issues (10)

### M1. `vc_engine/multi.py:44` — Hardcoded `_CLOUD_PREFIXES` misses new models
**Status:** COMPLETE  
**Category:** Maintenance  
`_CLOUD_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "claude-", "gemini-", "openrouter/")` is a hardcoded tuple. Missing: `deepseek-`, `qwen-`, `llama-` (cloud variants), `command-r-`, `mistral-` (cloud), etc. Will silently route cloud models to the local engine (404 fallback).

### M2. `vc_engine/__init__.py:24-28` — Bare `except ImportError` suppresses all import errors
**Status:** COMPLETE  
**Category:** Error handling  
The optional engine import loop catches `ImportError` with `logger.debug("[VECTOR] suppressed exception", exc_info=True)`. This silently swallows legitimate import errors (e.g., missing dependency, syntax error in imported module) and makes debugging very difficult.

### M3. `vc_engine/_discovery.py:20-35` — `_HOST_MAP` must be manually kept in sync with registered engines
**Status:** COMPLETE  
**Category:** Fragile coupling  
`_HOST_MAP` is a hardcoded dict mapping engine keys to config attribute names. When a new engine is registered via `@EngineRegistry.register()`, it won't appear in `_HOST_MAP` unless manually added. This is a maintenance trap.

### M4. `vc_security/boundary.py:27` — Duplicate `SecurityBlockError` (also in `guardrails.py:20`)
**Status:** COMPLETE  
**Category:** Code duplication / API confusion  
Two `SecurityBlockError` classes exist with the same name but different docstrings. Importing the wrong one is easy and will break `isinstance()` checks across modules.

### M5. `vc_security/credential_stripper.py:31` — `wrap_tool_output()` is misplaced
**Status:** COMPLETE  
**Category:** Dead code / Misplaced utility  
`wrap_tool_output()` is a generic XML-formatter for tool results — it has nothing to do with credential stripping. It's a utility function that belongs in a shared formatting module, not here.

### M6. `vc_security/taint.py:51-55` — `SINK_POLICY` module-level dict not extensible at runtime
**Status:** COMPLETE  
**Category:** Design  
`SINK_POLICY` is a module-level dict that maps tool names to taint propagation rules. Cannot be extended dynamically (e.g., by MCP tools or plugins registering new sinks).

### M7. `vc_security/injection_scanner.py` — Regex-based injection detection easily bypassed
**Status:** COMPLETE  
**Category:** Security  
Regex patterns for prompt injection detection can be bypassed with Unicode normalization, whitespace variations, HTML entity encoding, base64 payloads, and other obfuscation techniques. Should complement with LLM-based detection.

### M8. `vc_skills/manager.py` — STUB: `SkillManager` class is `pass`
**Status:** STUB  
**Category:** Stub  
Imports `SkillManager` from `vectorcode.src.skills.manager` (different path), falls back to an empty class. Zero functionality.

### M9. `vc_skills/overlay.py` — STUB: `SkillOverlay` class is `pass`, `write_overlay()` is `pass`
**Status:** STUB  
**Category:** Stub  
Same pattern as M8. Imports from `vectorcode.src.skills.overlay`, falls back to empty implementations.

### M10. `vc_tools/user_profile_manage.py` — Near-duplicate of `memory_manage.py`
**Status:** COMPLETE  
**Category:** Code duplication  
`user_profile_manage.py` manages `USER.md` with identical CRUD logic (read/add/update/remove) as `memory_manage.py` manages `MEMORY.md`. Should be refactored into a shared `MarkdownFileTool` base class.

---

## LOW Issues (6)

### L1. `vc_agents/digest_evaluator.py:7-8` — STUB: hardcoded `return {"score": 1.0, "feedback": "ok"}`
**Status:** STUB  
**Category:** Stub  
Always returns score 1.0. No actual evaluation logic. Every digest passes quality check unconditionally.

### L2. `vc_agents/operative.py:14-17` — Dual logger (loguru + stdlib logging)
**Status:** COMPLETE  
**Category:** Style inconsistency  
Imports both `from loguru import logger` and `import logging`. Uses `loguru` at line 14 but also creates a stdlib logger. Pick one.

### L3. `vc_system/core.py:32` — Import from `vector.channels._abc` (potential wrong package prefix)
**Status:** COMPLETE  
**Category:** Import ambiguity  
Uses `from vector.channels._abc import BaseChannel` — the `vector.` prefix (not `vectorcode.src.`) may be intentional if a separate `vector` package exists, but it's inconsistent with all other internal imports. Multiple other files also use `vector._rust_bridge` — this appears to be a separate package.

### L4. `vc_sessions/store.py` — Duplicate storage implementation (JSONL vs session.py's SQLite)
**Status:** COMPLETE  
**Category:** Code duplication  
Two session persistence backends exist: `store.py` uses JSONL files, `session.py` uses SQLite. No clear documentation on which is canonical or when to use which.

### L5. `vc_engine/cloud.py` — Very large file (~55K chars) with hardcoded pricing tables
**Status:** COMPLETE  
**Category:** Maintenance  
Direct API implementations for OpenAI, Anthropic, Google, MiniMax with hardcoded pricing tables. Pricing changes require code changes. Should externalize to a config/data file.

### L6. `vc_traces/store.py:93-97` — SQLite `check_same_thread=False` (documented as safe with WAL)
**Status:** COMPLETE  
**Category:** Concurrency (mitigated)  
Same `check_same_thread=False` pattern, but the file explicitly documents "safe with WAL mode" at line 93. However, WAL mode alone doesn't make concurrent writes safe — it only helps with read concurrency. Write serialization still needs locking.

---

## Issue Summary by Severity

| Severity | Count | Categories |
|----------|-------|------------|
| CRITICAL | 6 | Process kill (2), crash on missing dep (1), sandbox bypass (2), broken import (1) |
| HIGH | 11 | Async/sync mismatch (2), broken imports (5), SQLite concurrency (3), thread safety (1) |
| MEDIUM | 10 | Hardcoded config (2), error handling (1), code duplication (3), design (2), security (1), stub (2) |
| LOW | 6 | Stub (1), style (1), import ambiguity (1), duplication (1), maintenance (2) |

---

## Issue Summary by Category

| Category | Issues |
|----------|--------|
| **Broken imports** | C6, H3, H4, H5, H6, H7 (6 issues) |
| **Concurrency** | H1, H2, H8, H9, H10, H11, L6 (7 issues) |
| **Security** | C4, C5, M7 (3 issues) |
| **Stub / Partial** | M8, M9, L1 (3 issues) |
| **Code duplication** | M4, M10, L4 (3 issues) |
| **Process termination** | C1, C2 (2 issues) |
| **Crash on missing dep** | C3 (1 issue) |
| **Maintenance** | M1, M3, L5 (3 issues) |
| **Error handling** | M2 (1 issue) |
| **Design** | M5, M6 (2 issues) |
| **Style** | L2 (1 issue) |
| **Import ambiguity** | L3 (1 issue) |

---

## Recommendations (Priority Order)

1. **Fix C1+C2:** Replace `sys.exit(1)` / `raise ImportError` at module level with lazy imports + `raise ImportError` only when actually used.
2. **Fix C3:** Add Python fallback to `SecretScanner`/`PIIScanner.__init__()` using the `PATTERNS` dicts already defined. Gate the Rust path behind a `try/except`.
3. **Fix C6:** Change `from vector._rust_bridge` → `from vectorcode.src._rust_bridge` in `file_policy.py:42`.
4. **Fix H1+H2:** Replace `httpx.Client` with `httpx.AsyncClient` in `stream()` methods, or make `generate()` and `stream()` truly synchronous (remove `async` keyword).
5. **Fix H3-H7:** Replace all `from core.*` imports with `from vectorcode.src.vc_core.*` paths.
6. **Fix H8-H11+L6:** Add `threading.Lock` around all SQLite connections using `check_same_thread=False`. Wrap `_SPAWNED_AGENTS` in a thread-safe dict.
7. **Fix C4+C5:** Mark `repl.py` and `code_interpreter.py` sandboxes as "low-trust only". Require `code_interpreter_docker.py` for untrusted code.
8. **Fix M4:** Unify `SecurityBlockError` into a single module (e.g., `vc_security/types.py`), import from there in both `boundary.py` and `guardrails.py`.
9. **Fix M8+M9+L1:** Implement or remove the stub files.
10. **Fix M10:** Extract shared `MarkdownFileTool` base class from `memory_manage.py`/`user_profile_manage.py`.
