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
