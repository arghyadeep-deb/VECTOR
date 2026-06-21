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

## Recommended sequence
Do **VoxCPM (#2)** and **youtube gaps (#3)** first — bounded, high-confidence, fast wins.
Then **train-llm post-training (#1)** — biggest payoff but largest effort; needs its own plan.
**turbovec (#4)** only when corpus scale demands it. **voicebox (#5):** skip.
