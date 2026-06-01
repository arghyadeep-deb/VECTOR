# Web Tools Batch Audit

Audited against: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`
Date: 2026-06-01

Integration rule applied: non-Python services that work locally are integrated directly (sidecar/subprocess/npm), not reimplemented.

---

## 1. ai-website-cloner-template-master

**What it is:**
A Next.js 16 + shadcn/ui scaffold + a `/clone-website` Claude Code skill. The skill drives a multi-phase pipeline:
1. Browser MCP automation (Chrome/Playwright) to screenshot and inspect a live site
2. Design token extraction via `getComputedStyle()`
3. Component spec files written to `docs/research/components/`
4. Parallel git-worktree builder agents (one per section)
5. Assembly, wiring, visual diff QA

This is purely a **Claude Code agentic workflow** (SKILL.md + Next.js scaffold). It produces a local Next.js clone, not a standalone service. No backend binary; everything runs through the AI agent session.

**VECTOR parity check:**
- `core/video/website_to_video.py` + `WebsiteToVideo`: captures a URL to video (screenshots + HTML composition), NOT a website-to-Next.js code clone.
- `core/browser/dom_pruner.py`, `core/browser/pii_scrub.py`: browser observation helpers, not site reverse-engineering.
- `core/scraper/`: scrapes content (text/images), not CSS design tokens or component structure.
- VECTOR has NO `/clone-website` skill, no design-token extractor (`getComputedStyle` sweep), and no component-spec pipeline for code generation.

There is zero overlap. VECTOR can capture a website as video or scrape its text. It cannot reverse-engineer a site into a React/Next.js codebase. This is an entirely different capability.

**Integration plan:**
The repo is a **Claude Code skill template** — it runs inside agent sessions, not as a sidecar. Integration means installing the skill:

1. Copy `.claude/skills/clone-website/SKILL.md` into `~/.claude/skills/clone-website/SKILL.md` (or symlink).
2. The skill requires a browser MCP tool active in the session (`--chrome` flag or Playwright MCP). VECTOR already uses Playwright in `core/scraper/` and `core/research_engine/`.
3. The Next.js scaffold is only needed if VECTOR agents need to produce Next.js output. For VECTOR's use cases (competitor analysis, design extraction), the skill's extraction pipeline is the value — the Next.js scaffold can be ignored.
4. No Python code to write. The skill is self-contained markdown.

**Verdict: INTEGRATE DIRECTLY**
Install the `/clone-website` skill. VECTOR gains: design token extraction (`getComputedStyle` sweeps), parallel builder agent dispatch for UI generation, visual diff QA. Useful for `districts/design/`, competitor analysis, and any task where VECTOR needs to reproduce a UI pattern from a live site.

**Gaps to add to bug tracker:**
- W1: Install `ai-website-cloner-template-master/.claude/skills/clone-website/SKILL.md` into `~/.claude/skills/` so `/clone-website` is available in VECTOR agent sessions.
- W2: VECTOR's `core/browser/dom_pruner.py` has no `getComputedStyle` sweep — it prunes interactive elements for LLM context. Add a `extract_design_tokens(url)` function that extracts colors, fonts, spacing from a live page (mirrors what clone-website does in Phase 1). Wire to `WebContentExtractor`.

---

## 2. glif-mcp-server-main

**What it is:**
A TypeScript MCP server (`@glifxyz/glif-mcp-server`) that exposes glif.app AI workflows as MCP tools. glif.app is a no-code visual AI workflow builder (chained: image gen → upscale → text → audio → etc.). The server provides:
- `run_workflow` — run any glif workflow by ID with inputs, returns image/text/audio/video
- `workflow_info` — get workflow metadata
- `list_featured_workflows`, `search_workflows`, `my_workflows` — discovery
- `list_agents`, `load_agent` — agent browsing

The server is a thin HTTP bridge: it calls `https://simple-api.glif.app` and `https://glif.app/api` with a bearer token, then returns MCP-compliant content blocks with multimedia support (text, base64 images, JSON).

**VECTOR parity check:**
- `core/inference/provider_client.py`: 27 LLM providers but these are text/embedding model APIs. No workflow execution or chained AI pipeline runner.
- `core/api/routers/media.py`: media handling but no external workflow orchestration.
- `core/mcp_server.py`: 40+ MCP tools for VECTOR's own capabilities. Zero tools for external AI workflow platforms.
- `districts/content/`: content generation agents, but they run local models or call single LLM endpoints. No "chain image-gen → upscale → add text → export" workflow runner.

VECTOR has no glif equivalent. This is an external AI workflow execution surface — access to thousands of community-built multimedia pipelines (image generation, video effects, audio, composite workflows) via a single `run_workflow(id, inputs)` call.

**Integration plan:**
This is a Node.js MCP server. Integrate directly as a local sidecar:

```bash
# Install once
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\glif-mcp-server-main"
npm install && npm run build

# Add to VECTOR's MCP config (.mcp.json or settings.json)
{
  "mcpServers": {
    "glif": {
      "command": "node",
      "args": ["C:\\Users\\Arghyadeep\\Desktop\\V.E.C.T.O.R\\GitHub\\glif-mcp-server-main\\build\\index.js"],
      "env": { "GLIF_API_TOKEN": "${GLIF_API_TOKEN}" }
    }
  }
}
```

Once wired, VECTOR agents get `run_workflow`, `search_workflows`, `my_workflows` as MCP tools — no Python wrapper needed. Add `GLIF_API_TOKEN` to `.env`.

**Verdict: INTEGRATE DIRECTLY**
Wire as MCP sidecar. Gives VECTOR access to visual AI workflow pipelines (image gen, video effects, audio) without implementing any of the individual models. Especially valuable for `districts/content/` (script → image → composite → upload pipelines), `districts/marketing/` (ad creative generation), and `districts/design/`.

**Gaps to add to bug tracker:**
- W3: Build glif-mcp-server and add it to VECTOR's `.mcp.json` as a sidecar. Add `GLIF_API_TOKEN` to `.env` and `core/config.py`. No Python code needed — pure MCP wiring.
- W4: Add a `districts/content/glif_workflow_agent.py` that wraps common glif workflow IDs for VECTOR's content pipeline (image gen for thumbnails, video effects, audio creation). Thin Python wrapper over the MCP tool.

---

## 3. NotFair-main

**What it is:**
A Claude Code plugin (MIT) with production-grade skill files for:
- **Google Ads** (`/notfair:google-ads-audit`, `/notfair:google-ads`, `/notfair:google-ads-copy`, `/notfair:google-ads-landing`): full GAQL-based account audit, campaign management, RSA copy generation, landing page scoring
- **Meta Ads** (`/notfair:meta-ads-audit`, `/notfair:meta-ads`): Meta Marketing API audit with Pixel/CAPI health, creative fatigue, audience overlap, Learning Phase triage
- **SEO** (`/notfair:seo-analysis`, `/notfair:content-writer`, `/notfair:keyword-research`, `/notfair:meta-tags-optimizer`, `/notfair:schema-markup-generator`, `/notfair:seo-page`, `/notfair:broken-link-checker`, `/notfair:geo-optimizer`, `/notfair:setup-cms`): full GSC + PageSpeed + technical crawl pipeline
- **Cross-model** (`/notfair:gemini`): Gemini second-opinion gate

Also ships remote MCP servers (`NotFair-GoogleAds`, `NotFair-MetaAds`) that expose ~100 Google Ads tools and the full Meta Marketing API surface.

Key internal assets:
- `google-ads/shared/policy-registry.json`: battle-tested Google Ads policy volatility + assumptions
- `meta-ads/shared/preamble.md`: Meta platform preamble with LTD/frequency/CAPI rules
- `seo/shared/preamble.md`: GSC + PageSpeed + URL Inspection setup rules
- `references/account-health-scoring.md`: pulse metric formulas (Waste/Demand/CPA)
- `references/persona-discovery.md`, `references/beat-direction.md` etc.: rich reference library

**VECTOR parity check:**
- `districts/marketing/google_ads_agent.py`: exists — has industry benchmarks and policy rules (embedded from NotFair's JSON), basic audit + copy generation. Uses LLM reasoning; real Google Ads API calls only when `GOOGLE_ADS_DEVELOPER_TOKEN` set. PARTIAL parity.
- `districts/marketing/meta_ads_agent.py`: exists. Similar pattern — LLM-based with Meta Marketing API optional. PARTIAL parity.
- `districts/marketing/seo_agent.py`: exists — GSC + PageSpeed + broken link detection pipeline. Wraps Google APIs. REASONABLE parity.
- `districts/marketing/seo_specialist.py`: exists as well.
- `core/api/routers/ads.py`: full ads router with 15+ endpoints.
- `core/api/routers/seo.py`: minimal — only `/seo/status`.

Gap analysis:
- VECTOR's Google Ads agent has embedded policies but lacks: GAQL `runScript` fan-out (up to 20 parallel queries), `summarizeAccountSetup` cross-check, change-event analysis (last 30 days), scoped audit mode, `audit-history.json` tracking, business-context.json persistence for downstream skills.
- VECTOR's Meta agent lacks: Learning Phase / Learning Limited triage, CBO/ABO/Advantage+ Shopping structure diagnosis, frequency-first creative fatigue scoring, `suggestImprovement` heuristics.
- VECTOR's SEO agent lacks: URL Inspection API, Core Web Vitals monitoring (INP, CLS), GEO optimizer (AI search engine citation scoring), keyword cannibalization detection, schema markup generator, `setup-cms` connector workflow, per-audit business-context cache (`~/.toprank/`).
- SEO router (`core/api/routers/seo.py`) is a stub — only `/seo/status`. No action endpoints.
- NotFair's `geo-optimizer` skill (GEO score 0-100 for ChatGPT/Claude/Perplexity/Gemini/AI Overviews citation) has NO VECTOR equivalent. This is a 2026 gap — AI search is now traffic.

**Integration plan:**
The NotFair MCP servers (`NotFair-GoogleAds`, `NotFair-MetaAds`) are remote HTTPS endpoints. Add them to `.mcp.json`:

```json
{
  "mcpServers": {
    "NotFair-GoogleAds": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://notfair.co/api/mcp/google_ads"]
    },
    "NotFair-MetaAds": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://notfair.co/api/mcp/meta_ads"]
    }
  }
}
```

For the skill files: install the full NotFair plugin via Claude Code (`/plugin install notfair@nowork-studio`), or manually copy the skills into `brain/.claude/skills/notfair/`.

VECTOR's Python agents should remain as the autonomous-loop layer. NotFail MCP servers are the live-data connectors when the user or an agent explicitly invokes them. The Python agents use LLM reasoning + cached snapshots; the NotFair MCP tools provide real-time GAQL and Meta API access.

Specifically harvest into VECTOR Python agents:
- `google-ads/shared/policy-registry.json` → extend `GOOGLE_ADS_POLICIES` dict in `google_ads_agent.py`
- `meta-ads/shared/` preamble rules → extend `meta_ads_agent.py` LTD/frequency/CAPI heuristics
- `seo/references/` keyword-intent, cannibalization, schema patterns → extend `seo_agent.py`

**Verdict: INTEGRATE DIRECTLY + PATCH VECTOR**
Install the NotFair Claude Code plugin and wire the two remote MCP servers. Additionally, patch VECTOR's Python agents to absorb the policy rules, Meta LTD/frequency heuristics, and SEO reference docs that VECTOR currently lacks.

**Gaps to add to bug tracker:**
- W5: Add `NotFair-GoogleAds` and `NotFair-MetaAds` remote MCP servers to VECTOR's `.mcp.json` (OAuth sign-in via notfair.co).
- W6: Install NotFair plugin skills into `brain/.claude/skills/notfair/` (or via `/plugin install notfair@nowork-studio`).
- W7: Extend `districts/marketing/google_ads_agent.py` with: GAQL parallel fan-out pattern, change-event analysis (last 30 days), business-context.json persistence at `~/.toprank/`, `audit-history.json` tracking. Reference: `google-ads/audit/SKILL.md` Phase 1-3.
- W8: Extend `districts/marketing/meta_ads_agent.py` with: Learning Phase / Learning Limited triage logic, frequency-first creative fatigue scoring (frequency > 2.5 threshold), CBO/ABO/Advantage+ Shopping structure rules. Reference: `meta-ads/shared/preamble.md`.
- W9: Build `districts/marketing/geo_optimizer_agent.py` — GEO score (0-100) for AI citation on ChatGPT/Claude/Perplexity/Gemini/AI Overviews. This is a net-new capability with no VECTOR equivalent. Reference: `seo/geo-optimizer/SKILL.md`.
- W10: Expand `core/api/routers/seo.py` from a 1-endpoint stub to a full SEO action router: `/seo/audit`, `/seo/keywords`, `/seo/meta-tags`, `/seo/schema`, `/seo/geo-score`. Wire to `SEOAgent`.

---

## 4. iii-main

**What it is:**
`iii` (pronounced "three") is a Rust-engine distributed worker runtime. Core primitives: **Worker** (a process that registers with the engine), **Function** (unit of work with stable ID like `content::classify`), **Trigger** (anything that causes a function to run: HTTP, cron, queue, state change, stream event, direct call). 

The engine is a Rust binary (`engine/` — ELv2 license). SDKs exist for Node.js, Python (`pip install iii-sdk`), and Rust. Workers connect to the engine via WebSocket, register triggers and functions, and form a live catalog where any worker can call any other function by ID.

Python SDK (`sdk/packages/python/iii/`): async/await WebSocket client, register functions via decorator, declare triggers (HTTP endpoint, cron, queue sub, state change), stream primitives, OpenTelemetry integration.

Designed to replace: message queues (Redis/RabbitMQ), cron schedulers (APScheduler), HTTP routing, observability stacks — all with one unified runtime.

**VECTOR parity check:**
- `core/event_bus/`: async pub-sub with circuit breakers, rate limiting, DLQ. Covers intra-process pub-sub but not cross-process worker registration or inter-service function calling.
- `core/loop/cron_jobs.py` + APScheduler: handles VECTOR's cron tasks (2AM reflect, daily KIIT scrape). Covers scheduling but not worker catalog or distributed triggers.
- `core/api/routers/queue.py`: task queue endpoint. Single-process only.
- VECTOR has no concept of "workers joining a live catalog" or cross-process function routing by stable ID. Each district agent is instantiated in-process by the Governor.

There is partial conceptual overlap (event bus, cron, queue) but architecturally these are different things. iii is a distributed system runtime for multi-process/multi-machine coordination. VECTOR's event bus is intra-process. VECTOR does not need iii to run — it's a single-owner local system.

**Should VECTOR use iii?**
The iii engine is ELv2 (non-open-source for commercial/SaaS use; fine for personal use). For VECTOR as a local-first single-owner system, iii would add value only if VECTOR needs to distribute work across multiple processes or machines. Currently VECTOR's districts run in-process under the Governor's coroutine loop. The overhead of running a Rust engine sidecar + WebSocket protocol for something already handled by asyncio + APScheduler is unjustified.

However, iii has one genuinely useful piece: the **Python SDK's trigger primitives** (HTTP trigger, cron trigger, queue subscription, state-change trigger, stream). These patterns are cleaner than VECTOR's current ad-hoc `@router.on_event` + APScheduler mix. The SDK code (`triggers.py`, `channels.py`, `state.py`, `stream.py`) is well-designed Python — Apache 2.0 licensed.

**Integration plan:**
Do NOT run the iii Rust engine as a VECTOR dependency — unnecessary operational overhead for a local system.

DO harvest the Python SDK trigger patterns:
- `iii-sdk/src/iii/triggers.py`: `TriggerHandler`, `TriggerConfig`, `TriggerTypeRef` abstractions are clean. VECTOR's `cron_jobs.py` could adopt the same pattern.
- `iii-sdk/src/iii/channels.py`: `ChannelReader`/`ChannelWriter` with stream semantics — useful reference for VECTOR's event_bus improvement.
- `iii-sdk/src/iii/state.py`: persistent state API (get/set with TTL) — VECTOR uses episodic.py for this but iii's key-value state API is lighter for simple cases.

**Verdict: SAFE TO DELETE (engine) / PATCH VECTOR (SDK patterns)**
The Rust engine binary is not useful for VECTOR's local-first architecture. The Python SDK has good design patterns worth harvesting into VECTOR's cron/event-bus layer but nothing that blocks the repo from being deleted after extraction.

**Gaps to add to bug tracker:**
- W11: Harvest `iii-sdk` trigger pattern abstractions (`TriggerHandler`, `TriggerConfig`) into `core/event_bus/` as a cleaner interface for registering cron/HTTP/queue triggers. Current `cron_jobs.py` uses ad-hoc APScheduler calls; adopting iii-style typed trigger configs would make the system more inspectable and testable.
- W12: VECTOR's `core/loop/cron_jobs.py` has no unit tests. Add tests for the cron trigger registrations, using iii-SDK's `tests/test_api_triggers.py` as a model for how to mock the scheduler and verify trigger configs.

---

## 5. hyperframes-main

**What it is:**
HeyGen's open-source HTML-to-video rendering framework (Apache 2.0). Core concept: write a composition as an HTML file with `data-*` timing attributes + GSAP/CSS/Lottie/Three.js animations. The engine (Puppeteer + FFmpeg) seeks each frame in headless Chrome and encodes the result to deterministic MP4.

Key packages:
- `@hyperframes/engine`: frame capture service (Puppeteer → PNG frames), parallel coordinator, audio mixer, chunk encoder, streaming encoder, HDR capture
- `@hyperframes/producer`: HTTP render server (`POST /render`, `POST /render/stream` SSE, `GET /health`) — clean REST API, accepts HTML path, returns MP4 download URL
- `@hyperframes/cli`: `npx hyperframes init/preview/render/lint/inspect` — non-interactive CLI
- `@hyperframes/studio`: browser-based composition editor
- `@hyperframes/shader-transitions`: WebGL shader transitions
- `@hyperframes/aws-lambda`: distributed render on Lambda

Skill files (`skills/`): `hyperframes`, `hyperframes-cli`, `hyperframes-media`, `website-to-hyperframes`, `gsap`, `css-animations`, `lottie`, `three`, etc. — comprehensive agent-readable reference for the entire video production workflow.

**VECTOR parity check:**
- `core/video/html_renderer.py`: Playwright-based frame capture (Chromium), local HTTP server, window.__vector seek protocol, GPU/software toggle, 4K supersampling. STRONGLY PARALLEL to `@hyperframes/engine`.
- `core/video/video_encoder.py`: FFmpeg encode pipeline. Parallel to hyperframes' chunk encoder.
- `core/video/audio_mixer.py`: multi-track audio. Parallel to hyperframes' audio mixer.
- `core/video/vector_composer.py`: high-level orchestrator (HTML → frames → audio → MP4). Parallel to `@hyperframes/producer`.
- `core/video/website_to_video.py`: URL → screenshot → HTML composition → render. Parallel to `skills/website-to-hyperframes/`.

VECTOR's Python video stack (`core/video/`) is functionally equivalent to HyperFrames' core pipeline. It was built independently (not absorbed from hyperframes). Both use headless Chrome + FFmpeg + seekable HTML compositions.

Key differences:
1. **Hyperframes uses Puppeteer (Node.js); VECTOR uses Playwright (Python)** — different browsers but equivalent capability.
2. **Hyperframes has a tested, production-grade frame capture layer** with: `parallelCoordinator.ts` (multi-browser-context parallel capture tested to convergence), `chunkEncoder.ts` (streaming chunk-based encoding for long videos), `streamingEncoder.ts`, `hdrCapture.ts`, `extractionCache.ts`, `videoFrameInjector.ts`, `audioVolumeEnvelope.ts`. VECTOR's `html_renderer.py` has the basics but lacks: chunk-based streaming encode, HDR capture, extraction cache, audio volume envelopes.
3. **HyperFrames' producer server has a clean REST API** (`POST /render`) — VECTOR has no equivalent HTTP render endpoint; `core/video/` is a library only.
4. **HyperFrames' skills library** (`skills/hyperframes/`, `skills/website-to-hyperframes/`, etc.) is a rich agent reference library with production-grade guidance: beat direction, prompt expansion, visual styles, motion principles, per-library references (GSAP, Lottie, Three.js). VECTOR's video agents have none of this structured guidance.
5. **Catalog** (`npx hyperframes add flash-through-white`, `npx hyperframes add data-chart`): reusable blocks for transitions, captions, charts, overlays — zero VECTOR equivalent.

**Integration plan:**
Run `@hyperframes/producer` as a local HTTP sidecar. VECTOR's Python video pipeline calls it for rendering instead of running Playwright + FFmpeg in-process:

```bash
# Build once
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\hyperframes-main"
npm install && npm run build

# Run producer sidecar (add to run_vector.py startup)
node packages/producer/dist/server.js --port 7421
```

Python integration in `core/video/vector_composer.py`:
```python
# Optional: delegate to hyperframes producer if running
async def render_via_hyperframes(html_path: str, output_path: str, fps: int = 30) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post("http://localhost:7421/render", json={
            "compositionPath": html_path,
            "outputPath": output_path,
            "fps": fps,
        })
        return r.json()["outputUrl"]
```

Additionally, install the hyperframes skill library:
```bash
npx skills add heygen-com/hyperframes
```

This gives VECTOR agents the full `hyperframes`, `website-to-hyperframes`, `gsap`, `lottie`, `css-animations` skills — structured guidance for writing video compositions that VECTOR's Python agents currently lack.

**Verdict: INTEGRATE DIRECTLY + PATCH VECTOR**
Run `@hyperframes/producer` as a sidecar render server. Install the skills library. VECTOR's Python video stack should use hyperframes as the render backend rather than running its own parallel Playwright-based renderer — hyperframes' engine is better tested and has features (HDR, chunk encode, audio envelopes, streaming SSE progress) that VECTOR's Python equivalent lacks. VECTOR's HTML renderer (`html_renderer.py`) remains as a fallback if the sidecar is not running.

**Gaps to add to bug tracker:**
- W13: Build `@hyperframes/producer` and add a startup call in `run_vector.py` (or `scripts/install_service.ps1`) to launch it on port 7421 as a sidecar.
- W14: Add `render_via_hyperframes(html_path, output_path)` to `core/video/vector_composer.py` — calls the producer sidecar; falls back to VECTOR's own `html_renderer.py` if the sidecar is unreachable. Follows VECTOR's fallback-chain convention.
- W15: Install hyperframes skill library (`npx skills add heygen-com/hyperframes`) so VECTOR agents have structured guidance for writing HTML compositions, beat direction, GSAP animation patterns, and the `website-to-hyperframes` production workflow.
- W16: Harvest `hyperframes/packages/engine/src/services/chunkEncoder.ts` pattern into `core/video/video_encoder.py` — chunk-based streaming encode for long videos (>60s) currently not supported by VECTOR's encoder.
- W17: `core/video/html_renderer.py` has no extraction cache (repeated renders of the same composition re-parse from scratch). Add a simple `sha256(html_path + variables) → cached_frames_dir` check, mirroring `hyperframes/packages/engine/src/services/extractionCache.ts`.

---

## Summary

| Repo | Verdict | Action | Priority |
|------|---------|--------|----------|
| `ai-website-cloner-template-master` | INTEGRATE DIRECTLY | Install `/clone-website` skill into `~/.claude/skills/` | Medium — useful for design district + competitor analysis |
| `glif-mcp-server-main` | INTEGRATE DIRECTLY | Build + add to `.mcp.json` as MCP sidecar, add `GLIF_API_TOKEN` to `.env` | Medium — external AI workflow pipelines for content/marketing |
| `NotFair-main` | INTEGRATE DIRECTLY + PATCH VECTOR | Install plugin + wire remote MCP servers; absorb policy rules + SEO references into Python agents | High — live Google/Meta Ads API access + GEO optimizer is a real gap |
| `iii-main` | SAFE TO DELETE (engine) / PATCH VECTOR (SDK patterns) | Harvest trigger pattern abstractions; do not run Rust engine | Low — conceptual harvest only; VECTOR doesn't need distributed workers |
| `hyperframes-main` | INTEGRATE DIRECTLY + PATCH VECTOR | Run producer sidecar on port 7421; install skills; wire as render fallback | High — better render engine than VECTOR's own `html_renderer.py` |

## New Gaps for Master Tracker

| ID | Issue | Location | Severity |
|----|-------|----------|----------|
| W1 | Install `/clone-website` skill from `ai-website-cloner-template-master` into `~/.claude/skills/` | `~/.claude/skills/clone-website/` | MED |
| W2 | Add `extract_design_tokens(url)` to `core/browser/dom_pruner.py` — `getComputedStyle` sweep for colors/fonts/spacing | `core/browser/dom_pruner.py` | LOW |
| W3 | Build `glif-mcp-server-main` and add to `.mcp.json`; add `GLIF_API_TOKEN` to `.env` + `core/config.py` | `.mcp.json`, `core/config.py` | MED |
| W4 | Add `districts/content/glif_workflow_agent.py` — thin wrapper over glif MCP tools for content pipeline | `districts/content/` | LOW |
| W5 | Add `NotFair-GoogleAds` + `NotFair-MetaAds` remote MCP servers to VECTOR's `.mcp.json` | `.mcp.json` | HIGH |
| W6 | Install NotFair plugin skills into `brain/.claude/skills/notfair/` | `brain/.claude/skills/` | HIGH |
| W7 | Extend `google_ads_agent.py` with GAQL parallel fan-out, change-event analysis, business-context.json persistence | `districts/marketing/google_ads_agent.py` | MED |
| W8 | Extend `meta_ads_agent.py` with Learning Phase triage, frequency fatigue scoring, CBO/ABO/Advantage+ rules | `districts/marketing/meta_ads_agent.py` | MED |
| W9 | Build `geo_optimizer_agent.py` — GEO score (0-100) for AI search citation (ChatGPT/Claude/Perplexity/Gemini/AI Overviews) | `districts/marketing/geo_optimizer_agent.py` | HIGH (2026 traffic channel) |
| W10 | Expand `core/api/routers/seo.py` stub to full action router with `/seo/audit`, `/seo/keywords`, `/seo/geo-score` | `core/api/routers/seo.py` | MED |
| W11 | Harvest iii-SDK `TriggerHandler`/`TriggerConfig` pattern into `core/event_bus/` for typed trigger registration | `core/event_bus/` | LOW |
| W12 | Add unit tests for `core/loop/cron_jobs.py` trigger registrations (reference: iii-sdk's `test_api_triggers.py`) | `tests/test_cron_jobs.py` | LOW |
| W13 | Build `@hyperframes/producer` and add as sidecar startup in `run_vector.py` or `install_service.ps1` on port 7421 | `run_vector.py` / `scripts/` | HIGH |
| W14 | Add `render_via_hyperframes()` to `core/video/vector_composer.py` with fallback to `html_renderer.py` | `core/video/vector_composer.py` | HIGH |
| W15 | Install hyperframes skills (`npx skills add heygen-com/hyperframes`) for composition guidance in agent sessions | `~/.claude/skills/` | HIGH |
| W16 | Harvest chunk-based streaming encode pattern from `hyperframes/engine/src/services/chunkEncoder.ts` into `core/video/video_encoder.py` | `core/video/video_encoder.py` | MED |
| W17 | Add extraction cache to `core/video/html_renderer.py` (sha256 hash of html_path + variables → cached frames dir) | `core/video/html_renderer.py` | LOW |
