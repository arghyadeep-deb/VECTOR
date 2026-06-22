# Repo Absorption Batch — Ranked Synthesis (2026-06-21)

Five repos analyzed in parallel. Per-repo verdicts in this dir. Hand this file to Sonnet
as the integration order. Absorption rule (always): absorb ONLY gaps, reimplement in
Python, reuse VECTOR seams, no foreign traces (sweep hyphen/underscore/space/PascalCase +
User-Agent/header strings), gate any outward/money/file action through PermissionGateway.

## Ranked integration order

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 1 | **train-llm-from-scratch** | IMPLEMENT (post-training only) | Closes the loop: VECTOR reasons → stores reasoning_chains → **trains its own aligned model** via SFT/DPO/GRPO. This is the vector-chairman/OpenMythos endgame. counterfactual.py rejections → DPO preference pairs. | 2–3 sessions | **HIGH** |
| 2 | **VoxCPM** | UPGRADE | Replace Chatterbox cloning with VoxCPM2 (Apache-2.0, local): text-described "Voice Design" for the British VECTOR voice, better cloning (SIM 85.4 EN), 48 kHz, 30 langs. Keep Kokoro for live convo (VRAM). | 1 session + owner downloads 8 GB weights | **HIGH** |
| 3 | **youtube-automation-agent** | IMPLEMENT (3 narrow gaps) | 85% duplicate of `districts/content/`. Real gaps: live YouTube **trending harvest** (Data API mostPopular), **competitor channel analysis**, deterministic **SEO scorer + chapter builder**. MIT. | ~1.5 days | MEDIUM |
| 4 | **turbovec** | UPGRADE (opt-in, scale-gated) | Rust+Python ANN index, 4 GB/10M, faster than FAISS, pip-install. Only matters at >~1M vectors; lightrag coupling is the risk. Add behind a config flag, don't default. | 1 session + benchmark | LOW |
| 5 | **voicebox** | SKIP (already absorbed) | Same jamiepine/voicebox absorbed 2026-05-27. TTS/cloning superseded by VoxCPM. Only *maybe*-new: system dictation (type-into-any-app) — niche, owner-optional. | — | SKIP |

## Hard constraints Sonnet must respect
- **VRAM 12 GB / OLLAMA_MAX_LOADED_MODELS:** VoxCPM 2B (~8 GB) loads on-demand + unloads; cannot co-reside with vector-focus permanently. Serialize behind the model-residency lock (already in `hands/runner.py`).
- **Hindi/Bengali/Assamese:** VoxCPM Hindi WER is weak, no BN/AS — keep gTTS for `hi`/`bn`/`as`.
- **train-llm:** skip from-scratch pretraining (needs H100s); LoRA/small-scale only on the 5070 Ti. Run training overnight via a Hand / weekly_scheduler.
- These are ADDITIONS/UPGRADES — keep regression tests, run offline, don't touch the running soak.

## Recommended sequence (batch 1)
Do **VoxCPM (#2)** and **youtube gaps (#3)** first — bounded, high-confidence, fast wins.
Then **train-llm post-training (#1)** — biggest payoff but largest effort; needs its own plan.
**turbovec (#4)** only when corpus scale demands it. **voicebox (#5):** skip.

---

# Batch 2 (2026-06-22) — 5 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 6 | **SkillSpector** | IMPLEMENT (security) | NVIDIA, Apache-2.0. VECTOR absorbs external skills/repos with **zero source vetting** — `skills/loader.py` injects SKILL.md into prompts unscanned; audit found vendored jailbreak scripts. New surface: YARA (VECTOR has none), MCP tool-poisoning + Unicode/homoglyph/RTL deception, MCP least-privilege, static source→sink taint, OSV.dev CVE. Wire as a **pre-load + pre-absorption quarantine gate**. | 1–2 sessions | **HIGH** |
| 7 | **supertonic** | UPGRADE (live TTS) | On-device ONNX, **CPU-only / zero VRAM** (huge on 12 GB), ~99M/260 MB, sub-second, MIT code + OpenRAIL-M weights. Native local HI/JA (drops gTTS-cloud for `hi`). Replaces **Kokoro** as live engine after a voice A/B. No local cloning (that's VoxCPM's job). | 1 session | MED (HIGH for VRAM relief) |
| 8 | **supervision** | IMPLEMENT (augments sensing) | Roboflow, MIT, pip. Camera perception today is only face-ID + EAR fatigue — no person detection/tracking/zones. Upgrades the brittle frontal-face presence check (handles "present but turned away"). Needs a small YOLO (ultralytics). Sequence after ambient Part B.1. | 1 session | MED |
| 9 | **text-to-cad** | SKIP (bookmark) | MIT, build123d/OpenCascade. VECTOR has zero CAD; owner is a software builder, not hardware. Shiny-object scope creep. Revisit only if owner pivots to hardware. | — | LOW |
| 10 | **remotion** | SKIP | Source-available (NOT OSS), restrictive license (paid for orgs >3, derivatives restricted) — disqualifies autonomous/monetized content use. And VECTOR already built the same Playwright+ffmpeg composer in `core/video/` (`vector_composer.py`+`html_renderer.py`). | — | SKIP |

## MASTER RANKING (both batches, integration order for Sonnet)
1. **SkillSpector** (HIGH, security) — *do this FIRST*: it vets every repo/skill you absorb next, including the rest of this list. Self-protecting.
2. **train-llm post-training** (HIGH, strategic) — SFT/DPO/GRPO on reasoning_chains; own plan.
3. **VoxCPM** (HIGH, voice cloning) + **supertonic** (live TTS) — do together: they form the new voice stack.
4. **supervision** (MED) — after ambient Part B.1 (fatigue→context_engine) lands.
5. **youtube gaps** (MED) — 3 narrow content additions.
6. **turbovec** (LOW, opt-in/scale-gated).
7. SKIP: text-to-cad, remotion, voicebox.

## The clean voice stack (from both batches) — fits 12 GB
- **Live conversation:** Supertonic (CPU/zero-VRAM, native HI/JA) → replaces Kokoro after A/B.
- **Cloning / British "VECTOR voice" persona:** VoxCPM2 (load-on-demand, 8 GB).
- **Fallback:** Kokoro. **Bengali/Assamese:** keep gTTS (none of these support BN/AS).
- All three serialize behind the model-residency lock in `hands/runner.py`.

---

# Batch 3 (2026-06-22) - 4 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 11 | **quant-mind-master** | IMPLEMENT (narrow research ingestion) | MIT. VECTOR already has research agents, but lacks a clean paper-ingestion contract with typed inputs, section-tree artifacts, `as_of`, source/extraction refs, content hashes, citations, and canonical embedding text. Extend `PaperReader`/research library; do not import the framework. | 1 session | MED |
| 12 | **Pixelle-Video-main** | IMPLEMENT (2 narrow content upgrades) | Apache-2.0. VECTOR already owns the render/video engine. Useful gaps: asset-based storyboard generation from user photos/videos and a small provider capability registry for media models/workflows. Skip Streamlit/FastAPI engine duplication. | 1-2 sessions | MED |
| 13 | **OpenAlice-master** | LEARN / clean-room only | AGPL-3.0-only. Do not copy code. Useful architecture: broker carrier boundary, staged/committed/pushed order lifecycle, per-account guards, workspace inbox. VECTOR already has permission-gated execution, Cloudflare queue, Termux node, FinAgent/trading. Optional clean-room staged order lifecycle only. | 2-3 sessions if accepted | LOW-MED |
| 14 | **OpenCut-main** | SKIP | MIT but current repo is only a rewrite scaffold. README promises editor API/plugins/Rust core/MCP/headless later, but checkout has no real editor core or render API. VECTOR already has `core/video` and content pipeline. | - | SKIP |

## Updated master ranking notes

1. **Still first:** SkillSpector. It protects every future repo/skill absorption.
2. **Strategic:** train-llm post-training.
3. **Voice:** VoxCPM + supertonic.
4. **Ambient sensing:** supervision.
5. **Content/research narrow wins:** youtube gaps, Pixelle asset-video/provider registry, quant-mind paper-ingestion.
6. **Investment hardening:** OpenAlice-inspired staged order lifecycle only if the owner wants stronger real-money readiness.
7. **Scale-gated:** turbovec.
8. **Skip/bookmark:** OpenCut, text-to-cad, remotion, voicebox.

---

# Batch 4 (2026-06-22) - 1 more repo

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 15 | **open-webui-main** | DO NOT ABSORB; optionally integrate beside VECTOR | Source-available license with branding restrictions. Huge overlap with VECTOR's chat/RAG/auth/admin/voice surfaces. Best value is an OpenAI-compatible VECTOR gateway so Open WebUI can connect externally, plus clean-room security/chat UX patterns. | 0.5-1 session for gateway; 1-2 sessions for hardening patterns | MED for compatibility, LOW for absorption |

## Updated master ranking notes after Batch 4

1. **Still first:** SkillSpector. It should vet every future repo/skill absorption.
2. **Strategic:** train-llm post-training.
3. **Voice:** VoxCPM + supertonic.
4. **Ambient sensing:** supervision.
5. **Access/device mesh:** Cloudflare queue + Termux polling remains the real 24/7 build step.
6. **Compatibility:** OpenAI-compatible VECTOR gateway so Open WebUI and similar clients can connect without copying their code.
7. **Content/research narrow wins:** youtube gaps, Pixelle asset-video/provider registry, quant-mind paper-ingestion.
8. **Investment hardening:** OpenAlice-inspired staged order lifecycle only if stronger real-money readiness is desired.
9. **Scale-gated:** turbovec.
10. **Skip/bookmark:** OpenCut, text-to-cad, remotion, voicebox.

---

# Batch 5 (2026-06-22) - 3 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 16 | **OmniVoice-master** | IMPLEMENT as optional on-demand voice engine | Apache-2.0. Compact Python TTS package with 600+ languages, zero-shot cloning, voice design, and expressive tokens. Best first use is Voice Studio / high-quality multilingual generation, not always-on live conversation until latency/VRAM are benchmarked. | 1 session benchmark + adapter | HIGH for voice, MED for live |
| 17 | **OmniRoute-main** | IMPLEMENT narrow provider-router hardening only | MIT. Huge TypeScript gateway overlaps VECTOR, but confirms need for provider health, circuit breakers, model lockouts, quota/budget tracking, capability registry, and OpenAI-compatible API. Do not copy stealth/free-tier/OAuth bypass surfaces. | 1-2 sessions | HIGH for provider resilience |
| 18 | **nautilus_trader-develop** | DO NOT ABSORB; clean-room safety ideas only | LGPL-3.0-or-later. Production Rust/Python trading engine. Too large and separate for VECTOR absorption. Useful as a north star for staged orders, risk snapshots, paper/live parity, and optional external engine later. | 2-4 sessions for clean-room hardening | MED |

## Updated master ranking notes after Batch 5

1. **Still first:** SkillSpector. It protects every repo/skill/model absorption.
2. **Voice now:** follow `voice-stack-decision.md`: OmniVoice for high-quality Voice Studio, one fast live engine only, hold VoxCPM, skip voicebox.
3. **Provider resilience:** OmniRoute-inspired clean-room provider health, circuit breakers, quota/budget tracking, and capability registry.
4. **Strategic:** train-llm post-training.
5. **Access/device mesh:** Cloudflare queue + Termux polling remains the real 24/7 build step.
6. **Compatibility:** OpenAI-compatible VECTOR gateway for Open WebUI and other clients.
7. **Ambient sensing:** supervision.
8. **Content/research narrow wins:** youtube gaps, Pixelle asset-video/provider registry, quant-mind paper-ingestion.
9. **Investment hardening:** OpenAlice + Nautilus-inspired staged order lifecycle, risk snapshots, and paper/live parity only if stronger real-money readiness is desired.
10. **Scale-gated:** turbovec.
11. **Skip/bookmark:** OpenCut, text-to-cad, remotion, voicebox.

---

# Batch 6 (2026-06-22) - 4 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 19 | **LongCat-Video-main** | DO NOT ABSORB; optional external media provider | MIT code, but weights need separate license checks. Huge 13.6B video/avatar stack. Useful only as a disabled provider-registry/sidecar entry for long video, video continuation, and audio-to-avatar workflows. | 1 session for registry/spec; much larger for local integration | MED-LOW |
| 20 | **last30days-skill-main** | VET / CLEAN-ROOM research ideas | MIT, but it is an agent skill with large prompt/runtime instructions and shell/web/write expectations. Useful ideas: recency-first social intelligence, source fanout, signal scoring, clustering, HTML briefs. Must be gated behind SkillSpector/quarantine. | 1-2 sessions | MED-HIGH |
| 21 | **kickbacks.ai-main** | HARD SKIP / SECURITY CAUTION | Proprietary source-available ad injection into Codex/Claude surfaces with telemetry/kill-switch patterns. Do not run/copy. Useful only as a detector pattern for SkillSpector-style extension/adware checks. | 0.5 session for a future rule | SKIP / HIGH security |
| 22 | **helix-db-main** | OPTIONAL external memory mirror only | Apache/MIT SDK. Graph-vector DB can be useful for long-term knowledge graph experiments, but VECTOR's ADR keeps SQLite as local hot path. Do not replace runtime memory. | 1-2 sessions | LOW-MED |

## Updated master ranking notes after Batch 6

1. **Still first:** SkillSpector. It protects repo, skill, model, MCP, and plugin absorption.
2. **Security add-on:** kickbacks-style extension/adware detection belongs inside SkillSpector or the workspace-security gate.
3. **Voice:** follow `voice-stack-decision.md`: OmniVoice for high-quality Voice Studio, one fast live engine only, hold VoxCPM, skip voicebox.
4. **Provider resilience:** OmniRoute-inspired health checks, circuit breakers, quota/budget tracking, and capability registry.
5. **Strategic:** train-llm post-training.
6. **Access/device mesh:** Cloudflare queue + Termux polling remains the real 24/7 build step.
7. **Compatibility:** OpenAI-compatible VECTOR gateway for Open WebUI and other clients.
8. **Research/social intelligence:** last30days clean-room mode plus quant-mind paper ingestion and YouTube gaps.
9. **Content/media:** Pixelle provider registry first; LongCat only as optional external video/avatar sidecar.
10. **Memory:** HelixDB only as disabled-by-default graph-vector mirror after SQLite memory contracts are stable.
11. **Ambient sensing:** supervision.
12. **Investment hardening:** OpenAlice + Nautilus-inspired staged order lifecycle, risk snapshots, and paper/live parity only if stronger real-money readiness is desired.
13. **Scale-gated:** turbovec.
14. **Skip/bookmark:** kickbacks feature behavior, OpenCut, text-to-cad, remotion, voicebox.

---

# Batch 7 (2026-06-22) - 4 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 23 | **headroom-main** | IMPLEMENT narrow context-budget layer | Apache-2.0. Directly useful for reducing prompt/tool-output/research bloat. Absorb patterns: reversible compression handles, content-type compression policy, token-savings telemetry, output verbosity shaping. Do not wrap VECTOR wholesale with its proxy. | 1-2 sessions | HIGH-MED |
| 24 | **evolver-main** | CLEAN-ROOM ONLY | GPL-3.0-or-later and future source-available warning. VECTOR already has HP/ghost-memory evolution. Useful ideas: typed EvolutionEvent, StrategyGene/Capsule schema, evidence-backed prompt-policy changes, review/rollback metadata. | 1-2 sessions | MED-HIGH |
| 25 | **evolution-api-main** | DO NOT ABSORB; optional external WhatsApp provider | Apache-2.0 plus brand/notification conditions. Full WhatsApp/messaging API duplicates VECTOR comms. Useful only as an external endpoint/provider reference; prefer official WhatsApp Cloud API for production. | 1 session | MED |
| 26 | **ECC-main** | VET / SELECTIVE CLEAN-ROOM IDEAS | MIT but huge cross-harness skill/hook/plugin system. Do not bulk install. Useful for SkillSpector, skill inventory, hook/config audit, command registry validation, and status snapshots. | 1-2 sessions | HIGH for governance |

## Updated master ranking notes after Batch 7

1. **Still first:** SkillSpector, now with ECC-style skill inventory and kickbacks-style extension/adware detection.
2. **Context budget:** Headroom-inspired VECTOR-native compression/retrieval handles should be a near-term JARVIS stability upgrade.
3. **Voice:** follow `voice-stack-decision.md`: OmniVoice for high-quality Voice Studio, one fast live engine only, hold VoxCPM, skip voicebox.
4. **Provider resilience:** OmniRoute-inspired health checks, circuit breakers, quota/budget tracking, and capability registry.
5. **Strategic evolution/training:** train-llm post-training plus Evolver-inspired event/gene audit schemas, clean-room only.
6. **Access/device mesh:** Cloudflare queue + Termux polling remains the real 24/7 build step.
7. **Compatibility:** OpenAI-compatible VECTOR gateway for Open WebUI and other clients.
8. **Messaging:** WhatsApp should be a provider adapter behind VECTOR comms, not a copied Evolution API backend.
9. **Research/social intelligence:** last30days clean-room mode plus quant-mind paper ingestion and YouTube gaps.
10. **Content/media:** Pixelle provider registry first; LongCat only as optional external video/avatar sidecar.
11. **Memory:** HelixDB only as disabled-by-default graph-vector mirror after SQLite memory contracts are stable.
12. **Ambient sensing:** supervision.
13. **Investment hardening:** OpenAlice + Nautilus-inspired staged order lifecycle, risk snapshots, and paper/live parity only if stronger real-money readiness is desired.
14. **Scale-gated:** turbovec.
15. **Skip/bookmark:** kickbacks feature behavior, OpenCut, text-to-cad, remotion, voicebox, bulk ECC install, Evolver code absorption.

---

# Batch 8 (2026-06-22) - 5 more repos

| # | Repo | Verdict | Why / value | Effort | Priority |
|---|------|---------|-------------|--------|----------|
| 27 | **crawl4ai-main** | IMPLEMENT narrow crawler/extraction provider | Apache-2.0 plus attribution requirement. Strong fit for LLM-ready Markdown, schema extraction, BM25 filtering, deep-crawl resume, screenshots, and citation-ready crawl artifacts. Do not expose the full Docker API blindly. | 1-2 sessions | HIGH |
| 28 | **competitor-x-ray-main** | VET / CLEAN-ROOM workflow | MIT, tiny skill pack. Useful competitor intelligence workflow: ICP, funnel, monetization, evidence tiers, threat ranking, designed report. Skill file has hidden/zero-width/provenance-like text, so scan before any use. | 1 session | MED-HIGH |
| 29 | **cal.diy-main** | DO NOT ABSORB; clean-room scheduling concepts | MIT but huge Next.js/Prisma scheduling platform. VECTOR needs small availability/booking/calendar adapters, not a full Cal.com fork. | 1-2 sessions if booking needed | LOW-MED |
| 30 | **awesome-llm-apps-main** | REFERENCE ONLY | Apache-2.0 cookbook of many standalone agent/RAG templates. Useful as pattern library for specific gaps, but bulk copy would create duplicate tutorial-grade code. | 0.5-1 session per selected pattern | LOW-MED |
| 31 | **auto-browser-main** | IMPLEMENT selected browser governance patterns | MIT. Strong fit for safe browser automation: approvals, operator identity, auth-profile encryption, witness receipts, PII scrubbing, human takeover, curated MCP tool profile. Optional sidecar later. | 1-2 sessions | HIGH-MED |

## Updated master ranking notes after Batch 8

1. **Still first:** SkillSpector, including skill inventory, hidden-character detection, extension/adware checks, and external skill quarantine.
2. **Browser and web safety:** Auto Browser governance plus Crawl4AI extraction provider are near-term JARVIS upgrades for real web work.
3. **Context budget:** Headroom-inspired VECTOR-native compression/retrieval handles.
4. **Voice:** follow `voice-stack-decision.md`: OmniVoice for high-quality Voice Studio, one fast live engine only, hold VoxCPM, skip voicebox.
5. **Provider resilience:** OmniRoute-inspired health checks, circuit breakers, quota/budget tracking, and capability registry.
6. **Strategic evolution/training:** train-llm post-training plus Evolver-inspired event/gene audit schemas, clean-room only.
7. **Access/device mesh:** Cloudflare queue + Termux polling remains the real 24/7 build step.
8. **Compatibility:** OpenAI-compatible VECTOR gateway for Open WebUI and other clients.
9. **Messaging:** WhatsApp should be a provider adapter behind VECTOR comms, not a copied Evolution API backend.
10. **Research/social intelligence:** last30days clean-room mode, competitor-x-ray workflow, quant-mind paper ingestion, and YouTube gaps.
11. **Content/media:** Pixelle provider registry first; LongCat only as optional external video/avatar sidecar.
12. **Calendar/booking:** Cal.diy only informs small VECTOR-native availability/booking schemas.
13. **Memory:** HelixDB only as disabled-by-default graph-vector mirror after SQLite memory contracts are stable.
14. **Ambient sensing:** supervision.
15. **Investment hardening:** OpenAlice + Nautilus-inspired staged order lifecycle, risk snapshots, and paper/live parity only if stronger real-money readiness is desired.
16. **Pattern library:** awesome-llm-apps only for specific selected examples.
17. **Scale-gated:** turbovec.
18. **Skip/bookmark:** kickbacks feature behavior, OpenCut, text-to-cad, remotion, voicebox, bulk ECC install, Evolver code absorption, full Cal.diy absorption.
