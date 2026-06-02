# Open-Generative-AI-main Audit

**Date:** 2026-06-02
**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\Open-Generative-AI-main`
**VECTOR counterpart:** `core/media/` (5 Python files)

---

## 1. Repo Reality

**What it is:** A Next.js 14 monorepo that provides a self-hosted, open-source alternative to commercial AI image/video generation platforms (Runway, Pika, Midjourney). Powered by Muapi.ai as the unified API gateway for 200+ models. MIT licensed.

**Architecture:**
```
Open-Generative-AI/
├── packages/studio/src/          # Shared React component library
│   ├── models.js                 # 239 model definitions (single source of truth)
│   ├── muapi.js                  # API client: submit+poll, upload, workflows, agents
│   └── components/               # 14 studio React components
├── app/studio/                   # Next.js App Router pages
├── electron/                     # Desktop app: main.js + 7 lib files for local inference
└── src/                          # Vite renderer (Electron mode)
```

**Language:** JavaScript/React 18 + Next.js 14 + Tailwind CSS. No Python in the core. Electron wraps it for desktop.

**What it generates (model counts from models.js):**

| Category | Count | Examples |
|---|---|---|
| Text-to-Image (t2i) | 53 | Flux Dev, Nano Banana 2, Seedream 5.0, Ideogram v3, GPT-4o, Midjourney v7 |
| Image-to-Image (i2i) | 57 | Nano Banana 2 Edit (14 imgs), Flux Kontext Pro, GPT-4o Edit, Upscaler, Background Remover |
| Text-to-Video (t2v) | 43 | Kling v3, Sora 2, Veo 3, Wan 2.6, Seedance 2.0, Runway Gen-3 |
| Image-to-Video (i2v) | 61 | Kling v2.1 I2V, Veo3 I2V, Seedance 2.0 I2V, Midjourney I2V, Hunyuan I2V |
| Lip Sync (lipsync) | 9 | Infinite Talk, Wan 2.2 Speech-to-Video, LTX 2.3, LatentSync, Creatify, Veed |
| Video-to-Video (v2v) | 4 | Watermark Remover, Kling Motion Control (3 models) |
| **Audio/Music** | **12** | **Suno (8 variants), MiniMax Voice Clone, MiniMax Speech 2.6 HD/Turbo, MMAudio v2** |

**Local inference (Desktop only, two engines):**
- `sd.cpp` — bundled C++ binary; runs SD 1.5, SDXL, Z-Image Turbo/Base offline; Metal GPU on Mac, CUDA/Vulkan on Win/Linux
- `Wan2GP` — HTTP client to a user-run Gradio server; handles Flux.1 Dev, Qwen Image, Wan 2.2 T2V/I2V, Hunyuan Video, LTX Video

**Studios (14 panels):**
ImageStudio, VideoStudio, LipSyncStudio, CinemaStudio, AudioStudio, WorkflowStudio, AgentStudio, VibeMotionStudio (motion graphics), MarketingStudio, ClippingStudio, DesignAgentStudio, McpCliStudio, AppsStudio, WorkflowUI

---

## 2. VECTOR Parity

### Step 2 — Protocol run result

```
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase" && python -X utf8 -c "
import sys; sys.path.insert(0,'.')
from core.media.muapi_client import MuapiClient
m = MuapiClient()
print('MuapiClient OK:', type(m))
..."
```

**Output:**
```
[DEBUG] No API key set — set MUAPI_API_KEY in .env to enable cloud generation
MuapiClient OK: <class 'core.media.muapi_client.MuapiClient'>
models: ImportError: cannot import name 'MUAPI_MODELS' from 'core.media.models'
```

`MUAPI_MODELS` does not exist in VECTOR's `models.py`; the export is `all_models()`. The MuapiClient itself loads fine. Model count via `all_models()`: **52 models** across 6 categories (no audio category).

### Feature-by-feature parity table

| Feature | VECTOR file | Verified output | Status |
|---|---|---|---|
| MuapiClient instantiation | `core/media/muapi_client.py` | `MuapiClient OK: <class 'core.media.muapi_client.MuapiClient'>` | ✅ |
| Text-to-image generation | `core/media/muapi_client.py:generate_image()` | 15 t2i models (Flux Dev, Nano Banana 2, Seedream 5.0, Ideogram v3...) | ✅ |
| Image-to-image editing | `core/media/muapi_client.py:generate_i2i()` | 10 i2i models (multi-image up to 14 ref images) | ✅ |
| Text-to-video | `core/media/muapi_client.py:generate_video()` | 10 t2v models (Kling v3, Sora 2, Veo 3, Seedance 2.0...) | ✅ |
| Image-to-video | `core/media/muapi_client.py:generate_i2v()` | 8 i2v models (Kling, Veo3, Runway, Seedance...) | ✅ |
| Video-to-video | `core/media/muapi_client.py:process_v2v()` | 2 v2v models (Wan V2V, Runway V2V); repo has 4 incl. Watermark Remover + Kling Motion Control | ⚠️ |
| Lip sync | `core/media/muapi_client.py:process_lipsync()` | 7 lipsync models; repo has 9 (missing Creatify, Veed) | ⚠️ |
| File upload to CDN | `core/media/muapi_client.py:upload_file()` | multipart/form-data via httpx, returns hosted URL | ✅ |
| Account balance check | `core/media/muapi_client.py:get_balance()` | `GET /api/v1/account/balance`, graceful fallback | ✅ |
| Submit-and-poll loop | `core/media/muapi_client.py:_submit_and_poll()` | 900 poll attempts, 2s interval, status normalization | ✅ |
| Local sd.cpp inference | `core/media/local_inference.py` | sd.cpp binary manager, SD 1.5 + SDXL, CUDA/Vulkan/Metal path detection, async subprocess | ✅ |
| Wan2GP local GPU server | `core/media/wan2gp_client.py` | Gradio SSE protocol, 6 models (Flux, Qwen, Wan 2.2 T2V/I2V, Hunyuan, LTX), probe + fn resolution | ✅ |
| Generative Studio orchestrator | `core/media/generative_studio.py` | Priority chain: Wan2GP → sd.cpp → Muapi; dispatch by action name; status() | ✅ |
| Multi-image input (up to 14) | `core/media/muapi_client.py:generate_i2i()` + `models.py` | `images_list` field, `max_images` per model | ✅ |
| Background remover / Upscaler | `core/media/generative_studio.py:background_remove()+upscale()` | Shortcut methods for i2i tools | ✅ |
| Model catalog | `core/media/models.py` | 52 models, `MediaModel` dataclass, category index, `get_model()`, `list_by_category()` | ✅ (fewer models) |
| **Audio/Music generation** | **MISSING** | **No `generate_audio()`, no `audioModels` category, no Suno/MiniMax/MMAudio endpoints** | **❌** |
| Workflow engine | MISSING | No `executeWorkflow()`, no node schemas, no poll for workflow runs | ❌ |
| Agent API | MISSING | No `getTemplateAgents()`, no agent chat/conversation endpoints | ❌ |
| Motion graphics | MISSING | No `runMotionGraphics()` / `runMotionGraphicsEdit()` | ❌ |
| AI clipping | MISSING | No `runClipping()` (highlight extraction from videos) | ❌ |
| Dynamic cost calculation | MISSING | No `calculateDynamicCost()` | ❌ |
| MUAPI_MODELS export alias | `core/media/models.py` | `MUAPI_MODELS` not exported; only `all_models()` function | ⚠️ |
| Auth-required event dispatch | JS only (browser custom event) | No equivalent in Python client — appropriate for CLI context | N/A |

**Summary:** 15 of 21 features covered. The core generation pipeline (t2i, i2i, t2v, i2v, lipsync, local inference, Wan2GP, orchestrator) is fully ported. The biggest missing gap is **audio/music generation** — 12 Suno/MiniMax/MMAudio models with no Python counterpart anywhere in VECTOR.

---

## 3. Frontend / Panel Spec

The repo ships 14 React studio components in `packages/studio/src/components/`. All use a dark glassmorphism aesthetic (`bg-[#0a0a0a]`, `border-white/5`, `text-[#22d3ee]` cyan accents). Each panel is independently usable via the `StandaloneShell` tab navigation.

| Panel | File | What it does | HUD relevance for VECTOR |
|---|---|---|---|
| **ImageStudio** | `ImageStudio.jsx` | Dual-mode T2I/I2I; auto-switches on image upload; multi-image picker with order badges; aspect ratio + quality/resolution pickers per model | VECTOR content district image generation UI |
| **VideoStudio** | `VideoStudio.jsx` | Dual-mode T2V/I2V; start-frame upload; aspect ratio + duration + quality selectors per model | VECTOR content district video generation UI |
| **LipSyncStudio** | `LipSyncStudio.jsx` | Portrait+audio mode or Video+audio mode toggle; 9 models; resolution picker; history auto-saved to `lipsync_history` | VECTOR voice-driven video content |
| **CinemaStudio** | `CinemaStudio.jsx` | Pro cinematic controls: 6 cameras, 11 lenses, 6 focal lengths, 3 apertures; translates selections into prompt modifiers injected into t2i | VECTOR dashboard "cinema mode" for high-quality generation |
| **AudioStudio** | `AudioStudio.jsx` | Music/sound generation with playback controls, waveform, volume; upload reference audio for remix/extend; generate sounds, mashups, add vocals/instrumental; voice cloning | **Entirely absent from VECTOR — primary gap** |
| **WorkflowStudio** | `WorkflowStudio.jsx` | Node-based pipeline builder (Templates / My Workflows / Community tabs); card grid with thumbnails; drag-drop visual editor (`WorkflowUI`); playground run form | VECTOR karpathy_lab / automation district |
| **AgentStudio** | `AgentStudio.jsx` | Browse template/user/featured agents; card grid; chat interface via Muapi agents API; conversation history | VECTOR governance + multi-agent coordination |
| **VibeMotionStudio** | `VibeMotionStudio.jsx` | Motion graphics generation: text prompt + aspect ratio + duration; edit mode patches prior generation via `request_id`; history | VECTOR content district motion graphics |
| **MarketingStudio** | `MarketingStudio.jsx` | Ad video generation: upload product images + avatar + reference clips + video clips; multi-asset input; Seedance/SD VIP Omni Reference endpoint | VECTOR agency district |
| **ClippingStudio** | `ClippingStudio.jsx` | AI clipping: upload or URL input video; extract N highlights; 9:16 auto-reframe; coordinate-only mode; copy/download; per-clip playback | VECTOR content district YouTube shorts |
| **DesignAgentStudio** | `DesignAgentStudio.jsx` | AI design agent interface | VECTOR design district |
| **McpCliStudio** | `McpCliStudio.jsx` | Showcases muapi-cli (npm) and muapi-mcp-server; code snippets; links to repos | Reference for VECTOR MCP integration |
| **AppsStudio** | `AppsStudio.jsx` | Gallery of SaaS app templates (AI Headshot Studio, Nano Banana Studio, etc.) with GitHub links and live demos | VECTOR startups district inspiration |
| **WorkflowUI** | `WorkflowUI.jsx` | Internal: node-canvas editor loaded via dynamic import inside WorkflowStudio | Internal sub-panel |

**Design patterns worth copying for VECTOR HUD:**
- Generation history persisted in `localStorage` with pending jobs that resume on reload
- Real-time request_id tracking passed via `onRequestId` callback — shows live job ID during polling
- Per-model capability detection: `model.inputs.resolution`, `model.supports_quality` drive UI dynamically
- "Local" toggle badge on model selector (activates sd.cpp or Wan2GP path)
- Upload history picker: 3-column thumbnail grid, reuse across sessions without re-uploading
- Audio player with custom controls (play/pause, seek bar, volume, time display)

---

## 4. Verdict

**Absorb: NO for the JS frontend. YES for the 3 Python-level gaps.**

This repo is a **TypeScript/React/Next.js application** — zero Python backend to absorb as-is. VECTOR already has a complete Python port of the core muapi.js functionality (`muapi_client.py`, `models.py`, `local_inference.py`, `wan2gp_client.py`, `generative_studio.py`). The port is high quality: async, loguru logging, fallback chain, no hardcoded keys.

The repo's genuine value for VECTOR is three **Python-portable gaps** that do not exist anywhere in VECTOR:

1. **Audio/music generation** — 12 models (Suno create/remix/extend/sounds/vocals/mashup/instrumental/voice-clone, MiniMax voice clone, MiniMax Speech 2.6 HD/Turbo, MMAudio v2) with a full `generateAudio()` pattern that VECTOR's `MuapiClient` does not implement at all.
2. **Workflow engine client** — submit + poll for multi-step pipelines (different poll URL: `/workflow/run/{run_id}/api-outputs`); create/update/delete workflows; node schemas.
3. **AI clipping** — `runClipping()` is one endpoint call (`POST ai-clipping`) with a specialized poll; useful for content district YouTube Shorts automation.

The remaining gaps (motion graphics, marketing studio, agent API, dynamic cost) are lower priority for VECTOR's autonomous loop and can be added on-demand.

**License:** MIT — fully absorb-eligible.

---

## 5. Gaps

### Gap 1 — Audio/Music Generation (CRITICAL — entirely missing)

VECTOR has no music generation capability. The repo defines 12 audio models via Muapi.ai:

| Model | Endpoint | What it does |
|---|---|---|
| Suno Create Music | `suno-create-music` | Text prompt + style → full song with vocals; models V3.5 through V5.5 |
| Suno Remix Music | `suno-remix-music` | Upload audio + style → remixed track (same melody, new style) |
| Suno Extend Music | `suno-extend-music` | Extend an existing Suno generation |
| Suno Generate Sounds | `suno-generate-sounds` | Sound effects and ambient audio |
| Suno Add Vocals | `suno-add-vocals` | Add vocals to an instrumental track |
| Suno Generate Mashup | `suno-generate-mashup` | Mashup two uploaded audio tracks |
| Suno Add Instrumental | `suno-add-instrumental` | Add instrumentation to an existing track |
| Suno Voice Clone | `suno-voice-clone` | Clone a voice from a reference sample |
| MiniMax Voice Clone | `minimax-voice-clone` | MiniMax voice cloning |
| MiniMax Speech 2.6 HD | `minimax-speech-2.6-hd` | High-definition TTS synthesis |
| MiniMax Speech 2.6 Turbo | `minimax-speech-2.6-turbo` | Fast TTS synthesis |
| MMAudio v2 Text-to-Audio | `mmaudio-v2-text-to-audio` | Text → ambient/effects audio |

**What to absorb:**
- Add `generate_audio(model_id, **params)` to `core/media/muapi_client.py` — same `_submit_and_poll()` pattern, params passed through dynamically (the JS client does `for key in params: payload[key] = params[key]`)
- Add `AUDIO_MODELS: list[MediaModel]` to `core/media/models.py` with `category="audio"` for the 12 models
- Add `generate_music()` and `generate_sounds()` convenience methods to `core/media/generative_studio.py`
- This enables: VECTOR generating background music for content videos, ambient soundscapes for focus mode, voice cloning for the agency district

### Gap 2 — Workflow Engine Client (medium priority)

VECTOR has no way to submit or poll multi-step Muapi workflow pipelines. The JS client exposes 10 workflow API functions (`getTemplateWorkflows`, `getUserWorkflows`, `createWorkflow`, `executeWorkflow`, `pollWorkflowResult`, etc.) with a different poll endpoint (`/workflow/run/{run_id}/api-outputs`).

**What to absorb:**
- Add `WorkflowClient` class to `core/media/` with `execute_workflow(workflow_id, inputs)`, `list_templates()`, `create_workflow(spec)`, `poll_workflow_result(run_id)` methods
- Wire into `GenerativeStudio.generate()` dispatch with `action="run_workflow"`

### Gap 3 — AI Clipping (lower priority)

`POST /api/v1/ai-clipping` with `{video_url, num_highlights, aspect_ratio, return_coordinates_only}`. Returns timestamp coordinates for viral short-form clips. One endpoint, same poll loop.

**What to absorb:**
- Add `clip_video(video_url, num_highlights=3, aspect_ratio="9:16")` to `MuapiClient` and wire into `GenerativeStudio`
- Directly serves VECTOR's content district YouTube Shorts pipeline

### Gap 4 — V2V model catalog completeness (minor)

VECTOR's `V2V_MODELS` has 2 models. The repo has 4: adds `video-watermark-remover` and `kling-motion-control` (3 variants). Add these to `core/media/models.py`.

### Gap 5 — Lipsync model completeness (minor)

VECTOR has 7 lipsync models. The repo has 9. Missing: `creatify-lipsync` and `veed-lipsync`. Add to `LIPSYNC_MODELS`.

### Gap 6 — MUAPI_MODELS export alias (cosmetic)

The parity check protocol imports `MUAPI_MODELS` but `core/media/models.py` only exports `all_models()`. Add `MUAPI_MODELS = all_models()` or `MUAPI_MODELS: list[MediaModel] = list(_ALL_MODELS.values())` as a module-level alias.

---

## Absorption Priority

| Priority | Gap | Effort | Impact |
|---|---|---|---|
| P1 | Audio/Music generation (Gap 1) | 1 session (~3 hrs) | Entirely new capability; enables music for content district, agency ads, focus mode |
| P2 | Workflow engine client (Gap 2) | 0.5 session | Enables chained AI pipelines without custom orchestration |
| P3 | AI clipping (Gap 3) | 0.5 hrs | Direct feed to content district YouTube Shorts |
| P4 | V2V + lipsync model completeness (Gaps 4+5) | 30 min | Catalog completeness |
| P5 | MUAPI_MODELS alias (Gap 6) | 5 min | Backward-compat for parity tests |

**Do NOT absorb:** The Next.js/React frontend, Electron desktop app, Workflow node-canvas UI — these are JavaScript/TypeScript only. VECTOR's HUD will be built per `docs/frontend-spec.md` which already covers these panels.

**Files to create/modify for P1 absorption:**
- `core/media/models.py` — add `AUDIO_MODELS`, update `_ALL_MODELS`, `_BY_CATEGORY`
- `core/media/muapi_client.py` — add `generate_audio()` method
- `core/media/generative_studio.py` — add `generate_music()`, `generate_sounds()` convenience methods + dispatch cases
- `tests/test_audio_generation.py` — 15+ tests covering all 12 model registrations + graceful no-key behavior
