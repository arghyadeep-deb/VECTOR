"""Voice ENGINE comparison harness — Kokoro vs OmniVoice vs VoxCPM vs Supertonic.

This is the owner checkpoint from docs/repo_analysis/voice-stack-decision.md:
"Benchmark OmniVoice" / "Benchmark supertonic separately" before changing any
default. It measures real latency/output for whichever engines are actually
installed in this environment, and reports "unavailable" honestly for the
rest — it never installs anything and never flips a default. The owner reads
the report and decides.

Run directly to produce the report:
    PYTHONUTF8=1 python -m core.training.benchmarks.voice_engine_benchmark
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from loguru import logger

__all__ = ["benchmark_engine", "run_voice_engine_benchmark", "ENGINE_PROBES", "LANGUAGE_COVERAGE"]


# Claimed language coverage per each engine's own absorption doc / docstring
# (docs/repo_analysis/*.md) — metadata, not a runtime check, since the
# packages for omnivoice/voxcpm/supertonic aren't installed in this environment.
LANGUAGE_COVERAGE = {
    "kokoro": ["en", "ja", "zh", "es", "fr", "hi", "it", "pt"],
    "omnivoice": ["en", "hi", "bn", "as", "ja", "zh", "es", "fr"],  # 600+ languages per omnivoice.md
    "voxcpm": ["en", "zh", "ja", "ko", "de", "fr", "es", "it"],  # 30 langs per VoxCPM.md; weak Hindi WER, no bn/as
    "supertonic": ["en", "hi", "ja"],  # native HI/JA per supertonic.md
}


def _probe_kokoro(text: str, language: str) -> dict:
    try:
        from core.voice.tts import VoiceTTS
    except Exception as exc:
        return {"status": "unavailable", "engine": "kokoro", "reason": f"import failed: {exc}"}

    tts = VoiceTTS()
    if not getattr(tts, "_kokoro_ok", False):
        return {"status": "unavailable", "engine": "kokoro", "reason": "kokoro model not loaded"}

    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "bench.wav")
        started = time.perf_counter()
        result = tts.synthesize_to_file(text, out_path)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if result.get("status") != "ok":
            return {"status": "unavailable", "engine": "kokoro", "reason": result.get("error", "synthesis failed")}
        audio_bytes = Path(out_path).stat().st_size
        return {
            "status": "ok",
            "engine": "kokoro",
            "latency_ms": latency_ms,
            "audio_bytes": audio_bytes,
            "vram_resident": True,  # kokoro is the permanent-VRAM live engine per models.md
        }


def _probe_omnivoice(text: str, language: str) -> dict:
    try:
        from core.voice.engines.omnivoice_engine import OmniVoiceEngine
    except Exception as exc:
        return {"status": "unavailable", "engine": "omnivoice", "reason": f"import failed: {exc}"}

    engine = OmniVoiceEngine()
    if not engine.config.enabled:
        return {"status": "unavailable", "engine": "omnivoice", "reason": "disabled by default (voice.omnivoice_enabled=False)"}
    try:
        import omnivoice  # noqa: F401
    except ImportError:
        return {"status": "unavailable", "engine": "omnivoice", "reason": "omnivoice package not installed"}

    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "bench_omnivoice.wav")
        started = time.perf_counter()
        try:
            saved_path = engine.synthesize_to_file(text, language=language, output_path=out_path)
        except Exception as exc:
            return {"status": "unavailable", "engine": "omnivoice", "reason": str(exc)}
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        audio_bytes = Path(saved_path).stat().st_size if Path(saved_path).exists() else 0
        return {"status": "ok", "engine": "omnivoice", "latency_ms": latency_ms, "audio_bytes": audio_bytes}


def _probe_voxcpm(text: str, language: str) -> dict:
    try:
        from core.voice.voxcpm_cloning import get_voxcpm_cloner, VoxCPMCloner
    except Exception as exc:
        return {"status": "unavailable", "engine": "voxcpm", "reason": f"import failed: {exc}"}

    if not VoxCPMCloner.available():
        return {"status": "unavailable", "engine": "voxcpm", "reason": "voxcpm package not installed (pip install voxcpm, ~8GB weights)"}

    cloner = get_voxcpm_cloner()
    started = time.perf_counter()
    try:
        samples, sample_rate = cloner.synthesize(text)
    except Exception as exc:
        return {"status": "unavailable", "engine": "voxcpm", "reason": str(exc)}
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    audio_bytes = int(len(samples) * 2) if samples is not None else 0  # int16-equivalent estimate
    return {"status": "ok", "engine": "voxcpm", "latency_ms": latency_ms, "audio_bytes": audio_bytes, "sample_rate": sample_rate}


def _probe_supertonic(text: str, language: str) -> dict:
    try:
        from core.voice.engines.supertonic_engine import SupertonicEngine
    except Exception as exc:
        return {"status": "unavailable", "engine": "supertonic", "reason": f"import failed: {exc}"}

    engine = SupertonicEngine()
    if not engine.available():
        return {"status": "unavailable", "engine": "supertonic", "reason": "disabled by default or supertonic package not installed"}

    started = time.perf_counter()
    try:
        result = engine.synthesize(text, language=language)
    except Exception as exc:
        return {"status": "unavailable", "engine": "supertonic", "reason": str(exc)}
    return {"status": "ok", "engine": "supertonic", "latency_ms": round((time.perf_counter() - started) * 1000, 2), **result}


ENGINE_PROBES = {
    "kokoro": _probe_kokoro,
    "omnivoice": _probe_omnivoice,
    "voxcpm": _probe_voxcpm,
    "supertonic": _probe_supertonic,
}


def benchmark_engine(engine_name: str, text: str, language: str = "en") -> dict:
    probe = ENGINE_PROBES.get(engine_name)
    if probe is None:
        return {"status": "error", "engine": engine_name, "error": f"unknown engine '{engine_name}'"}
    try:
        return probe(text, language)
    except Exception as exc:
        logger.warning("[VECTOR][voice_benchmark] {} probe crashed: {}", engine_name, exc)
        return {"status": "unavailable", "engine": engine_name, "reason": f"probe crashed: {exc}"}


def run_voice_engine_benchmark(texts: list[str] | None = None) -> dict:
    """Run all 4 engines against the same prompt set. Never raises."""
    texts = texts or ["Hello, this is VECTOR speaking. This is a benchmark test of voice synthesis quality."]

    engines: dict[str, dict] = {}
    for name in ENGINE_PROBES:
        results = [benchmark_engine(name, t) for t in texts]
        ok_results = [r for r in results if r.get("status") == "ok"]
        if ok_results:
            avg_latency = round(sum(r["latency_ms"] for r in ok_results) / len(ok_results), 2)
            engines[name] = {**ok_results[0], "avg_latency_ms": avg_latency, "runs": len(ok_results)}
        else:
            engines[name] = results[0] if results else {"status": "unavailable", "engine": name, "reason": "no results"}

    return {
        "engines": engines,
        "language_coverage": LANGUAGE_COVERAGE,
        "note": (
            "This report does not select a default. omnivoice/voxcpm/supertonic "
            "show 'unavailable' until their packages/weights are installed — that "
            "is an owner action (heavy install), not a code gap. Re-run after "
            "installing to get real numbers for that engine."
        ),
    }


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    report = run_voice_engine_benchmark()
    print(json.dumps(report, indent=2))
