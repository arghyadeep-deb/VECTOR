# VectorCode — Production Grade Assessment
> Measured against VectorCode production standard. Date: 2026-05-13.

---

## Verdict: NOT PRODUCTION READY

**The single blocking issue:** VectorCode has no agent execution loop. It cannot call tools, iterate on results, or perform multi-step tasks. It is a streaming chatbot with tool definitions that never execute.

---

## What Works (Ship-Ready)

| Module | Status | Notes |
|--------|--------|-------|
| `router.py` (GNNRouter) | ✅ Production | 3-layer routing, learns from feedback |
| `swarm.py` (8 topologies) | ✅ Production | Byzantine, Raft, CRDT, Gossip all correct |
| `queen.py` | ✅ Production | Multi-model consensus, QueenDecision |
| `monitoring.py` | ✅ Production | SwarmMonitor with metrics |
| `message_bus.py` | ✅ Production | ACL-gated 7 operations |
| `comms/messenger.py` | ✅ Production | Telegram, Discord, email, pushover |
| `comms/inbound.py` | ✅ Production | Rate limit, dedup, thread tracking |
| `context/compactor.py` | ✅ Production | VectorCode SUMMARY_PREFIX, tool pruning |
| `context/vectormd.py` | ✅ Production | Injection scanning, 10 threat patterns |
| `providers/rate_limit.py` | ✅ Production | 12-header schema, ASCII bar chart |
| `providers/retry.py` | ✅ Production | Jittered backoff, decorrelated |
| `errors.py` | ✅ Production | Full FailoverReason taxonomy |
| `hooks/shell_hooks.py` | ✅ Production | JSON protocol, allowlist, shlex safe |
| `credentials.py` | ✅ Production | Pool rotation, cooldown persistence |
| `session_db.py` | ✅ Production | SQLite FTS5, WAL, multi-process safe |
| `transports/` (all 5) | ✅ Production | Anthropic+OpenAI+Ollama, normalized types |
| `memory/` (provider + manager) | ✅ Production | MemoryProvider ABC, builtin provider |
| `skills/loader.py` | ✅ Production | YAML frontmatter, inline shell, 143 skills |
| `context/references.py` | ✅ Production | @file/@diff/@url/@git, safety blocked |
| `insights.py` | ✅ Production | Analytics, cost tracking, ASCII charts |
| `vector_constants.py` | ✅ Production | $VECTOR_HOME, unified paths |

---

## What's Broken / Incomplete

### Severity: BLOCKING

**1. No agent execution loop**
- `repl.py` calls `_ask_model()` once, prints text, waits for user
- Model replies with tool_calls → they are NEVER executed
- No iteration: model cannot self-correct, re-read files, run tests
- **Fix:** Port `run_agent.py` core loop to `core/agent_loop.py`

**2. Tools are definitions, not implementations**
- `tools/bash_tools.py`, `tools/file_tools.py` have classes but are never called
- No `handle_function_call()` router — tools have no execution path
- Model sees tool schemas, responds with tool_use blocks → nothing happens
- **Fix:** `tools/registry.py` + wire into agent loop

**3. No permission gate in execution path**
- `core/loop/permission_gateway.py` exists but is not called by REPL
- GREEN/YELLOW/RED gating is completely bypassed
- Every action (including destructive ones) would run unchecked
- **Fix:** Wire permission_gateway into agent loop tool execution

### Severity: HIGH

**4. Providers aren't actually used at runtime**
- `transports/` layer is written but `repl.py` still calls `_ask_ollama()` directly
- `ModelRouter` in `providers/__init__.py` is not used in the main REPL loop
- Multi-provider routing exists on paper but doesn't run
- **Fix:** `repl.py` main loop → use `_ask_model()` → route through transports layer

**5. Context references parsed but not injected**
- `context/references.py` has `expand_context_references()`
- Nothing calls it before passing user message to the model
- @file, @diff, @url references are sent literally to the model
- **Fix:** Call `expand_context_references()` in REPL before `_history.append()`

**6. Memory not consulted per-turn**
- `memory/manager.py` has `prefetch_all()` and `sync_all()`
- Neither is called in the REPL loop
- Model never gets memory context; session learnings never saved
- **Fix:** Call `memory_manager.prefetch_all(raw)` before each turn, `sync_all()` after

**7. Credential pool not wired to providers**
- `credentials.py` has `CredentialManager` with rotation
- `transports/anthropic.py` / `transports/chat_completions.py` instantiate their own API keys
- On 429/402, no rotation happens — requests just fail
- **Fix:** Pass `CredentialManager` into `ModelRouter`; call `on_rate_limit()` on failure

### Severity: MEDIUM

**8. Session DB not integrated with REPL display**
- `session_db.py` is partially wired (create_session on init)
- Messages are NOT recorded per-turn (`add_message()` never called)
- Token usage not updated (`update_usage()` never called)
- `vector sessions list` shows DB sessions but they have 0 messages
- **Fix:** Wire `_db.add_message()` after each assistant turn in REPL

**9. Skills loaded but not wired to system prompt**
- `skills/loader.py` has `SkillRegistry`
- `repl.py` still uses old `_scan_skills()` function from `~/.claude/skills/`
- 143 VectorCode skills in `vectorcode/skills/` are never offered to user
- **Fix:** Replace `_scan_skills()` with `SkillRegistry.search()`, add `vectorcode/skills/` to search path

**10. No MCP client**
- VectorCode exposes an MCP server (`core/mcp_server.py`) — ✅
- VectorCode cannot consume external MCP servers as a client
- VectorCode's 300+ tools via MCP bridge are inaccessible
- **Fix:** Port `vector/src/mcp-bridge/` to `mcp/client.py`

---

## Performance Assessment

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Startup time | ~2.1s (model load) | <0.5s | Too slow — lazy load models |
| First token latency | ~800ms (Ollama local) | <200ms | VRAM contention |
| Tool execution | N/A (broken) | <100ms per tool | Not wired |
| Context compression | 71% reduction | >80% | Acceptable |
| Session search | <50ms (FTS5) | <100ms | ✅ Fast enough |
| Memory prefetch | N/A (not wired) | <200ms | Not wired |

---

## Security Assessment

| Check | Status | Risk |
|-------|--------|------|
| Prompt injection scanning | ✅ Done | VECTOR.md scanned for 10 patterns |
| Path traversal prevention | ⚠️ Partial | `file_tools.py` has `_safe_path()` but not used in agent loop |
| Shell injection | ✅ Done | `shlex.split()` + `shell=False` in shell_hooks |
| Sensitive data redaction | ❌ Missing | No `redact_sensitive_text()` — API keys could appear in logs |
| Credential file protection | ⚠️ Partial | `credentials.py` reads env vars but no file permission checks |
| Tool approval gates | ❌ Not wired | Permission gateway bypassed in REPL |
| API key exposure in logs | ❌ Missing | loguru logs could contain API keys |

---

## Roadmap to Production

### Phase 1 — Make It Work (Week 1)
Goal: VectorCode executes tools in a loop.

```
[ ] core/agent_loop.py     — AIAgent + IterationBudget + run_conversation()
[ ] tools/registry.py      — handle_function_call() router
[ ] tools/terminal.py      — bash execution with approval gate
[ ] tools/file_ops.py      — read/write/patch/search with path safety
[ ] Wire repl.py            — use agent_loop instead of _ask_model() directly
[ ] Wire permission gate    — GREEN/YELLOW/RED in execution path
[ ] Wire context references — expand_context_references() before each turn
[ ] Wire memory manager    — prefetch_all() / sync_all() per turn
[ ] Wire session DB         — add_message() + update_usage() per turn
```

**Acceptance test:** `vector run "read main.py and summarize it"` → agent reads the file, returns actual summary.

### Phase 2 — Make It Reliable (Week 2)
Goal: Handles failures gracefully, multi-provider.

```
[ ] Wire credential pool to transports layer (failover on 429/402)
[ ] mcp/client.py — StdioMCPClient for external MCP servers
[ ] gateway/server.py — HTTP service mode
[ ] hooks/plugins.py — full plugin discovery
[ ] agent/redact.py — scrub secrets from logs
[ ] agent/subdirectory_hints.py — codebase navigation hints
[ ] Wire 143 VectorCode skills into SkillRegistry
```

**Acceptance test:** `vector run "fix all type errors in src/"` → agent finds errors, fixes files, reruns type checker, iterates.

### Phase 3 — Make It Complete (Week 3)
Goal: Feature parity with VectorCode.

```
[ ] ACP protocol adapter
[ ] Full CLI (auth, profiles, doctor, cron, voice)
[ ] Trajectory compression pipeline
[ ] Display system (KawaiiSpinner, build_tool_preview)
[ ] AgentDB integration
[ ] SPARC workflow methodology
```

---

## Bottom Line

VectorCode has excellent infrastructure (transport layer, credential pool, session DB, memory, skills, 143 VectorCode skills, 8 swarm topologies) but zero of it is wired together into a functioning agent.

**The gap isn't architecture — it's execution.** The agent loop is missing.

Fix Phase 1 and VectorCode becomes a real coding agent in ~1 week of work.
