# VECTOR — Remaining Work (handoff for Claude Code)

State as of 2026-06-11: items 0 (local scrub), 1-2, 4 (doctor+smoke), 5, 7, 8,
9 (instagram/tiktok/twitter), and 10 (gate wiring, mojibake, voice_stream.js)
DONE — see "DONE 2026-06-11" at the bottom. Remaining: owner-manual items
below + GitHub force-push decision (item 0b).

Context Claude Code should know:
- Python 3.12 required (`pyproject.toml`), repo stores LF, working tree CRLF.
- Pre-commit syntax gate INSTALLED and verified (blocks unparseable staged files).
- Design doc for voice: `docs/REALTIME_CONVERSATION_DESIGN.md`.
- 75 agents registered in `config/agent_manifest.yaml`; governor routing map
  in `core/city/governor.py`.

---

## 0a. KEY ROTATION — owner manual, DO FIRST

Local git history is scrubbed (verified: `git log --all -- .env` empty;
backup bundle at `../VECTOR-backup-20260611.bundle`). But the keys lived in
~3000 commits that were pushed to GitHub, so rotate every key in .env at its
provider (OpenAI/Anthropic/ElevenLabs/etc) regardless of the push decision.

## 0b. GITHUB PUSH — needs owner decision

Force-push of scrubbed history to github.com/arghyadeep-deb/VECTOR was
REJECTED: history contains 4 blobs >100MB (models/kokoro/*.onnx ×2,
models/piper/*.onnx, a 293MB cmake .gch on main). Options:
(a) authorize `git filter-repo --strip-blobs-bigger-than 100M` (model files
    already backed up at `../model-backup-20260611/`, restored to disk after,
    then gitignore models/*.onnx) → force-push main;
(b) delete the GitHub repo and re-push fresh scrubbed history;
(c) leave GitHub stale (secrets remain there — rotation then mandatory).

## 3. ENROLL OWNER VOICE (needs your mic, ~2 min)

```
python scripts/enroll_owner_voice.py       # resemblyzer is now installed
```

## 4b. VENTURE PIPELINE FIRST LIVE RUN (owner-triggered)

```
python districts/news_trends/venture_pipeline.py --live   # hits Reddit/HN
```

## 6. VOICE RUNTIME TUNING (after first HUD conversation)

Symptoms → knobs (all in CONFIG["voice"], read by core/voice/realtime.py):
- VECTOR cuts me off mid-sentence → raise `endpoint_silence_ms` (280 → 400+)
- Doesn't notice I stopped talking → lower it
- Interrupts itself / false barge-in → raise `vad_threshold` or
  `bargein_debounce_ms`; check client echo guard (audio.js server-voice events)
- Slow first audio → confirm `realtime_stt_model: small` loads, Ollama
  `vector-focus` warm (`keep_alive:-1` already set), check GPU VRAM

> Prompt: "Voice issue: <symptom>. Relevant: core/voice/realtime.py
> (feed_pcm/endpointing), core/voice/vad.py, frontend/js/voice_duplex.js."

## 7. DEDUPLICATION SESSION — EVALUATED 2026-06-11, VERDICT: keep all separate

All three pairs compared API-by-API. None are mergeable; do not re-attempt:
- **CircuitBreaker**: `core/event_bus/circuit_breaker.py` is SYNC-first
  (`call(fn)`, `get_stats()`, `CircuitBreaker(name, ...)`) used inside
  `core/event_bus/bus.py`'s synchronous delivery path; `core/resilience/`
  is ASYNC-only (`async call(fn, *args)`, asyncio.Lock, config object,
  registry, force_open/close). A shim would change sync→async semantics in
  the bus delivery path. Incompatible — keep both.
- **ModelRouter**: name collision, not duplicates. `core/engine/providers/`
  maps tier hints → Ollama models (port of router.rs); `core/inference/`
  classifies tasks → LoRA adapter hot-swap. Different classes, different
  jobs. Keep both.
- **persona vs personality**: layered, not duplicated —
  `core/personality/middleware.py` imports from `core.persona`; all external
  callers (voice routers, avatar, inference) use `core.personality`. The two
  ConsistencyEnforcers differ in scope (district output audit vs persona
  consistency). Merging = broad blast radius for no gain. Keep both.
- NOT duplicates (name collisions, different fields — rename only if touched):
  WSCommandRequest/Response in core/api/schemas.py vs routers/websocket.py

## DONE 2026-06-11 (don't redo)

- **Item 0 (local)**: .env scrubbed from all history via git-filter-repo
  (verified empty); 943MB backup bundle + on-disk .env untouched. Push
  blocked → see 0b above. Runtime-artifact dirs untracked + gitignored
  (data/{security/incidents,rejected_runs,reports,feedback}, screenshots).
- **Items 1-2**: git pre-commit hook installed + verified; resemblyzer
  installed (via webrtcvad-wheels — plain webrtcvad needs a C compiler).
- **Item 4**: doctor → required_failed: 0; smoke → ok, 75 agents/28 districts.
- **Item 5**: full suite triaged. Root cause of the 120s hang:
  tests/test_phase2_districts.py patched `ollama.chat` but districts route
  through `core.inference.vectorcode_llm.chat` → 11 patches re-seamed.
- **Item 7**: evaluated, all pairs kept separate (see verdicts above).
- **Item 8**: DONE — idle timeout + wake-word resume in core/voice/realtime.py
  (`_go_idle`/`_idle_frame`/`_wake_up`; openwakeword per-frame when available,
  STT-burst KWS fallback otherwise; barge-in regression-tested).
- **Item 9**: DONE — upload_to_tiktok (Content Posting API) +
  upload_to_twitter (X v2 chunked media) implemented behind
  CONFIG content.upload_dry_run (default True); Instagram client-scope bug
  fixed (publish POST ran after AsyncClient closed); scheduled-upload
  routing covers all 4 platforms.
- **Item 10**: pre_commit_gate.py → syntax gate wired (blocking, exit 2);
  mojibake fully cleaned (both `Ã¢â‚¬` and `â†’` families, 300+ lines,
  0 left repo-wide); voice_stream.js was already removed.
- **Bonus**: loop mode now calls bootstrap_agents() (was: empty city, every
  governor dispatch returned no_agents); agent_base self-test matches
  hp_validator clamp+EMA; 32 broken vectorcode files restored (a sys.path
  cleanup had deleted if-bodies / left stray mid-try imports);
  compileall = 0 errors repo-wide.

## DONE 2026-06-10 (previous session)

44 syntax-error files restored · .env untracked · voice Phases 1-5 ·
venture pipeline (SocialMiner/ProblemClusterer/VenturePipeline + weekly cron)
· vendored three.js/MediaPipe (fixed broken 3D city) · approvals + ventures
widgets · speaker verification + enrollment · pre-commit syntax gate ·
running-loop singleton (fixed 2 broken _pending_voice paths) · event-driven
think wake · design/data_analytics registered · nightly self-check cron ·
requires-python 3.12
