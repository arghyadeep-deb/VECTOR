# remotion — Absorption Analysis

**Verdict:** SKIP (architecturally redundant — VECTOR already built a Remotion-equivalent in `core/video/`; license is also restrictive for an autonomous commercial-content use case)

---

**What it is:**

Remotion (`remotion-dev/remotion`) is a framework for **creating videos programmatically using React/TypeScript**. You declare a video as React components; data, math, APIs, CSS/Canvas/SVG/WebGL drive each frame.

- **Stack:** JS/TS/Bun monorepo (`bun.lock`, `bunfig.toml`, `turbo.json`), 130+ packages under `packages/`. Core packages: `remotion` (the React primitives), `@remotion/renderer` (Node.js/Bun SSR render engine, `packages/renderer/package.json:4` — `"Render Remotion videos using Node.js or Bun"`), `@remotion/cli`, `@remotion/bundler`, `@remotion/lambda` (AWS cloud render), `@remotion/compositor-*` (per-platform Rust native binaries for ffmpeg ops), `@remotion/mcp` (a Model Context Protocol server), plus templates including `template-prompt-to-video` and `template-prompt-to-motion-graphics`.
- **Render mechanism (identical pattern to what VECTOR built):** bundle the React composition → launch **headless Chromium** → seek the player to each frame's timestamp and `page.screenshot()` each frame → stitch frames with **ffmpeg**. Evidence in `packages/renderer/src/`: `open-browser.ts`, `render-frame.ts`, `render-frames.ts`, `call-ffmpeg.ts`, `ffmpeg-args.ts`, `prespawn-ffmpeg.ts`, `create-ffmpeg-merge-filter.ts`, `offthread-video-server.ts`.
- **How you'd invoke it programmatically:** the SSR API — `bundle()` (`packages/bundler`), `selectComposition()` (`renderer/src/select-composition.ts`), `renderMedia()` (`renderer/src/render-media.ts`). A Python service would shell out to a small Node script that calls these, or call the `@remotion/mcp` server.

**LICENSE TERMS (precise — `LICENSE.md`):** Remotion is **NOT** open-source in the OSI sense — it is source-available with a two-tier license (`package.json` files declare `"license": "SEE LICENSE IN LICENSE.md"`).
- **Free License** (`LICENSE.md:12-39`) — eligible only if you are: an **individual**; a for-profit org with **up to 3 employees**; a non-profit/not-for-profit; or evaluating pre-commercial. Free users may use it non-commercially **or commercially** to create videos/images and may modify it for their own use case.
- **Disallowed (`LICENSE.md:29-31`):** you may **not** copy or modify Remotion code to sell/rent/license/sublicense your own derivative of Remotion.
- **Company License** (`LICENSE.md:41-45`) — **required** for any for-profit org not in the Free tier; paid, priced at remotion.pro.
- Note (`LICENSE.md:1-3`): the license "slightly changes" in Remotion 5.0 (see PR #3750) — terms are a moving target.

---

**VECTOR already has:**

A full programmatic-video stack in `districts/content/` + `core/video/`, and crucially **VECTOR already independently built the exact Remotion architecture** (HTML/CSS/JS composition → headless-Chromium frame capture → ffmpeg encode):

- `core/video/vector_composer.py:1-684` — `VectorComposer.render()` pipeline: "HTML composition → frame capture → audio mix → video encode → final MP4" (`:5`), parallel browser-context capture (`:11`), `CompositionTemplate.youtube_video()` template builder (`:456`) with CSS `@keyframes` animations (`:431,:571-578`).
- `core/video/html_renderer.py:1-307` — `HTMLFrameRenderer` launches **headless Chromium via Playwright** (`:128-162`), injects a runtime, **seeks each frame deterministically** (`:198-200` → `window.__vector.renderSeek(frame_time)`), `page.screenshot()` per frame (`:210`), with deterministic font hinting (`:248`). This is the same frame-seek-and-screenshot loop Remotion's renderer runs.
- `core/video/runtime/vector_runtime.js:6-23` — VECTOR's own animation runtime: `renderSeek(t)` frame-accurate seeking, `enableRenderMode()` (pauses RAF for deterministic capture), **adapters for GSAP timelines, anime.js, and the Web Animations API (WAAPI)** (`:81-118`). This is VECTOR's home-grown equivalent of Remotion's deterministic-time core.
- `core/video/video_encoder.py`, `audio_mixer.py`, `composition_linter.py`, `hyperframes_sidecar.py`, `studio_server.py` — encode, audio mix, lint, and a render sidecar (`vector_composer.py:234-257` calls a "hyperframes producer sidecar" on port 7421, with html_renderer fallback).
- District 18 agents: `video_pipeline.py:1-700` (topic→script→TTS→**HTML composition→render MP4 on RTX GPU**→captions→upload, nightly 22:00 cron), `video_generator.py`, `video_merger.py` (ffmpeg transitions, 366 LOC), `comfyui_adapter.py` (local SD image gen, 727 LOC), `caption_generator.py`, `website_to_video.py`, `uploader.py`, `voice_generator.py`.

So VECTOR's "FFmpeg + ComfyUI + SadTalker" description undersells it — VECTOR also has a **browser-rendered, data-driven, animated HTML composition engine**, which is precisely Remotion's value proposition.

---

**Overlap vs new:**

- **Overlap (near-total):** Remotion's core selling points — programmatic/data-driven videos, animated explainers, CSS/SVG/Canvas/WebGL rendered via headless browser, frame-accurate deterministic seeking, ffmpeg stitching, templated compositions — are all **already implemented** in `core/video/vector_composer.py` + `html_renderer.py` + `vector_runtime.js`. VECTOR even matches Remotion's most distinctive trick (deterministic per-frame `renderSeek`) and supports GSAP/anime.js/WAAPI/CSS keyframes.
- **What Remotion genuinely does better (not currently in VECTOR):**
  1. **React as the authoring layer** — JSX components, props, `<Sequence>`/`<Composition>` timing primitives, Fast Refresh studio preview. VECTOR authors compositions as Python-generated HTML strings (`CompositionTemplate.youtube_video`), which is lower-level and less ergonomic for complex motion graphics.
  2. **Maturity & breadth** — battle-tested renderer, `@remotion/lambda` cloud scaling, large template/ecosystem library (Lottie, Three.js, Skia, captions, transitions), Rust native compositor for fast ffmpeg ops.
  3. **A polished prompt→video / prompt→motion-graphics path** (`template-prompt-to-video`, `template-prompt-to-motion-graphics`) and an MCP server.
- **None of these are gaps VECTOR cannot already cover functionally** — they are quality/ergonomics deltas on a capability VECTOR already shipped.

---

**License fit:**

For the **owner personally today** (KIIT student, individual) the **Free License applies** and is fine even for commercial videos. **But** this is being weighed for VECTOR's **autonomous content/agency district** (District 18 + District 19 agency, client work, monetized YouTube/content generation). Two problems:
1. **Scaling/entity risk:** if VECTOR's content output ever operates under a for-profit org exceeding 3 employees (the agency district's whole premise is client/revenue work), a **paid Company License becomes mandatory** — an ongoing cost and licensing-compliance burden bolted onto an otherwise local-first, zero-runtime-cost system. That contradicts VECTOR's "₹0, local, private" design ethos.
2. **Derivative restriction:** absorbing/forking Remotion code into VECTOR risks the `LICENSE.md:29-31` "no derivative of Remotion" clause, and the license is explicitly **changing in 5.0**. This is exactly the kind of license entanglement VECTOR's absorption rule avoids (prior absorptions skipped AGPL/ELv2 cores for the same reason).

Net: usable free for the individual case, but a **poor fit for an autonomous, potentially-commercial content engine** where the whole point is to scale output without per-tool licensing exposure.

---

**Integration plan (if any):**

Not recommended. *If* it were pursued (per VECTOR's Node.js multi-language rule — npm + subprocess/HTTP, never reimplement): stand up a Node render-service in e.g. `core/video/remotion_service/` (`npm i remotion @remotion/renderer @remotion/bundler @remotion/cli`), wrap `bundle()`→`selectComposition()`→`renderMedia()` in a tiny HTTP server, and have `video_pipeline.py` POST a composition ID + props JSON instead of calling `vector_composer.render()`. **Effort: HIGH** — adds a Node/Bun toolchain + Chromium download + React build step parallel to VECTOR's existing Playwright/Chromium stack (duplicate browser engines), plus authoring every template twice (Python HTML today vs. React tomorrow). The payoff is only ergonomic, and it imports the license liability above.

---

**Recommendation:**

**SKIP. Priority: LOW.** Remotion is excellent software and is the canonical tool for programmatic React video — but VECTOR independently built the **same architecture** (`core/video/vector_composer.py` + `html_renderer.py` + `vector_runtime.js`: deterministic headless-Chromium frame-seek capture of animated HTML/CSS/JS with GSAP/anime.js/WAAPI adapters, then ffmpeg encode), so there is **no real capability gap** to fill — only an authoring-ergonomics delta (React/JSX vs Python-generated HTML). Adopting Remotion would add a second Node/Bun + Chromium toolchain, duplicate every template, and — most decisively — attach a **source-available license that mandates a paid Company License the moment VECTOR's content/agency districts operate commercially at any scale**, with terms explicitly changing in 5.0. That trades VECTOR's local-first, zero-cost, fully-owned video engine for a heavier, license-encumbered dependency. The right move is to **keep and incrementally improve VECTOR's own composer** (e.g. add a lightweight component/sequence abstraction over `CompositionTemplate` if richer motion graphics are ever needed). Revisit only if VECTOR's home-grown composer proves inadequate for complex motion graphics AND the owner is comfortable with the licensing exposure — neither is true today.
