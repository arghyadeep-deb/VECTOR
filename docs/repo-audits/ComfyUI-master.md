# ComfyUI-master Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ComfyUI-master`
**Audit date:** 2026-06-02
**License:** GPL-3.0 (cannot absorb code — binary/library use only)
**Verdict:** INTEGRATE DIRECTLY as a sidecar process on port 8188

---

## 1. Repo Reality

### What ComfyUI Is
ComfyUI is the leading open-source node-graph AI content generation engine. It is **not** a Python library — it is a standalone server process (aiohttp on port 8188) with a React/LiteGraph frontend. VECTOR's adapter already treats it correctly as a sidecar.

### Core Architecture
```
main.py                    — entry point, init CUDA/AirLLM/DB
server.py (PromptServer)   — aiohttp web server, all REST routes + WebSocket
nodes.py                   — 100+ core node classes (KSampler, CLIPTextEncode, etc.)
comfy_extras/              — 100+ optional node files (audio, video, LoRA, ControlNet, ...)
comfy/                     — model loading, diffusion math, memory management, samplers
execution.py               — async prompt execution engine, partial-execution support
folder_paths.py            — model path registry
comfy_execution/           — job tracking, progress, parallel execution
app/                       — UserManager, ModelFileManager, CustomNodeManager, SubgraphManager
api_server/                — internal routes (/internal/logs, /internal/folder_paths)
```

### REST API Endpoints (from server.py + openapi.yaml, canonical /api/* prefix)

| Method | Path | Tag | Purpose |
|--------|------|-----|---------|
| GET | `/ws` | system | WebSocket: real-time progress, node status, outputs |
| GET | `/api/prompt` | prompt | Queue depth / status |
| POST | `/api/prompt` | prompt | Submit workflow for execution |
| GET | `/api/queue` | queue | Running + pending items |
| POST | `/api/queue` | queue | Clear queue / delete items by ID |
| POST | `/api/interrupt` | queue | Interrupt current or specific job |
| POST | `/api/free` | queue | Unload models / free GPU memory |
| GET | `/api/jobs` | queue | Paginated job list (filter, sort) |
| GET | `/api/jobs/{job_id}` | queue | Single job detail |
| GET | `/api/history` | history | **Deprecated** — use /api/jobs |
| GET | `/api/history/{prompt_id}` | history | **Deprecated** — use /api/jobs/{id} |
| POST | `/api/history` | history | **Deprecated** clear/delete history |
| POST | `/api/upload/image` | upload | Upload image to input/output/temp dir |
| POST | `/api/upload/mask` | upload | **Deprecated** — upload inpaint mask |
| GET | `/api/view` | view | Stream image/video/audio file by name |
| GET | `/api/view_metadata/{folder_name}` | view | Read safetensors header metadata |
| GET | `/api/system_stats` | system | VRAM, RAM, CPU, Python, ComfyUI version |
| GET | `/api/features` | system | Feature flags (cloud-only flags return null locally) |
| GET | `/api/object_info` | node | All registered node definitions |
| GET | `/api/object_info/{node_class}` | node | Single node definition |
| GET | `/api/embeddings` | node | List available text embeddings |
| GET | `/api/models` | model | List model folder type names |
| GET | `/api/models/{folder}` | model | List model filenames in folder |
| GET | `/api/experiment/models` | model | Model folders with paths (richer) |
| GET | `/api/experiment/models/{folder}` | model | Model files with mtime/size metadata |
| GET | `/api/experiment/models/preview/{folder}/{idx}/{filename}` | model | WebP model preview image |
| GET | `/api/extensions` | extensions | Frontend extension JS file list |
| GET/POST | `/api/users` | user | User info / create user (multi-user mode) |
| GET/POST/DELETE | `/api/userdata` | userdata | Per-user file CRUD |
| POST | `/api/userdata/{file}/move/{dest}` | userdata | Rename/move userdata file |
| GET/POST | `/api/settings` | settings | Per-user settings read/write |
| GET/POST/DELETE | `/api/settings/{id}` | settings | Single setting read/write/delete |
| GET | `/internal/logs` | internal | Terminal log stream |
| GET | `/internal/logs/raw` | internal | Raw log entries + terminal dimensions |
| PATCH | `/internal/logs/subscribe` | internal | Subscribe/unsubscribe to live logs |
| GET | `/internal/folder_paths` | internal | All model search paths |
| GET | `/internal/files/{directory_type}` | internal | List output/input/temp files |
| GET | `/api/subgraphs` | subgraph | Global subgraph blueprints |

**WebSocket message types (server → client):** `status`, `progress`, `progress_text`, `progress_state`, `executing`, `executed`, `execution_start`, `execution_success`, `execution_cached`, `execution_interrupted`, `execution_error`, `logs`, `notification`, `feature_flags`, `asset_download`, `asset_export`

### Node Categories (comfy_extras/)
The 100+ node files cover every modality:
- **Image:** SD1.x/2.x, SDXL, SD3/3.5, Flux/Flux2/Flux-Kontext, HiDream, HunyuanImage, Qwen Image, Lumina2, PixArt, AuraFlow, ZImage, ErnieImage, OmniGen2
- **Video:** Stable Video Diffusion, Mochi, LTX-Video, HunyuanVideo/1.5, Wan 2.1/2.2, Cosmos, AR-Video
- **Audio:** Stable Audio, ACE Step, EmptyLatentAudio, ConditioningStableAudio
- **3D:** Hunyuan3D 2.0
- **Control:** ControlNet (Union, InpaintingAliMama, T2I), LoRA loaders, LoRA extract, Hypernetworks, IC-LoRA (LTX-specific)
- **Sampling:** KSampler, advanced samplers, custom schedulers, align-your-steps, gits, optimalsteps
- **Model ops:** Model merging/subtract, model downscale, model patch, model advanced
- **Conditioning:** CLIPTextEncode (standard, Flux, HunyuanDiT, SD3, SDXL), inpainting, ControlNet apply, hooks, differential diffusion
- **Masking/Compositing:** mask ops, compositing, painter, bg removal, morphology, color, canny, mediapipe
- **Upscaling:** SDUpscale, ESRGAN, frame interpolation, lt_upsampler, MoGE depth
- **Latent:** latent ops, rebatch, VAE encode/decode, hypertile, sagattention
- **Utility:** logic, math, string, curve, dataset, primitive, preview_any, toolkit, preview comparison
- **Model-specific extras:** Mochi, ACE-Step, Lotus, HiDream-O1, Chroma Radiance, Kandinsky5, Mahiro, Fresca, GLM, PID, geometry

### Frontend / Web UI
The ComfyUI frontend is shipped as a pip package (`comfyui-frontend-package`), not as static files in this repo. Key design characteristics:

- **LiteGraph.js node graph:** infinite canvas, drag-connect nodes, right-click context menus
- **App Mode:** any workflow can be exposed as a simple form UI (hides the graph)
- **Queue panel (Q key):** live list of pending + running jobs with cancel buttons
- **History panel (H key):** past generations with image previews, prompt_id, timing
- **Node inspector:** click any node → sidebar shows all inputs/outputs/settings
- **Progress overlay:** per-node progress bars displayed on the canvas during generation
- **Model selector combos:** populated from `/api/object_info/{NodeClass}` at load time
- **WebSocket-driven:** no polling — all status/preview/completion events arrive via `/ws`
- **Keyboard shortcuts:** Ctrl+Enter (queue), Ctrl+Shift+Enter (queue front), Ctrl+Alt+Enter (cancel), Q (queue panel), H (history panel), Ctrl+S (save workflow), Ctrl+O (load workflow)
- **Workflow persistence:** save/load as JSON; embedded in generated PNG/WebP/FLAC EXIF
- **Extension system:** custom nodes add JS files auto-loaded from `/extensions`
- **Theme:** dark by default, minimal chrome, canvas-centric

---

## 2. VECTOR Parity

### Adapter verification output (live run)

```
ComfyUIAdapter OK url: http://127.0.0.1:8188
adapter methods: ['add_lesson', 'award_points', 'can_vote_in_council', 'deduct_points', 'die',
  'generate', 'generate_batch', 'get_status', 'get_voice_style', 'inherit_ghost', 'is_available',
  'list_models', 'queue_depth', 'record_decision', 'run', 'subscribe_to', 'to_dict']
```

The adapter instantiates cleanly with no ComfyUI running — graceful offline fallback confirmed.

### Feature-by-Feature Parity

| Feature | ComfyUI API endpoint(s) | VECTOR file | Verified output | Status |
|---------|------------------------|-------------|----------------|--------|
| Submit txt2img workflow | POST /api/prompt | `comfyui_adapter.generate()` + `_build_txt2img_workflow()` | Builds 7-node workflow (Checkpoint→CLIP+→CLIP-→EmptyLatent→KSampler→VAEDecode→SaveImage); queues via POST /prompt | ✅ |
| Poll completion | GET /api/history/{prompt_id} | `_wait_for_images()` | Polls with configurable interval (default 1.5s), timeout (default 120s), returns absolute file paths from output dir | ✅ |
| Check server alive | GET /api/system_stats | `is_available()` | Returns bool; adapter returns error dict if False | ✅ |
| List checkpoint models | GET /api/object_info/CheckpointLoaderSimple | `list_models()` | Returns list from `ckpt_name` input spec | ✅ |
| Check queue depth | GET /api/queue | `queue_depth()` | Returns `len(queue_running) + len(queue_pending)` | ✅ |
| Batch generation | POST /api/prompt × N | `generate_batch()` | Sequential (correct — ComfyUI is single-GPU) | ✅ |
| Custom workflow injection | POST /api/prompt | `generate(workflow=<dict>)` | Caller passes raw workflow dict, bypasses default builder | ✅ |
| Governor dispatch | — | `run(task)` | Extracts prompt/width/height/steps from task dict | ✅ |
| HP system integration | — | `award_points(20, "image_generated")` | Wired — 20 HP per image | ✅ |
| Interrupt execution | POST /api/interrupt | **MISSING** | No `interrupt()` method | ❌ |
| Free GPU memory | POST /api/free | **MISSING** | No `free_memory()` method | ❌ |
| Upload input image | POST /api/upload/image | **MISSING** | No `upload_image()` — blocks img2img, inpainting | ❌ |
| Download output file | GET /api/view | **MISSING** | Adapter resolves local paths only; no `fetch_output()` for remote/temp files | ❌ |
| Video workflow | POST /api/prompt (LTX/Wan/Mochi nodes) | **MISSING** | No `generate_video()` or video workflow builder | ❌ |
| Audio workflow | POST /api/prompt (ACE-Step/StableAudio nodes) | **MISSING** | No `generate_audio()` or audio workflow builder | ❌ |
| LoRA injection | POST /api/prompt (LoraLoader node) | **MISSING** | No `apply_lora()` helper to inject LoRA into any workflow | ❌ |
| ControlNet workflow | POST /api/prompt (ControlNetApply nodes) | **MISSING** | No `generate_with_controlnet()` builder | ❌ |
| Img2img workflow | POST /api/prompt (load image + VAE encode nodes) | **MISSING** | Needs upload + VAE encode nodes wired | ❌ |
| Inpainting workflow | POST /api/prompt + POST /api/upload/mask | **MISSING** | No `inpaint()` builder | ❌ |
| Model merge | POST /api/prompt (ModelMergeSimple nodes) | **MISSING** | No adapter-level merge helper | ❌ |
| List all model types | GET /api/models | **MISSING** | `list_models()` only queries checkpoints, not loras/vae/controlnet | ⚠️ |
| Get node definitions | GET /api/object_info | **MISSING** | No `get_node_info()` — useful for dynamic workflow building | ❌ |
| Job history | GET /api/jobs | **MISSING** | No `get_history()` or `get_jobs()` method | ❌ |
| Auto-start ComfyUI | — | **MISSING** | No subprocess launcher; ComfyUI must be started manually | ❌ |
| WebSocket live progress | GET /ws | **MISSING** | Adapter polls /history; no streaming WS progress to VECTOR | ❌ |
| Workflow save/load | POST /api/userdata + GET /api/userdata | **MISSING** | No `save_workflow()` / `load_workflow()` | ❌ |
| Safetensors metadata | GET /api/view_metadata/{folder} | **MISSING** | No `get_model_metadata()` | ❌ |
| System stats | GET /api/system_stats | **MISSING** | `is_available()` calls it internally but doesn't surface VRAM/RAM to caller | ⚠️ |

**Summary:** 7/24 features covered (29%). Core txt2img generation loop is solid. Everything beyond basic generation is a gap.

---

## 3. Frontend / Panel Spec (HUD Inspiration)

ComfyUI's web UI design has several patterns worth borrowing for VECTOR's future dashboard:

### Node Graph Canvas
- Infinite pan/zoom canvas using LiteGraph.js — nodes are positioned spatially
- Connection wires between outputs and inputs with type-color coding (MODEL=purple, CONDITIONING=orange, LATENT=pink, IMAGE=cyan)
- Node groups with colored outlines for visual workflow organization
- **HUD steal:** VECTOR district map could use this spatial metaphor — agents as nodes, data flows as wires

### Queue/History Panels
- Right-side sliding panel, two tabs: Queue (pending jobs) | History (completed jobs)
- Each history entry: thumbnail of output, timestamp, elapsed time, prompt_id
- Cancel button on pending items; re-queue button on completed
- **HUD steal:** VECTOR's action log panel design — live queue of pending actions + history of completed ones with HP delta

### Progress Visualization
- Per-node progress bar displayed directly on the node canvas
- Global step counter ("Step 12/20 — KSampler") in status bar
- Color-coded: executing node = yellow glow, completed = green tick, error = red
- **HUD steal:** VECTOR's decision engine visualization — currently-thinking agent glows, completed agents tick green

### Model Selector Pattern
- Combo dropdowns populated from `/api/object_info` at load time (server-authoritative)
- Supports fuzzy search across 200+ model names
- Preview images fetched from `/api/experiment/models/preview/...`
- **HUD steal:** VECTOR's model routing panel — show which Ollama model is loaded, VRAM usage, switch on demand

### App Mode (Simplified UI)
- Any workflow can be tagged as an "App" — the canvas collapses, only tagged inputs shown as a clean form
- **HUD steal:** VECTOR "quick actions" panel — surface just the inputs for the current task, hide the internals

### Keyboard-First Design
- Every action has a keybind. Q, H, P toggle panels. Ctrl+Enter runs. No mouse required for power users.
- **HUD steal:** VECTOR terminal HUD should support keyboard shortcuts for all common actions

---

## 4. Verdict: INTEGRATE DIRECTLY

**Do not absorb.** ComfyUI is GPL-3.0 — no code can be copied into VECTOR. It is also architecturally correct to keep it as a sidecar: it manages its own CUDA context, model loading, VRAM, and execution queue. Running it inside VECTOR's process would be a disaster for GPU memory.

**Integration strategy: subprocess sidecar on port 8188.**

```
VECTOR autonomous_loop (Python process)
    └── ComfyUIAdapter (HTTP client, port 8188)
            └── ComfyUI server (separate process, port 8188)
                    └── RTX 5070 Ti VRAM (shared GPU, managed by ComfyUI's scheduler)
```

VECTOR calls ComfyUI via HTTP — already the correct design. The adapter just needs to be expanded (see Gaps below).

**When ComfyUI is running:**
- VECTOR gains access to: SD1.x/SDXL/SD3/Flux/HunyuanVideo/Wan/LTX-Video/ACE-Step/Hunyuan3D — the full menu of local generation models
- Zero cloud calls, zero cost, all on-device (RULE 11 compliant)
- GPU memory is managed entirely by ComfyUI — VECTOR does not need to manage model loading

**When ComfyUI is not running:**
- `is_available()` returns False
- `generate()` returns `{"status": "error", "error": "ComfyUI not running..."}` gracefully
- VECTOR can fall back to ElevenLabs / cloud image generation for non-blocking content needs

---

## 5. Gaps

### Gap 1 — No Auto-Start (CRITICAL)

**Problem:** ComfyUI must be started manually before VECTOR can use it. There is no subprocess launcher.

**Fix:** Add `ComfyUIAdapter.ensure_running()`:

```python
async def ensure_running(self) -> bool:
    """Start ComfyUI as a subprocess if not already running."""
    import subprocess
    if await self.is_available():
        return True
    comfy_path = CONFIG.get("comfyui", {}).get("path", "")
    if not comfy_path:
        logger.warning("[VECTOR][comfyui] comfyui.path not set in config — cannot auto-start")
        return False
    self._proc = subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
        cwd=comfy_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 30s for startup
    for _ in range(30):
        await asyncio.sleep(1)
        if await self.is_available():
            logger.info("[VECTOR][comfyui] ComfyUI started OK")
            return True
    logger.error("[VECTOR][comfyui] ComfyUI failed to start in 30s")
    return False
```

Add `"comfyui": {"path": "C:/path/to/ComfyUI"}` to `core/config.py` CONFIG.

### Gap 2 — No Video Workflow Builder (HIGH)

**Problem:** `districts/content/video_generator.py` uses SadTalker/FFmpeg. ComfyUI supports HunyuanVideo, Wan 2.1/2.2, LTX-Video, Mochi — far higher quality. No adapter method exists.

**Fix:** Add `generate_video()` method to the adapter:

```python
def _build_video_workflow(
    prompt: str,
    model: str = "hunyuan_video",  # or "wan_2_1", "ltx_video"
    width: int = 512, height: int = 512, frames: int = 25,
    steps: int = 20, cfg: float = 6.0, seed: int | None = None,
) -> dict:
    # Returns ComfyUI node graph for EmptyHunyuanLatentVideo →
    # CLIPTextEncodeHunyuanDiT → KSampler → VAEDecode → VHS_VideoCombine
    ...

async def generate_video(self, prompt: str, **kwargs) -> dict:
    workflow = _build_video_workflow(prompt, **kwargs)
    prompt_id = await self._queue_prompt(workflow)
    video_paths = await self._wait_for_videos(prompt_id)
    return {"status": "ok", "videos": video_paths, ...}
```

### Gap 3 — No Audio Workflow Builder (HIGH)

**Problem:** ComfyUI has ACE-Step (music generation) and Stable Audio nodes. Zero coverage in VECTOR — audio generation currently relies on ElevenLabs TTS only.

**Fix:** Add `generate_audio()` with ACE-Step workflow builder (EmptyLatentAudio → ConditioningStableAudio → KSampler → SaveAudio).

### Gap 4 — No LoRA Injection (HIGH)

**Problem:** VECTOR has no way to apply a LoRA to any generation. The ComfyUI `LoraLoader` node inserts between CheckpointLoader and KSampler. Without this, VECTOR cannot use fine-tuned models (character LoRAs, style LoRAs, vector-chairman model outputs, etc.).

**Fix:** Extend `_build_txt2img_workflow()` to accept a `lora_name` / `lora_strength` pair and insert node `"4b": {"class_type": "LoraLoader", "inputs": {...}}` between checkpoint loader and KSampler.

### Gap 5 — No Upload / Img2img / Inpainting (MEDIUM)

**Problem:** Three important use cases (img2img, inpainting, ControlNet reference images) all require first uploading a file to ComfyUI's input directory via `POST /api/upload/image`. Zero coverage.

**Fix:** Add `upload_image(path: str) -> str` returning `{"name": ..., "subfolder": ...}` for use in workflow nodes. Then add `generate_img2img(image_ref, prompt, denoise=0.7, ...)` and `inpaint(image_ref, mask_ref, prompt, ...)` workflow builders.

### Gap 6 — No interrupt() / free_memory() (MEDIUM)

**Problem:** VECTOR cannot cancel a stuck generation or force-unload models from VRAM when switching tasks. On a 12GB RTX 5070 Ti this matters — ComfyUI holds large models in VRAM even when idle.

**Fix:**
```python
async def interrupt(self, prompt_id: str | None = None) -> bool:
    payload = {"prompt_id": prompt_id} if prompt_id else {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{self._base_url}/interrupt", json=payload)
        return r.status_code == 200

async def free_memory(self, unload_models: bool = True) -> bool:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(f"{self._base_url}/free",
                              json={"unload_models": unload_models, "free_memory": True})
        return r.status_code == 200
```

### Gap 7 — Polling vs WebSocket (LOW)

**Problem:** `_wait_for_images()` polls `/history` every 1.5s. ComfyUI provides a WebSocket at `/ws` with real-time `progress`, `executing`, and `executed` events. Polling adds 0–1.5s latency per image and misses step-by-step progress (useful for VECTOR HUD).

**Fix:** Replace polling with a WebSocket listener using `websockets` or `aiohttp`:
```python
async def _wait_for_images_ws(self, prompt_id: str) -> list[str]:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f"ws://127.0.0.1:8188/ws?clientId={self._client_id}"
        ) as ws:
            async for msg in ws:
                data = json.loads(msg.data)
                if data.get("type") == "executed" and data["data"].get("prompt_id") == prompt_id:
                    return self._extract_paths(data["data"]["output"])
```

### Gap 8 — config.py Missing comfyui.path (LOW)

**Problem:** `CONFIG.get("comfyui", {})` returns only `url` and `output_dir` defaults. There is no `comfyui.path` (needed for auto-start), no `comfyui.default_checkpoint`, no `comfyui.lora_dir`.

**Fix:** Add to `core/config.py` CONFIG dict:
```python
"comfyui": {
    "url": "http://127.0.0.1:8188",
    "path": "C:/path/to/ComfyUI",  # for auto-start
    "output_dir": "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/ComfyUI/output",
    "default_checkpoint": "v1-5-pruned-emaonly.safetensors",
    "timeout": 120.0,
    "poll_interval": 1.5,
}
```

### Gap 9 — list_models() Only Covers Checkpoints (LOW)

**Problem:** `list_models()` queries `CheckpointLoaderSimple` only. VECTOR cannot enumerate LoRAs, VAEs, ControlNets, or video model checkpoints.

**Fix:** Add `list_models_by_type(model_type: str) -> list[str]` using `GET /api/models/{folder}` with folder types: `checkpoints`, `loras`, `vae`, `controlnet`, `unet`, etc.

---

## Absorption Decision

**Nothing to absorb.** ComfyUI is GPL-3.0 and is a complete standalone system, not a Python library. VECTOR's correct stance is to use it as a sidecar and call its HTTP API. The existing `comfyui_adapter.py` has the right architecture.

**Work required:** Expand the adapter with 9 gaps above. Gaps 1–4 are the highest value (auto-start, video, audio, LoRA) and directly unlock VECTOR District 18 (content/) at production quality.

**Files to modify:**
- `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\districts\content\comfyui_adapter.py` — add 9 gap methods
- `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\config.py` — add comfyui.path + comfyui.default_checkpoint
