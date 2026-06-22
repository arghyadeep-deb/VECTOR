# OmniVoice-master - VECTOR Absorption Review

**Verdict:** IMPLEMENT as an optional on-demand voice studio engine after a local benchmark.

**Priority:** HIGH for multilingual voice capability, MEDIUM for immediate live-conversation work

**Effort:** 1 session for adapter + benchmark; 1 more session if it replaces the current cloning path

**License:** Apache-2.0

**Repo size inspected:** ~78 files / ~1.19 MB source checkout

## What It Is

OmniVoice is a multilingual zero-shot TTS and voice-cloning model package. The README claims:

- 600+ language support
- zero-shot voice cloning from reference audio
- voice design from attributes such as gender, age, pitch, accent, dialect, and whisper
- non-verbal tokens such as laughter and sighs
- pronunciation control
- fast inference with diffusion-style generation
- Python API and CLI

The implementation is a compact Python package around `OmniVoice.from_pretrained(...)` and `model.generate(...)`, with batch inference, Gradio demo, training scripts, and evaluation utilities.

## VECTOR Already Has

- `core/voice/` realtime conversation stack
- `/ws/voice/stream` and `/ws/voice/duplex`
- Kokoro / pyttsx3 fallback path
- voice cloning / voice studio surfaces
- `core/config.py` voice configuration, including `voice_design_description`
- repo-analysis plans for VoxCPM and supertonic
- model residency constraints: one Ollama/model-heavy path at a time on 12 GB VRAM

## Overlap

Approximate overlap: **45-55%**.

VECTOR already has the voice pipeline and UI/control surfaces. OmniVoice is not a new voice pipeline; it is a better candidate model for high-quality multilingual generation, cloning, and designed voices.

## Why It Matters

OmniVoice may be more important than the earlier VoxCPM/supertonic split because it targets 600+ languages. That directly affects Hindi, Bengali, Assamese, and other multilingual everyday use cases.

But it should not become the always-on live voice engine until measured. Live VECTOR conversation cares about:

- voice-to-first-audio latency
- interruption/barge-in behavior
- VRAM residency
- startup time
- sentence streaming
- reliability under long-running use

OmniVoice is better suited first for:

- Voice Studio generation
- narration
- content voiceovers
- multilingual replies when quality matters more than latency
- creating the British VECTOR persona voice
- batch audio generation

## Real Gaps It Can Fill

1. **Multilingual local TTS.** Current VECTOR notes still preserve gTTS for some languages. OmniVoice may remove or reduce that cloud fallback if benchmark quality is good.

2. **Unified cloning + design engine.** One model supports reference-audio cloning and attribute-based voice design, reducing the need for multiple voice engines.

3. **Voice Studio quality path.** VECTOR can keep Kokoro/supertonic for live low-latency speech and use OmniVoice for high-quality generated audio.

4. **Language-aware voice selection.** Add a small policy that chooses live/fast TTS versus OmniVoice high-quality TTS based on language, latency target, and GPU availability.

## What Not To Absorb

- Do not import training code into VECTOR.
- Do not copy Gradio demo code.
- Do not vendor eval scripts.
- Do not make OmniVoice load at startup.
- Do not let it co-reside with the main local LLM if VRAM is tight.
- Do not remove Kokoro/pyttsx3/gTTS fallbacks until benchmarked per language.

## Implementation Plan For Sonnet

Build a thin optional adapter.

1. Add `core/voice/engines/omnivoice_engine.py`.
   - Lazy-load model only on first request.
   - Accept `text`, `language`, `profile`, `ref_audio`, `ref_text`, `instruct`, `speed`, `num_step`.
   - Return WAV bytes or a temp file path matching existing VECTOR TTS conventions.

2. Add config under `voice`.
   - `omnivoice_enabled: bool = false`
   - `omnivoice_model: str = "k2-fsa/OmniVoice"`
   - `omnivoice_device: str = "cuda:0"`
   - `omnivoice_dtype: str = "float16"`
   - `omnivoice_live_allowed: bool = false`
   - `omnivoice_unload_after_seconds: int = 300`

3. Wire only into Voice Studio first.
   - Add provider option: `omnivoice`.
   - Keep existing default live TTS unchanged.
   - Add owner-visible failure fallback.

4. Add model-residency guard.
   - Reuse the existing local model lock / GPU residency rule.
   - If a local LLM is busy, queue or reject with a clean message.

5. Add benchmark command.
   - Generate fixed English, Hindi, Bengali, Assamese, and one long narration sample.
   - Record load time, generation time, output duration, peak VRAM if available, and failure mode.
   - Store results in `docs/voice/OMNIVOICE_BENCHMARK.md`.

6. Add tests.
   - adapter skips when disabled
   - config defaults are safe
   - generate path is mockable without loading model
   - Voice Studio fallback works when OmniVoice raises
   - live conversation path does not use OmniVoice unless explicitly enabled

## Acceptance Criteria

- VECTOR starts without importing torch/transformers for OmniVoice.
- Existing voice tests still pass.
- Voice Studio can select OmniVoice when enabled.
- Provider API keys are not involved.
- No cloud fallback is silently used.
- Benchmark doc tells whether it should replace VoxCPM, supertonic, neither, or only the high-quality studio path.

## Final Recommendation

Implement OmniVoice, but only as a lazy, opt-in high-quality voice engine first. If benchmarks show fast enough generation and sane VRAM behavior, it can replace VoxCPM as the main cloning/design engine. Keep the live conversation engine separate until latency is proven.
