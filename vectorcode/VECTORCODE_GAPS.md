# VectorCode — Implementation Gaps vs. Source Agent A & Source Agent B

**Project root:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\`
**Python source:** `vectorcode/python/vectorcode/`
**Reference repos:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\`

Current overall implementation: **~25% complete** across both Source Agent A and Source Agent B absorption.

---

## PRIORITY 1 — HIGH IMPACT (Missing Core Features)

### 1.1 source-a Tool System (port 60+ missing tools)

Reference: `GitHub\NousResearch_source-a-agent\repo\tools\`

**Already ported:** file_tools.py, bash_tools.py, git_tools.py, browser_tools.py (basic), web_tools.py, code_graph.py, autonomous.py (basic spawn)

**Missing — port these from source-a:**
- **Sandboxed code execution** — source-a has `tools/code_execution.py` with Docker/Python sandbox. Port to `tools/code_execution.py`
- **MCP client tool** — source-a has `tools/mcp_tool.py` that connects to external MCP servers. Port to `tools/mcp_tool.py` using `@modelcontextprotocol/sdk`
- **SSH/Docker backend** — source-a has `tools/terminal.py` with SSH and Docker exec backends. Port to `tools/terminal.py`
- **Image generation** — source-a has `tools/image_gen.py` supporting Replicate, ComfyUI, local diffusers. Port to `tools/image_gen.py`
- **TTS / STT** — source-a has `tools/audio.py`. Port to `tools/audio.py`
- **Cron/scheduling** — source-a has `tools/cron.py`. Port to `tools/cron.py`
- **Discord connector** — source-a has `tools/discord_tool.py`. Port to `comms/discord_bot.py`
- **Checkpoint/restore** — source-a has `tools/checkpoint.py` for snapshotting workspace state. Port to `tools/checkpoint.py`
- **Delegate tool improvements** — Current `autonomous.py` is basic. Upgrade to match source-a' `tools/delegate.py` with proper sub-agent communication

### 1.2 Trajectory Compression Pipeline

Reference: `GitHub\NousResearch_source-a-agent\repo\trajectory_compressor.py`

**Current state:** `repl.py::_compress_history()` and `context/compactor.py` — simple truncation only.

**Port source-a' full compressor:**
- Token-budget-aware compression (not char-count-based)
- LLM-based summarization of middle turns (source-a uses the model itself)
- Head/tail protection (always keep first N and last N turns)
- Metrics collection (tokens saved, compression ratio)
- Async execution so compression doesn't block the REPL
- Replace `context/compactor.py` with the full port

### 1.3 Context Engine & Prompt Caching

Reference: `GitHub\NousResearch_source-a-agent\repo\agent\context_engine.py`, `agent\prompt_cacher.py`

**Missing entirely.** Current code just appends to a message list.

**Port:**
- `context/engine.py` — ContextEngine with token budgeting, sliding window, priority-based retention
- `context/prompt_cache.py` — LRU cache for frequent system prompt prefixes, VECTOR.md sections

### 1.4 Error Classifier & Retry Logic

Reference: `GitHub\NousResearch_source-a-agent\repo\agent\errors.py`, `agent\retry.py`

**Current:** No structured error handling. Ollama errors just print and return.

**Port:**
- `providers/errors.py` — ErrorClassifier (rate_limit, auth, timeout, server_error, context_window, etc.)
- `providers/retry.py` — RetryHandler with exponential backoff, jitter, max_retries per error type

---

## PRIORITY 2 — MEDIUM IMPACT (Features Users Notice)

### 2.1 Gateway System (Multi-Platform Messaging)

Reference: `GitHub\NousResearch_source-a-agent\repo\gateway\`

**Current:** Only `comms/telegram_bot.py` (basic long-polling).

**Port from source-a gateway/ directory:**
- `comms/discord_bot.py` — Discord gateway with slash commands
- `comms/slack_bot.py` — Slack RTM/Events API
- `comms/webhook_server.py` — Generic webhook receiver (FastAPI)
- `comms/email_client.py` — IMAP/SMTP for email
- `comms/session_manager.py` — Cross-platform session state

### 2.2 Personality System

Reference: `GitHub\NousResearch_source-a-agent\repo\agent\personalities\`

**Missing entirely.** source-a has 12 built-in personalities.

**Port:**
- `persona/personalities.py` — Loadable personality profiles (professional, pirate, mentor, etc.)
- Each personality = system prompt override + style params + verbosity settings
- CLI flag: `vector --personality mentor repl`

### 2.3 Agent YAML Configs + Runtime Agent Registry

Reference: `GitHub\ruvnet_Source Agent B\repo\agents\` (YAML files), `agent_types.py`

**Current:** 62 agent types hardcoded as factory classes in `agent_types.py`. No runtime registration.

**Port from Source Agent B:**
- `agents/registry.py` — Runtime agent registry (register/list/get by name)
- `agents/loader.py` — Load agent definitions from `.yaml` or `.toml` files
- `agents/definitions/` — Directory of agent YAML configs (one per type)
- Replace hardcoded `agent_types.py` with registry-based loading

### 2.4 Git Worktree Isolation

Reference: `GitHub\NousResearch_source-a-agent\repo\agent\worktree.py`

**Missing entirely.** source-a creates isolated git worktrees for risky operations.

**Port:**
- `tools/worktree.py` — `create_worktree()`, `destroy_worktree()`, `diff_between_worktrees()`
- Integration with permission system — RED-gated operations auto-create worktree

### 2.5 Shell Hooks & Environment Detection

Reference: `GitHub\NousResearch_source-a-agent\repo\source-a_constants.py`

**Current:** No shell integration.

**Port:**
- `hooks/shell_hooks.py` — Shell prompt hooks (zsh/bash), pre-execution validation
- `config/env_detector.py` — Detect Termux/WSL/Container/Docker and adjust paths

---

## PRIORITY 3 — LOWER IMPACT (Nice-to-Have)

### 3.1 Reasoning Tag Stripper
From source-a: Strip  thinking... tags from model output before displaying. Port to `utils/reasoning_stripper.py`

### 3.2 Skills Sync & Hub
From source-a: `vector skills sync` and `vector skills install <hub-url>` for community skills. Currently skills are just scanned from `~/.claude/skills/`. Port to `vector code skills sync`

### 3.3 Toolset Filtering
From source-a: Enable/disable tool categories at runtime. `vector tools enable code` / `vector tools disable browser`. Port to `tools/registry.py`

### 3.4 Session Export (Markdown/HTML)
From source-a: `vector sessions export <id> --format markdown`. Current export is JSON only.

### 3.5 Bash Completion
From source-a: Shell completion scripts. Generate `_vector` completion for bash/zsh.

### 3.6 ACP Protocol Adapter
From source-a `acp_adapter/` and `acp_registry/`: Agent Communication Protocol. Not started.

### 3.7 Source Agent B v3 Architecture
From Source Agent B `v3/`: Modular agent lifecycle, coordinated execution, infrastructure layer. Not started.

---

## FILE-BY-FILE MIGRATION PLAN

### source-a → VectorCode files to create:

```
vectorcode/python/vectorcode/
├── tools/code_execution.py     → port from source-a tools/code_execution.py
├── tools/mcp_tool.py           → port from source-a tools/mcp_tool.py  
├── tools/terminal.py           → port from source-a tools/terminal.py
├── tools/image_gen.py          → port from source-a tools/image_gen.py
├── tools/audio.py              → port from source-a tools/audio.py
├── tools/cron.py               → port from source-a tools/cron.py
├── tools/checkpoint.py         → port from source-a tools/checkpoint.py
├── tools/worktree.py           → port from Source Agent A/worktree.py
├── tools/delegate.py           → upgrade from autonomous.py
├── context/engine.py           → port from Source Agent A/context_engine.py
├── context/prompt_cache.py     → port from Source Agent A/prompt_cacher.py
├── providers/errors.py         → port from Source Agent A/errors.py
├── providers/retry.py          → port from Source Agent A/retry.py
├── comms/discord_bot.py        → port from source-a gateway/discord/
├── comms/slack_bot.py          → port from source-a gateway/slack/  
├── comms/webhook_server.py     → port from source-a gateway/webhook/
├── comms/email_client.py       → port from source-a gateway/email/
├── comms/session_manager.py    → port from source-a gateway/session.py
├── persona/personalities.py    → port from Source Agent A/personalities/
├── agents/registry.py          → new, runtime agent registry
├── agents/loader.py            → new, YAML agent loader
├── agents/definitions/         → directory of agent .yaml files
├── utils/reasoning_stripper.py → port from source-a
├── hooks/shell_hooks.py        → port from source-a
├── config/env_detector.py      → port from source-a source-a_constants.py
└── trajectory_compressor.py    → replace current context/compactor.py with full port
```

### Existing files that need upgrades:

```
context/compactor.py    → replace with full source-a trajectory_compressor.py port
autonomous.py           → upgrade delegate to source-a tools/delegate.py quality
repl.py                 → add reasoning tag stripping, personality loading
```

---

## QUICK START

```bash
# Reference repos
cd C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\NousResearch_source-a-agent\repo
cd C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ruvnet_Source Agent B\repo

# VectorCode source
cd C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\python\vectorcode

# Run self-tests after each port:
python repl.py
python session.py
python config.py
```

Start with Priority 1. Each port should preserve the original license headers and credit the source repository.

