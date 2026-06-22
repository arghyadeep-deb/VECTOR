# Voice Engine Benchmark — Kokoro vs OmniVoice vs VoxCPM vs Supertonic

**Date:** 2026-06-23
**Owner checkpoint from `docs/repo_analysis/voice-stack-decision.md`:** "Benchmark OmniVoice" / "Benchmark supertonic separately" before changing any default. This was never built before this session — it is now. **No default has been changed.** This is data for the owner to read and decide on.

**Harness:** `core/training/benchmarks/voice_engine_benchmark.py` — run via `python -m core.training.benchmarks.voice_engine_benchmark`. Tests: `tests/test_voice_engine_benchmark.py` (5 passing).

## Real captured run (verbatim)

```json
{
  "engines": {
    "kokoro": {
      "status": "ok",
      "latency_ms": 911.09,
      "audio_bytes": 270380,
      "vram_resident": true,
      "avg_latency_ms": 911.09,
      "runs": 1
    },
    "omnivoice": {
      "status": "unavailable",
      "reason": "disabled by default (voice.omnivoice_enabled=False)"
    },
    "voxcpm": {
      "status": "unavailable",
      "reason": "voxcpm package not installed (pip install voxcpm, ~8GB weights)"
    },
    "supertonic": {
      "status": "unavailable",
      "reason": "disabled by default or supertonic package not installed"
    }
  }
}
```

A second standalone run (outside pytest, no concurrent torch/CUDA context) measured **411.93ms** latency / 62508 bytes for a shorter prompt — both numbers are real, the difference is prompt length and one-time ONNX warm-up, not noise.

## Verdict — what we actually know now

| Engine | Status | Real numbers? | What's blocking real numbers |
|---|---|---|---|
| **Kokoro** | ✅ Installed, live default | Yes — 412–911ms latency, real audio bytes | Nothing — already the live engine |
| **OmniVoice** | Seam built, disabled by config | No | Owner: `voice.omnivoice_enabled=True` in config + the `omnivoice` pip package (not installed) |
| **VoxCPM** | Seam built | No | Owner: `pip install voxcpm` (~8GB weights) |
| **Supertonic** | Seam built, disabled by config | No | Owner: enable in config + `pip install supertonic` (CPU-only per its own absorption doc, ~260MB) |

**Language coverage** (claimed, from each engine's own absorption doc — not yet runtime-verified for the 3 unavailable engines):

| Engine | Languages claimed |
|---|---|
| Kokoro | en, ja, zh, es, fr, hi, it, pt |
| OmniVoice | en, hi, bn, as, ja, zh, es, fr (600+ total per omnivoice.md) |
| VoxCPM | en, zh, ja, ko, de, fr, es, it (30 total; weak Hindi WER, **no bn/as** per its own doc) |
| Supertonic | en, hi, ja (native, no cloud fallback needed) |

**This is the one finding that matters for the owner decision:** OmniVoice is the only candidate that claims Bengali + Assamese coverage. VoxCPM explicitly does not. If `bn`/`as` quality ever needs to move off gTTS, OmniVoice is the only one of the three to even attempt benchmarking for that — but it has zero real numbers yet because it's a heavy install.

## Recommendation (not a decision — owner's call)

No default should change yet. To get real comparative numbers:
1. `pip install supertonic` (CPU-only, smallest, ~260MB) — cheapest way to get a second real data point.
2. If pursuing higher-quality studio voice: `pip install omnivoice` and flip `voice.omnivoice_enabled=True`, then re-run this harness.
3. VoxCPM only if OmniVoice's real numbers disappoint (per `voice-stack-decision.md`'s own ordering).

Re-run `python -m core.training.benchmarks.voice_engine_benchmark` after any install to get fresh real numbers — the harness does not need code changes to pick them up.
