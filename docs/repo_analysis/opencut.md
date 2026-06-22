# OpenCut-main - VECTOR Absorption Review

**Verdict:** SKIP for now.

**Priority:** LOW / SKIP

**Effort:** None

**License:** MIT

**Repo size inspected:** ~91 files / ~0.64 MB

## What It Is

OpenCut is intended to become a free/open-source video editor for web, desktop, and mobile. The current repository is explicitly a ground-up rewrite. Its README says the useful future pieces are still coming:

- Editor API
- third-party plugins
- Rust core
- MCP server
- headless mode
- scripting tab

The current checked-out code is mostly a Bun/TanStack/Cloudflare web scaffold with shadcn-style UI components. It does not contain the promised editor core, timeline engine, rendering API, plugin runtime, MCP server, or headless renderer.

## VECTOR Already Has

- `core/video/vector_composer.py`
- `core/video/html_renderer.py`
- `core/video/video_encoder.py`
- `core/video/audio_mixer.py`
- `districts/content/video_pipeline.py`
- `districts/content/video_merger.py`
- `districts/content/caption_generator.py`
- `districts/content/comfyui_adapter.py`

VECTOR already has the automation video path OpenCut is hoping to expose later.

## Overlap

Approximate overlap today: **low in code, high in intended mission**.

OpenCut's future roadmap overlaps with VECTOR's content tooling, but the actual repo does not yet contain the pieces VECTOR would absorb.

## Real Gaps Worth Absorbing

None from the current repo.

The future OpenCut roadmap could become interesting if it ships a stable programmatic editor API, headless batch renderer, AI/MCP tool interface, plugin-first timeline operations, or Rust media core usable from Python or a local service.

## What Not To Absorb

- Do not add Bun/TanStack/Cloudflare web scaffold code to VECTOR.
- Do not import its UI component library.
- Do not build against the future roadmap.
- Do not replace VECTOR's browser/ffmpeg composer.

## Recommendation To Sonnet

No implementation.

Add no dependencies, no routes, no agents, and no new files from OpenCut. Keep this repo bookmarked and re-evaluate only after the rewrite ships a real editor core or headless API.

## Final Recommendation

**SKIP.** This repo is currently a placeholder for a future system. Absorbing it now would create scaffolding around promises instead of capabilities.
