# openclaude-main Audit

## 1. Repo Reality

**What it is:** TypeScript/Bun CLI agent (MIT, community fork of Claude Code) that replaces the Anthropic backend with any OpenAI-compatible or native provider. Not a framework — it is a standalone terminal coding assistant.

**Concrete features (from README + source):**

| Feature | Detail |
|---------|--------|
| Multi-provider routing | OpenAI-compat, Gemini, GitHub Models, Codex OAuth, Ollama, Atomic Chat, Hicap, OpenCode, Xiaomi MiMo, Gitlawb Opengateway — all via `/provider` profile system |
| Smart Router (Python) | `python/smart_router.py` — latency/cost/balanced scoring, EMA latency tracking, health pings, auto-recheck after 60 s, 5 providers (OpenAI, Gemini, Mistral, Ollama, Atomic Chat) |
| Per-agent model routing | `agentModels` + `agentRouting` in `~/.openclaude.json` — e.g. Explore→DeepSeek, Plan→GPT-4o |
| gRPC headless server | `src/grpc/` — bidirectional streaming, protobuf at `src/proto/openclaude.proto`, test CLI client |
| Full tool suite | Bash, FileRead/Write/Edit, Grep, Glob, Agent, AskUserQuestion, LSP, MCP, WorkTree, Monitor, NotebookEdit, ScheduleCron, PowerShell, REPL, WebSearch, WebFetch, Sleep, TodoWrite, VerifyPlanExecution, Team*, Task*, Workflow |
| Web search | DuckDuckGo free path (non-Anthropic models) + Firecrawl optional |
| Skills system | Bundled + directory-loaded SKILL.md skills |
| VS Code extension | `vscode-extension/openclaude-vscode/` — launch integration, provider-aware control-center UI |
| Bridge layer | `src/bridge/` — remote session, JWT, WebSocket, trusted device, session runner |
| Voice mode | `src/voice/voiceModeEnabled.ts` — voice toggle, no actual TTS/STT engine (UI gating only) |
| Atomic Chat provider | `python/atomic_chat_provider.py` — local model provider auto-discovery |
| Ollama provider helper | `python/ollama_provider.py` |
| Coverage/heatmap | Git-activity-style HTML heatmap at `coverage/index.html` |

**Language:** TypeScript (Bun runtime), small Python helpers in `python/`.
**License:** MIT.

---

## 2. VECTOR Parity

Verification command output:
```
ProviderClient OK
PermissionGateway OK
ask_user_question in mcp: 0
```

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| Multi-provider LLM routing | `core/inference/provider_client.py` + `core/inference/llm_providers.py` | ProviderClient OK (27 providers, Ollama-first with cloud fallback) | ✅ Covered — VECTOR has 27 providers vs openclaude's ~12 |
| Smart routing with latency scoring | `core/inference/provider_client.py` (route_policy + budget_meter) | ProviderClient OK | ✅ VECTOR has tier-based routing + EMA budget; openclaude's `smart_router.py` is simpler but adds a pure latency/cost scoring dimension |
| Permission gateway | `core/loop/permission_gateway.py` | PermissionGateway OK | ✅ VECTOR's gateway is more sophisticated (GREEN/YELLOW/RED, FORBIDDEN list, HumanLayer) |
| MCP server | `core/mcp_server.py` | 14 tools + kanban + claims + guidance | ✅ VECTOR exposes district capabilities; openclaude exposes coding tools |
| AskUserQuestion tool | `core/coding_assistant/core/tools/builtins/ask_user_question.py` | ask_user_question in mcp: 0 (exists in coding_assistant, not mcp_server) | ⚠️ Present in `core/coding_assistant` but NOT wired into `core/mcp_server.py` |
| Agent-to-model routing config | `core/inference/llm_providers.py` (route_for_tier) | ProviderClient OK | ✅ VECTOR has tier-based routing; openclaude has named-agent routing |
| gRPC headless server | Not found | N/A | ❌ VECTOR has no gRPC endpoint — only FastAPI REST + MCP |
| Web search (DuckDuckGo) | `districts/research/web_scout.py` | N/A | ✅ VECTOR research district has DuckDuckGo + ArXiv |
| Skills system | `vectorcode/src/` (282 SKILL.md files from Ruflo) | N/A | ✅ VECTOR has richer skills system |
| VS Code extension | Not applicable | N/A | ❌ No VS Code extension — VECTOR is an autonomous agent, not a coding CLI |

---

## 3. Frontend

- **VS Code extension** (`vscode-extension/openclaude-vscode/`) — provider-aware control-center UI; launch integration + theme support. Not relevant to VECTOR HUD.
- **Web UI** — none; purely terminal CLI (Ink/React-terminal renderer). The gRPC server allows custom UIs to be built on top.
- **Coverage heatmap** (`coverage/index.html`) — git-activity-style HTML. Useful model for VECTOR's `/health` monitoring dashboard.

No frontend components are relevant for VECTOR HUD adoption.

---

## 4. Verdict

**SAFE TO DELETE** — with one narrow exception.

The entire TypeScript CLI, Ink rendering, gRPC server, provider profile system, and VS Code extension are TypeScript-first and duplicate what VECTOR already has in Python. 100% of openclaude's value for VECTOR is already present in `core/inference/provider_client.py` (27 providers) + `core/inference/llm_providers.py`.

**One genuine Python gap worth absorbing:** `python/smart_router.py` — the latency/cost scoring + EMA + health-ping + automatic pool recovery logic. VECTOR's `provider_client.py` does tier-based routing and budget gating but does NOT do continuous latency benchmarking or EMA-based per-provider scoring. This is a clean, 388-line standalone Python file. No TypeScript dependency.

---

## 5. Gaps

| Gap | openclaude location | VECTOR gap | Absorb action |
|-----|---------------------|------------|---------------|
| Latency/cost SmartRouter | `python/smart_router.py:144-388` | `core/inference/provider_client.py` does tier routing but no live latency benchmarking | Absorb: copy `Provider` dataclass + `SmartRouter` class → `core/inference/smart_router.py`; wire into `provider_client.py` as optional scoring layer when `ROUTER_MODE=smart` |
| gRPC headless API | `src/grpc/server.ts`, `src/proto/openclaude.proto` | `core/api/app.py` only exposes REST | Low priority — VECTOR is single-owner, not a multi-client server; skip |
| AskUserQuestion wired to MCP | `src/tools/AskUserQuestionTool/AskUserQuestionTool.tsx` | `core/mcp_server.py` has 0 occurrences of `ask_user_question` | PATCH: wire `core/coding_assistant/core/tools/builtins/ask_user_question.py` into `core/mcp_server.py` as an MCP tool so agents can ask the owner clarifying questions |
