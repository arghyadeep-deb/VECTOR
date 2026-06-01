# Repo Audit — hyperframes-main
> Source: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\hyperframes-main`
> Audited: 2026-06-02
> VECTOR Codebase: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`
> Verdict: **INTEGRATE DIRECTLY + PATCH VECTOR**

---

## Step 1 — Repo Reality

### Monorepo Packages (8 total)

| Package | Version | Role |
|---------|---------|------|
| `@hyperframes/core` | 0.6.63 | Shared types, runtime contract, lint rules, composition compiler, registry, generators |
| `@hyperframes/engine` | 0.6.63 | Low-level rendering engine — Puppeteer browser pool, BeginFrame CDP, audio mixer, video frame extractor, streaming encoder, HDR pipeline |
| `@hyperframes/producer` | 0.6.63 | High-level render orchestrator — 6-stage pipeline, HTTP server (Hono), SSE streaming, distributed render, AWS Lambda adapter |
| `@hyperframes/studio` | 0.6.63 | React 19 WYSIWYG editor — CodeMirror panels, timeline UI, Vite devserver, Zustand state |
| `@hyperframes/player` | 0.6.63 | Browser-side composition player — preview parity with producer |
| `@hyperframes/cli` | 0.6.63 | `hyperframes` CLI — scaffold, install from registry, start studio, trigger renders |
| `@hyperframes/shader-transitions` | 0.6.63 | GLSL → Node.js SDR/HDR shader transition library (60+ transitions) |
| `@hyperframes/aws-lambda` | 0.6.63 | AWS Lambda handler + CDK construct + SDK for distributed cloud rendering |

---

### `@hyperframes/producer`
**What it does:** The rendering engine that converts HTML compositions to MP4/WebM/MOV.

Six-stage pipeline:
1. **Compile** — HTML bundler inlines CSS/JS, resolves sub-compositions, injects timing attributes (`data-start`, `data-duration`, `data-end`), handles deterministic font embedding (11 bundled font families from `@fontsource/`).
2. **Probe** — Browser-driven duration discovery; reconciles declared vs actual media durations via `ffprobe`.
3. **Extract Videos** — Pre-extracts video frames via FFmpeg into JPEG sequences with an LRU disk cache; replaces `<video>` with `<img>` for deterministic capture.
4. **Audio** — Mixes composition audio tracks (GSAP-animated volume envelopes, Ramer–Douglas–Peucker simplification, per-keyframe `volume` filter) into `audio.aac` via FFmpeg `filter_complex`.
5. **Capture** — Chrome `HeadlessExperimental.beginFrame` (atomic compositor control, Linux only) or `Page.captureScreenshot` fallback. Browser pool with acquire/release. Parallel workers with adaptive retry. HDR layered compositing via WebGPU float16 readback.
6. **Encode + Assemble** — `libx264`/VP9/ProRes via FFmpeg. Streaming encoder (`-f image2pipe`) pipes frames to FFmpeg stdin without disk write. Chunked-concat path for distributed chunk assembly. `faststart` mux pass for web delivery.

HTTP server runs on port 9847 (configurable via `PRODUCER_PORT`). Routes:
- `POST /render` — blocking render, returns JSON
- `POST /render/stream` — SSE streaming render with progress
- `GET /render/queue` — queue status
- `POST /lint` — composition lint
- `GET /health`
- `GET /outputs/:token` — download rendered artifact

Distributed mode: `plan()` → N×`renderChunk()` → `assemble()` — driven by AWS Step Functions or in-process simulation.

---

### `@hyperframes/engine`
**What it does:** The pure rendering primitives that producer orchestrates.

Key capabilities not in producer directly:
- **Browser Manager** — Chrome executable resolution (auto-discovers Puppeteer cache + headless-shell), pooled browser lifecycle.
- **BeginFrame** — `HeadlessExperimental.beginFrame` with per-page CDP session cache, `hasDamage` detection with last-frame reuse on no-damage frames.
- **HDR Capture** — WebGPU float16 readback: FFmpeg extracts raw HDR pixels (rgba64le) → linear light conversion → WebGPU texture upload → GPU shader transform → readback → PQ/HLG re-encode. Requires headed Chrome (not headless — WebGPU unavailable in headless mode).
- **Streaming Encoder** — `FrameReorderBuffer` ensures out-of-order parallel workers feed FFmpeg stdin in correct frame sequence.
- **Video Frame Extractor** — LRU disk cache for extracted video frames (avoids re-extraction per render).
- **Video Frame Injector** — `BeforeCaptureHook` that swaps `<video>` for pre-extracted `<img>` frames. Two-bound LRU keyed by frame path (entry count + byte budget).
- **Layer Compositor** — Z-order analysis: groups DOM elements into contiguous layers; HDR video elements become separate layers for per-element WebGPU compositing.
- **Shader Transitions** — GLSL-ported math (60+ transitions) operating on rgb48le buffers. PQ/HLG linearization LUTs (65536 entries, built once).
- **Parallel Coordinator** — CPU/memory heuristic auto-selects worker count; adaptive retry if a worker fails.

---

### `@hyperframes/studio`
**What it does:** React 19 WYSIWYG editor for building compositions visually.

- CodeMirror 6 panels (HTML/CSS/JS editing with autocomplete)
- Live preview via `@hyperframes/player` (embedded in iframe)
- Render trigger via `@hyperframes/producer` (devDep)
- `mediabunny` for client-side waveform/audio analysis
- Tailwind CSS + Phosphor Icons UI
- Zustand state management
- Studio API (`@hyperframes/core/studio-api`) — Hono sub-app with routes: projects, files, preview, lint, render (SSE), thumbnail, waveform, fonts, registry

---

### Template Registry (80+ blocks, 30+ components)
Pre-built HTML compositions in `registry/blocks/`:
- Data visualizations: `data-chart`, `flowchart`, `flowchart-vertical`, `us-map`, `world-map`, `us-map-bubble`, `us-map-flow`
- Social cards: `reddit-post`, `x-post`, `spotify-card`, `instagram-follow`, `tiktok-follow`, `macos-notification`
- Shader VFX: `vfx-liquid-glass`, `vfx-shatter`, `vfx-portal`, `vfx-magnetic`, `vfx-text-cursor`
- Transitions: 60+ shader transitions across 15 categories (blur, dissolve, distortion, 3D, mechanical, etc.)
- iOS 26 Liquid Glass components (5 blocks)

---

## Step 2 — VECTOR Parity Check

### Parity test result
```
$ python -X utf8 -c "
  from core.video.html_renderer import HTMLRenderer  # wrong class name
  from core.video.vector_composer import VectorComposer"
ImportError: cannot import name 'HTMLRenderer'
```
Class is `HTMLFrameRenderer`, not `HTMLRenderer` — audit note only, not a bug in VECTOR.

```
$ python -X utf8 -c "
  from core.video.html_renderer import HTMLFrameRenderer
  from core.video.vector_composer import VectorComposer
  h = HTMLFrameRenderer(); c = VectorComposer()"
HTMLFrameRenderer OK: <class 'core.video.html_renderer.HTMLFrameRenderer'>
VectorComposer OK:    <class 'core.video.vector_composer.VectorComposer'>
```

### Feature-by-feature parity table

| Hyperframes Feature | VECTOR Status | Notes |
|---------------------|--------------|-------|
| HTML → frame capture (Playwright) | ✅ `core/video/html_renderer.py` | VECTOR uses Playwright; hyperframes uses Puppeteer + BeginFrame CDP. Functionally equivalent for SDR. |
| Frame encode (FFmpeg H.264/VP9/ProRes) | ✅ `core/video/video_encoder.py` | NVENC GPU path present. |
| Audio mixing (multi-track, FFmpeg) | ✅ `core/video/audio_mixer.py` | Basic multi-track. Missing: GSAP-animated volume envelopes, keyframe simplification. |
| Composition linter | ✅ `core/video/composition_linter.py` | Regex-based port of hyperframes lint rules (7 rule sets). |
| VectorComposer (pipeline orchestrator) | ✅ `core/video/vector_composer.py` | 3 stages: capture → audio → encode. No probe stage. |
| HTML compiler (CSS/JS inline, timing attrs) | ❌ Not built | Hyperframes compiles `data-start/duration/end`, resolves sub-compositions, inlines assets, injects deterministic fonts. VECTOR has no equivalent. |
| BeginFrame deterministic capture | ❌ Not built | VECTOR uses `page.screenshot()` (non-atomic). Hyperframes uses `HeadlessExperimental.beginFrame` → one CDP call = one layout+paint+composite cycle. Determinism gap. |
| Browser pool (acquire/release) | ❌ Not built | VECTOR spawns + closes a fresh browser per job. Hyperframes pools a single Chrome instance with ref-counting. |
| Parallel capture workers | ⚠️ `workers` field in `ComposerJob` but not wired | Hyperframes has full parallel coordinator with adaptive retry. |
| Video frame pre-extraction | ❌ Not built | Hyperframes extracts video → JPEG sequence before capture begins; replaces `<video>` with `<img>` for determinism. VECTOR has no equivalent — video in HTML compositions will be a black frame. |
| Video frame injector (BeforeCaptureHook) | ❌ Not built | Companion to above. |
| Streaming encode (pipe to FFmpeg stdin) | ⚠️ `StreamingEncoder` class exists in `video_encoder.py` but is unused | Hyperframes' streaming path eliminates disk I/O between capture and encode. |
| HDR capture (WebGPU float16) | ❌ Not built | Hyperframes captures HDR via WebGPU readback (requires headed Chrome). VECTOR has no HDR frame path. |
| Shader transitions (60+, rgb48le) | ❌ Not built | GLSL-ported transitions operating on 16-bit buffers. PQ/HLG linearization. Layer compositor for z-order. VECTOR has no shader transition system. |
| Layer compositor (z-order HDR) | ❌ Not built | Groups DOM + HDR elements for per-element compositing. |
| Distributed render (plan/chunk/assemble) | ❌ Not built | Hyperframes splits a render into N chunks for parallel Lambda execution. VECTOR has no distributed render. |
| AWS Lambda render adapter | ❌ Not built | Step Functions state machine + CDK construct. Out of scope for VECTOR v1. |
| Studio API (Hono server, 9 routes) | ⚠️ `core/video/studio_server.py` partial | VECTOR has a basic studio server; hyperframes has full project/files/preview/lint/render/thumbnail/waveform/fonts/registry routes. |
| Template registry (80+ blocks) | ❌ Not pulled in | 80+ HTML composition blocks with preview videos. VECTOR has `CompositionTemplate` (3 manually coded templates). |
| Composition variables system | ✅ `window.__vector.setVariables()` in VECTOR runtime | VECTOR's JS contract covers this. Hyperframes has a typed `CompositionVariable` system with validation. |
| `window.__hf` seek protocol (runtime) | ⚠️ VECTOR uses `window.__vector` contract | Different protocol name. Hyperframes compositions use `window.__hf`; VECTOR templates use `window.__vector`. Hyperframes blocks won't work with VECTOR's renderer without a protocol bridge. |
| Waveform analysis | ❌ Not built | Hyperframes extracts waveform data for studio timeline. |
| Thumbnail generation | ❌ Not built | Hyperframes generates composition previews at specified timecodes. |
| Deterministic font embedding | ❌ Not built | Hyperframes embeds 11 font families as data URIs at compile time for pixel-identical cross-host renders. VECTOR relies on system fonts. |
| Composition probe (duration discovery) | ❌ Not built | Hyperframes probes actual media durations via `ffprobe` + browser to reconcile declared vs actual lengths. |

---

## Step 3 — Integration Plan

### Run `@hyperframes/producer` as a Sidecar on Port 7421

The producer's default port is 9847 (`PRODUCER_PORT`). VECTOR will run it on 7421 to avoid collision.

**Start command:**
```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\hyperframes-main"
bun install
bun run build:producer
PRODUCER_PORT=7421 node packages/producer/dist/index.js
```

Or via the server export:
```js
// packages/producer/src/server.ts exports startServer()
// PRODUCER_PORT=7421 node -e "import('./dist/index.js')"
```

**Health check:** `GET http://localhost:7421/health` → `{"status":"ok"}`

**Render endpoint:** `POST http://localhost:7421/render`
```json
{
  "projectDir": "/path/to/composition/",
  "fps": 30,
  "quality": "standard",
  "format": "mp4"
}
```
Returns: `{"outputUrl": "/outputs/<token>", "durationMs": 4200, ...}`

**Download:** `GET http://localhost:7421/outputs/<token>` → binary MP4

---

### Add `render_via_hyperframes()` to `core/video/vector_composer.py`

```python
# core/video/vector_composer.py
# Add after existing imports:
import httpx

HYPERFRAMES_SIDECAR_URL = "http://localhost:7421"
HYPERFRAMES_SIDECAR_TIMEOUT = 300  # seconds

async def render_via_hyperframes(
    job: "ComposerJob",
) -> "ComposerResult":
    """
    Delegate render to the @hyperframes/producer sidecar (port 7421).
    Falls back to VECTOR's html_renderer.py if the sidecar is unreachable.

    The sidecar provides:
      - BeginFrame deterministic capture (vs Playwright screenshot)
      - Deterministic font embedding (pixel-identical cross-host)
      - Probe stage (actual media duration reconciliation)
      - Video frame pre-extraction (no black frames for <video> elements)
      - Shader transitions (60+ GLSL transitions)
      - Streaming encode (no disk I/O between capture and encode)

    Usage:
        from core.video.vector_composer import VectorComposer, ComposerJob
        job = ComposerJob(
            composition_path="path/to/index.html",
            output_path="out.mp4",
            fps=Fps(30, 1),
            resolution="landscape",
        )
        result = asyncio.run(render_via_hyperframes(job))
    """
    import time
    from pathlib import Path

    t0 = time.perf_counter()

    # Resolve absolute paths
    comp_path = Path(job.composition_path).resolve()
    project_dir = str(comp_path.parent)
    output_path = Path(job.output_path).resolve()

    payload = {
        "projectDir": project_dir,
        "fps": job.fps.num if job.fps.den == 1 else f"{job.fps.num}/{job.fps.den}",
        "quality": job.quality,
        "format": job.format,
        "entryFile": comp_path.name,
    }

    try:
        async with httpx.AsyncClient(timeout=HYPERFRAMES_SIDECAR_TIMEOUT) as client:
            # Trigger render
            resp = await client.post(
                f"{HYPERFRAMES_SIDECAR_URL}/render",
                json=payload,
            )
            resp.raise_for_status()
            render_data = resp.json()

            # Download output
            output_url = render_data.get("outputUrl")
            if not output_url:
                raise RuntimeError(f"Sidecar returned no outputUrl: {render_data}")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with client.stream("GET", f"{HYPERFRAMES_SIDECAR_URL}{output_url}") as stream:
                stream.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in stream.aiter_bytes(65536):
                        f.write(chunk)

            total_ms = (time.perf_counter() - t0) * 1000
            file_size = output_path.stat().st_size if output_path.exists() else 0

            logger.info(
                "[VECTOR][composer] hyperframes render complete: {} ({:.1f}MB, {:.1f}s)",
                output_path, file_size / 1_048_576, total_ms / 1000,
            )

            return ComposerResult(
                output_path=str(output_path),
                duration_seconds=render_data.get("durationMs", 0) / 1000,
                frame_count=render_data.get("framesRendered", 0),
                file_size_bytes=file_size,
                total_ms=total_ms,
                capture_avg_ms=render_data.get("capturePerfSummary", {}).get("avgMs", 0.0),
                codec=render_data.get("codec", "h264"),
                has_audio=render_data.get("hasAudio", False),
            )

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning(
            "[VECTOR][composer] hyperframes sidecar unreachable ({}), "
            "falling back to html_renderer.py",
            e,
        )
        # Fallback: use VECTOR's own Playwright-based renderer
        composer = VectorComposer(on_progress=None)
        return await composer.render(job)
```

**Wire into `VectorComposer.render()`** — add `use_hyperframes: bool = True` to `ComposerJob`:
```python
# In VectorComposer.render(), before Stage 1:
if job.use_hyperframes:
    try:
        return await render_via_hyperframes(job)
    except Exception as e:
        logger.warning("[VECTOR][composer] hyperframes render failed: {}, using fallback", e)
        # continue to VECTOR's own pipeline
```

---

## Step 4 — Verdict: INTEGRATE DIRECTLY + PATCH VECTOR

**Reasoning:**

1. **Hyperframes is TypeScript/Node.js** — it cannot be reimplemented in Python without losing the core value (BeginFrame CDP, WebGPU HDR, Puppeteer browser pool). This is not like absorbing a Python library — the fundamental capability lives in Node.js.

2. **The sidecar approach is correct** — run producer as a local HTTP service on port 7421, call from Python via `httpx`. This is exactly how VECTOR is architected for cross-language tools (ADB, Ollama, FFmpeg subprocess, etc.).

3. **VECTOR's renderer stays as fallback** — `html_renderer.py` uses Playwright which is installed anyway. On Windows (VECTOR's primary machine), BeginFrame is not available (Linux-only CDP API), so the sidecar provides the same `Page.captureScreenshot` path hyperframes falls back to. The sidecar is still worth using for: deterministic fonts, probe stage, video frame extraction, and the studio API.

4. **Do NOT reimplement** — hyperframes has 40+ service files, 200+ test files, and 80+ pre-built composition blocks. Reimplementing is a 400h project with no benefit.

5. **Template registry is immediately valuable** — 80+ production-quality HTML compositions (data charts, world maps, social cards, shader VFX, iOS Liquid Glass) are directly usable by District 18 (content/) and District 15 (reflection/) once the sidecar is wired.

---

## Step 5 — Gaps (Numbered)

### Gap 1 — Missing `render_via_hyperframes()` in VectorComposer
**File:** `core/video/vector_composer.py`
**What's missing:** No method to delegate renders to the hyperframes sidecar. The `ComposerJob` dataclass has no `use_hyperframes` flag.
**Fix:** Add the `render_via_hyperframes()` async function and `use_hyperframes: bool = True` field to `ComposerJob` (see Step 3 code above).
**Effort:** 30 min.

### Gap 2 — No sidecar process manager
**File:** `core/video/` (missing: `hyperframes_sidecar.py`)
**What's missing:** Nothing starts/monitors the `@hyperframes/producer` Node.js process. If it crashes, VECTOR silently falls back to Playwright with no alerting.
**Fix:** Create `core/video/hyperframes_sidecar.py` — starts the producer via `subprocess.Popen`, monitors via `/health`, auto-restarts on crash, exposes `is_healthy() -> bool`. Wire into `run_vector.py` startup.
**Effort:** 2h.

### Gap 3 — Runtime protocol mismatch: `window.__vector` vs `window.__hf`
**File:** `core/video/runtime/vector_runtime.js` and all 80+ registry blocks
**What's missing:** VECTOR's compositions use `window.__vector.renderSeek(t)` / `window.__vector.enableRenderMode()`. Hyperframes' registry blocks use `window.__hf` and `window.__player` (the hyperframe runtime contract defined in `packages/core/src/runtime/README.md`).
**Fix:** Add a protocol bridge to `vector_runtime.js`:
```js
// In vector_runtime.js, after defining window.__vector:
if (!window.__hf) {
  window.__hf = {
    seek: (t) => window.__vector?.renderSeek(t),
    play: () => window.__vector?.disableRenderMode?.(),
    pause: () => window.__vector?.enableRenderMode?.(),
  };
}
```
This lets VECTOR render hyperframes registry blocks without patching each block.
**Effort:** 1h.

### Gap 4 — Video frame pre-extraction not in VECTOR pipeline
**File:** `core/video/vector_composer.py` → `_capture_frames()`
**What's missing:** VECTOR's `HTMLFrameRenderer` does not pre-extract `<video>` elements before capture. Any composition containing `<video>` (e.g., product showcases, background loops) will render as black frames.
**Fix:** When NOT using the hyperframes sidecar, add a pre-extraction step: call `ffprobe` on each `<video src>` found in the HTML, extract frames to a temp dir, inject `<img>` replacements via Playwright's `page.evaluate()` before each `renderSeek()` call.
**Effort:** 6h (the hard part is resolving `src` paths and injecting via JS).

### Gap 5 — Deterministic fonts missing from VECTOR renderer
**File:** `core/video/html_renderer.py` → `_browser_args()`
**What's missing:** Hyperframes embeds 11 font families as data URIs at compile time to guarantee pixel-identical output across machines. VECTOR uses system fonts → font rendering varies between machines (different hinting, anti-aliasing).
**Fix:** For each font used in a composition (scan `font-family` CSS), load font from `@fontsource/` npm packages and inject `@font-face` data URIs into the HTML before capture. Short-term: run the composition through the hyperframes sidecar which handles this automatically.
**Effort:** 4h for Python implementation; 0h if using sidecar.

### Gap 6 — Composition probe stage missing
**File:** `core/video/vector_composer.py` → `render()`
**What's missing:** VECTOR uses `ComposerJob.duration_seconds` as-is. Hyperframes runs a browser-driven probe that discovers the actual composition duration (respects media file lengths, animation end events) before allocating frames. VECTOR will cut off or waste frames if `duration_seconds` is wrong.
**Fix:** Add `_probe_duration()` method to `VectorComposer`: launch browser, load composition, inject JS to detect `window.__vector.getTotalDuration?.() || <default>`, close browser. Use result as actual duration.
**Effort:** 2h.

### Gap 7 — VECTOR's `studio_server.py` lacks the hyperframes Studio API routes
**File:** `core/video/studio_server.py`
**What's missing:** VECTOR's studio server is minimal. Hyperframes' Studio API (`createStudioApi`) has 9 route groups: projects, files, preview, lint, render (SSE), thumbnail, waveform, fonts, registry. These are needed for District 18 (content/) to have a real composition editor UI.
**Fix:** Option A: Mount the hyperframes studio API alongside the producer sidecar (run `bun run studio` in the hyperframes monorepo). Option B: Re-expose the studio API routes in `core/video/studio_server.py` as thin proxies to the sidecar.
**Effort:** 2h (Option A: zero Python code; Option B: 4h).

### Gap 8 — Template registry not indexed in VECTOR
**File:** None yet — needs `core/video/template_registry.py`
**What's missing:** VECTOR's `CompositionTemplate` class has 3 hard-coded templates (`data_viz`, `title_card`, `youtube_video`). Hyperframes has 80+ blocks in `registry/blocks/` with metadata (`registry-item.json`), preview videos, and GSAP animations. District 18 (content/) and the `content_strategist.py` agent should be able to browse and request any block by name.
**Fix:** Create `core/video/template_registry.py` — scans `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\hyperframes-main\registry\`, indexes `registry-item.json` files, exposes `list_blocks()`, `get_block(name)`, `copy_block_to(name, dest_dir)`. Agents pass the `destDir` path as `ComposerJob.composition_path`.
**Effort:** 2h.

### Gap 9 — No SSE streaming progress for long renders
**File:** `core/video/vector_composer.py`
**What's missing:** VECTOR's `on_progress` callback is synchronous and in-process. Hyperframes' `POST /render/stream` uses Server-Sent Events so a web UI or external client can track render progress in real time.
**Fix:** Wire the hyperframes sidecar's SSE stream into VECTOR's `on_progress` callback: consume `text/event-stream` from `POST /render/stream` and fire `on_progress(pct, stage)` on each `data:` event.
**Effort:** 2h.

### Gap 10 — `ComposerJob.workers` field is wired but unused
**File:** `core/video/vector_composer.py` → `_capture_frames()`
**What's missing:** `ComposerJob.workers: int = 1` exists but `HTMLFrameRenderer` has no parallel capture path. Hyperframes' parallel coordinator splits the frame range across N browser contexts.
**Fix:** Short-term: route multi-worker jobs to the hyperframes sidecar (which has a full parallel coordinator). Long-term: split frame ranges in `HTMLFrameRenderer` and capture in parallel `asyncio` tasks.
**Effort:** 1h (via sidecar routing); 8h (native Python).

---

## Summary Table

| Gap | File | Priority | Effort |
|-----|------|----------|--------|
| 1 — `render_via_hyperframes()` | `core/video/vector_composer.py` | P0 | 30 min |
| 2 — Sidecar process manager | `core/video/hyperframes_sidecar.py` (new) | P0 | 2h |
| 3 — Runtime protocol bridge `__vector` ↔ `__hf` | `core/video/runtime/vector_runtime.js` | P1 | 1h |
| 4 — Video frame pre-extraction | `core/video/vector_composer.py` + `html_renderer.py` | P1 | 6h |
| 5 — Deterministic fonts | `core/video/html_renderer.py` | P1 | 0h via sidecar |
| 6 — Composition probe stage | `core/video/vector_composer.py` | P1 | 2h |
| 7 — Studio API routes | `core/video/studio_server.py` | P2 | 2h |
| 8 — Template registry indexer | `core/video/template_registry.py` (new) | P2 | 2h |
| 9 — SSE streaming progress | `core/video/vector_composer.py` | P2 | 2h |
| 10 — Parallel capture workers | `core/video/vector_composer.py` | P3 | 1h via sidecar |

**Total to unblock Districts 18/15/19 via sidecar:** Gap 1 + Gap 2 + Gap 3 + Gap 8 = **~6h**.
**Full native parity (offline, no sidecar):** Gaps 4–6 = additional **10h**.
