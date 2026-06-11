# VECTOR Audit Remediation — Issue Index

Source: full-codebase audit (2026-06-12). Tracks every issue from the audit
report. Status legend: ⬜ todo · 🟨 partial · ✅ resolved · 🔍 needs-verify.

> Analysis state: issues captured from the audit verbatim. Per-issue root-cause
> + fix is filled during the read-only analysis pass (before execution). Some
> issues were already fixed in the 2026-06-11 production-hardening session —
> flagged below and to be re-verified against current code.

## Production-readiness verdict (audit): NOT production-grade as-is

The 7 headline reasons, each mapped to tracked issues:

| # | Reason | Issues | Status |
|---|--------|--------|--------|
| 1 | 25 CRITICAL (path traversal, auth bypass, eval-on-untrusted, hardcoded secrets) | 01-08, 12 | 01/02 ✅, 06/07 🟨, rest ⬜ |
| 2 | 25+ broken imports (crash by sys.path state) | 09, 25, 27d | ⬜ |
| 3 | 544 swallowed exceptions | 23 | ⬜ |
| 4 | Unbounded memory leaks (OOM in 24/7) | 18, 17 | 18 ✅, 17 🟨 |
| 5 | SQLite concurrency corruption under load | 17 | 🟨 (episodic done; 11+ todo) |
| 6 | 35 divergent duplicate files | 21, 22, 27 | ⬜ |
| 7 | 8 stub files (semantic, planner, reasoning core) | 26 | ⬜ |

This remediation plan closes all 7. The single biggest score levers are the
Security cluster and SQLite concurrency (see [SCORECARD.md](./SCORECARD.md)).

## Issue summary (from audit)

| Severity | core/ | vectorcode/src (11 subdirs) | vectorcode/src (tools+cli+channels) | districts+tests |
|----------|-------|------------------------------|--------------------------------------|------------------|
| CRITICAL | 6 | 6 | 7 | 6 |
| HIGH | 10 | 11 | 13 | 12 |
| MEDIUM | 12 | 10 | 13 | 25+ |
| LOW | 11 | 6 | 6 | — |
| TOTAL | 39 | 33 | 39 | 43+ |

LOC: ~14.45M incl. node_modules; ~891,738 excluding node_modules.

**Baseline scores** (see [SCORECARD.md](./SCORECARD.md)): Code Quality 38/100,
JARVIS Closeness 42/100. Weighted levers: Security (25/100) and Production
Readiness (20/100) are the lowest — prioritize those issue groups.

## Top 25 (Critical + High) — tracker

### Security
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [01](./issue-01-mcp-path-traversal.md) | Path traversal in MCP memory_export/import | mcp_server.py:1052 | ✅ resolved (hardening Task 02) — re-verify |
| [02](./issue-02-unauth-memory-clear.md) | Unauthenticated memory_clear | mcp_server.py:1039 | ✅ resolved (hardening Task 02) — re-verify |
| [03](./issue-03-eval-exec-untrusted.md) | eval()/exec() on untrusted code | tools/skills_guard.py, vc_tools/templates/loader.py:92 | ⬜ todo |
| [04](./issue-04-shell-injection-blocklist.md) | Bypassable shell-injection sanitization | templates/loader.py:116 | ⬜ todo |
| [05](./issue-05-bypassable-sandboxes.md) | Bypassable code sandboxes | vc_tools/repl.py, code_interpreter.py | ⬜ todo |
| [06](./issue-06-hardcoded-secrets.md) | Hardcoded secrets (SUDO_PASSWORD, HMAC, Flask) | terminal_tool.py, webhook.py, districts/ | 🟨 partial (social-sim done Task 05; SUDO/HMAC todo) |
| [07](./issue-07-brain-server-auth.md) | Auth bypass on brain server | districts/ cloud API | 🟨 partial (comms done Task 04; brain server needs-verify) |
| [08](./issue-08-tokens-in-cli-args.md) | Tokens in CLI args | slack_daemon.py:147 | ⬜ todo |

### Stability
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [09](./issue-09-broken-core-imports.md) | 25+ broken `core.*` bare imports | vc_system/, vc_agents/, channels/ | ⬜ todo |
| [10](./issue-10-rust-bridge-wrong-package.md) | vector._rust_bridge wrong package | shell_exec.py:139, sqlite.py:46 | ⬜ todo |
| [11](./issue-11-sqlite-unreachable-code.md) | sqlite.py unreachable code (NameError) | sqlite.py | ⬜ todo |
| [12](./issue-12-sysexit-at-import.md) | sys.exit(1) at module import | nexa_shim.py:31 | ⬜ todo |
| [13](./issue-13-raise-importerror-module-level.md) | raise ImportError at module level | apple_fm_shim.py:26 | ⬜ todo |
| [14](./issue-14-terminal-tool-logger-docstring.md) | logger NameError (docstring) | terminal_tool.py | ⬜ todo |
| [15](./issue-15-timeouterror-shadows-builtin.md) | TimeoutError shadows builtin | core/errors.py:56 | ⬜ todo |

### Concurrency
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [16](./issue-16-sense-cache-thread-unsafe.md) | Thread-unsafe _SENSE_CACHE dict | context_engine.py:9 | ⬜ todo |
| [17](./issue-17-sqlite-no-locking.md) | 12+ SQLite conns check_same_thread=False, no locking | many | 🟨 partial (episodic done Task 07; 11+ todo) |
| [18](./issue-18-unbounded-lists.md) | Unbounded in-memory lists | point_system._logs, loop_guard._recent_calls | ✅ resolved (hardening Task 07) — re-verify |
| [19](./issue-19-spawned-agents-not-threadsafe.md) | _SPAWNED_AGENTS dict not thread-safe | agent_tools.py:32 | ⬜ todo |
| [20](./issue-20-sync-httpx-in-async.md) | Sync httpx.Client in async stream() | _openai_compat.py:119, ollama.py:181 | ⬜ todo |

### Architecture
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [21](./issue-21-system-vc-system-duplicate.md) | system/ vs vc_system/ divergent duplicates | 7 files each | ⬜ todo |
| [22](./issue-22-tools-vc-tools-duplicate.md) | tools/ vs vc_tools/ divergent duplicates | 8+ files | ⬜ todo |
| [23](./issue-23-bare-except.md) | 544 bare `except Exception` | repo-wide | ⬜ todo |
| [24](./issue-24-mcp-monolith.md) | mcp_server.py 3,920-line monolith | mcp_server.py | ⬜ todo |
| [25](./issue-25-syspath-hacks.md) | sys.path.insert hacks | 3+ instances | ⬜ todo |

### Completeness / Stubs
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [26](./issue-26-stub-files.md) | Stub / not-implemented files (8 items) | planner, semantic, reasoning_memory, vc_skills, digest_evaluator, imessage, finagent | ⬜ todo — core ones (semantic.search, reasoning retrieve) HIGH |

### Duplicate code
| # | Issue | Source (audit) | Status |
|---|-------|----------------|--------|
| [27](./issue-27-duplicate-code.md) | Duplicate code (6 pairs) | system/vc_system (→21), tools/vc_tools (→22), storage, telemetry shims, **SecurityBlockError isinstance break**, *_manage CRUD | ⬜ todo — 27e SecurityBlockError is a correctness bug (HIGH) |

## More issues
Additional issues (MEDIUM/LOW and other batches) will be appended here and as
new `issue-NN-*.md` files as they are shared.
