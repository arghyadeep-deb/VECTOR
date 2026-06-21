# VoxCPM — Absorption Analysis
**Verdict:** UPGRADE (better than existing) — replaces the **Chatterbox cloning backend** and becomes VECTOR's multilingual TTS engine; Kokoro stays as the lightweight fallback.

**What it is:** VoxCPM2 (OpenBMB) — a tokenizer-free, diffusion-autoregressive TTS system on a MiniCPM-4 backbone.
- Stack: PyTorch ≥2.5, CUDA ≥12.0, transformers, torchaudio, gradio, funasr, librosa, modelscope/HF weights (`pyproject.toml:26-52`).
- Model size / VRAM: **2B params, ~8 GB VRAM**, 48 kHz output, RTF ~0.30 on RTX 4090 (~0.13 with Nano-vLLM) (`README.md:316,314,49`).
- Languages: **30**, including **Hindi, Japanese, English** explicitly; no Bengali/Assamese in the official list (`README.md:52-53`). Note: README itself flags Hindi as a *weak* language — Minimax-MLS WER Hindi 19.7% vs ElevenLabs 5.83% (`README.md:406`), though SIM is class-leading at 85.6 (`README.md:439`).
- Cloning: 4 modes — Voice Design (text-description only, no reference), Controllable Cloning (reference + style steer), Ultimate Cloning (reference + transcript continuation), plus SFT/LoRA finetune from 5–10 min of audio (`README.md:44-46,527`).
- License: **Apache-2.0** — weights and code, commercial-ready (`pyproject.toml:10`, `LICENSE:1`). Fully absorbable, no copyleft.
- Python API surface: `VoxCPM.from_pretrained(...)`, `.generate(text, reference_wav_path=, prompt_text=, prompt_wav_path=)`, `.generate_streaming(...)`, `.load_lora()/.unload_lora()` (`src/voxcpm/core.py:104,174,177,317`).

**VECTOR already has:**
- `core/voice/tts.py` — Kokoro-ONNX primary (GPU fp16), pyttsx3/gTTS fallback chain; voice map en→bf_emma, hi→hf_alpha, ja→jf_alpha; bn/as routed to gTTS-via-Bengali (`tts.py:32-44,107-139`). Has a `profile_name` cloned-voice hook (`tts.py:208-235`) and `synthesize_to_file` (`tts.py:237-271`).
- `core/voice/cloning.py` — `VoiceCloner` zero-shot cloning via **Chatterbox-TTS** (CUDA, 24 kHz, guarded optional dep), `synthesize()` + `synthesize_long()` with chunk+crossfade (`cloning.py:101,179,240`).
- `core/voice/voice_profiles.py` — `VoiceProfileStore` (collections-backed), `get_reference_bytes()`, `get_default()`/`set_default()` (`voice_profiles.py:116,305,319,284`).
- `core/voice/elevenlabs_tts.py` — cloud TTS, local-first per `prefer_local_voice=True`.
- Config seams: `CONFIG["voice"]` has `cloning_engine="chatterbox"`, `cloning_device`, `default_voice_profile`, `prefer_local_voice=True`, `sample_rate` (`core/config.py:192-199`).

**Overlap %:** ~70% overlaps the **cloning** layer (zero-shot clone-from-reference) and ~40% overlaps the **base TTS** layer (en/hi/ja). VoxCPM and Chatterbox solve the same job (local CUDA clone from a short WAV) — that is a true duplicate. Kokoro overlaps only on en/hi/ja synthesis but is 80 MB ONNX vs an 8 GB model, so it is NOT a duplicate to remove — it is the cheap fallback.

**Genuine gaps / what's better:**
1. **Cloning quality + control** — Chatterbox is continuation-only with crude `exaggeration`/`cfg_weight` knobs. VoxCPM2 adds Voice Design (create the British "VECTOR voice" from a *text description* with zero reference audio — directly solves the British-voice goal without sourcing a clean reference WAV), Controllable Cloning (steer emotion/pace while preserving timbre), and Ultimate Cloning (transcript-conditioned, highest fidelity). SIM 85.4 EN beats every open competitor in the table (`README.md:434`).
2. **Multilingual breadth** — Chatterbox/Kokoro cover en/hi/ja and degrade bn/as to gTTS-via-Bengali. VoxCPM2 natively handles 30 languages from one model, no per-language voice files. (Caveat: bn/as still unsupported officially; hi intelligibility is mediocre per the vendor's own WER.)
3. **48 kHz studio output** + built-in super-resolution vs Chatterbox 24 kHz / Kokoro 16 kHz (`README.md:47,316`).
4. **LoRA finetune** — 5–10 min of audio adapts a permanent speaker/British persona, hot-swappable (`README.md:527`, `core.py:317`). Chatterbox has no finetune path in VECTOR.
5. **Streaming + OpenAI-compatible serving** (Nano-vLLM / vLLM-Omni) for low-latency real-time loop use.

**If UPGRADE — what to replace & migration risk:**
- **Replace Chatterbox, keep Kokoro.** VoxCPM becomes the cloning/multilingual engine; Kokoro remains the always-resident lightweight fallback when VRAM is contended.
- **VRAM is the real risk.** RTX 5070 Ti is **12 GB**. VoxCPM2 needs ~8 GB. `vector-focus` (gemma4:e4b) is meant to be permanent-resident VRAM, and `OLLAMA_MAX_LOADED_MODELS=1`. 8 GB TTS + a ~4–6 GB e4b model is a tight-to-over-budget fit for simultaneous residency. Mitigation: load VoxCPM **on-demand** (mirror Chatterbox's lazy singleton in `cloning.py:154-175`), unload after synth, or keep Kokoro for live conversation and reserve VoxCPM for content-district file rendering + persona generation where latency is non-critical. Do NOT make VoxCPM the permanent real-time conversational engine on 12 GB alongside vector-focus.
- Second risk: heavy dep tree (funasr, modelscope, gradio, ~8 GB weight download) — must stay a **guarded optional install** exactly like chatterbox-tts, never imported at module level.
- Third: Hindi WER is weak out-of-the-box; a Hindi/British LoRA may be needed before trusting it over gTTS for hi.

**Integration plan:**
- **Create** `core/voice/voxcpm_cloning.py` — a `VoxCPMCloner` class with the *same* public shape as `VoiceCloner` (`available()`, `synthesize()`, `synthesize_long()`, plus new `design(description, text)` for reference-free voice design and `clone_ultimate(text, ref, transcript)`). Lazy singleton model load, guarded import (`import voxcpm`), graceful `available()=False`.
- **Modify** `core/config.py:193` — add `cloning_engine` choices `"chatterbox"|"voxcpm"`; add `voxcpm_model_dir`, `voxcpm_inference_timesteps`, `voxcpm_cfg_value`, `voice_design_description` (the British VECTOR persona string).
- **Modify** `core/voice/tts.py:208-271` — in `_speak_clone()`/`synthesize_to_file()`, dispatch on `CONFIG["voice"]["cloning_engine"]` via a small `get_cloner()` factory; no other call-site changes. Reuse `VoiceProfileStore.get_reference_bytes()` unchanged (`voice_profiles.py:319`).
- **Reuse seams (do not duplicate):** `core/voice/voice_profiles.py` store, the existing `profile_name` plumbing in tts.py, `core/voice/effects.py` DSP, `prefer_local_voice` ordering, the lazy-singleton + temp-WAV-resolve pattern already in `cloning.py`.
- **Add** one Voice-Design endpoint to `core/api/routers/voice.py` (mirror the existing profile endpoints) so the owner can generate the British VECTOR voice from a description and save it as the default profile.
- **Tests:** new `tests/test_voxcpm_cloning.py` — chunker reuse, `available()=False` graceful path with no GPU/dep, engine-factory dispatch, config validation. Model-dependent synth tests guarded by `available()` exactly like `cloning.py:344-356`.
- **Effort:** ~1 focused session for the wrapper + factory + tests (the heavy lifting is the 8 GB weight download and a Hindi/British LoRA, both owner one-time steps).

**Recommendation:**
Absorb VoxCPM2 as an **alternate, config-selectable cloning/multilingual engine that supersedes Chatterbox**, but explicitly *not* as a replacement for Kokoro and *not* as the permanent real-time conversational voice on a 12 GB card. The decisive wins are Voice Design (build the British "VECTOR voice" from a text prompt with no reference WAV needed), genuinely controllable + transcript-faithful cloning, 48 kHz quality, LoRA persona finetuning, and one-model 30-language coverage — all under Apache-2.0 and fully local, satisfying VECTOR's no-cloud rule. The two hard constraints are VRAM (load on-demand / unload after synth so it never collides with vector-focus) and Hindi quality (vendor's own WER is poor — keep gTTS for hi until a LoRA proves out, and use VoxCPM primarily for English persona voice + content-district file rendering where latency and co-residency don't bite). Net: it is strictly better than Chatterbox for VECTOR's actual goals, so swap the cloning backend behind the existing `cloning_engine` config seam and gate it as a guarded optional install.
