# Open WebUI Audit

**Repo:** open-webui-main (v0.9.5)
**Tech:** SvelteKit frontend + Python FastAPI backend (single package `open_webui`)
**License:** MIT

---

## 1. Repo Reality

Open WebUI is a self-hosted AI platform — essentially a polished multi-user chat UI with a full Python backend. It is NOT a pure frontend; the backend is a substantial FastAPI application.

### UI Pages / Panels (SvelteKit routes under `src/routes/(app)/`)
| Route | Panel |
|-------|-------|
| `/` (home) | Landing / new chat |
| `/c/[id]` | Chat conversation view |
| `/channels/[id]` | Discord-style channels (real-time team messaging) |
| `/calendar` | Event / schedule calendar |
| `/notes` | Persistent markdown notes |
| `/automations` | Automation scheduler (rrule-based) |
| `/playground` | Raw API playground (stream testing) |
| `/workspace/models` | Custom model builder (Ollama modelfile editor) |
| `/workspace/prompts` | Prompt library |
| `/workspace/tools` | Python tool functions (BYOF) |
| `/workspace/knowledge` | RAG knowledge bases |
| `/workspace/functions` | Filter/pipeline functions |
| `/workspace/skills` | Skill bundles |
| `/admin/` | Admin dashboard |
| `/admin/analytics` | Usage charts by model/user |
| `/admin/users` | User management |
| `/admin/evaluations` | Model leaderboard / feedback scoring |
| `/admin/settings` | Global config |
| `/admin/functions` | Admin-controlled functions |
| `/watch` | Ambient screen-cast viewer |

### Backend Routers (`backend/open_webui/routers/`)
Full Python FastAPI stack covering: `chats`, `memories`, `retrieval` (RAG with 9 vector DBs), `images` (DALL-E / ComfyUI / A1111), `audio` (STT/TTS multi-provider), `channels`, `automations`, `calendar`, `notes`, `skills`, `analytics`, `evaluations`, `terminals` (WebSocket proxy to terminal servers), `functions`, `knowledge`, `ollama`, `openai`, `pipelines`, `scim`, `models`, `prompts`, `tasks`, `users`, `groups`, `folders`, `files`, `retrieval`.

### Standout AI features
- **Local RAG**: 9 vector DB backends (Chroma, Qdrant, Milvus, PGVector, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle23ai). Content extractors: Tika, Docling, Mistral OCR, PaddleOCR.
- **Memories**: per-user vector-indexed personal memory with semantic search.
- **Model evaluations**: ELO-style leaderboard from thumbs-up/down feedback — tracks which model wins A/B comparisons.
- **Automations**: rrule-based scheduled chat actions — a cron engine inside the AI UI.
- **Terminals**: WebSocket reverse-proxy to external terminal servers (xterm.js in UI).
- **Python BYOF tools**: users define pure Python functions executed by the backend via Pyodide in-browser.
- **Skills**: Markdown instruction bundles, shareable across users/groups.
- **Channels**: real-time Socket.IO messaging rooms (group/team chat layer).
- **Native Ollama integration**: model pull, delete, push, modelfile edit, all from the UI.
- **OpenTelemetry**: built-in traces/metrics/logs.
- **Redis-backed horizontal scaling**: multi-worker WebSocket sync.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|-------------------|--------|
| Chat UI with conversation history | `frontend/VECTOR.html` — `F.chat` widget + `/api/chats/*` | ⚠️ VECTOR's chat is a minimal single-widget panel; Open WebUI has a full multi-session, forking, markdown-rendering chat with branching |
| RAG / document upload | `core/memory/` (LightRAG) | ⚠️ LightRAG is wired but `get_vault_context` is missing (A6 bug); Open WebUI's RAG is production-grade with 9 DB backends |
| Personal memories (semantic) | `core/memory/episodic.py` | ⚠️ VECTOR's episodic memory is FTS5/SQLite; no per-user semantic memory with embedding search like Open WebUI |
| Image generation | `districts/content/video_generator.py` + ComfyUI adapter | ✅ VECTOR has ComfyUI + DALL-E adapter |
| Voice / audio | `core/voice/` (STT/TTS full stack) | ✅ VECTOR has Whisper + Kokoro + multi-provider TTS |
| Model management (Ollama) | `core/inference/ollama_safe.py` + `/api/inference/*` | ⚠️ VECTOR calls Ollama programmatically; no web UI for model pull/delete/modelfile editing |
| Prompt library | No VECTOR equivalent | ❌ Missing |
| Python tool functions (BYOF) | `core/mcp_server.py` (MCP tools) | ⚠️ Different model — VECTOR uses MCP rather than BYOF Python functions |
| Skills bundles | Brain `.claude/skills/` (Claude Code skills) | ⚠️ VECTOR skills are Claude Code skills, not shareable UI bundles |
| Model evaluations / leaderboard | `core/city/evolution_engine.py` (HP system) | ⚠️ VECTOR HP measures agent lifespan, not LLM response quality A/B evaluation |
| Automations (scheduled) | `core/loop/autonomous_loop.py` + APScheduler | ✅ VECTOR's loop is always-on; scheduled tasks supported |
| Channels (team chat rooms) | `vectorcode/src/channels/` (30+ platform adapters) | ⚠️ VECTOR channels are outbound message bridges to Telegram/Discord/etc — not an internal multi-user chat room system |
| Calendar | `districts/time_calendar/` | ✅ VECTOR has KIIT scraper + Google Calendar |
| Notes | `districts/memory_curator/` + Obsidian sync | ⚠️ VECTOR writes to Obsidian vault; no in-UI markdown notes editor |
| Admin analytics | `/api/analytics` router stub (VECTOR has this) | ✅ VECTOR has analytics.py router |
| Model leaderboard / feedback scoring | None | ❌ Missing |
| Terminal WebSocket proxy | None | ❌ Missing |
| RBAC user groups | `core/collections/auth.py` (JWT + RBAC) | ✅ VECTOR has RBAC via collections engine |
| SCIM 2.0 / LDAP | None | ❌ Missing (enterprise feature, not relevant for single-owner) |
| Multi-user system | None (VECTOR is single-owner) | ❌ By design — VECTOR is a single-owner agent OS |

---

## 3. Integration Plan

**Non-Python rule applies**: Open WebUI has a SvelteKit frontend built with Vite and a Python backend. The Python backend (`open_webui`) is actually a separate well-engineered FastAPI app — it is NOT VECTOR's FastAPI.

**Integration approach:**
- Run Open WebUI on **port 8080** (`uvicorn open_webui.main:app --port 8080`) alongside VECTOR's FastAPI on its default port.
- VECTOR's HUD proxies to it via an iframe or dedicated HUD panel.
- Open WebUI's Ollama integration auto-connects to `OLLAMA_HOST=127.0.0.1:11434` — the same Ollama instance VECTOR uses.
- VECTOR's `core/inference/provider_client.py` can call Open WebUI's `/api/chat/completions` (OpenAI-compatible endpoint) to leverage its RAG pipeline, giving VECTOR agents access to uploaded knowledge bases via a standard API call.
- Shared model list: Open WebUI reads from the same local Ollama, so model routing stays consistent.

**HUD panel:** Add a dock button "KNOWLEDGE" that opens an iframe to `http://localhost:8080` fullscreen. The iframe gives access to the full chat UI, workspace, and admin panels without rebuilding them in VECTOR.

**What it adds over VECTOR's HUD:**
- Production-quality multi-session chat with conversation branching/forking.
- Document upload + RAG pipeline (9 vector DBs) accessible from UI.
- Python BYOF tool execution with in-browser Pyodide sandbox.
- Model evaluation leaderboard (fills VECTOR's gap in tracking LLM response quality).
- Prompt library and skill bundles with group sharing.
- Real-time channels for multi-device VECTOR sessions.
- Model management UI: pull/delete/edit modelfiles for local Ollama models.

---

## 4. Verdict

**INTEGRATE DIRECTLY**

Open WebUI's Python backend is production-grade and covers several VECTOR gaps that would take significant effort to rebuild (RAG pipeline with 9 DB backends, model evaluations, BYOF tools, channels). Running it as a sidecar service and proxying from the HUD iframe costs zero rebuild time and gives VECTOR a world-class AI UI immediately.

Run via: `cd open-webui-main && pip install -e backend/ && uvicorn open_webui.main:app --port 8080`

**Do not copy or port Open WebUI's Python backend into VECTOR's codebase** — it is a standalone FastAPI service and should remain independent.

---

## 5. Gaps Revealed

| # | Gap | Severity |
|---|-----|----------|
| G1 | **No conversation-level RAG** — VECTOR can't attach documents to a chat turn and query them; LightRAG is vault-level only | HIGH |
| G2 | **No model evaluation leaderboard** — VECTOR HP tracks agent health, not LLM response quality A/B scoring | MEDIUM |
| G3 | **No prompt library** — VECTOR has no UI or API for storing/sharing reusable prompt templates | MEDIUM |
| G4 | **No in-UI model management** — users can't pull/delete/edit Ollama modelfiles without a terminal | LOW |
| G5 | **Missing `get_vault_context` in ContextEngine** — existing LightRAG wiring is broken (A6 bug in master tracker) | HIGH (pre-existing A6) |
| G6 | **No internal real-time chat rooms** — VECTOR's channel system bridges external platforms; there is no local multi-device / multi-session messaging room | LOW |
