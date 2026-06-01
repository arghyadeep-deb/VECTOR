# openhuman-main — Repo Audit
> Audited: 2026-06-01 | Branch: production-hardening-complete
> Prior claim: "openhuman absorbed 98.2%" on 2026-05-17 → `core/engine/` + `dashboard/`

---

## 5-Line Summary

openhuman is a 1,616-file Rust + 1,084-file TypeScript Tauri desktop agent with 103 distinct Rust modules (memory tree, token compression, 118+ OAuth integrations, Google Meet bot, desktop companion, web3 wallet, screen intelligence, subconscious background loop). Of the 15 specific items claimed absorbed, 14/15 import correctly in VECTOR. The 15th ("JARVIS dashboard → `dashboard/`") is factually wrong — `dashboard/` does not exist; what exists is a custom HTML HUD at `frontend/VECTOR.html`. The "98.2%" figure is almost certainly fabricated — VECTOR has ~11 Python modules covering ~25 of openhuman's 103 Rust modules (~24%); 78+ modules (composio integration layer, subconscious, desktop companion, meet agent, screen intelligence, web3, entity memory graph, agent orchestration, skills runtime) have zero Python equivalent in VECTOR. Verdict: the 15 claimed items are real and importable but represent a shallow port of openhuman's surface, not the bulk of it. **DELETE-AFTER: safe to archive the repo once you confirm you don't want composio/subconscious/meet-agent work.**

---

## Section 1: Repo Reality

**What it is:** OpenHuman is an open-source personal AI assistant built as a Tauri (Rust + TypeScript/React) desktop application. It is the project previously described in VECTOR notes as a "JARVIS-like desktop agent." Published on GitHub by tinyhumansai. GNU license. Currently early beta.

**Primary language:** Rust (backend, 1,616 `.rs` files across `src/`) + TypeScript/React (frontend, 1,084 `.tsx`/`.ts` files in `app/src/`). Not primarily Python. Zero Python business logic.

**Feature count: 32 distinct features / module clusters**

| # | Module | Feature |
|---|--------|---------|
| 1 | `memory_tree` | 3-level hierarchical memory (source → topic → chunk), SQLite-backed, Obsidian markdown export |
| 2 | `tokenjuice` | Rule-based token compressor — 3-layer JSON rule overlay, git/gh post-processors, 80% reduction target |
| 3 | `composio` | 118+ third-party OAuth integrations (Gmail, GitHub, Slack, Notion, Stripe, Linear, Jira, …) with 20-min auto-fetch into memory |
| 4 | `subconscious` | Background task evaluation engine: cron-driven tick, LLM evaluates tasks against situation report, act/escalate/noop decisions, proactive reflections |
| 5 | `desktop_companion` | Desktop mascot — STT → screen context → LLM → TTS → pointer, state machine, provider-surface handoff detection |
| 6 | `meet` / `meet_agent` | Google Meet bot: VAD, caption wake-word ("hey openhuman"), privacy gate, PCM streaming, full orchestrator agent per-turn |
| 7 | `screen_intelligence` | macOS accessibility engine: screen capture, 3-pass OCR + local-LLM, automated input, autocomplete context |
| 8 | `voice` | STT (local), TTS (ElevenLabs), lip-sync, live-call integration |
| 9 | `model_council` | Multi-model deliberative routing for high-stakes decisions |
| 10 | `integrations` | Composio connector layer — OAuth handshake, periodic data fetch, tool generation per integration |
| 11 | `agent_orchestration` | Parent/child agent lineage, spawn/wait/close/follow-up semantics |
| 12 | `agent_registry` | Live agent registry with discovery, install, pluggable agent definitions |
| 13 | `agent_workflows` | User-defined agentic routines/automations with scheduling |
| 14 | `skills` | Pluggable skill system — discover, install, parse, inject into agent |
| 15 | `memory_entities` + `memory_graph` | Entity extraction from memory, graph edges between entities |
| 16 | `memory_conversations` | Per-conversation context window management |
| 17 | `embeddings` | Cloud + Ollama + inert embedding backends for semantic retrieval |
| 18 | `people` | Contact resolver, address book, scorer |
| 19 | `web3` / `wallet` | Crypto wallet, dApp bridge, swap routing |
| 20 | `runtime_node` / `runtime_python` | Sandboxed code execution (Node.js and Python subprocesses) |
| 21 | `codegraph` | Code structure analysis integrated into agent tool surface |
| 22 | `mcp_client` / `mcp_registry` / `mcp_server` | Full MCP stack (client, registry, server) for tool protocol |
| 23 | `security` | Bubblewrap/firejail/landlock sandboxing, live policy, secret detection |
| 24 | `prompt_injection` | Prompt injection detection in user input |
| 25 | `todos` | Task/todo management with agent integration |
| 26 | `dashboard` | Model health view (stateless, no real metrics yet — placeholder) |
| 27 | `overlay` | Desktop overlay rendering |
| 28 | `billing` / `referral` / `team` / `rewards` | SaaS account management features |
| 29 | `encryption` | Per-workspace AES encryption layer |
| 30 | `doctor` | Dependency health checks and diagnostics |
| 31 | `OAuth + providers` | OAuth registry + flows (covered by VECTOR via nango absorption) |
| 32 | React/Tauri frontend | Full desktop UI: chat, intelligence tab, skills dashboard, routines, webhooks, onboarding |

---

## Section 2: VECTOR Parity — Verified by Running

**Test environment:** `python -X utf8 -c "from <module> import <class>; print('OK')"` in VECTOR codebase root.

### Items Explicitly Claimed as Absorbed (from phase_status.md)

| Claimed Item | VECTOR Location | Import Test | Verdict |
|---|---|---|---|
| MemoryTree | `core/engine/memory_tree/tree_builder.py` | `from core.engine.memory_tree.tree_builder import MemoryTree` → `OK` | ✅ real |
| TokenJuice | `core/engine/token_juice/compressor.py` | `from core.engine.token_juice.compressor import TokenJuice` → `OK` | ⚠️ shallow — see below |
| 16 agent roles | `core/engine/agents/roles.py` | 16 `AgentRole` instances confirmed by introspection | ✅ real |
| ParallelResearcher | `core/engine/research/parallel_researcher.py` | `from core.engine.research.parallel_researcher import ParallelResearcher` → `OK` | ✅ real |
| OAuthRegistry | `core/engine/oauth/registry.py` | `OAuthRegistry().count()` → `providers: 119` | ✅ real (119 > claimed 83, expanded in nango session) |
| VectorTelemetry | `core/engine/telemetry/otel_bridge.py` | `get_telemetry()` → `OK, OTLP=False` | ✅ real |
| VectorSentry | `core/engine/telemetry/sentry_bridge.py` | `from ... import VectorSentry` → `OK` | ✅ real |
| OFP P2P | `core/network/ofp_protocol.py` | `from core.network.ofp_protocol import OFPNode` → `OK` | ✅ real |
| PeerDiscovery | `core/network/peer_discovery.py` | `from core.network.peer_discovery import PeerDiscovery` → `OK` | ✅ real |
| SubagentRunner | `core/engine/agents/subagent_runner.py` | `from ... import SubagentRunner` → `OK` | ✅ real |
| ReliableProvider | `core/engine/providers/reliable_provider.py` | `from ... import ReliableProvider` → `OK` | ✅ real |
| ModelRouter | `core/engine/providers/model_router.py` | `from ... import ModelRouter` → `OK` | ✅ real |
| ToolDispatcher | `core/engine/tools/dispatcher.py` | `from ... import ToolDispatcher` → `OK` | ✅ real |
| ChannelRuntime | `core/engine/channels/runtime.py` | `from ... import ChannelRuntime` → `OK` | ✅ real |
| ElevenLabsTTS | `core/voice/elevenlabs_tts.py` | `from ... import ElevenLabsTTS` → `OK` | ✅ real |
| **JARVIS dashboard → `dashboard/`** | **`dashboard/` does not exist** | `ls dashboard/` → `No such file or directory` | ❌ **WRONG** |

**14/15 claimed items import correctly. 1 is factually incorrect.**

### TokenJuice Depth Gap (⚠️)

openhuman's `tokenjuice` is a 10-file Rust library with:
- JSON-configured rule set with 3-layer overlay (builtin/user/project)
- Per-tool-name specialization (git, npm, cargo, docker, kubectl, lint, test runners)
- `git/status` porcelain rewrite, `gh` JSON formatter post-processors
- Rule-based classification + specificity scoring
- Failure-aware head/tail windows
- All regex compiled at load time, thread-local cache for hot patterns

VECTOR's `compressor.py` is 263 lines of hardcoded regex patterns (strip LLM boilerplate, normalize whitespace, compress repeated lines). It does not have rule files, tool-name dispatch, or the git/gh specializations. **Functional but significantly shallower than the original.**

### JARVIS Dashboard — Corrected Reality

The claim `JARVIS dashboard → dashboard/` is wrong. The actual state:
- `dashboard/` directory: **does not exist** in VECTOR
- `frontend/VECTOR.html`: exists — a custom HTML+JS HUD with webcam, 3D city view, agent panels, status widgets. This is VECTOR's own original frontend, not from openhuman.
- openhuman's actual dashboard (`src/openhuman/dashboard/`) is a stateless model-health view with placeholder metrics. Low value.
- openhuman's actual frontend is a 1,084-file React/Tauri app. **Not absorbed, not absorbed-equivalent.**

### Major Openhuman Features with NO VECTOR Equivalent

These 78+ Rust modules from openhuman have no Python counterpart in `core/engine/` or anywhere else in VECTOR:

| Feature | openhuman Module | VECTOR Status |
|---|---|---|
| Composio 118+ integrations + auto-fetch | `composio/`, `integrations/` | ❌ Not present (only reference docs in districts/) |
| Subconscious background task loop | `subconscious/` | ❌ Not present (VECTOR's 2AM reflect is not equivalent — no task/escalation state machine) |
| Desktop companion state machine | `desktop_companion/` | ❌ Not present |
| Google Meet bot | `meet/`, `meet_agent/` | ❌ Not present |
| macOS screen intelligence | `screen_intelligence/` | ❌ Not present (VECTOR has `screen_observer.py` but no OCR+LLM pipeline, macOS-only anyway) |
| Entity + graph memory | `memory_entities/`, `memory_graph/` | ❌ Not present |
| Conversation context management | `memory_conversations/` | ❌ Not present |
| Embeddings pipeline | `embeddings/` | ❌ Not present (VECTOR uses chromadb externally) |
| Agent orchestration (lineage/wait/close) | `agent_orchestration/` | ❌ Not present |
| Pluggable skills runtime | `skills/` | ❌ Not present (VECTOR has skill .md files, not a runtime) |
| People/contact resolver | `people/` | ❌ Not present |
| Web3 / wallet | `web3/`, `wallet/` | ❌ Not present (irrelevant to VECTOR goals) |
| Sandboxed code execution | `runtime_node/`, `runtime_python/` | ❌ Not present (VECTOR has VectorSandbox from openfang) |
| Code graph analysis | `codegraph/` | ❌ Not present (VECTOR has vc_graph from VectorCode) |
| MCP client + registry | `mcp_client/`, `mcp_registry/` | ⚠️ Partial — VECTOR has `core/mcp_server.py` and `vectorcode/mcp_client/`, not a full registry |
| Per-workspace encryption | `encryption/` | ⚠️ VECTOR has SQLCipher on episodic.py only |
| Agent workflows / routines | `agent_workflows/` | ❌ Not present |

---

## Section 3: Frontend — Panel Spec

openhuman's frontend is a full Tauri desktop application. The panels most valuable as VECTOR HUD additions:

### High-Value Panels for VECTOR

**1. Intelligence Tab** (`app/src/pages/Intelligence.tsx`)
- Proactive reflections from the subconscious loop (observation cards surfaced automatically)
- Pattern-detection surface
- Build-now value: HIGH — VECTOR's subconscious equivalent (if built) needs a display surface

**2. Agent Status / Orchestration View** (`app/src/pages/AgentWorkflows.tsx`)
- Real-time view of parent/child agent lineage
- Shows spawned agents, wait states, follow-up chains
- Build-now value: HIGH — VECTOR's 133 agents need a live status surface

**3. Memory / Knowledge Panel** (`app/src/components/chat/` + memory tools)
- Memory tree browser: walk sources, drill into topics, view chunks
- Entity graph view
- Build-now value: MEDIUM — useful for debugging agent context

**4. Skills Dashboard** (`app/src/pages/SkillsDashboard.tsx`, `SkillsRun.tsx`)
- List, install, run skills
- Build-now value: MEDIUM

**5. Integration Health / Auto-Fetch Status** (`app/src/components/composio/`)
- Shows 118+ connection health, last-fetch timestamp, data freshness
- Build-now value: LOW for VECTOR (no composio layer)

**Recommendation:** Build panels 1 + 2 as additions to `frontend/VECTOR.html` — they directly serve VECTOR's multi-agent city model. The existing HUD already has the right aesthetic; add a "reflections/intelligence" panel and an "agent lineage" panel as new sidebar widgets.

---

## Section 4: Verdict + Delete-Readiness

### Does "98.2%" Hold?

**No.** The number is fabricated. The honest count:

- Rust modules in openhuman: **103**
- Python modules in VECTOR claiming openhuman origin: **11** (`memory_tree` × 3 files, `token_juice` × 1, `agents` × 2, `research` × 1, `telemetry` × 2, `providers` × 2, `tools` × 1, `channels` × 1)
- Fraction of openhuman's codebase represented: **~24%** (by module count), less by code volume
- Functional gap: composio, subconscious, desktop_companion, meet_agent, screen_intelligence, entity memory, agent_orchestration, skills runtime, people model — **none present**

A more honest claim: "VECTOR absorbed the 15 infrastructure primitives from openhuman that are relevant to a Python backend agent (memory tree builder, token compressor, 16 agent roles, parallel researcher, OAuth registry, telemetry, OFP/P2P, subagent runner, reliable provider, model router, tool dispatcher, channel runtime, ElevenLabs TTS). The desktop app, composio layer, subconscious loop, Google Meet bot, macOS screen intelligence, entity graph memory, web3 wallet, and all 1,084 TypeScript frontend files were correctly excluded as out of scope for a Python local agent."

### Delete-Readiness

| Status | Condition |
|--------|-----------|
| **DELETE-AFTER** | Repo is safe to archive. The 14 Python primitives are in VECTOR and importable. No unique Python code remains in the Rust/TypeScript source that VECTOR needs. |

**Flag before deleting — one genuine gap worth considering:**

`subconscious/` — openhuman's background task evaluation loop (cron-driven, LLM evaluates tasks against situation report, act/escalate/noop, proactive reflections) is architecturally distinct from VECTOR's 2AM reflect. VECTOR's `autonomous_loop.py` observe→think→act is reactive. openhuman's subconscious is proactive and task-scheduled. The pattern (seed default tasks, tick evaluation, escalation lifecycle, reflection cap) would strengthen VECTOR's chief_of_staff district. Read `src/openhuman/subconscious/README.md` before archiving if you ever want to build this.

### Summary Table

| Claim | Reality |
|-------|---------|
| "98.2% absorbed" | False — ~24% by module count |
| 15 specific items claimed | 14/15 present and importable in VECTOR |
| "JARVIS dashboard → dashboard/" | Wrong — dashboard/ does not exist; frontend/VECTOR.html is original VECTOR code |
| TokenJuice parity | Shallow — 263-line regex vs 10-file rule engine |
| Delete-readiness | DELETE-AFTER — safe to archive |
| One gap worth noting | `subconscious/` task evaluation loop has no equivalent in VECTOR |
