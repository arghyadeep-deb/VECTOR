# Frontend / UI Batch Audit
> Audited: 2026-06-01  
> Auditor: Claude Sonnet 4.6 sub-agent  
> VECTOR codebase: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`

---

## ComfyUI-master

**What it is:**  
ComfyUI is the dominant open-source AI image/video/audio/3D generation engine. It runs as a Python `aiohttp` server on port 8188 with a node-graph browser UI. Key features:
- Supports SD1.x, SDXL, SD3.5, Flux, Flux Kontext (image editing), HunyuanDiT, HiDream, Wan 2.x, LTX-Video, Mochi, Stable Audio, ACE Step (music), Hunyuan3D 2.0, and dozens more models.
- REST + WebSocket API (`/prompt`, `/history`, `/view`, `/upload/image`, `/system_stats`, `/object_info`).
- Async queue with partial re-execution (only re-runs changed nodes).
- Smart VRAM offloading — runs large models on as little as 1 GB VRAM.
- LoRA / ControlNet / Inpainting / Upscalers / Embeddings support.
- ~80 built-in `comfy_extras` node modules covering video, audio, 3D, compositing, motion, masks, latent manipulation.
- App Mode: any workflow can be exposed as a simple parametric UI.
- 8188-based HTTP API used by automation tools.

**VECTOR parity:**  
`districts/content/comfyui_adapter.py` exists and is a proper async HTTP client against ComfyUI's API (queue prompt, poll history, retrieve images). It handles txt2img, custom workflows, model listing, and availability check. However:
- VECTOR's adapter is a *client* only — it assumes ComfyUI is already running externally.
- ComfyUI itself is the server providing: diffusion models, video models, audio models, 3D models, ControlNet, the node execution engine, VRAM management, LoRA injection, etc.
- VECTOR has NO diffusion engine of its own. Without ComfyUI running, `comfyui_adapter.py` returns `{"status": "error", "error": "ComfyUI not running"}`.
- VECTOR's `districts/content/video_generator.py` uses SadTalker for talking-head video only; it does NOT cover Wan 2.x, LTX-Video, Hunyuan Video, Stable Audio, or 3D generation.

**Integration plan:**  
ComfyUI is already the intended backend — the adapter already points to `http://127.0.0.1:8188`. The integration is architectural: run ComfyUI as a persistent sidecar process that VECTOR's loop can submit jobs to.

1. **Startup**: Add a step in `run_vector.py` / `scripts/install_service.ps1` to launch ComfyUI if not already running:  
   `python "C:\path\to\ComfyUI-master\main.py" --port 8188 --listen 127.0.0.1`
2. **Port**: 8188 (already in `CONFIG["comfyui"]["url"]`).
3. **VECTOR loop integration**: `ComfyUIAdapter.generate()` is already callable by any district agent. Route content requests through the governor → content district → ComfyUIAdapter.
4. **HUD panel**: Add a "ComfyUI" status card to `frontend/VECTOR.html` showing: running/stopped, current queue depth (`/queue` endpoint), last generated image thumbnail.
5. **Model coverage**: Point `CONFIG["comfyui"]["output_dir"]` at the ComfyUI output folder and `extra_model_paths.yaml` at local model directories.

**Verdict: INTEGRATE DIRECTLY**  
Run as a sidecar. VECTOR's adapter is already wired. The gap is just lifecycle management (auto-start, health monitoring) and HUD visibility.

**Gaps this reveals:**
- No ComfyUI auto-start or health-restart logic in `ops/sre_monitor.py`.
- No HUD panel for generation queue / live preview.
- `comfyui_adapter.py` only wraps txt2img; VECTOR has no video-gen or audio-gen workflow abstraction for the ComfyUI API (Wan, LTX, ACE Step).
- No LoRA injection helper — content agents cannot dynamically select LoRA models.

---

## ComfyUI-Manager-main

**What it is:**  
ComfyUI-Manager is a ComfyUI custom-node plugin that adds a full node-package management system to the ComfyUI UI:
- Install / remove / enable / disable custom nodes via a browser GUI.
- 1,400+ registered custom nodes in `custom-node-list.json`.
- 1,000+ model entries in `model-list.json` with direct download links.
- Version snapshots: save and restore exact node + model versions as JSON.
- Hub integration with the official `registry.comfy.org`.
- `cm-cli.py` for headless install/uninstall without the GUI.
- Security audit (`security_check.py`) that scans custom nodes for dangerous imports.
- `manager_core.py`: git-based install, pip dep resolution, `uv` support.

**VECTOR parity:**  
VECTOR has no equivalent. The closest things are:
- `districts/coding/git_bot.py` — GitHub automation, not package management.
- `core/migration/` — schema migrations, not plugin management.

This is a management UI for ComfyUI itself, not for VECTOR. It has no Python API surface usable by VECTOR agents. Its value is entirely in the ComfyUI browser UI workflow.

**Integration plan:**  
Install it as a ComfyUI custom node (the standard method). No VECTOR code changes needed.

```
cd C:\path\to\ComfyUI-master\custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager comfyui-manager
```

This gives ComfyUI's browser UI (port 8188) the Manager tab. VECTOR's `ComfyUIAdapter` continues to work via the REST API — Manager is purely a UX layer on top.

**Verdict: INTEGRATE DIRECTLY**  
Install as a ComfyUI plugin via git clone into `custom_nodes/`. Zero VECTOR code changes. Gives VECTOR's operator the ability to install new diffusion model nodes from the browser without CLI gymnastics.

**Gaps this reveals:**
- No automated way for VECTOR to install/uninstall ComfyUI nodes programmatically. `cm-cli.py` could be wrapped in a VECTOR tool, but this is low priority.

---

## openclaude-main

**What it is:**  
OpenClaude is an open-source TypeScript/Node.js CLI coding agent, a community fork of Claude Code that supports multiple LLM backends. Key features:
- Terminal-first coding assistant (bash, file read/write/edit, grep, glob, agents, tasks, MCP, slash commands, streaming).
- Supports: OpenAI-compatible APIs, Gemini, GitHub Models, Codex OAuth, Ollama, Atomic Chat, Xiaomi MiMo, OpenRouter, DeepSeek, Groq, Mistral, LM Studio, Bedrock, Vertex.
- Agent routing: different agents (Explore, Plan, frontend-dev) can be routed to different models per task.
- Python bridge in `python/` directory: `smart_router.py` (multi-provider intelligent router with latency/cost/health scoring and rolling averages), `ollama_provider.py` (native Ollama bridge).
- Provider profiles saved locally via `/provider` command.
- VS Code extension for launch integration.
- `SmartRouter`: pings all providers at startup, scores by latency + cost + health, falls back automatically.

**VECTOR parity:**  
VECTOR has a substantially more complete version of everything OpenClaude provides:
- `core/inference/provider_client.py` — 27-provider routing, Ollama-first with fallback.
- `core/inference/smart_routing/` — full smart routing package with `classifier.py`, `fallback_chain.py`, `wallet.py`, `balance.py`, `model_catalog.py`, `stats.py`, `proxy.py`.
- `vectorcode/src/agent/` — full agent runtime including LSP, tool guardrails, context engine, curator.
- `vectorcode/src/router.py` — 4-layer routing (MoE→GNN→keyword→regex).
- VECTOR is itself an autonomous CLI agent with 27 providers.

OpenClaude's `python/smart_router.py` is a ~200-line script offering latency/cost scoring across 4 providers. VECTOR's `smart_routing/` directory implements the same concept but with far more depth (balance tracking, wallet, stats, proxy, 27 providers, MoE gating).

The only potentially novel pattern in OpenClaude is the `SmartRouter.avg_latency_ms` rolling average updating from real request timings — VECTOR's `smart_routing/stats.py` should cover this but worth verifying.

**Integration plan:**  
None required. VECTOR subsumes all capabilities. The Python utilities (`smart_router.py`, `ollama_provider.py`) offer nothing VECTOR's `provider_client.py` doesn't already do better.

**Verdict: SAFE TO DELETE**  
VECTOR's 27-provider client with 4-layer routing, MoE gating, budget metering, and ReasoningBank integration is strictly more capable than OpenClaude's Python bridge layer. The TypeScript CLI itself is irrelevant — VECTOR is its own autonomous loop.

**Gaps this reveals:**
- Verify that `core/inference/smart_routing/stats.py` tracks per-provider rolling latency averages from real requests (not just static configuration). If missing, add a 10-sample EMA update in `ProviderClient._call_*` methods.

---

## openclaw-main

**What it is:**  
OpenClaw is a sophisticated TypeScript/Node.js personal AI assistant gateway with an exceptionally deep feature set:
- **22+ messaging channels**: WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, IRC, Microsoft Teams, Matrix, Feishu, LINE, Mattermost, Nextcloud Talk, Nostr, Synapse, Tlon, Twitch, Zalo, WeChat, QQ, WebChat — with full session state machines, DM pairing/allowlists, typing indicators, ACK reactions, streaming draft controls.
- **Talk system** (`src/talk/`): real-time voice sessions — TTS (OpenAI-compatible speech providers + Mistral, DashScope), STT (Realtime WebSocket transcription), full duplex audio codec, turn tracking, agent consult runtime.
- **Image generation** (`src/image-generation/`, `packages/media-generation-core`): provider registry for image generation — OpenAI-compatible image providers, normalization, runtime types.
- **Video generation** (`src/video-generation/`): provider registry for video generation.
- **Canvas** (`skills/canvas/`): serve HTML to companion iOS/macOS/Android node apps via WebView, with live reload, snapshot, and eval.
- **Daemon mode**: `launchd` (macOS) / `schtasks` (Windows) / `systemd` (Linux) — persistent gateway stays running after reboot.
- **Skills ecosystem**: 50+ built-in skills (`skills/` directory) — `canvas`, `obsidian`, `notion`, `github`, `gh-issues`, `discord`, `tmux`, `spotify-player`, `gemini`, `openai-whisper`, `voice-call`, `summarize`, `diagram-maker`, `coding-agent`, `peekaboo` (screenshot), `healthcheck`, `taskflow`, `session-logs`, etc.
- **Agent architecture** (`src/agents/`): full multi-agent spawn, ACP protocol, MCP integration, LSP runtime, model discovery with auth, compaction rotation, live model switching.
- **Memory**: root-memory-files architecture (file-based persistent memory).
- **Security defaults**: DM pairing policy, allowlist enforcement, `openclaw doctor` for config auditing.
- **Companion native apps**: `apps/` has iOS, macOS, Android, macOS-MLX-TTS, and Swabble (shared kit).
- **Context engine**: delegate/registry/legacy context pattern.
- **Model failover**: auth profile rotation with automatic fallback.
- **Cron/scheduled tasks**: built-in cron runtime for scheduled agent runs.

**VECTOR parity:**

| OpenClaw Feature | VECTOR Status |
|---|---|
| 22+ chat channels | VECTOR has 30+ channel adapters in `vectorcode/src/channels/` |
| Session state machines | VECTOR has session management but simpler (no per-channel DM policy) |
| Talk/TTS/STT | VECTOR has `core/voice/` (Kokoro, Whisper, ElevenLabs, cloning) |
| Image generation providers | VECTOR uses ComfyUI adapter only; no provider registry |
| Video generation providers | VECTOR uses SadTalker/FFmpeg only; no provider registry |
| Canvas (HTML → native app) | VECTOR has no canvas/WebView bridge |
| Daemon mode (launchd/schtasks) | VECTOR has `scripts/install_service.ps1` (NSSM, Windows only) |
| 50+ built-in skills | VECTOR has 282 skill .md files in brain |
| MCP integration | VECTOR has `core/mcp_server.py` with 14+ tools |
| ACP agent spawn protocol | VECTOR has swarm/claims but no ACP sidecar protocol |
| Memory (file-based) | VECTOR has SQLite episodic + LightRAG RAG memory |
| Companion native iOS/macOS/Android apps | VECTOR has phone_node (Termux, Android only) |
| Model failover/auth rotation | VECTOR has `fallback_chain.py` in smart_routing |
| Cron/scheduled | VECTOR has APScheduler + `cron_jobs.py` |

**Genuinely novel features OpenClaw has that VECTOR lacks:**
1. **Canvas sidecar** — serving HTML to companion native apps via WebView. VECTOR has a web HUD but no push-to-phone WebView bridge.
2. **Image/video generation provider registry** — OpenClaw abstracts image-gen and video-gen behind a provider registry with OpenAI-compatible providers, normalization, and runtime types. VECTOR's content district only knows ComfyUI + SadTalker hardcoded.
3. **Per-channel DM security policy** (pairing codes, allowlists, `openclaw doctor`) — VECTOR's channel adapters do not implement a unified inbound security policy.
4. **Companion native apps** (iOS, macOS, Android) with Canvas WebView rendering.
5. **ACP agent spawn protocol** — standardized parent-child agent sidecar communication.

However, all of these are TypeScript services requiring Node.js 24. The integration rule applies: if a service works in any language and VECTOR doesn't have it, integrate directly.

**Integration plan:**

For the **Canvas + Companion apps** feature specifically:
- Run OpenClaw gateway as a Node.js sidecar: `openclaw gateway --port 18789`
- OpenClaw's gateway handles: channel routing, Canvas HTML serving, native app pairing.
- VECTOR loop: when a response needs to be pushed to phone/desktop, route via `vectorcode/src/channels/` → OpenClaw gateway WebSocket bridge.
- Add a VECTOR `districts/communications/openclaw_bridge.py` that wraps `openclaw message send` subprocess calls and `openclaw agent` for delegated tasks.

For the **image/video generation provider registry**:
- Absorb the provider registry pattern into `districts/content/` as a Python `ImageGenProviderRegistry` + `VideoGenProviderRegistry` (similar to the `ProviderClient` pattern for LLMs).
- Wire: ComfyUI (local) as primary, OpenAI DALL-E + Stability as cloud fallbacks.

**Verdict: PATCH VECTOR**  
The channel adapters and voice pipeline are already covered. The unique gaps are: (a) Canvas/WebView push to native apps, (b) image/video generation provider registry abstraction. Do not run OpenClaw as a full sidecar — it would duplicate VECTOR's channel management. Instead, absorb the two distinct Python-portable patterns.

**Gaps this reveals:**
- Gap: `ImageGenProviderRegistry` — content district hardcodes ComfyUI; needs a provider registry with cloud fallbacks.
- Gap: `VideoGenProviderRegistry` — same pattern for video.
- Gap: Canvas/WebView bridge — no mechanism to push HTML UI to phone companion apps.
- Gap: Per-channel inbound security policy (`dmPolicy`, `allowFrom`) missing from VECTOR channel adapters.
- Gap: `openclaw doctor`-style config health checker for channel configurations.

---

## mistral-vibe-main

**What it is:**  
Mistral Vibe is Mistral AI's open-source Python CLI coding assistant (`pip install mistral-vibe`). It is a fully-featured agentic coding tool comparable to Claude Code. Key features:
- **Agent loop** (`vibe/core/agent_loop.py`): async streaming agent loop with MCP integration, middleware pipeline (auto-compact, context warning), hooks system (PreToolUse/PostToolUse), multi-agent coordination.
- **Built-in tools** (`vibe/core/tools/builtins/`): `bash.py` (tree-sitter AST-aware bash safety), `read_file.py`, `write_file.py`, `search_replace.py`, `grep.py`, `todo.py`, `task.py` (subagent delegation), `ask_user_question.py` (interactive multi-option Q&A), `webfetch.py`, `websearch.py`, `skill.py`.
- **Built-in agents** (`vibe/core/agents/`): `default`, `plan` (read-only), `accept-edits` (auto-approve edits), `auto-approve`, `lean`, plus custom agent profiles.
- **Subagents**: `task` tool delegates to subagents; built-in `explore` read-only subagent.
- **Skills system** (`vibe/core/skills/`): markdown-based skill files discoverable from project `.vibe/` or `~/.vibe/`; `SkillManager` with filter, discovery, loading.
- **LLM backends** (`vibe/core/llm/backend/`): `anthropic.py`, `mistral.py`, `openai_responses.py`, `generic.py`, `vertex.py`, `reasoning_adapter.py` — all async, streamed.
- **TTS** (`vibe/core/tts/`): `mistral_tts_client.py`, factory, port abstraction.
- **Transcription** (`vibe/core/transcribe/`): `mistral_transcribe_client.py`, factory.
- **ACP protocol** (`vibe/acp/`): `acp_agent_loop.py`, `session.py`, `tools/builtins/` — standardized agent communication protocol with bash/grep/read/write/skill/task/todo/webfetch/websearch tools.
- **Config system** (`vibe/core/config/`): layered Pydantic config with merge strategies, harness files, patches, orchestrator.
- **Compaction** (`vibe/core/compaction.py`): context window management, prior message collection.
- **Hooks** (`vibe/core/hooks/`): PreToolUse/PostToolUse/UserMessage hooks with config-driven rules.
- **Session management** (`vibe/core/session/`).
- **Autocompletion** (`vibe/core/autocompletion/`).
- **Voice mode**: integrated via TTS + transcription clients.
- **Trust folder system**: controls which directories the agent can act in.
- **Tool permissions**: per-tool permission scopes, approval gates.

**VECTOR parity:**

| Mistral Vibe Feature | VECTOR Status |
|---|---|
| Async agent loop | VECTOR: `core/loop/autonomous_loop.py` (observe→think→act→reflect, never stops) |
| Tool system (bash/file/grep/task/todo) | VECTOR: `vectorcode/src/agent/` has LSP, tool guardrails; `core/mcp_server.py` has 14+ tools |
| Subagent delegation via `task` tool | VECTOR: `vectorcode/src/swarm.py` (8 topologies), `core/city/agent_registry.py` |
| Skills system (markdown .md) | VECTOR: 282 skill .md files in `brain/.claude/skills/` |
| LLM backends (5 providers) | VECTOR: 27 providers via `core/inference/provider_client.py` |
| TTS integration | VECTOR: `core/voice/tts.py`, Kokoro + ElevenLabs + pyttsx3 fallback |
| STT integration | VECTOR: `core/voice/stt.py` (Whisper) |
| ACP protocol | Not in VECTOR |
| Hooks (PreToolUse/PostToolUse) | VECTOR: `vectorcode/src/agent/tool_guardrails.py` |
| Layered config with Pydantic merge | VECTOR: `core/config.py` (Pydantic, SecretStr, no hardcoded keys) |
| Context compaction | VECTOR: `core/jcode/session_persistence.py`, trajectory auto-compact |
| Trust folder / permission scopes | VECTOR: `core/loop/permission_gateway.py` (GREEN/YELLOW/RED) |
| Interactive `ask_user_question` | Not in VECTOR as a tool |
| Session management | VECTOR: `core/jcode/session_persistence.py` |
| Voice mode CLI | VECTOR: `core/voice/ambient_listener.py` + wake word |

**Genuinely novel patterns in Mistral Vibe that VECTOR lacks:**

1. **`ask_user_question` tool**: The agent can pause mid-task and present structured multi-option questions to the user (tab UI). VECTOR has HumanLayer for YELLOW/RED approval gates but no structured in-task clarification tool that returns typed answers.
2. **ACP protocol** (`vibe/acp/`): Standardized agent communication protocol for parent-child agent spawning with well-typed session and tool interfaces. VECTOR's swarm uses its own protocol.
3. **Tree-sitter bash safety** in `bash.py`: Static AST analysis of bash commands before execution to detect dangerous patterns. VECTOR's `PromptInjectionScanner` is LLM-based; Vibe's is deterministic tree-sitter based — complementary, not duplicated.
4. **Agent profiles with `lean` mode** and custom profile files: fine-grained tool availability per agent role.

All of Mistral Vibe's novel patterns are pure Python, making them absorbable.

**Integration plan (PATCH VECTOR — absorb 3 patterns):**

1. **`ask_user_question` tool** → implement in `core/loop/permission_gateway.py` or as a new `core/tools/ask_user.py`. The gateway already handles HumanLayer prompts; extend to support structured multi-option questions returned as typed dicts to the calling agent.
2. **Tree-sitter bash safety** → add `pip install tree-sitter tree-sitter-bash` and implement `core/security/bash_ast_guard.py` modeled on Vibe's `bash.py`. Wire as a PreToolUse hook in `core/loop/permission_gateway.py` before any `GREEN` shell command.
3. **Agent profiles** (read-only, accept-edits, auto-approve, lean) → map to VECTOR's existing `GREEN/YELLOW/RED` policy tiers. Add named profile presets to `core/loop/permission_gateway.py` so districts can instantiate agents with a specific trust level without modifying policy scores.

Do NOT absorb: LLM backends (VECTOR has 27, Vibe has 5), ACP protocol (VECTOR's swarm is more capable), config system (VECTOR's Pydantic config is already layered), compaction (VECTOR already has jcode trajectory auto-compact), TTS/STT (VECTOR already has these).

**Verdict: PATCH VECTOR**  
Three focused Python absorptions: `ask_user_question`, tree-sitter bash safety, and agent profile presets. The rest is fully covered by VECTOR's existing modules.

**Gaps this reveals:**
- Gap: No structured in-task `ask_user_question` tool with typed multi-option responses.
- Gap: Bash command pre-execution AST safety (tree-sitter based) — current security is LLM prompt injection scanning, not static analysis.
- Gap: Named agent permission profiles — permission_gateway operates on dynamic scores; no preset profiles for quick district configuration.

---

## Summary

| Repo | Verdict | Integration method | Priority |
|---|---|---|---|
| ComfyUI-master | INTEGRATE DIRECTLY | Run as persistent sidecar on port 8188; auto-start via NSSM/run_vector.py; VECTOR adapter already wired | HIGH — blocks image/video/audio/3D generation |
| ComfyUI-Manager-main | INTEGRATE DIRECTLY | Install as ComfyUI custom node (`git clone` into `custom_nodes/`); zero VECTOR changes | MEDIUM — improves ComfyUI model/node management UX |
| openclaude-main | SAFE TO DELETE | VECTOR's 27-provider client + 4-layer MoE router subsumes everything | LOW — no new Python absorptions needed |
| openclaw-main | PATCH VECTOR | Absorb: `ImageGenProviderRegistry`, `VideoGenProviderRegistry` as Python classes in `districts/content/`; Canvas/WebView gap noted but not blocking | MEDIUM — image/video provider abstraction is genuinely missing |
| mistral-vibe-main | PATCH VECTOR | Absorb 3 patterns: `ask_user_question` tool, tree-sitter bash AST guard, named agent permission profiles | MEDIUM — ask_user_question and bash AST guard are high-quality Python utilities |

---

## New Gaps Catalogue

| Gap | Where to build | Blocking? |
|---|---|---|
| ComfyUI auto-start + health restart | `ops/sre_monitor.py` — add ComfyUI process check | Yes — blocks generation |
| ComfyUI video/audio workflow abstractions | `districts/content/comfyui_adapter.py` — add `generate_video()`, `generate_audio()` | No |
| ComfyUI LoRA injection helper | `districts/content/comfyui_adapter.py` — add LoRA param to workflow builder | No |
| ComfyUI HUD panel | `frontend/VECTOR.html` — queue depth + last image thumbnail card | No |
| `ImageGenProviderRegistry` | `districts/content/image_gen_registry.py` | No |
| `VideoGenProviderRegistry` | `districts/content/video_gen_registry.py` | No |
| Canvas/WebView push to phone companion | `districts/communications/` — new bridge | No |
| Per-channel inbound DM security policy | `vectorcode/src/channels/_abc.py` — add `dm_policy` + `allow_from` | No |
| `ask_user_question` tool | `core/tools/ask_user.py` or extend `permission_gateway.py` | No |
| Tree-sitter bash AST guard | `core/security/bash_ast_guard.py` | No |
| Named agent permission profiles | `core/loop/permission_gateway.py` — add profile presets | No |
| Per-provider rolling latency EMA in stats | `core/inference/smart_routing/stats.py` — verify EMA from real requests | No |
