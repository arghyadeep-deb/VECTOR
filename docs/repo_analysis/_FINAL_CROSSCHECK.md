# Final Repo Crosscheck - VECTOR Absorption Strategy

**Date:** 2026-06-22

**Scope:** 31 external repos reviewed across 8 batches.

**Goal:** Make VECTOR more independent, diverse, dynamic, and JARVIS-like without bloating it with duplicate engines, unsafe skills, incompatible licenses, or full apps that should stay external.

## Executive Count

| Category | Count | Meaning |
|---|---:|---|
| Near-term implement / upgrade | 14 | Actually useful for VECTOR if reimplemented narrowly and tested |
| Deferred / optional sidecar / benchmark | 8 | Potentially helpful, but only after core contracts are stable or if owner priority changes |
| Reference / clean-room only | 5 | Useful ideas, but code/license/scope blocks absorption |
| Hard skip / not needed | 4 | Duplicate, unsafe, restrictive, or not aligned |

Total: **31 repos**.

## Near-Term Implementation Candidates

These make VECTOR more JARVIS-like in real capability, not just bigger.

| Priority | Repo | What to actually implement |
|---:|---|---|
| 1 | SkillSpector | Mandatory pre-load scanner for skills/repos/MCP/tools. Hidden Unicode, prompt injection, suspicious shell/network/file access, dependency/CVE checks. |
| 2 | auto-browser | Browser action governance: approvals, operator identity, encrypted auth profiles, PII scrubbing, audit/witness receipts, human takeover state. |
| 3 | crawl4ai | Web extraction provider: clean Markdown, schema extraction, BM25 pruning, crawl artifacts, content hashes, citations. |
| 4 | headroom | Context-budget manager: compression handles, retrieval, token telemetry, output verbosity shaping. |
| 5 | OmniRoute | Provider resilience: health checks, circuit breakers, quota/budget tracking, model lockouts, capability registry. |
| 6 | OmniVoice | High-quality Voice Studio engine, lazy-loaded. Benchmark before making live default. |
| 7 | train-llm-from-scratch | Not pretraining. Use SFT/DPO/GRPO on VECTOR reasoning chains and outcomes. |
| 8 | youtube-automation-agent | Only YouTube trending harvest, competitor channel analysis, SEO scorer, chapter builder. |
| 9 | supervision | Ambient person/presence/tracking upgrade for camera perception. |
| 10 | quant-mind | Paper/research ingestion contract with section tree, `as_of`, citations, hashes. |
| 11 | Pixelle-Video | Asset-based storyboard workflow and media-provider capability registry. |
| 12 | competitor-x-ray | VECTOR-native competitor-intelligence workflow with evidence tiers and threat ranking. |
| 13 | last30days-skill | Recency/social-intelligence research mode after SkillSpector quarantine. |
| 14 | supertonic | Benchmark as fast/low-resource live TTS candidate only. |

## Deferred Or Optional

These can help independence/diversity, but implementing them now would add weight before the base is ready.

| Repo | Status | Why deferred |
|---|---|---|
| VoxCPM | Hold | Good voice design/cloning, but overlaps OmniVoice. Revisit only if OmniVoice fails quality/language/setup tests. |
| turbovec | Scale-gated | Useful only when VECTOR memory/search exceeds large vector scale. Add only after benchmark. |
| HelixDB | Optional sidecar | Good for graph-vector mirror, but must not replace SQLite hot path. |
| LongCat-Video | Optional external provider | Valuable for avatar/long video only with GPU/cloud and verified model-weight license. |
| Evolution API | Optional external provider | WhatsApp backend if needed, but official WhatsApp Cloud API should be preferred. |
| Cal.diy | Optional concept source | Useful for availability/booking schemas, not full scheduling SaaS absorption. |
| open-webui | External client/gateway | Useful target for OpenAI-compatible VECTOR gateway, not code absorption. |
| awesome-llm-apps | Pattern library | Good examples, but only inspect specific templates when solving a specific gap. |

## Reference / Clean-Room Only

These can improve design quality, safety, or architecture, but should not be copied directly.

| Repo | Reason |
|---|---|
| Evolver | GPL; VECTOR already has HP/ghost-memory evolution. Use only event/gene/audit ideas. |
| ECC | Useful governance/hook/skill inventory ideas, but huge duplicate harness surface. |
| OpenAlice | AGPL; use clean-room staged order lifecycle and broker-boundary ideas only. |
| Nautilus Trader | LGPL and too large; use clean-room trading safety concepts only. |
| remotion | Restrictive/source-available and VECTOR already has a Playwright+ffmpeg composer. |

## Hard Skip / Not Needed

| Repo | Why |
|---|---|
| kickbacks.ai | Proprietary ad/telemetry/injection behavior. Security caution only. |
| voicebox | Already absorbed/superseded. Adds voice-stack duplication. |
| OpenCut | Current checkout is a scaffold, not a real editor/render core. |
| text-to-cad | Interesting but unrelated to current VECTOR/JARVIS goals unless owner moves into CAD/hardware. |

## Duplicate Clusters

### Voice

Too many voice repos were reviewed:

- OmniVoice
- VoxCPM
- supertonic
- voicebox
- existing Kokoro / pyttsx3 / gTTS

**Decision:** keep one high-quality studio engine and one fast live engine.

- High-quality studio: **OmniVoice first**
- Live conversation: **Kokoro now**, benchmark **supertonic**
- Fallback: **pyttsx3/gTTS**
- Hold: **VoxCPM**
- Skip: **voicebox**

This avoids VRAM pressure, duplicate routing, and test explosion.

### Video / Media

Reviewed:

- Pixelle-Video
- LongCat-Video
- OpenCut
- remotion
- existing VECTOR `core/video`

**Decision:** VECTOR owns the video engine. Add a media-provider registry and asset-storyboard workflow. LongCat can be an external provider later. Skip OpenCut/remotion.

### Research / Web Intelligence

Reviewed:

- crawl4ai
- last30days
- competitor-x-ray
- quant-mind
- youtube-automation-agent
- awesome-llm-apps examples

These are not pure duplicates if separated properly:

- Crawl4AI = extraction layer
- quant-mind = paper ingestion schema
- last30days = recency/social signal layer
- competitor-x-ray = business/creator competitor brief
- youtube = platform-specific content intelligence

**Decision:** implement as separate modes behind one research artifact schema.

### Agent Harness / Skill Systems

Reviewed:

- SkillSpector
- ECC
- Evolver
- last30days skill
- competitor-x-ray skill
- awesome agent skills

**Decision:** SkillSpector first. No external skill is trusted until scanned. ECC/Evolver are references, not installed systems.

### Trading / Money

Reviewed:

- OpenAlice
- Nautilus Trader
- existing FinAgent/backtest stack

**Decision:** no engine absorption. Only clean-room staged order, risk snapshot, paper/live parity, broker boundary ideas. Real-money actions stay behind PermissionGateway.

### Memory / Vector Search

Reviewed:

- turbovec
- HelixDB
- existing SQLite/FTS/semantic memory

**Decision:** SQLite remains hot path. turbovec is scale-gated. HelixDB is optional mirror only.

## SOC Crosscheck: Did We Under-Value Anything?

### Promote From "Maybe" To Real Candidate

1. **Auto Browser** should be promoted. It is not just browser automation; it provides the missing safety model for real-world web action.
2. **Crawl4AI** should be promoted. VECTOR needs robust clean extraction before better research and browsing can happen.
3. **Headroom** should be promoted. Context budget is a stability feature, not an optimization luxury.
4. **Competitor X-Ray** should be promoted as a workflow, not a skill import. It fits agency/startup/content intelligence.
5. **last30days** should be promoted after SkillSpector. It gives VECTOR current social/news intelligence.

### Keep Deferred Despite Being Interesting

1. **LongCat-Video**: impressive, but model-heavy and license/weights must be checked.
2. **HelixDB**: powerful, but replacing SQLite would hurt local reliability.
3. **Cal.diy**: useful idea, huge app.
4. **VoxCPM**: keep as backup to OmniVoice.
5. **turbovec**: only matters at scale.

### Correct Hard Skips

The hard skips still look correct:

- kickbacks.ai: trust/security violation.
- voicebox: duplicate.
- OpenCut: scaffold only.
- remotion: license + duplicate renderer.
- text-to-cad: bookmark only unless hardware/CAD becomes a real VECTOR district.

## Recommended Build Order For Sonnet

1. **SkillSpector security gate**
2. **Browser/Web layer:** Auto Browser governance + Crawl4AI extraction provider
3. **Context/provider layer:** Headroom-style context budget + OmniRoute provider resilience
4. **Voice layer:** OmniVoice adapter + supertonic benchmark
5. **Research layer:** quant-mind ingestion + last30days + competitor-x-ray + YouTube gaps
6. **24/7 access layer:** Cloudflare queue + Termux polling
7. **Strategic autonomy:** train-llm post-training + Evolver-style audit events
8. **Media/content:** Pixelle registry/storyboard; LongCat external provider later
9. **Optional external integrations:** Open WebUI gateway, WhatsApp provider, booking adapter
10. **Deferred scale:** turbovec, HelixDB mirror

## Final Judgment

To make VECTOR closer to JARVIS, do **not** maximize repo count. Maximize capability diversity under one coherent authority model.

The right absorption strategy is:

- one security gate
- one browser/web extraction layer
- one context budget layer
- one provider resilience layer
- one voice studio engine and one live voice engine
- one unified research artifact schema with multiple research modes
- one local-first memory hot path
- optional external sidecars only when they do not weaken VECTOR's core runtime

This gives VECTOR independence and dynamism without turning it into a pile of overlapping apps.

