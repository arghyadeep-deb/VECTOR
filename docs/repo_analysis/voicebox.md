# voicebox — Absorption Analysis

> Authored by Opus (parallel agent hit session limit before writing; recovered from recon).

**Verdict:** SKIP (mostly already absorbed) — with ONE small optional new gap: system-wide dictation.

**Is this the already-absorbed repo?:** Yes — jamiepine/voicebox, the same project VECTOR absorbed 2026-05-27. The prior pass took the Python parts into `core/voice/`: `cloning.py` (Chatterbox zero-shot cloning), `voice_profiles.py`, `effects.py` (DSP chain), long-form chunking+crossfade. It explicitly SKIPPED the Tauri/Rust desktop app, web/React UI, MLX (Mac-only) backend, and STT/VAD/wake-word.

**What it is:** TS/Tauri/web desktop "voice studio" with a Python FastAPI `backend/` (backends: `luxtts_backend`, `mlx_backend`, `pytorch_backend`, `qwen_llm_backend`), an `mcp_server/`, SQLAlchemy DB, soundfile/librosa/torch. License: check repo `LICENSE`.

**Already absorbed into VECTOR:** voice cloning, profiles, effects, chunking (`core/voice/cloning.py`, `voice_profiles.py`, `effects.py`). VECTOR also already has STT (`core/voice/stt.py` Whisper), ambient listening (`ambient_listener.py`), wake word (`wake_word.py`), conversation manager, realtime.

**Genuinely NEW / unabsorbed gaps:**
- **System-wide dictation** ("dictate into any app" — STT → inject text into the focused OS window). VECTOR has Whisper STT but not the *OS text-injection* layer. Python-portable (pyautogui/keyboard already in VECTOR's deps for pc_controller). LOW-MEDIUM value — niche, owner-facing convenience, not core autonomy.
- Extra TTS backends (luxtts, qwen_llm) — **superseded** by the VoxCPM UPGRADE recommendation; do not absorb these.
- Its own MCP server — VECTOR already has `core/mcp_server.py`; not needed.

**Integration plan (for the one new gap only):** if owner wants dictation: `core/voice/dictation.py` — Whisper STT (reuse `stt.py`) → `pc_controller` keystroke injection, toggled by a hotkey/wake phrase. ~half a session. Gate any "type into app" action through PermissionGateway (it writes to arbitrary apps).

**Recommendation:** **SKIP** — this is the repo you already absorbed; its TTS/cloning is now better served by VoxCPM. The only thing worth revisiting is **system dictation**, and only if you personally want push-to-talk-into-any-app. Everything else is duplicate or superseded. Do not re-absorb.
