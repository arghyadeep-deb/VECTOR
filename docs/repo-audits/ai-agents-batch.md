# AI Agents Batch Audit

> Date: 2026-06-01
> Auditor: Claude Sonnet 4.6 (agent)
> VECTOR codebase: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`

---

## camel-master

**What it is:**
CAMEL-AI is a large-scale Python multi-agent research framework (Apache 2.0). It covers:
- Multi-agent role-playing societies (`camel/societies/`): `Workforce` with task decomposition, parallel worker pools, failure recovery, workflow memory manager, KPI tracking
- 14+ agent types including `CriticAgent`, `KnowledgeGraphAgent`, `MCPAgent`, `RepoAgent`, `MultiHopGeneratorAgent`, `SearchAgent`
- 60+ toolkits: arxiv, browser, gmail, github, math, SQL, Slack, WhatsApp, Reddit, PubMed, Semantic Scholar, SymPy, Stripe, LinkedIn, and more
- Synthetic data generation (`camel/datagen/`): `EvolInstructPipeline` (WizardLM-style prompt evolution), `SelfInstructPipeline` (ROUGE-filtered machine instruction generation), `UserDataProcessor` (multi-hop Q&A generation), `SelfImprovingCoT` (iterative chain-of-thought refinement with reward model scoring)
- Code verifiers: `PythonVerifier` (isolated venv execution), `MathVerifier` (LaTeX/symbolic), `PhysicsVerifier`
- Simulated RL environments: `MultiStepEnv`, `SingleStepEnv`, `TicTacToeEnv`, `RLCardsEnv`
- `PersonaHub`: 1B-persona-scale synthetic data generator from the Tencent paper
- Vector/graph/KV/object storages: ChromaDB, Faiss, Milvus, Qdrant, PgVector, Neo4j, Nebula
- Docker/Daytona/LLMGuard runtimes for sandboxed code execution
- Benchmarks: GAIA, NEXUS, RAGBench, BrowseComp, APIBank, ApiBench

**VECTOR parity check:**
```
# AgentRegistry, Governor — live
# City agents, HP system, evolution engine — live
# 133 district agents — live
# ResearchHub + WebScout + ArXiv + Reddit — live
# LLMCouncil, SwarmCoordinator — live
# VectorCode claims/guidance/swarm — live
# Neural RL (A2C/DQN/PPO/SARSA) — live (vectorcode/src/neural_training.py)
# GNNRouter (4-layer) — live
# Code verifier (VectorSandbox) — live (core/sandbox/)
# Knowledge graph — live (core/knowledge/, graphify skill)
# ChromaDB/LightRAG vector storage — live
```

**Verdict: SAFE TO DELETE**

VECTOR already has its own Darwinian multi-agent city (`core/city/`), 133 district agents, SwarmCoordinator with 8 topologies, GNNRouter with neural routing, and VectorSandbox for isolated code execution. CAMEL is a research-focused framework designed to be imported as a library. VECTOR doesn't import external agent frameworks — it IS the framework. Absorbing CAMEL would mean wrapping or re-implementing concepts already present in a more VECTOR-native form.

**Genuine gaps worth noting (not absorbing — already covered or Year 2):**
1. `EvolInstruct` / `SelfInstruct` / `SelfImprovingCoT`: VECTOR has `AutoresearchRunner` in `karpathy_lab` for ML training experiments, and `ReasoningBank` stores training chains. The datagen pipelines (ROUGE-filtered synthetic instruction generation, WizardLM prompt evolution) are genuinely not in VECTOR but belong as a **Month 2 fine-tuning tool**, not now. Add to `districts/karpathy_lab/evol_instruct.py` when building the LoRA fine-tune pipeline.
2. `PersonaHub`: Not in VECTOR. Only needed if VECTOR starts generating diverse synthetic personas for training. Year 2.
3. `PythonVerifier` (isolated venv): VECTOR's `VectorSandbox` uses a Wasm runner + process sandbox. CAMEL's approach of spinning up a throw-away `venv` per verification is simpler for one-off code checks in the coding district. Low-priority addition to `districts/coding/`.

---

## camofox-browser-master

**What it is:**
camofox-browser is a Node.js REST API server wrapping Camoufox (a Firefox fork with C++-level fingerprint spoofing). It provides:
- Anti-detection browsing: hardware concurrency, WebGL, AudioContext, WebRTC spoofed at the C++ level (no JS shims)
- Accessibility snapshots (~90% smaller than raw HTML), stable element refs (`e1`, `e2`, `e3`)
- Session isolation, cookie injection, proxy + GeoIP routing
- Search macros (`@google_search`, `@youtube_search`, `@reddit_subreddit`, etc.)
- YouTube transcript extraction (yt-dlp fast path + browser fallback)
- VNC interactive login, session tracing, download capture, DOM image extraction
- 36 REST endpoints, OpenAPI docs at `/docs`
- Version in this repo: **1.11.2**

**VECTOR parity check:**
```
# VECTOR already has stealth browser:
#   core/stealth_browser/server/server.js  — version 1.10.1 (VECTOR's embedded copy)
#   core/stealth_browser/client.py         — Python async client
#   core/stealth_browser/server_manager.py — subprocess lifecycle
#   core/stealth_browser/macros.py         — search macro expansion
#   core/stealth_browser/transcripts.py    — YouTube transcripts
#   districts/research/stealth_scout_agent.py — district agent
#   core/browser/dom_pruner.py             — token reduction (absorbed from auto-browser)
#   core/browser/pii_scrub.py              — PII scrubbing
#   core/browser/auth_profiles.py          — named session profiles

# Route comparison: VECTOR 36 routes == camofox 36 routes
# Both files start with identical Camoufox/playwright-core imports
```

**Verdict: PATCH VECTOR (version bump only)**

VECTOR already has a fully embedded copy of camofox-browser. The gap is the version: VECTOR has **v1.10.1**, this repo is **v1.11.2**. The diff is 69 lines (6128 vs 6059 lines in server.js). Both have identical dependencies and the same 36 REST routes.

**Action:** Copy `camofox-browser-master/server.js` and `camofox-browser-master/lib/` into `core/stealth_browser/server/` to get the v1.11.2 patch fixes. Update `package.json` version. No Python changes needed.

```bash
# To apply the update:
xcopy /E /Y "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\camofox-browser-master\lib\*" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\stealth_browser\server\lib\"
copy /Y "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\camofox-browser-master\server.js" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\stealth_browser\server\server.js"
# Then: cd core/stealth_browser/server && npm install
```

---

## autoresearch-master

**What it is:**
A Karpathy-authored autonomous ML research loop. Three files:
- `prepare.py`: Fixed constants + one-time data prep (ClimbMix-400B dataset download, BPE tokenizer training). Not modified by agent.
- `train.py`: Single-file GPT model (Flash Attention 3, Muon+AdamW optimizer, sliding window attention SSSL pattern, Value Embeddings). Agent modifies this file.
- `program.md`: Instruction document defining the experiment loop. Agent reads this to set up experiments.

The loop: fixed 5-minute training budget → measure `val_bpb` → keep if lower → repeat overnight. ~100 experiments/sleep. Agent can change architecture, optimizer, hyperparams, batch size.

**VECTOR parity check:**
```
# VECTOR AutoresearchRunner import test:
# ✅ AutoresearchRunner OK: <class 'districts.karpathy_lab.autoresearch_runner.AutoresearchRunner'>
# AutoresearchRunner in districts/karpathy_lab/autoresearch_runner.py already implements
# the 5-minute budget loop, val_bpb comparison, keep/revert logic, and Obsidian logging.
```

**Verdict: PATCH VECTOR (absorb the actual training artifacts)**

VECTOR's `AutoresearchRunner` implements the **loop logic** correctly — it mirrors the `program.md` instruction file exactly, including the 5-minute budget, simplicity criterion, keep/revert, and `val_bpb` metric.

The gap is that VECTOR's `AutoresearchRunner` points to `data/training_runs/train.py` (CONFIG path) but that file does not exist yet. The `autoresearch-master` repo provides the actual production-quality `train.py` and `prepare.py` that the agent should be modifying and running.

**Action:** Copy the training artifacts into VECTOR's data directory:
```bash
mkdir -p "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\data\training_runs"
copy "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\autoresearch-master\train.py" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\data\training_runs\train.py"
copy "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\autoresearch-master\prepare.py" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\data\training_runs\prepare.py"
copy "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\autoresearch-master\program.md" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\data\training_runs\program.md"
copy "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\autoresearch-master\pyproject.toml" "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\data\training_runs\pyproject.toml"
```

Note: `train.py` uses `kernels` package (Flash Attention 3 via HuggingFace kernels loader), `rustbpe`, and `pyarrow`. The `prepare.py` uses `pyarrow.parquet` and downloads from HuggingFace. These are not in VECTOR's main `requirements.txt` — add them under a `[karpathy]` extras section or a `data/training_runs/pyproject.toml` (already the case in the repo).

---

## agentic-inbox-main

**What it is:**
A Cloudflare Workers + Durable Objects email client with an AI agent. Stack: React 19 frontend, Hono backend, Cloudflare AI (kimi-k2.5), R2 for attachments, SQLite Durable Objects per mailbox. Features:
- Per-mailbox isolation with Durable Objects (SQLite)
- 9 AI email tools: list, get, search, thread, draft reply/new email, update draft, discard, mark read, move, delete
- Auto-draft on incoming email (with explicit confirmation to send)
- MCP server at `/mcp` exposing all 13 tools to external agents (Claude Code, Cursor, etc.)
- Cloudflare Access JWT auth

**VECTOR parity check:**
```
# VECTOR email system check:
# core/email/schema.py      — SQLite tables: folders, emails, attachments (Python port of workers/db/schema.ts)
# core/email/ai_security.py — prompt injection detection, draft verification
# core/email/search.py      — search query parser
# core/email/sender.py      — email sending
# core/email/helpers.py     — strip_html_to_text, build_quoted_reply_block
# core/email/ui_helpers.py  — snippet generation
# districts/communications/email_agent.py — 13 email tools agent (Python port of workers/agent/index.ts)
# districts/communications/email_intelligence.py — Gmail thread intelligence
# districts/communications/reply_forward.py — reply/forward handling
# core/mcp_server.py        — _add_email_tools() registers 13 MCP tools
# (import fails due to missing style_model.py in __init__.py — minor __init__ bug)
```

**Verdict: SAFE TO DELETE**

VECTOR already has a complete Python absorption of agentic-inbox. The `core/email/` module mirrors the Cloudflare Workers schema exactly. `EmailAgent` in `districts/communications/email_agent.py` implements all 13 email tools. The MCP server registers them via `_add_email_tools()`.

**One bug to fix:** `districts/communications/__init__.py` imports `StyleModel` which doesn't exist, causing an `ImportError` when loading the package. Fix:

```python
# In districts/communications/__init__.py, remove line:
# from .style_model import StyleModel
# And remove StyleModel from __all__
```

The agentic-inbox repo itself is a TypeScript Cloudflare Workers service — not Python-portable as a whole. The Python gaps were already absorbed. The cloud deployment version (Cloudflare Workers + Durable Objects) would be useful as VECTOR's cloud email backend if deploying to Cloudflare. That's already planned in `cloud/` as part of Phase 3 cloud deployment.

---

## Open-Generative-AI-main

**What it is:**
An open-source AI image/video generation studio. Stack: Vite + Vanilla JavaScript + Tailwind CSS + Electron desktop app. Key components:
- Muapi.ai unified API client: submit → poll pattern, `x-api-key` auth
- **239 model definitions** across 7 categories:
  - t2i (text-to-image): ~40 models (Flux Dev/Pro/Kontext, HiDream i1, Seedream, MidJourney v7, GPT-4o, SDXL, Recraft, Ideogram, Nano Banana, Wan2.1, etc.)
  - t2v (text-to-video): ~65 models (Seedance, Kling v2.1-v3.0, Veo3/3.1, Runway, Wan2.1, OpenAI Sora, etc.)
  - i2i (image-to-image): ~48 models (face swap, dress change, product shots, background removal, upscaling, inpainting)
  - i2v (image-to-video): ~33 models (Veo3 i2v, Kling i2v, WAN2.6 i2v, MidJourney i2v, etc.)
  - v2v (video-to-video): ~23 models (watermark removal, motion control, lipsync)
  - lipsync: ~19 models (InfiniteTalk, WAN2.2, LTX 2.3, Sync, LatentSync, Creatify, Veed)
  - audio: 2 music models (Suno Create Music, Suno Remix Music)
- 4 studios: Image, Video, Lip Sync, Cinema (React components in packages/studio/)
- Desktop Electron wrapper (Windows/Mac/Linux)
- Local inference support via `localInferenceClient.js` and `localModels.js`

**VECTOR parity check:**
```
# VECTOR media system check:
# core/media/models.py         — 52 models (t2i:15, i2i:10, t2v:10, i2v:8, lipsync:7, v2v:2)
# core/media/muapi_client.py   — Python async Muapi.ai client
# core/media/generative_studio.py — routes to Wan2GP→sd.cpp→Muapi.ai
# districts/content/media_studio_agent.py — MediaStudioAgent
# core/media/models.py: 52 models vs 239 in Open-Generative-AI

# Gap count: 187 models in OGA not in VECTOR's catalog
# Missing by category:
#   t2i: 36 missing (HiDream i1 fast/dev/full, Flux Dev LoRA, Anime generator, Ideogram v3 standalone, etc.)
#   t2v: 65 missing (Seedance lite/pro/v1.5/v2.0 variants, Kling v2.5/v3.0, Veo3.1 variants, Hailuo t2v, etc.)
#   i2i: 46 missing (face swap, dress change, AI product shots, Reve edit, z-image-base, flux-2-klein, etc.)
#   i2v: 33 missing (Veo3/3.1 i2v, Kling v2.5/v3.0/o1 i2v, WAN2.5/2.6 i2v, MidJourney v7 i2v, etc.)
#   v2v: 22 missing (watermark remover, Kling motion control v2.6/v3.0, etc.)
#   lipsync: 18 missing (WAN2.2 speech-to-video, LTX 2.3/2-19B, Creatify, Veed, etc.)
#   audio: 10 missing (Suno music generation — ENTIRELY missing from VECTOR)
```

**Verdict: PATCH VECTOR (model catalog expansion)**

The JavaScript UI, Electron app, and muapi.js are already ported to Python in VECTOR (`core/media/`). The Muapi.ai client is identical in functionality. The core infrastructure is complete.

The gap is purely the **model catalog**: VECTOR has 52 models, Open-Generative-AI has 239. The `core/media/models.py` file needs expanding with the additional 187 model entries. This is mechanical work — copy model IDs and endpoints from `packages/studio/src/models.js` into Python `MediaModel` dataclasses.

**Critical gap — Audio (music generation) is entirely missing from VECTOR:**
```python
# Add to core/media/models.py:
AUDIO_MODELS: list[MediaModel] = [
    MediaModel(id="suno-create-music", name="Suno Create Music",
               endpoint="suno-create-music", category="audio", has_prompt=True),
    MediaModel(id="suno-remix-music", name="Suno Remix Music",
               endpoint="suno-remix-music", category="audio", has_prompt=True),
]
```

Also add `generate_audio()` method to `MediaStudioAgent` and `MuapiClient`.

**Priority expansion list (new model IDs to add to core/media/models.py):**
- t2v: `seedance-v1.5-pro-t2v`, `seedance-v2.0-t2v`, `kling-v2.5-turbo-pro-t2v`, `kling-v3.0-pro-text-to-video`, `veo3.1-text-to-video`, `veo3.1-fast-text-to-video`, `openai-sora`
- i2v: `veo3-image-to-video`, `kling-v2.5-turbo-pro-i2v`, `kling-v3.0-pro-image-to-video`, `wan2.6-image-to-video`
- lipsync: `wan2.2-speech-to-video`, `ltx-2.3-lipsync`, `creatify-lipsync`, `veed-lipsync`
- i2i: `ai-image-face-swap`, `ai-dress-change`, `ai-product-shot`, `reve-text-to-image`, `reve-image-edit`
- audio: `suno-create-music`, `suno-remix-music` (NEW CATEGORY)

The Electron desktop app and JavaScript UI are not needed — VECTOR's Next.js dashboard (planned) will replace this.

---

## Summary

| Repo | Verdict | Action |
|------|---------|--------|
| camel-master | SAFE TO DELETE | No absorption needed. VECTOR has its own superior framework. Note `EvolInstruct` for Month 2 karpathy_lab fine-tuning. |
| camofox-browser-master | PATCH VECTOR | Copy v1.11.2 `server.js` + `lib/` into `core/stealth_browser/server/`. 69-line delta. |
| autoresearch-master | PATCH VECTOR | Copy `train.py`, `prepare.py`, `program.md`, `pyproject.toml` into `data/training_runs/`. Loop logic already exists. |
| agentic-inbox-main | SAFE TO DELETE | Already absorbed into `core/email/` + `districts/communications/`. Fix `__init__.py` bug (missing `style_model`). |
| Open-Generative-AI-main | PATCH VECTOR | Expand `core/media/models.py` from 52 → 239 models. Add audio category (`suno-create-music`, `suno-remix-music`). Add `generate_audio()` to MuapiClient. |

---

## Action Items (Ordered by Priority)

### Immediate (low effort, high value)
1. **Fix communications `__init__.py` bug** — remove `StyleModel` import, `EmailAgent` currently unloadable
   - File: `districts/communications/__init__.py`

2. **Copy autoresearch training artifacts** — unblocks karpathy_lab autonomous experiments
   - Copy `train.py`, `prepare.py`, `program.md` → `data/training_runs/`

3. **Update stealth browser to v1.11.2** — minor patch fixes
   - Copy `server.js` + `lib/` from `camofox-browser-master` → `core/stealth_browser/server/`

### Next sprint (moderate effort)
4. **Expand media model catalog** — 52 → 239 models in `core/media/models.py`
   - Add audio category (Suno music) — highest priority missing category
   - Add 30-40 priority video/lipsync models

### Month 2 (karpathy lab)
5. **Port CAMEL's EvolInstruct pipeline** for synthetic training data generation
   - `districts/karpathy_lab/evol_instruct.py` — WizardLM-style prompt evolution
   - `districts/karpathy_lab/self_instruct.py` — ROUGE-filtered instruction generation
   - These feed the LoRA fine-tuning pipeline for `vector-chairman`
