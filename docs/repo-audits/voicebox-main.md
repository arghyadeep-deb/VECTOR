# Repo Audit — voicebox-main vs VECTOR

**Repo:** `GitHub/voicebox-main` (jamiepine/voicebox) — local-first AI voice studio, FOSS alternative to ElevenLabs + WisprFlow.
**Stack:** Python/FastAPI backend (`backend/`), React + Tauri (Rust) desktop frontend (`app/`), web shim (`web/`), MCP server, landing site.
**VECTOR target:** `core/voice/` (tts, cloning, voice_profiles, effects, stt, elevenlabs_tts, voice_personality, streamer, wake_word).
**Audited:** 2026-05-31 · all parity claims verified by **running VECTOR code**, not by trusting `phase_status.md`.

---

## Section 1 — Repo Reality (concrete features)

voicebox is a full bidirectional voice I/O studio. Actual capabilities found in source:

| # | Feature | Where (repo) |
|---|---------|--------------|
| F1 | **7 TTS engines** — Qwen3-TTS, Qwen CustomVoice, LuxTTS, Chatterbox Multilingual, Chatterbox Turbo, HumeAI TADA, Kokoro | `backend/backends/*.py` |
| F2 | **Zero-shot voice cloning** from a reference sample (Chatterbox + Qwen) | `backend/backends/chatterbox_backend.py` |
| F3 | **Preset voices** — 50+ Kokoro + 9 Qwen CustomVoice, no reference needed | `backend/backends/kokoro_backend.py`, seed |
| F4 | **23 languages** auto-routed per engine | `backend/config.py`, frontend `languages.ts` |
| F5 | **Post-processing effects** (8) via Spotify `pedalboard`: pitch, reverb, delay, chorus, compressor, gain, highpass, lowpass + 4 built-in presets | `backend/services/effects.py` |
| F6 | **Paralinguistic tags** (`[laugh]`, `[sigh]`…) — Chatterbox Turbo only | `backend/services/tts.py`, frontend `ParalinguisticInput.tsx` |
| F7 | **Unlimited-length generation** — sentence chunking + crossfade | `backend/utils/chunked_tts.py` |
| F8 | **Generation versions / takes / favorites** — provenance + lineage tracking | `backend/services/versions.py` |
| F9 | **Async serial generation queue** — non-blocking, SSE status, crash-recovery | `backend/services/task_queue.py` |
| F10 | **Voice profile management** — create/record/import/export, multi-sample, per-profile default effects + engine + language | `backend/services/profiles.py` |
| F11 | **Stories editor** — multi-track timeline, trim/split, version-pinned clips | `backend/services/stories.py`, `StoriesTab/` |
| F12 | **Global dictation / voice input** — push-to-talk + toggle chords, macOS auto-paste, in-app mic | `backend/utils/capture_chords.py`, `ChordPicker/` |
| F13 | **Speech-to-Text (Whisper)** — base→large→turbo, MLX/PyTorch backends | `backend/services/transcribe.py` |
| F14 | **Captures tab** — every dictation/upload stored as audio+transcript; replay, re-transcribe, refine, promote-to-sample | `backend/routes/captures.py`, `backend/services/captures.py` |
| F15 | **Agent voice output** — `voicebox.speak` MCP tool + `POST /speak` REST, per-agent voice binding | `backend/mcp_server/`, `backend/routes/speak.py` |
| F16 | **Voice personalities** — free-form persona per profile; Compose / Rewrite / Respond via bundled local Qwen3 LLM | `backend/services/personality.py` |
| F17 | **LLM transcript refinement** — filler/stutter/self-correction cleanup, repetition-collapse | `backend/services/refinement.py` |
| F18 | **REST API + MCP server** (HTTP + stdio transports), 4 MCP tools | `backend/routes/`, `backend/mcp_server/` |
| F19 | **Model management** — per-model unload, custom dir, download cancel/clear | `backend/routes/models.py`, `ServerSettings/ModelManagement.tsx` |
| F20 | **Multi-GPU backends** — MLX/Metal, CUDA, ROCm, DirectML, Intel XPU, CPU | `backend/backends/mlx_backend.py`, `pytorch_backend.py` |
| F21 | **On-screen bidirectional pill** — recording/transcribing/refining/speaking OS overlay | `app/src/components/CapturePill/` |
| F22 | **Tauri native desktop app** + landing site | `tauri/`, `landing/` |

---

## Section 2 — VECTOR Parity (verified by running)

Every row below was tested with `python -X utf8 -c "..."` against the live VECTOR codebase.

### F2 — Zero-shot voice cloning · ✅ real & working (needs optional dep for actual synth)
```
$ python -c "from core.voice.cloning import VoiceCloner, chunk_text, crossfade_arrays; ..."
cloner: True | available(chatterbox): False
chunk: ['Hello world.', 'How are you? Fine.']
crossfade len: 180
```
`VoiceCloner` loads, chunker + crossfade (pure functions) work. Actual synthesis is **⚠️ gated on `pip install chatterbox-tts`** (not installed) — degrades to `available()=False` exactly as designed. Code path is real. Verdict ✅ (code) / ⚠️ (synth needs dep).

### F5 — Post-processing effects · ✅ real & working (subset without pedalboard)
```
effect types: ['chorus','compressor','delay','echo','gain','highpass','lowpass','normalize','pitch','reverb']
available (no pedalboard): ['delay','echo','gain','normalize']
chain applied, peak: 0.9 shape ok: True
```
numpy-native effects (gain/normalize/delay/echo) run live; pitch/reverb/chorus/compressor/highpass/lowpass declared but **⚠️ need `pip install pedalboard`**. Chain dispatch + graceful skip verified. voicebox has 8 effects; VECTOR declares 10 (adds echo+normalize). No flanger as a separate type. Verdict ✅.

### F7 — Unlimited-length generation (chunk + crossfade) · ✅ real & working
`chunk_text` + `crossfade_arrays` proven above; `VoiceCloner.synthesize_long()` wires them together. Verdict ✅.

### F10 — Voice profile management · ✅ real & working (one storage bug, below)
```
create+get: True | type: cloned | personality: terse engineer | effects: [{'type':'reverb','params':{'wet':0.2}}]
default set: AuditMorgan
list_all: 3
deleted, now: None
```
Full CRUD + `set_default`/`get_default` + effects/personality/engine persistence verified through the Collections engine. Import/export not present (voicebox has it) — minor gap. Verdict ✅ for core CRUD.
**⚠️ BUG:** `upload_reference()` / `get_reference_bytes()` crash — `_bootstrap_storage` calls `FileStorage(str(base))` but `FileStorage.__init__(self, driver)` expects a `StorageDriver`, so `self.driver` becomes a `str` and `.put()` raises `AttributeError: 'str' object has no attribute 'put'`. This breaks storing a cloning reference sample — the exact input voice cloning depends on. See Section 4.

### F16 — Voice personalities · ⚠️ present but shallow vs repo
```
cleaned: 'So , , we need to check the logs'
rate(urgent): 190
modulated: 'Hello. ... How are you?'  (dramatic pauses)
```
`voice_personality.py` works: filler removal, sentiment→speech-rate, pause modulation. **But** this is regex/heuristic — voicebox's F16 is an **LLM-driven Compose/Rewrite/Respond** pipeline (local Qwen3 rewrites text in-character). VECTOR has no Compose/Rewrite-as-profile path. Verdict ⚠️ (a different, lighter feature wearing the same name).

### F17 — LLM transcript refinement · ❌ missing
voicebox cleans raw STT through an LLM with toggle flags + repetition-collapse. VECTOR's filler removal (`voice_personality.remove_fillers`) is regex-only and operates on TTS *input*, not STT *output*. No `refinement` equivalent in `core/voice/`. Verdict ❌.

### F13 — Speech-to-Text (Whisper) · ✅ real & working
```
WhisperSTT importable: True
methods: ['name','record_and_transcribe','record_until_silence','transcribe']
```
Whisper STT present with record/transcribe paths. voicebox exposes a base→large→turbo size ladder + MLX backend; VECTOR uses `base` (per phase_status, upgrade to large-v3 for prod). Verdict ✅ (core), ⚠️ on size-ladder parity.

### F1 — Multi-engine TTS · ⚠️ partial
VECTOR `tts.py` engines: **Kokoro** (primary) → **pyttsx3** (fallback), plus **Chatterbox** via `cloning.py` and **ElevenLabs** (cloud). That covers 2 of voicebox's 7 engines (Kokoro, Chatterbox). No Qwen3-TTS / Qwen CustomVoice / LuxTTS / HumeAI TADA. For a local-first single-owner assistant this is acceptable, but it is **not** 7-engine parity. Verdict ⚠️.
**⚠️ Live issue:** Kokoro model file is corrupt —
```
[VECTOR][tts] Kokoro init failed: INVALID_PROTOBUF : Load model from models\kokoro\kokoro-v1.0.onnx failed: Protobuf parsing failed.
kokoro_ok: False  → pyttsx3 fallback ready
```
TTS works only via pyttsx3 right now; Kokoro `.onnx` needs re-download.

### F15 / F18 — Agent voice output (MCP `speak` + REST) · ⚠️ present but BROKEN
VECTOR exposes `speak_as` + `list_voice_profiles` MCP tools (`core/mcp_server.py:563-592`) and a `POST /voice/speak` + `/voice/profiles` REST router (`core/api/routers/voice.py`). The surface exists. **But the MCP tool is broken:**
```
$ tts.speak('test', profile_name='Morgan')
RESULT: speak_as MCP tool is BROKEN -> VoiceTTS.speak() got an unexpected keyword argument 'profile_name'
```
`core/mcp_server.py:591` calls `tts.speak(text, profile_name=profile_name)`, but `VoiceTTS.speak(self, text, lang, agent)` has no `profile_name` param. Any agent calling `speak_as` gets a TypeError. Verdict ⚠️ (broken; one-line fix in Section 4).

### Local-first cloning wiring (ElevenLabs fallback) · ✅ real & working
`core/voice/elevenlabs_tts.py:104-118` checks `prefer_local_voice` (default True), fires `VoiceCloner.synthesize_long()` before any ElevenLabs cloud call. Local-first contract is honored. Verdict ✅.

### Features with NO VECTOR equivalent (expected — UI/DB scope)
| Repo feature | VECTOR | Verdict |
|---|---|---|
| F3 50+ preset voice catalog | only Kokoro 3-lang map (en/hi/ja) | ❌ (curated catalog absent) |
| F6 Paralinguistic tags | none | ❌ |
| F8 Generation versions/takes/favorites | none | ❌ |
| F9 Async generation queue + SSE + crash-recovery | none in voice layer | ❌ |
| F11 Stories multi-track editor | none | ❌ (UI feature) |
| F12 Global dictation chords / macOS auto-paste | none (VECTOR has wake_word + ambient_listener, different model) | ❌ |
| F14 Captures tab (audio+transcript store) | none | ❌ |
| F19 Model management UI | none | ❌ (UI) |
| F20 Multi-GPU backend matrix (MLX/ROCm/DirectML/XPU) | CUDA/CPU only via torch | ❌ |
| F21 On-screen bidirectional pill | none (HUD spec only — Section 3) | ❌ |
| F22 Tauri desktop app + landing | N/A | ❌ (out of scope) |

### Parity tally
- ✅ real & working: **6** (cloning, effects, chunk/crossfade, profile CRUD, STT, local-first wiring)
- ⚠️ present but stub/broken/shallow: **5** (multi-engine TTS, personality, MCP speak_as, profile reference-sample storage, Kokoro model)
- ❌ missing: **11** (refinement, presets catalog, paralinguistic, versions, queue, stories, dictation chords, captures, model mgmt, multi-GPU, pill)

---

## Section 3 — Frontend → VECTOR HUD Voice Panel Spec (document only)

voicebox's desktop UI (`app/src/`, React + Tauri, Tailwind v4 + shadcn/ui + framer-motion + lucide-react) is a clean reference for a future VECTOR voice HUD. **Documented, not built.**

### Layout
- **Fixed left rail sidebar**, `w-20` (80px), icon-only, vertical. `bg-sidebar`, right border. macOS adds `pt-14` for the traffic-light region. (`Sidebar.tsx`)
- 7 nav tabs, each a 48px circular button (`rounded-full`), active state = subtle white glow + accent-tinted top-masked border that **fades with distance from the logo** (`accentOpacity = max(0.08, 0.5 - index*0.07)`).
- Logo top, version + update badge pinned bottom (`mt-auto`); bottom padding grows when audio player is open.
- Main area to the right; a **floating generate box** docks at the bottom (`FloatingGenerateBox.tsx`) — expandable, with engine/model selector, paralinguistic tag inserter (`/` opens a tag picker), Compose (Dices) + persona (Sparkles/Wand2) buttons.

### Nav tabs (icon → route)
`Generate (Volume2 →/)` · `Stories (AudioLines)` · `Captures (Captions)` · `Voices (Mic)` · `Effects (Wand2)` · `Models (Box)` · `Settings (Settings)`.

### Color scheme (`app/src/index.css`, HSL tokens, light + dark)
- **Dark theme** (the one to mirror for a HUD): `--background: 0 0% 6%`, `--card: 0 0% 8%`, `--sidebar: 0 0% 4%`, `--foreground: 0 0% 95%`, `--border: 0 0% 12%`, `--muted-foreground: 0 0% 60%`.
- **Accent (signature gold):** `--accent: 43 50% 45%` dark / `43 55% 58%` light — a warm amber/gold. All active states, audio bars, badges use it.
- Destructive red `0 62.8% 50%`. Radius `0.5rem`. Scrollbars hidden globally.

### Key widgets to reuse for a VECTOR HUD
- **CapturePill** (`CapturePill.tsx`) — the standout. A floating OS-level pill with a **shared state machine**: `recording | transcribing | refining | speaking | completed | rest | error`. Same surface for both input (dictation) and output (agent speech). Animated 5-bar audio visualizer (`PillAudioBars`) with three motion modes (generating = quick pulse, playing = wave, idle = flat), framer-motion driven, accent-colored. Elapsed timer. Error variant copies message to clipboard on click. **This is the single best thing to lift conceptually** for VECTOR's loop-state HUD (observe/think/act/speak map cleanly onto it).
- **EngineModelSelector** — dropdown of engine + model variant, language list filtered per engine.
- **EffectsChainEditor** — ordered, reorderable list of `{type, params}` cards with live preview + preset save. Maps 1:1 onto VECTOR's `AudioEffects.apply(chain)`.
- **AudioPlayer** + **AudioBars** — persistent bottom player with waveform.
- **ChordPicker** — push-to-talk / toggle hotkey capture UI.
- **StoryTrackEditor** — multi-track timeline (only relevant if VECTOR ever does podcast/narrative).

### HUD recommendation (spec only)
A VECTOR voice HUD should adopt: the **80px icon rail**, the **dark gold-accent token set**, and especially the **bidirectional CapturePill state machine** as the canonical surface for autonomous-loop status (`observe → think → act → speak`). Generate box, effects chain editor, and per-profile voice picker map directly onto existing VECTOR voice endpoints (`/voice/speak`, `/voice/profiles`, effects chains).

---

## Section 4 — Verdict: **PATCH VECTOR**

Size-of-gap reasoning: voicebox is a 22-feature desktop product, but ~half its features are **UI/DB scope** (stories, captures tab, model-mgmt UI, generation versions, async queue, pill, Tauri app, multi-GPU matrix) that a local-first single-owner agent does not need wired into `core/voice/`. The **voice-engine core that VECTOR actually needs** — cloning, effects, chunking, profiles, STT, local-first ElevenLabs fallback — **is already absorbed and genuinely works** (6 ✅). The absorption is real, not faked. What remains is **a small, sharp set of bugs + 2 genuine feature gaps**, not a vast hole. So: patch, do not re-integrate the repo.

### Exact fixes (file:line)
1. **MCP `speak_as` is broken** — `core/mcp_server.py:591` calls `tts.speak(text, profile_name=profile_name)` but `VoiceTTS.speak(self, text, lang, agent)` (`core/voice/tts.py:68`) has no such kwarg → TypeError on every agent speak. **Fix:** add a `profile_name` param to `VoiceTTS.speak` that resolves the profile via `get_profile_store().get(name)`, picks cloning vs engine, and applies the profile's effect chain — OR route `speak_as` through `core/voice/elevenlabs_tts.speak_content()` which already does local-first. (This single bug means agent voice output, voicebox's headline F15, does not work today.)
2. **Profile reference-sample storage is broken** — `core/voice/voice_profiles.py:181` does `FileStorage(str(base))`, but `FileStorage.__init__(self, driver)` (`core/collections/storage.py:217`) expects a `StorageDriver`. **Fix:** `from core.collections.storage import LocalDriver; self._storage = FileStorage(LocalDriver(str(base)))` (or just `FileStorage()` to use config defaults). Without this, `upload_reference()` / `get_reference_bytes()` crash — you cannot store the reference clip that cloning needs.
3. **Kokoro model corrupt** — `models/kokoro/kokoro-v1.0.onnx` fails protobuf parse → TTS silently falls back to pyttsx3. **Fix (ops, not code):** re-download the Kokoro ONNX weights. Tracked in `phase_status.md` as a known must-do.

### Genuine feature gaps worth adding (small, optional)
4. **STT refinement** (F17) — add `core/voice/refinement.py` (LLM-driven STT cleanup + repetition-collapse). voicebox's `backend/services/refinement.py` is a clean Python reference; reuses VECTOR's existing `provider_client` for the LLM call.
5. **LLM persona Compose/Rewrite** (F16) — upgrade `voice_personality.py` (currently regex-only) with an optional LLM-rewrite-in-character path mirroring `backend/services/personality.py::rewrite_as_profile`, gated on a profile's `personality` field (already stored — verified above).

Everything else (presets catalog, paralinguistic tags, stories, captures, queue, multi-GPU, pill) is UI/product scope — defer; the pill is captured as a Section-3 spec for a future HUD, not a `core/voice/` gap.

---
**No VECTOR code was modified. Read + run only. This is the only file written.**
