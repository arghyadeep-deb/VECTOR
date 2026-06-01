# LibreChat Audit

**Repo:** LibreChat-main (v0.8.6-rc1)
**Tech:** React/TypeScript frontend + Node.js/Express backend + MongoDB (Mongoose)
**License:** MIT

---

## 1. Repo Reality

LibreChat is a self-hosted ChatGPT-clone that unifies every major AI provider behind a single polished chat interface. Monorepo: `api/` (Node.js/Express), `client/` (React/Vite), `packages/` (shared data-provider + data-schemas libs).

### UI Pages / Components (`client/src/routes/` + `client/src/components/`)
| View / Route | Description |
|---|---|
| `/` (ChatRoute) | Main multi-session chat UI |
| `/search` | Full-text conversation search |
| `/share/[id]` | Public conversation share page |
| Dashboard | Analytics for admins |
| Agents panel | No-code custom agent builder with marketplace |
| Tools sidebar | MCP tool selector, plugin auth per tool |
| Prompts panel | Prompt library with group sharing |
| Skills panel | Markdown SKILL.md bundles (analogous to Claude Code skills) |
| Artifacts panel | Live React/HTML/Mermaid code execution in chat |
| Files / SharePoint | File upload, Google Drive / OneDrive picker, S3 storage |
| MCP config dialog | Add/remove/configure MCP servers per user |
| Bookmarks | Conversation bookmarks with tags |
| OAuth / Auth panel | Multi-provider SSO (Google, GitHub, Discord, etc.) |
| Side panel | Conversation list with cursor pagination, tags, archive |

### Backend Services (`api/server/`)
Node.js/Express: `convos`, `messages`, `agents`, `assistants`, `skills`, `mcp`, `actions`, `files`, `models`, `presets`, `prompts`, `search`, `oauth`, `auth`, `share`, `balance`, `roles`, `categories`, `tags`, `keys`, `settings`, `banner`, `types`.

### Standout AI features
- **Multi-provider unified endpoint**: Claude, GPT-4o, Gemini, Mistral, Ollama, Groq, DeepSeek, OpenRouter, Cohere, AWS Bedrock, Azure, Vertex AI — all in one dropdown.
- **MCP (Model Context Protocol)**: first-class MCP server management — add any MCP server per-user with OAuth reconnect manager; tools appear automatically in chat.
- **LibreChat Agents**: no-code agent builder with an agent marketplace (community-built agents, shareable with users/groups). Agents can use MCP tools, file search, code execution, subagents.
- **Skills**: Markdown SKILL.md instruction bundles — same concept as Claude Code skills but surfaced in the chat UI with file management, import/export (zip), per-user/group access control.
- **Subagents**: delegate focused child agent runs with isolated context windows.
- **Artifacts**: live code execution sandbox in the chat window — React, HTML, Mermaid diagrams render inline. Backed by `api/server/services/Artifacts/` with persistent artifact storage (KV API).
- **Code Interpreter API**: sandboxed execution in Python, Node.js, Go, C/C++, Java, PHP, Rust, Fortran — files upload/download inline.
- **Conversation forking/branching**: fork any message into a parallel branch, full tree management.
- **Resumable streams**: Redis-backed — AI response continues across tab/device/reconnect.
- **Reasoning UI**: dedicated chain-of-thought display for R1-style models (DeepSeek-R1, Claude thinking).
- **Web search**: 15+ search providers injected as context into chat.
- **Full-text search**: MongoDB-backed search across all messages.
- **Balance/token metering**: per-user token budget with spend tracking.
- **Two-factor auth + LDAP**.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|-------------------|--------|
| Multi-provider AI chat | `core/inference/provider_client.py` (27 providers) | ✅ VECTOR has 27 providers but no chat UI — programmatic only |
| MCP server management | `core/mcp_server.py` (14 tools) | ⚠️ VECTOR has a fixed MCP server; LibreChat lets users add/remove/auth MCP servers dynamically from the UI |
| Custom agents (no-code) | `core/city/agent_registry.py` + 133 agent files | ⚠️ VECTOR agents are code-defined Python classes; LibreChat agents are UI-configurable with a marketplace |
| Agent marketplace | None | ❌ Missing |
| Skills (SKILL.md bundles) | Brain `.claude/skills/` (Claude Code skills) | ⚠️ Claude Code skills are Claude Code internal; LibreChat skills appear inside the chat UI, importable/exportable by users |
| Subagents | `core/city/agent_registry.py` (agent delegation) | ⚠️ VECTOR agent delegation is autonomous-loop-level; LibreChat subagents are user-triggered in chat |
| Artifacts (live code execution) | `districts/coding/` (GitBot, etc.) | ❌ No in-chat live React/HTML rendering sandbox |
| Code Interpreter (sandboxed) | `core/sandbox/` (VectorSandbox) | ⚠️ VectorSandbox is a process isolation layer; LibreChat's code interpreter is a multi-language file-in/file-out sandbox wired directly into chat |
| Conversation branching/forking | None | ❌ Missing |
| Resumable streams (Redis) | None (VECTOR's async loop is persistent by design) | ❌ No equivalent for browser-side resumable streaming |
| Reasoning UI (chain-of-thought display) | None | ❌ Missing — VECTOR stores reasoning chains in `reasoning_memory.py` but doesn't display them |
| Prompt library with sharing | None | ❌ Missing |
| Web search in chat | `districts/research/web_scout.py` | ⚠️ VECTOR's web search is autonomous-loop-triggered, not user-invoked in a chat turn |
| Conversation full-text search | None | ❌ Missing — VECTOR episodic memory has FTS5 but no chat-level search UI |
| Token balance / spend tracking | `core/metering/budget_meter.py` | ✅ VECTOR has per-agent budget metering |
| OAuth2 multi-provider auth | `core/engine/oauth/` (83 providers) | ✅ VECTOR has OAuth flows but no user login UI |
| File upload + cloud storage | `core/collections/storage.py` (local + S3) | ✅ VECTOR has file storage but no chat file attachment UX |
| SharePoint / Google Drive picker | None | ❌ Missing (enterprise feature) |
| Multi-user access control | `core/collections/auth.py` | ✅ VECTOR has JWT + RBAC (single-owner though) |
| Conversation export (screenshot/md/json) | None | ❌ Missing |

---

## 3. Integration Plan

**Non-Python rule applies**: LibreChat is Node.js/Express + React. Do not reimplement in Python.

**Integration approach:**
- Run LibreChat API on **port 3080** (`cd api && node server/index.js`) alongside VECTOR's FastAPI.
- Configure `librechat.yaml` to point to VECTOR's Ollama instance: `OLLAMA_BASE_URL=http://localhost:11434`.
- Add all VECTOR cloud providers (Anthropic, Gemini, OpenAI, Groq, etc.) to LibreChat's `librechat.yaml` `endpoints:` block using the same API keys from VECTOR's `.env` — shared single credential store.
- Wire LibreChat's MCP config to VECTOR's `core/mcp_server.py`: add `http://localhost:8765` as an MCP server in LibreChat → all VECTOR MCP tools (city, memory, kanban, council, etc.) appear as tools inside LibreChat chat turns.
- VECTOR's autonomous loop can call LibreChat's OpenAI-compatible endpoint (`POST http://localhost:3080/api/completions`) if it needs the reasoning-UI display layer or artifacts sandbox.

**HUD panel:** Add a "CHAT" dock button that opens an iframe to `http://localhost:3080` fullscreen. The reasoning UI and artifacts sandbox are uniquely valuable for monitoring VECTOR's own chain-of-thought runs.

**What it adds over VECTOR's HUD:**
- Multi-provider dropdown in a single chat UI — switch between Claude/Gemini/Ollama mid-conversation.
- In-chat artifact rendering: React/HTML components generated by VECTOR agents display live.
- Reasoning UI: DeepSeek-R1 and Claude thinking traces render in a collapsible block.
- Agent marketplace: community agents importable as starting templates for new VECTOR districts.
- Skills UI: VECTOR's brain skills could be imported as LibreChat skill bundles for interactive use.
- Conversation forking for exploratory reasoning (try multiple decision branches).
- Code interpreter: sandboxed multi-language execution without VectorSandbox setup.
- MongoDB full-text search across all historical AI conversations.

**MongoDB requirement:** LibreChat uses MongoDB. Add `MONGODB_URI=mongodb://localhost:27017/LibreChat` to VECTOR's `.env`. MongoDB is a separate process (run via Docker: `docker run -d -p 27017:27017 mongo`). This is the only new infrastructure dependency.

---

## 4. Verdict

**INTEGRATE DIRECTLY**

LibreChat fills three significant VECTOR gaps that are hard to rebuild: in-chat Artifacts (live code rendering), the Reasoning UI for chain-of-thought display, and the Skills marketplace for discoverable SKILL.md bundles. The MCP bridge is particularly powerful — wiring LibreChat's MCP client to VECTOR's MCP server makes all 14+ VECTOR tools accessible directly from the LibreChat chat UI with zero additional code.

Run via:
```
cd LibreChat-main
npm install
cp librechat.example.yaml librechat.yaml   # edit with Ollama + API keys
docker run -d -p 27017:27017 mongo         # MongoDB
node api/server/index.js
```

The Redis dependency for resumable streams is optional for single-user local use.

---

## 5. Gaps Revealed

| # | Gap | Severity |
|---|-----|----------|
| G1 | **No in-chat Artifacts sandbox** — VECTOR cannot render live React/HTML components generated by agents in a browser view | HIGH |
| G2 | **No chain-of-thought display** — VECTOR stores reasoning chains in `reasoning_memory.py` but no UI surfaces them visually in the HUD | HIGH |
| G3 | **No conversation branching** — VECTOR cannot fork a decision at a message and explore two parallel branches | MEDIUM |
| G4 | **No chat-level prompt library** — reusable prompts exist only as Claude Code skills, not as user-accessible UI templates | MEDIUM |
| G5 | **No conversation search** — VECTOR episodic FTS5 is internal; no search UI over historical chat | MEDIUM |
| G6 | **No dynamic MCP server management** — VECTOR's MCP server is fixed at startup; users cannot add/remove/auth MCP servers without editing code | MEDIUM |
| G7 | **No agent marketplace** — VECTOR's 133 agents are all code-defined; no discovery or import of community agents from a catalog | LOW |
| G8 | **No multi-language code interpreter wired to chat** — VectorSandbox exists but isn't surfaced as a chat tool the user can invoke | LOW |
