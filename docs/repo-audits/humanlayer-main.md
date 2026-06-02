# humanlayer-main Audit

## 1. Repo Reality

HumanLayer has pivoted from a Python approval SDK to **CodeLayer** — an open-source AI coding IDE (Tauri + React desktop app) and orchestration layer for Claude Code sessions. The original Python/TypeScript HumanLayer SDK (which VECTOR already integrated) was removed in PR #646. What remains is: a Go daemon (`hld`) that manages approval sessions and Claude Code process orchestration, a TypeScript MCP server (`hlyr`) bridging Claude Code ↔ hld, a Tauri desktop UI (`humanlayer-wui`/CodeLayer), a Go client library (`claudecode-go`), and legacy contract/database TypeScript packages.

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| HumanLayer approval for RED actions | `core/loop/permission_gateway.py` lines 19-28 | `humanlayer in gateway: 19:# HumanLayer — RED-tier enforcement (RULE 3, VECTOR_FIT.md: critical) 21: from humanlayer import HumanLayer as _HumanLayer 22: _hl = _HumanLayer()` — import wired, falls back to asyncio.Event when SDK not pip-installed | COVERED (fallback active) |
| Human-in-the-loop approval flow | `core/loop/permission_gateway.py` — RED tier with `asyncio.wait_for` timeout → reject | Verified: timeout now raises `asyncio.TimeoutError` → returns `False` | COVERED |
| Council deliberation before RED | `districts/governance/llm_council.py` | Council gate HP>700 confirmed in phase_status.md | COVERED |

**Verification output (exact):**
```
humanlayer in gateway: 19:# HumanLayer — RED-tier enforcement (RULE 3, VECTOR_FIT.md: critical)
21:    from humanlayer import HumanLayer as _HumanLayer
22:    _hl = _HumanLayer()
24:    logger.info("[VECTOR][gateway] HumanL
```
Runtime note: `HumanLayer not installed — using asyncio Event fallback for RED` — the SDK is imported at runtime but `pip install humanlayer` has not been run. The fallback is functional.

### What humanlayer-main has that VECTOR does NOT

- **`hld` Go daemon** — persistent local approval daemon with SQLite state, managing multiple concurrent Claude Code sessions and routing approval requests. VECTOR's gateway is in-process; it does not have a persistent out-of-process approval daemon
- **`hlyr` MCP server** — TypeScript MCP server that bridges `claude code` ↔ `hld` via JSON-RPC, enabling multi-session orchestration from a single daemon. VECTOR has `core/mcp_server.py` but it is a different purpose (VECTOR tools), not a multi-session claude orchestrator
- **`claudecode-go`** — Go SDK for programmatically spawning, monitoring, and killing Claude Code sessions. VECTOR has no equivalent session manager for Claude Code itself
- **CodeLayer UI (`humanlayer-wui`)** — Tauri + React desktop app showing pending approvals as rich cards (tool name, params, context diff) with keyboard shortcuts. VECTOR has no graphical approval UI
- **Multi-session orchestration** — `hld` can run 10+ parallel Claude Code sessions with shared approval routing. VECTOR runs single-session

---

## 3. Frontend

N/A for VECTOR's primary use case. CodeLayer's Tauri UI is a standalone desktop app and does not share components with VECTOR's planned Next.js dashboard.

---

## 4. Verdict

**PATCH — install the Python SDK, keep the repo for reference**

Action: `pip install humanlayer` in VECTOR's `.venv` to activate the live HumanLayer approval path (currently using asyncio fallback). The Python SDK itself was removed from this repo in PR #646 and is now published to PyPI separately — `pip install humanlayer` pulls from PyPI, not this repo.

The Go components (`hld`, `hlyr`, `claudecode-go`) and CodeLayer UI are genuinely novel capabilities that VECTOR does not have. However, they are TypeScript/Go and solve a different problem (orchestrating Claude Code sessions for a team) rather than VECTOR's own autonomous loop approval. They should not be absorbed.

---

## 5. Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| `pip install humanlayer` activation | HIGH | Run `pip install humanlayer` in `.venv`. This activates the live HumanLayer approval API (Slack/email/web approval channels) instead of the current asyncio.Event fallback. One command, zero code changes. |
| Graphical approval UI | Low | CodeLayer's Tauri app shows rich approval cards. VECTOR's planned Next.js dashboard could add an `/approvals` panel for pending RED actions. Low priority until cloud deploy is done. |
| Persistent approval daemon | Low | `hld` survives VECTOR restarts and queues approvals. VECTOR's current in-process gateway loses pending approvals on restart. Solvable by persisting `_pending_events` to SQLite in `permission_gateway.py`. |
