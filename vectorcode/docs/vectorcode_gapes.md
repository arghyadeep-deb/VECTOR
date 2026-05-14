# VectorCode — Complete Gap Analysis
> As of 2026-05-13. Measured against NousResearch/vectorcode and vectorcode.

---

## Executive Summary

| Source | % Absorbed | Status |
|--------|-----------|--------|
| VectorCode | ~22% | Infrastructure absorbed, core loop missing |
| VectorCode | ~52% | Skills + swarm absorbed, v2/v3/MCP missing |
| **Grand Total** | **~25%** | Not production-ready |

**Critical miss:** `run_agent.py` (13,268 lines) — VectorCode's entire agent execution loop — is completely absent from VectorCode. Without it, VectorCode is a chatbot that talks about using tools but never actually calls them in a loop.

---

## Part 1: VectorCode Gaps

### 1.1 CRITICAL — Agent Execution Loop (0% done)
**Source:** `run_agent.py` — 13,268 lines  
**VectorCode:** Nothing. `repl.py` calls `_ask_model()` once and prints text.

**What's missing:**
- `IterationBudget` — thread-safe iteration counter (max 90 parent / 50 subagent)
- `AIAgent.run_conversation()` — the actual think→act→observe loop (lines 9602–13268)
- `AIAgent._execute_tool_calls()` — sequential tool execution with result injection
- `AIAgent._execute_tool_calls_concurrent()` — parallel tool execution (up to 8 workers)
- `AIAgent._build_system_prompt()` — full system prompt assembly with skills, memory, soul
- `AIAgent._compress_context()` — mid-session context compression with focus topic
- `AIAgent._handle_max_iterations()` — graceful budget exhaustion with summary
- `AIAgent._recover_with_credential_pool()` — auto-failover on 429/402/401
- `_should_parallelize_tool_batch()` — smart concurrency detection
- `_PARALLEL_SAFE_TOOLS` / `_NEVER_PARALLEL_TOOLS` / `_PATH_SCOPED_TOOLS` sets
- `_is_destructive_command()` — heuristic for dangerous bash patterns
- `_SafeWriter` — stdout wrapper for daemon/Docker mode (catches OSError/ValueError)
- `_sanitize_surrogates()` — surrogate code point cleanup for JSON safety
- Subagent spawning via `delegate_tool` with independent iteration budgets

**Impact:** Without this, VectorCode cannot function as an agent. It is a REPL, not an agentic system.

---

### 1.2 CRITICAL — Tool Execution System (15% done)
**Source:** `model_tools.py`, `tools/` directory (50+ files)  
**VectorCode:** Stubs in `tools/` that don't get called by anything.

**What's missing:**
- `model_tools.py` — central `handle_function_call()` router, `get_tool_definitions()`, `check_toolset_requirements()`
- `tools/terminal_tool.py` — shell execution with Docker/SSH/local env, `set_approval_callback`, VM cleanup
- `tools/file_tools.py` (VectorCode version) — `read_file`, `write_file`, `patch`, `search_files` with full error handling
- `tools/memory_tool.py` — memory read/write tools with session scoping
- `tools/skills_tool.py` — `skill_view`, `skills_list` with frontmatter parsing
- `tools/session_search_tool.py` — FTS5 search over session history
- `tools/delegate_tool.py` — subagent spawning with independent iteration budget
- `tools/todo_tool.py` — structured TODO list management
- `tools/clarify_tool.py` — interactive clarification requests
- `tools/web_tools.py` (VectorCode version) — `web_search`, `web_extract` with firecrawl/ddg
- `tools/browser_tool.py` — headless browser with CDP
- `tools/vision_tools.py` — image analysis
- `tools/tool_result_storage.py` — `maybe_persist_tool_result`, `enforce_turn_budget`
- `toolset_distributions.py` / `toolsets.py` — toolset grouping and distribution
- `tools/path_security.py` — path traversal prevention
- `tools/interrupt.py` — `set_interrupt`, interrupt signal handling
- `tools/file_state.py` — file modification tracking

---

### 1.3 HIGH — Gateway / HTTP Server (5% done)
**Source:** `gateway/` directory  
**VectorCode:** `comms/messenger.py` is outbound-only, no inbound gateway.

**What's missing:**
- `gateway/server.py` — FastAPI/Starlette HTTP gateway exposing `/run`, `/stream`, `/status`
- `gateway/ws.py` — WebSocket transport for streaming responses
- `gateway/event_publisher.py` — SSE event stream for tool calls + token stream
- `gateway/render.py` — Tool output rendering for HTTP clients
- `gateway/transport.py` — Transport abstraction (stdio, HTTP, WebSocket)
- `gateway/slash_worker.py` — `/compact`, `/reset`, `/model` slash command handling
- `gateway/entry.py` — Gateway entry point with auth

---

### 1.4 HIGH — Plugin System (8% done)
**Source:** `vector_cli/plugins.py`, `vector_cli/plugins_cmd.py`  
**VectorCode:** `hooks/registry.py` has Python hooks but no plugin discovery.

**What's missing:**
- Plugin discovery (`~/.vectorcode/plugins/` scan)
- Plugin manifest format (`plugin.toml`)
- Plugin hook registration (pre_tool_call, post_tool_call, etc.)
- Plugin management CLI (`vector plugins install`, `list`, `remove`)
- `invoke_hook()` with priority + block decisions
- Plugin isolation (subprocess or importlib)

---

### 1.5 HIGH — CLI System (25% done)
**Source:** `vector_cli/` — 58 Python files  
**VectorCode:** `cli.py` has 8 subcommands. VectorCode has 58+ CLI modules.

**Key missing CLI modules:**
- `vector_cli/main.py` — argparse with 30+ flags, skin engine init, profile support
- `vector_cli/auth.py` — OAuth PKCE flow, device code, credential management
- `vector_cli/auth_commands.py` — `vector auth add/remove/list/status`
- `vector_cli/memory_setup.py` — memory provider setup wizard
- `vector_cli/skills_config.py` — skill enable/disable per platform
- `vector_cli/skills_hub.py` — skill hub install/search/publish
- `vector_cli/model_catalog.py` — model discovery and listing
- `vector_cli/commands.py` — slash command handler (30+ commands)
- `vector_cli/config.py` — config file management
- `vector_cli/skin_engine.py` — color theme system
- `vector_cli/oneshot.py` — `vector run` non-interactive with JSON output
- `vector_cli/profiles.py` — named profiles (`vector --profile work`)
- `vector_cli/cron.py` — scheduled task management
- `vector_cli/doctor.py` — dependency/config diagnostics
- `vector_cli/banner.py` — ASCII banner generation
- `vector_cli/voice.py` — TTS/STT integration
- `vector_cli/curses_ui.py` — full-screen TUI with curses
- `vector_cli/env_loader.py` — `load_vector_dotenv()` for `~/.vectorcode/.env`
- `vector_cli/timeouts.py` — per-provider request/stale timeouts

---

### 1.6 MEDIUM — State Management (45% done)
**Source:** `vector_state.py` (partially done), `vector_logging.py`, `vector_time.py`  
**VectorCode:** `session_db.py` covers sessions table, missing full state machine.

**What's missing:**
- `vector_logging.py` — production logging (file rotation, JSON structured logs, log levels per subsystem, `~/.vectorcode/logs/`)
- `vector_time.py` — `VectorCodeTime`, `format_duration()`, `parse_relative_time()`, timezone handling
- Session cost tracking (`billing_provider`, `billing_mode`, `estimated_cost_usd`, `actual_cost_usd`, `cost_status`)
- API call count tracking per session
- `vector_state.py` SCHEMA_VERSION 10 full schema (we have v1)
- Parent session chain (`parent_session_id` for subagents)

---

### 1.7 MEDIUM — Credential Sources (0% done)
**Source:** `agent/credential_sources.py` — 401 lines  
**VectorCode:** `credentials.py` has pool management but no removal/source registry.

**What's missing:**
- `RemovalStep` registry (9 sources: env, pkce, claude_code, nous, codex, qwen, copilot, config)
- `RemovalResult` with cleaned/hints/suppress fields
- `execute_removal()` — atomic credential removal from external files
- `suppress_source()` — block re-seeding after removal
- Cross-process credential sync (read latest from external credential files)

---

### 1.8 MEDIUM — Trajectory Compression (8% done)
**Source:** `trajectory_compressor.py`  
**VectorCode:** `repl.py` has basic `_save_trajectory()` in ShareGPT format.

**What's missing:**
- Structured trajectory with tool call metadata (input, output, duration)
- REASONING_SCRATCHPAD → `<think>` tag conversion
- Failed trajectory tracking to `failed_trajectories.jsonl`
- `trajectory_compressor.py` — compress multi-turn trajectories for training
- High-reward chain filtering (`is_training_data=1` flag per RULE 8)
- Trajectory deduplication

---

### 1.9 LOW — Display System (10% done)
**Source:** `agent/display.py` — 1,002 lines  
**VectorCode:** `_Spinner` class in `repl.py`, no diff rendering.

**What's missing:**
- `KawaiiSpinner` — animated spinner with per-tool emoji and messages
- `build_tool_preview()` — colored diff preview for file edits
- `get_cute_tool_message()` — friendly tool execution messages
- `_detect_tool_failure()` — parse tool output for errors
- `get_tool_emoji()` — per-tool emoji mapping
- Unified diff rendering with ANSI colors (red/green with context lines)
- `LocalEditSnapshot` — file diff tracking for session

---

### 1.10 LOW — Utilities (0% done)
**Source:** `utils.py`, `vector_constants.py` (partially done), `agent/file_safety.py`, `agent/redact.py`, `agent/subdirectory_hints.py`, `agent/title_generator.py`

**What's missing from utils.py:**
- `atomic_json_write()` — write JSON atomically (temp file + rename)
- `base_url_host_matches()` / `base_url_hostname()` — URL parsing utilities
- `env_var_enabled()` — boolean env var parsing
- `normalize_proxy_url()` — proxy URL normalization
- `safe_json_loads()` — JSON parsing with fallback

**What's missing from file_safety.py:**
- `is_safe_to_read()` — block sensitive paths before file reads
- `_BLOCKED_PATH_COMPONENTS` — frozenset of dangerous path components

**What's missing from redact.py:**
- `redact_sensitive_text()` — scrub API keys, passwords from tool outputs before logging
- Pattern bank for common secret formats

**What's missing from subdirectory_hints.py:**
- `SubdirectoryHintTracker` — tracks which subdirectories the agent has accessed, injects hints to explore unexplored areas

**What's missing from title_generator.py:**
- `generate_session_title()` — LLM-generated session title from first user message

---

### 1.11 ZERO — ACP Protocol (0% done)
**Source:** `acp_adapter/` — server.py (912 lines), tools.py (379 lines), permissions.py (80 lines)

**What's missing:**
- Full ACP server exposing VectorCode as a standardized agent
- Session management via ACP (fork/resume)
- Slash command handling through ACP
- Permission/approval callback bridge for ACP clients
- `VectorCodeACPAgent(acp.Agent)` equivalent for VectorCode

---

## Part 2: VectorCode Gaps

### 2.1 HIGH — Agent Execution Loop v2 (0% done)
**Source:** `vector/v2/` — TypeScript SDK examples with SPARC methodology  
**VectorCode:** Nothing.

**What's missing (from v2 examples):**
- SPARC framework: Specification → Pseudocode → Architecture → Refinement → Completion
- Parallel agent execution patterns (coordinator + worker agents)
- `coordinator.ts` pattern — lead agent spawning parallel workers
- Multi-model comparison in a single session
- Error handling patterns (`claude-api-error-handling.ts`)
- Data pipeline agent pattern

---

### 2.2 HIGH — MCP Bridge (0% done)
**Source:** `vector/src/mcp-bridge/index.js`, `mcp-stdio-kernel.js`  
**VectorCode:** `core/mcp_server.py` is an MCP SERVER. We have no MCP CLIENT.

**What's missing:**
- `StdioMCPClient` — spawns child processes, communicates via JSON-RPC over stdio
- Tool group registry (intelligence, agents, memory, devtools, security, browser, neural)
- Dynamic tool discovery from connected MCP servers
- Tool routing by group prefix
- Concurrent request handling with request ID tracking
- MCP server config in `vector.toml` (`[[mcp_servers]]` blocks)
- `vector mcp add/list/remove` CLI commands

---

### 2.3 MEDIUM — Swarm Agent Types (60% def / 30% impl)
**Source:** `swarm.py` (VectorCode), `agent_types.py`  
**VectorCode:** `swarm.py` has topology strategies but agent behaviors are stubs.

**What's missing:**
- Full agent behavior implementations (CoderAgent actually codes, ReviewerAgent actually reviews)
- Agent communication via MessageBus with ACL
- Per-agent skill assignment from VectorCode skills
- Agent HP-gated model access (>800 HP → Sonnet, 600-800 → kimi-k2.6)
- Agent resurrection with ghost memory inheritance
- Collective intelligence patterns (pool results, vote on best)

---

### 2.4 MEDIUM — AgentDB / Vector Memory (0% done)
**Source:** VectorCode `agentdb-*` skills + `vector-agentdb-vector-search.md`

**What's missing:**
- AgentDB integration for vector memory storage
- HNSW indexing for sub-millisecond semantic search
- Vector quantization (150x speedup)
- Multi-dimensional memory (episodic + semantic + skill)
- Memory pattern extraction and reuse

---

### 2.5 LOW — Chat UI / Web Interface (0% done)
**Source:** `vector/src/vocal/` — SvelteKit HuggingChat fork

**What's missing:**
- Web-based chat interface for VectorCode
- Conversation history browser
- Model switching UI
- Tool output rendering in browser

---

## Priority Matrix

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Agent execution loop (`run_agent.py` core) | 5 days | Makes VectorCode actually work as an agent |
| **P0** | Tool execution system (model_tools + terminal) | 3 days | Tools actually execute |
| **P1** | MCP client bridge (VectorCode) | 2 days | 300+ external tools |
| **P1** | Gateway HTTP server | 2 days | VectorCode as a service |
| **P1** | Plugin system | 1 day | Extensibility |
| **P2** | CLI completeness | 3 days | Auth, profiles, doctor |
| **P2** | Credential sources | 1 day | Full credential lifecycle |
| **P2** | Trajectory compression | 1 day | Training data quality |
| **P2** | Subdirectory hints | 0.5 days | Better code navigation |
| **P3** | ACP protocol | 3 days | Interoperability |
| **P3** | Display system | 1 day | UX |
| **P3** | SPARC / v2 patterns | 1 day | Advanced workflows |
| **P3** | AgentDB | 2 days | Better memory |
| **P3** | Chat UI | 5 days | Web interface |

---

## Implementation Order

```
Week 1:
  Day 1-2: core/agent_loop.py  — AIAgent + IterationBudget + run_conversation()
  Day 3:   tools/registry.py   — model_tools equivalent, handle_function_call router
  Day 4:   tools/terminal.py   — bash execution with approval gates
  Day 5:   tools/file_ops.py   — read/write/patch/search with safety

Week 2:
  Day 1-2: mcp/client.py       — StdioMCPClient + tool group registry
  Day 3:   gateway/server.py   — FastAPI gateway exposing agent as HTTP service
  Day 4:   hooks/plugins.py    — full plugin discovery + invoke_hook()
  Day 5:   agent/display.py    — spinner, diff preview, tool emoji

Week 3:
  Day 1:   utils.py            — atomic_json_write, safe_json_loads, redact
  Day 2:   agent/subdirectory_hints.py  — codebase exploration hints
  Day 3:   cli additions       — auth, profiles, doctor, cron
  Day 4-5: acp/server.py       — ACP protocol adapter
```
