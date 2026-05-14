# Vector Code — Product Specification

> **Version:** 0.1.0-draft  
> **Status:** Pre-development  
> **Tagline:** Your terminal. Any model. Full agency.

---

## Table of Contents

1. [Vision & Philosophy](#1-vision--philosophy)
2. [Core Differentiators](#2-core-differentiators)
3. [System Architecture](#3-system-architecture)
4. [Model Provider System](#4-model-provider-system)
5. [Agentic Loop](#5-agentic-loop)
6. [Tool System](#6-tool-system)
7. [Permission & Safety System](#7-permission--safety-system)
8. [Context & Memory System](#8-context--memory-system)
9. [Terminal UI (TUI)](#9-terminal-ui-tui)
10. [Configuration System](#10-configuration-system)
11. [Extensibility — MCP & Plugins](#11-extensibility--mcp--plugins)
12. [CLI Reference](#12-cli-reference)
13. [Session Management](#13-session-management)
14. [Multi-Agent Architecture](#14-multi-agent-architecture)
15. [Technology Stack](#15-technology-stack)
16. [File & Directory Structure](#16-file--directory-structure)
17. [Roadmap](#17-roadmap)
18. [Competitive Positioning](#18-competitive-positioning)

---

## 1. Vision & Philosophy

Vector Code is a **terminal-native, model-agnostic agentic coding tool**. It operates at the project level — reading codebases, planning changes across multiple files, executing shell commands, running tests, and iterating on failures — all without locking you into a single AI provider.

### Core Principles

| Principle | Meaning |
|-----------|---------|
| **Model Freedom** | Use any local model (Ollama, LM Studio) or any cloud API (Anthropic, OpenAI, Google, Mistral, Groq, etc.) |
| **Terminal First** | Lives in your shell. Composable with pipes, CI/CD, scripts, and Unix tools. |
| **Transparent Agency** | Every action is visible. The agent never acts silently — it explains, then executes. |
| **Human in the Loop** | You approve risky actions. Autonomy is a dial, not a default. |
| **Minimal Setup** | One binary. Works in your existing environment with your existing tools. |
| **Open & Extensible** | MCP protocol support, plugin system, hooks, custom agents. |

---

## 2. Core Differentiators

### vs. Claude Code
- **Not locked to Anthropic.** Run the same agentic workflows with GPT-5, Gemini 2.5, local Llama 4, Mistral, or any provider.
- **Fully open source** — inspect, fork, and contribute.
- **No subscription required.** Bring your own API key or run 100% locally for free.

### vs. OpenCode
- **Richer TUI** with split-pane file diff preview, inline tool output rendering, and interactive approval dialogs.
- **VECTOR.md** project config file (like Claude Code's CLAUDE.md) with deeper auto-memory and session recall.
- **Built-in sub-agent orchestration** with a planner agent that delegates to worker agents.
- **First-class local model support** with automatic model capability detection (context window, tool-use support, vision).

### vs. external agent
- **Coding-first focus.** Vector Code is specifically designed for software development workflows, not general assistant tasks.
- **Git-native** with automatic diff previews, commit message generation, and PR description writing.

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Vector Code CLI                          │
│                                                                  │
│  ┌──────────────┐   ┌───────────────┐   ┌────────────────────┐  │
│  │  CLI Parser  │──▶│  Query Engine │──▶│  Agentic Loop      │  │
│  │ (Commander)  │   │ (Orchestrator)│   │  Think→Act→Observe │  │
│  └──────────────┘   └───────────────┘   └────────────────────┘  │
│                              │                    │              │
│                    ┌─────────▼──────┐  ┌──────────▼──────────┐  │
│                    │  Model Router  │  │    Tool Executor     │  │
│                    │  (Any Provider)│  │  (FS, Bash, Search)  │  │
│                    └─────────┬──────┘  └──────────┬──────────┘  │
│                              │                    │              │
│         ┌────────────────────▼────────────────────▼──────────┐  │
│         │              Context Manager                        │  │
│         │  (VECTOR.md · Session Memory · Compaction Pipeline) │  │
│         └────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     TUI Layer (Ink/React)                 │   │
│  │   Chat · Diff Preview · Tool Log · Approval Dialogs      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │                            │
  ┌───────▼──────┐           ┌─────────▼────────┐
  │ Cloud APIs   │           │  Local Models     │
  │ Anthropic    │           │  Ollama           │
  │ OpenAI       │           │  LM Studio        │
  │ Google       │           │  llama.cpp server │
  │ Mistral      │           │  Any OpenAI-compat │
  │ Groq / etc.  │           └──────────────────┘
  └──────────────┘
```

### Key Pipeline

```
User Input → CLI Parser → Query Engine → Model Router → LLM
                                    ↑                      ↓
                              Tool Results ←── Tool Executor
                                    ↓
                              TUI renders output / asks for approval
```

---

## 4. Model Provider System

This is the defining feature of Vector Code. Every user interaction routes through the **Model Router**, which is provider-agnostic.

### 4.1 Supported Provider Categories

#### Cloud Providers (API Key)
| Provider | Models | Notes |
|----------|--------|-------|
| Anthropic | claude-opus-4, claude-sonnet-4-6, claude-haiku-4-5 | Full tool-use support |
| OpenAI | gpt-5, gpt-4o, gpt-4o-mini, o3 | Full tool-use support |
| Google | gemini-2.5-pro, gemini-2.5-flash | Full tool-use support |
| Mistral | mistral-large, codestral | Full tool-use support |
| Groq | llama-4-scout, llama-3.3-70b | Fast inference |
| Cohere | command-r-plus | |
| DeepSeek | deepseek-coder-v3 | Code-specialized |
| xAI | grok-3 | |
| Together AI | Any model hosted on Together | |
| OpenRouter | Any model on OpenRouter | Meta-provider |

#### Local Providers (No API Key)
| Provider | Protocol | Notes |
|----------|----------|-------|
| Ollama | OpenAI-compatible REST | Best local DX |
| LM Studio | OpenAI-compatible REST | GUI + API |
| llama.cpp server | OpenAI-compatible REST | Raw speed |
| Any OpenAI-compat | Custom base URL | Bring your own |

### 4.2 Model Capability Detection

When a model is first used, Vector Code probes it to detect:
- Context window size
- Tool/function-calling support
- Vision support (image inputs)
- Structured output support

This metadata is cached in `~/.config/vector/model-registry.json` and used to gate features automatically. If a model doesn't support native tool use, Vector Code falls back to a **prompt-engineered tool use** mode (XML-tagged responses parsed by the engine).

### 4.3 Model Configuration

```toml
# ~/.config/vector/config.toml

[model]
default = "anthropic/claude-sonnet-4-6"   # active model
fast = "groq/llama-4-scout"               # used for cheap sub-tasks (titles, summaries)
local = "ollama/qwen2.5-coder:32b"        # fallback when offline

[providers.anthropic]
api_key = "sk-ant-..."                     # or set ANTHROPIC_API_KEY env var

[providers.openai]
api_key = "sk-..."

[providers.ollama]
base_url = "http://localhost:11434"        # default Ollama address

[providers.custom]
name = "my-local-server"
base_url = "http://localhost:8080/v1"
api_key = "none"                           # leave blank for no auth
```

### 4.4 Runtime Model Switching

```bash
# Switch model for this session only
/model anthropic/claude-opus-4

# Switch to local model
/model ollama/llama4:scout

# List all configured models
/models

# Compare two models on the same prompt
vector run --compare "openai/gpt-4o vs anthropic/claude-sonnet-4-6" "explain this function"
```

---

## 5. Agentic Loop

Vector Code implements the standard **Think → Act → Observe** agentic loop.

```
┌─────────────────────────────────────────────────────────┐
│                    AGENTIC LOOP                          │
│                                                          │
│   ┌──────────┐                                           │
│   │  INPUT   │  User message / task                      │
│   └────┬─────┘                                           │
│        ▼                                                 │
│   ┌──────────┐                                           │
│   │  THINK   │  Model reasons, plans next action         │
│   └────┬─────┘                                           │
│        ▼                                                 │
│   ┌──────────┐    ┌─────────────────────────────────┐   │
│   │  ACT     │───▶│ Tool Call (read / write / bash)  │   │
│   └────┬─────┘    └──────────────┬──────────────────┘   │
│        │                         │                       │
│        ▼                         ▼                       │
│   ┌──────────┐    ┌──────────────────────────────────┐  │
│   │ OBSERVE  │◀───│ Tool Result (stdout / file / err) │  │
│   └────┬─────┘    └──────────────────────────────────┘  │
│        │                                                 │
│        ▼                                                 │
│   ┌──────────┐                                           │
│   │  DONE?   │── YES ──▶ Respond to user                 │
│   └────┬─────┘                                           │
│        │ NO                                              │
│        └──────▶ THINK (next iteration)                  │
└─────────────────────────────────────────────────────────┘
```

### Loop Configuration
```toml
[agent]
max_iterations = 50          # hard cap on agentic steps per task
think_budget_tokens = 8000   # extended thinking token budget (if model supports it)
auto_approve_reads = true    # never prompt for read-only operations
auto_approve_bash = false    # always confirm shell commands
```

---

## 6. Tool System

Vector Code ships with a **core tool set**. All tools declare metadata: name, description, input schema, `is_read_only`, `is_concurrency_safe`, and `risk_level`.

### 6.1 Filesystem Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read contents of a file |
| `write_file` | Write/overwrite a file |
| `edit_file` | Precise string-replace edit (preferred over full rewrite) |
| `create_file` | Create a new file at a path |
| `delete_file` | Delete a file (requires approval) |
| `list_directory` | List files/dirs in a path |
| `glob` | Find files matching a pattern |
| `grep` | Search file contents with regex |
| `move_file` | Move or rename a file |

### 6.2 Shell Tools

| Tool | Description |
|------|-------------|
| `bash` | Execute a shell command and capture stdout/stderr |
| `background_bash` | Run a long-running process in background (e.g. a dev server) |

### 6.3 Code Intelligence Tools

| Tool | Description |
|------|-------------|
| `find_symbol` | Find function/class/variable definitions across the codebase |
| `get_diagnostics` | Run linter/type-checker and return errors |
| `get_test_results` | Run test suite and return pass/fail |

### 6.4 Git Tools

| Tool | Description |
|------|-------------|
| `git_status` | Get current working tree status |
| `git_diff` | Show diff of staged or unstaged changes |
| `git_log` | Show recent commit history |
| `git_commit` | Stage all changes and commit with a message |
| `git_create_branch` | Create and checkout a new branch |
| `git_push` | Push to remote (requires approval) |

### 6.5 Web & Research Tools

| Tool | Description |
|------|-------------|
| `web_search` | Search the web for documentation, errors, etc. |
| `web_fetch` | Fetch the content of a URL |

### 6.6 Agent Tools (Multi-Agent)

| Tool | Description |
|------|-------------|
| `spawn_agent` | Delegate a sub-task to a worker agent |
| `read_memory` | Read from the session memory store |
| `write_memory` | Write a key-value pair to session memory |

### 6.7 Tool Risk Levels

Every tool is tagged with a risk level used by the permission system:

| Level | Description | Default Behavior |
|-------|-------------|-----------------|
| `safe` | Read-only, no side effects | Auto-approved |
| `low` | Writes to a new file | Auto-approved (configurable) |
| `medium` | Edits existing files, runs safe commands | Ask once per session |
| `high` | Deletes files, pushes to remote, runs untrusted scripts | Always ask |
| `critical` | Network requests with credentials, CI triggers | Require explicit `/allow` command |

---

## 7. Permission & Safety System

### 7.1 Permission Modes

Set globally or per-session:

```
--mode cautious     # Ask before every file write or bash command (default)
--mode standard     # Auto-approve file edits; ask for bash
--mode autonomous   # Auto-approve everything except `critical` tools
--mode read-only    # Only allow read tools; reject all writes
```

### 7.2 Approval Dialog

When Vector Code needs approval, it shows a rich TUI dialog:

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ Action Required                                      │
│                                                          │
│  Tool: bash                                              │
│  Risk: MEDIUM                                            │
│                                                          │
│  Command:                                                │
│    npm run test -- --watch=false                         │
│                                                          │
│  [y] Yes   [n] No   [a] Yes to all similar   [d] Details│
└─────────────────────────────────────────────────────────┘
```

### 7.3 Allowlist & Denylist

```toml
[permissions]
# Always auto-approve these patterns
allow_bash = ["npm test", "npm run build", "cargo build", "go test ./..."]
allow_write_paths = ["src/**", "tests/**"]

# Never allow these — hard block
deny_bash = ["rm -rf /", "curl * | sh"]
deny_write_paths = [".env", "*.pem", "secrets/**"]
```

### 7.4 Hooks (Deterministic Pre/Post Actions)

Hooks run regardless of model judgment:

```toml
[hooks]
after_write_file = ["npx prettier --write {file}"]   # auto-format on save
before_bash = ["echo 'Running: {command}' >> .vector/audit.log"]
after_git_commit = ["./scripts/notify-slack.sh"]
```

---

## 8. Context & Memory System

### 8.1 VECTOR.md (Project Config)

Create `VECTOR.md` in your project root. Vector Code reads it at the start of every session.

```markdown
# VECTOR.md — Project Configuration

## Project
Name: my-api
Language: TypeScript (Node.js 22)
Package Manager: pnpm

## Architecture
- src/routes/   → Express route handlers
- src/services/ → Business logic
- src/db/       → Prisma ORM models

## Conventions
- All functions must have JSDoc comments
- Use Zod for all runtime validation
- Tests go in __tests__/ next to the module they test

## Build & Test
- Build: `pnpm build`
- Test: `pnpm test`
- Lint: `pnpm lint`

## Review Checklist
Before committing: run lint, run tests, check for console.log statements
```

### 8.2 Session Memory (.vector/memory.md)

Auto-generated file where Vector Code stores learnings between sessions:

```markdown
# Vector Code Memory

## Build Commands
- Build: `pnpm build` (takes ~12s)
- Test: `pnpm test` (runs Jest, ~8s)

## Known Issues
- The `auth.test.ts` is currently skipped due to a flaky mock

## Architecture Notes
- Database connection pool is in `src/db/connection.ts`
- Config is loaded from environment via `src/config/index.ts`
```

### 8.3 Context Compaction Pipeline

As conversations grow, Vector Code runs a 5-stage compaction pipeline to stay within the model's context window:

1. **Trim tool results** — truncate large bash outputs, keeping first/last N lines
2. **Summarize closed topics** — compress resolved sub-tasks into a summary paragraph
3. **Prioritize recency** — keep the last N messages in full; compress older ones
4. **Embed VECTOR.md** — always keep project config in context
5. **Preserve decisions** — important decisions made during the session are never compacted away

---

## 9. Terminal UI (TUI)

Built with **React + Ink** — a fully reactive terminal UI.

### 9.1 Layout

```
┌────────────────────────────────────────────────────────────────┐
│ Vector Code  ●  anthropic/claude-sonnet-4-6  ●  my-api        │
├─────────────────────────────────────────┬──────────────────────┤
│                                         │  📄 DIFF PREVIEW     │
│  [session chat / output stream]         │                       │
│                                         │  src/routes/auth.ts  │
│  ▶ Reading: src/routes/auth.ts          │  ──────────────────  │
│  ▶ Running: npm test                    │  + const token =     │
│  ✓ Tests: 42 passed, 0 failed           │  + jwt.sign(...)     │
│                                         │  - const t = ...     │
│                                         │                       │
│                                         │  [y] Accept  [n] Rej │
├─────────────────────────────────────────┴──────────────────────┤
│  > Type a message or /command...                               │
└────────────────────────────────────────────────────────────────┘
```

### 9.2 Slash Commands

| Command | Description |
|---------|-------------|
| `/model <id>` | Switch model for this session |
| `/models` | List all available models |
| `/mode <mode>` | Change permission mode |
| `/memory` | View current session memory |
| `/compact` | Manually trigger context compaction |
| `/clear` | Clear conversation history |
| `/cost` | Show token usage and estimated cost so far |
| `/undo` | Revert the last file write |
| `/diff` | Show all changes made this session |
| `/commit` | Commit all changes with AI-generated message |
| `/spawn <task>` | Spawn a worker agent for a sub-task |
| `/help` | Show all commands |
| `/exit` | Exit Vector Code |

---

## 10. Configuration System

### 10.1 Config File Location

```
~/.config/vector/config.toml    # global config (user)
<project-root>/vector.toml      # project-level config (overrides global)
.vector/                        # runtime data dir (gitignored)
  session.json                  # current session state
  memory.md                     # auto-generated memory
  audit.log                     # action log
```

### 10.2 Full Config Reference

```toml
# vector.toml / ~/.config/vector/config.toml

[model]
default = "anthropic/claude-sonnet-4-6"
fast = "groq/llama-4-scout"
local = "ollama/qwen2.5-coder:32b"

[providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"    # read from env var

[providers.openai]
api_key_env = "OPENAI_API_KEY"

[providers.ollama]
base_url = "http://localhost:11434"

[providers.groq]
api_key_env = "GROQ_API_KEY"

[providers.custom_local]
name = "my-server"
base_url = "http://localhost:8080/v1"
api_key = ""

[agent]
max_iterations = 50
think_budget_tokens = 8000
auto_compact_threshold = 0.85    # compact at 85% context usage

[permissions]
mode = "standard"
allow_bash = []
deny_bash = ["rm -rf"]
allow_write_paths = []
deny_write_paths = [".env", "*.pem"]

[hooks]
after_write_file = []
before_bash = []
after_git_commit = []

[ui]
theme = "dark"                   # dark | light | auto
show_diff_panel = true
show_token_counter = true
syntax_highlight = true
```

---

## 11. Extensibility — MCP & Plugins

### 11.1 MCP (Model Context Protocol) Support

Vector Code supports MCP servers, allowing integration with external tools, databases, and APIs.

```toml
# Add MCP servers in config
[[mcp_servers]]
name = "github"
type = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_TOKEN = "ghp_..." }

[[mcp_servers]]
name = "postgres"
type = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]
```

Manage via CLI:
```bash
vector mcp add github
vector mcp list
vector mcp remove github
```

### 11.2 Plugin System

Plugins extend Vector Code with custom slash commands, tools, and agents.

```
<project>/.vector/plugins/
  review-pr/
    plugin.toml        # metadata + command declaration
    agent.md           # system prompt for this plugin's agent
    tools.js           # optional custom tools
```

```toml
# plugin.toml
name = "review-pr"
command = "/review-pr"
description = "Review a GitHub PR for issues, security, and style"
agent_prompt = "agent.md"
```

---

## 12. CLI Reference

### Basic Usage

```bash
# Start interactive session in current project
vector

# Run a one-shot task non-interactively
vector run "add input validation to all API route handlers"

# Run with a specific model
vector --model openai/gpt-4o "explain this codebase"

# Run in read-only mode
vector --mode read-only "describe the database schema"

# Pipe input into vector
cat error.log | vector run "explain these errors and suggest fixes"

# Run on a specific directory
vector --dir /path/to/project
```

### Agent Management

```bash
# List available agents
vector agents list

# Create a new custom agent
vector agents create

# Run a specific agent
vector agents run security-review
```

### Session Management

```bash
# List past sessions
vector sessions list

# Resume a past session
vector sessions resume <session-id>

# Export session as markdown
vector sessions export <session-id> > session.md
```

### Model Management

```bash
# List all configured providers and models
vector models list

# Test a model connection
vector models test ollama/llama4:scout

# Set default model
vector models set-default anthropic/claude-opus-4

# Pull a local model via Ollama (convenience wrapper)
vector models pull qwen2.5-coder:32b
```

---

## 13. Session Management

Each Vector Code session is stored in `.vector/sessions/<uuid>.json`:

```json
{
  "id": "sess_abc123",
  "created_at": "2026-05-12T10:00:00Z",
  "model": "anthropic/claude-sonnet-4-6",
  "project": "/home/user/my-api",
  "messages": [...],
  "tool_calls": [...],
  "files_modified": ["src/routes/auth.ts", "tests/auth.test.ts"],
  "token_usage": { "input": 24500, "output": 3200, "cache_read": 18000 },
  "cost_usd": 0.12
}
```

Sessions are **resumable** — `vector sessions resume <id>` restores full context and continues from where you left off.

---

## 14. Multi-Agent Architecture

For complex tasks, Vector Code can spawn **worker agents** that run in parallel.

### Architecture

```
┌──────────────────────────────────────────────────────┐
│                  LEAD AGENT (Planner)                 │
│   Model: claude-opus-4 or gpt-5                      │
│   Task: "Add OAuth2 login to the app"                │
│                                                       │
│   Spawns:                                             │
│   ├── Worker A: "Update auth routes"                 │
│   ├── Worker B: "Update database schema"             │
│   └── Worker C: "Write tests for OAuth flow"         │
└──────────┬───────────────────────────────────────────┘
           │ coordinates & merges
┌──────────▼─────┐  ┌──────────────┐  ┌──────────────┐
│   Worker A     │  │   Worker B   │  │   Worker C   │
│ (fast model)   │  │ (fast model) │  │ (fast model) │
│ src/routes/    │  │ src/db/      │  │ tests/auth/  │
└────────────────┘  └──────────────┘  └──────────────┘
```

### Usage

```bash
# Explicitly spawn workers
/spawn "review all files in src/services/ for security issues"

# Lead agent auto-spawns when task is complex
vector run "refactor the entire authentication system to use JWT"
```

Workers use the configured `fast` model by default to minimize cost. The lead agent uses the `default` model.

---

## 15. Technology Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| **Language** | TypeScript (Node.js) | Ecosystem, type safety, same as Claude Code |
| **CLI Parser** | Commander.js | Battle-tested, TypeScript support |
| **TUI** | React + Ink | Reactive terminal UI, composable components |
| **Config** | TOML | Human-friendly, typed config |
| **HTTP Client** | `undici` / native fetch | Fast, minimal |
| **Provider Adapters** | Custom adapters per provider | Thin wrappers normalizing to OpenAI tool format |
| **MCP Client** | `@modelcontextprotocol/sdk` | Official MCP SDK |
| **Storage** | JSON files (sessions, model registry) | Simple, inspectable, no external deps |
| **Diff / Patch** | `diff` npm package | Clean unified diffs |
| **Syntax Highlight** | `highlight.js` | Terminal ANSI output |
| **Tests** | Vitest | Fast, ESM-native |
| **Build** | esbuild | Single binary output |

### Minimum Requirements

- **Node.js:** v20.0.0 or higher
- **OS:** macOS, Linux, Windows (WSL2 recommended)
- **Disk:** ~50MB for the binary
- **Network:** Only when using cloud providers; fully offline with local models

---

## 16. File & Directory Structure

```
vector-code/                       # monorepo root
├── packages/
│   ├── core/                      # core agentic engine
│   │   ├── src/
│   │   │   ├── agent/
│   │   │   │   ├── loop.ts        # main agentic loop
│   │   │   │   ├── planner.ts     # multi-agent planner
│   │   │   │   └── worker.ts      # worker agent
│   │   │   ├── tools/
│   │   │   │   ├── index.ts       # tool registry
│   │   │   │   ├── filesystem.ts  # read/write/glob/grep
│   │   │   │   ├── bash.ts        # shell execution
│   │   │   │   ├── git.ts         # git operations
│   │   │   │   └── web.ts         # search + fetch
│   │   │   ├── providers/
│   │   │   │   ├── index.ts       # model router
│   │   │   │   ├── anthropic.ts
│   │   │   │   ├── openai.ts
│   │   │   │   ├── google.ts
│   │   │   │   ├── ollama.ts
│   │   │   │   ├── openai-compat.ts  # generic OpenAI-compat adapter
│   │   │   │   └── capability-probe.ts
│   │   │   ├── context/
│   │   │   │   ├── manager.ts     # context window management
│   │   │   │   ├── compactor.ts   # 5-stage compaction pipeline
│   │   │   │   └── memory.ts      # VECTOR.md + session memory
│   │   │   └── permissions/
│   │   │       ├── system.ts      # permission evaluation
│   │   │       └── hooks.ts       # hook runner
│   ├── cli/                       # CLI entry point
│   │   ├── src/
│   │   │   ├── index.ts           # main CLI
│   │   │   ├── commands/          # subcommands (run, models, sessions, mcp)
│   │   │   └── ui/                # React/Ink TUI components
│   │   │       ├── App.tsx
│   │   │       ├── Chat.tsx
│   │   │       ├── DiffPanel.tsx
│   │   │       ├── ApprovalDialog.tsx
│   │   │       ├── ToolLog.tsx
│   │   │       └── StatusBar.tsx
│   └── mcp/                       # MCP client integration
│       └── src/
│           ├── client.ts
│           └── registry.ts
├── docs/
├── tests/
├── package.json
└── vector.toml                    # root config
```

---

## 17. Roadmap

### v0.1.0 — MVP (Month 1–2)
- [ ] Core agentic loop (Think → Act → Observe)
- [ ] Provider system: Anthropic, OpenAI, Ollama (local)
- [ ] Core tools: filesystem, bash, git (read ops)
- [ ] Basic TUI: chat interface, tool log
- [ ] VECTOR.md project config
- [ ] Permission system (cautious mode default)
- [ ] Session save/resume

### v0.2.0 — Model Parity (Month 2–3)
- [ ] All major cloud providers (Google, Mistral, Groq, etc.)
- [ ] Generic OpenAI-compat adapter (any local server)
- [ ] Capability auto-detection (context, tools, vision)
- [ ] Prompt-engineered tool use fallback for non-native models
- [ ] `/models` command + model switching
- [ ] Token cost tracking per provider

### v0.3.0 — Power Features (Month 3–4)
- [ ] Diff preview panel in TUI
- [ ] Git tools (commit, branch, push)
- [ ] Context compaction pipeline
- [ ] Session memory auto-generation
- [ ] Hooks system
- [ ] MCP support

### v0.4.0 — Multi-Agent (Month 4–5)
- [ ] Worker agent spawning
- [ ] Lead agent planner
- [ ] Parallel agent execution
- [ ] Agent output merging

### v0.5.0 — Extensibility (Month 5–6)
- [ ] Plugin system
- [ ] Custom agents (agent.md)
- [ ] Web search + fetch tools
- [ ] Extended thinking support (where models support it)

### v1.0.0 — Stable Release
- [ ] IDE integrations (VS Code extension)
- [ ] CI/CD mode (non-interactive, JSON output)
- [ ] Web dashboard for session history
- [ ] Team/shared config support

---

## 18. Competitive Positioning

| Feature | Vector Code | Claude Code | OpenCode | Aider |
|---------|-------------|-------------|----------|-------|
| Any cloud provider | ✅ | ❌ (Anthropic only) | ✅ | ✅ |
| Local models (Ollama) | ✅ | ❌ | ✅ | ✅ |
| Capability auto-detection | ✅ | N/A | Partial | ❌ |
| Rich TUI + diff panel | ✅ | ✅ | ✅ (basic) | ❌ |
| Project config file | ✅ (VECTOR.md) | ✅ (CLAUDE.md) | ✅ (AGENTS.md) | ❌ |
| Session memory | ✅ | ✅ | ❌ | ❌ |
| Multi-agent orchestration | ✅ | ✅ | ❌ | ❌ |
| MCP support | ✅ | ✅ | ✅ | ❌ |
| Plugin/hooks system | ✅ | ✅ | ❌ | ❌ |
| Open source | ✅ | ❌ | ✅ | ✅ |
| No subscription required | ✅ | ❌ | ✅ | ✅ |
| Cost tracking | ✅ | ✅ | Partial | ❌ |

---

*Vector Code Specification — v0.1.0-draft*  
*Built to be the most model-flexible agentic coding tool in the terminal.*
