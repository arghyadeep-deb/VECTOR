# VECTOR — Remaining Work (handoff for Claude Code)

State as of 2026-06-10: zero syntax errors repo-wide; voice Phases 1-5 +
venture pipeline + speaker verification + approvals/ventures HUD widgets +
nightly self-check all code-complete and committed. Nothing below blocks
daily use except item 0.

Context Claude Code should know:
- Python 3.12 required (`pyproject.toml`), repo stores LF, working tree CRLF.
- `scripts/precommit_syntax_gate.py` exists — install via item 2 BEFORE editing.
- Design doc for voice: `docs/REALTIME_CONVERSATION_DESIGN.md`.
- 75 agents registered in `config/agent_manifest.yaml`; governor routing map
  in `core/city/governor.py` (~line 140-600).

---

## 0. SECURITY — do first (5 min, partly manual)

`.env` was tracked in git until commit 45eb07ce0; secrets remain in ~3000
commits of history.

> Prompt: "Rotate help: list every key name in my .env (don't print values).
> Then scrub .env from all git history with git-filter-repo, preserving my
> working tree. Verify with: git log --all --oneline -- .env returning empty."

Then rotate each key at its provider (manual — OpenAI/Anthropic/ElevenLabs/etc).

## 1-4. ONE-COMMAND ACTIVATIONS + FIRST RUNS (~30 min total)

```
python scripts/install_git_hooks.py        # commit gate live
pip install resemblyzer
python scripts/enroll_owner_voice.py       # speaker verification live (needs mic)
python run_vector.py doctor                # dependency report
python run_vector.py smoke                 # spine boots?
python districts/news_trends/venture_pipeline.py --live   # first pipeline run
```

> Prompt for failures: "I ran `python run_vector.py smoke` and got <paste
> error>. Diagnose and fix — the spine is core/loop/autonomous_loop.py,
> entry run_vector.py."

## 5. RUN THE TEST SUITE (never validated this session)

> Prompt: "Run pytest on this repo (146 test files in tests/). Triage
> failures into: (a) broken by recent changes — fix those; (b) pre-existing
> failures — list them, fix only quick wins; (c) environment/missing-dep
> skips — note them. Recent changes touched: core/voice/realtime.py,
> speaker_verify.py, core/api/routers/voice_ws.py, core/loop/cron_jobs.py,
> autonomous_loop.py (singleton + wake_think), core/api/tasks.py,
> core/api/routers/{tasks,startups}.py, nudge_engine.py, frontend/js/*."

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

## 8. DUPLEX SESSION LIFECYCLE (design decision needed from your testing)

Currently /ws/voice/duplex listens forever. Design §6 wants: 30s inactivity →
IDLE → wake word ("Vector") to resume. Needs openwakeword frames fed from the
duplex stream (core/voice/wake_word.py exists).

> Prompt: "In core/voice/realtime.py add session timeout: after
> CONFIG[voice][conversation_timeout_sec] (default 30) of no speech, transition
> to IDLE and require wake word to resume. Feed frames to
> core/voice/wake_word.py's openwakeword model while IDLE; on detection,
> transition to LISTENING + send a 'state' event. Don't break barge-in."

## 9. CONTENT UPLOADER STUBS

`districts/content/uploader.py`: YouTube works; instagram/tiktok/twitter/
facebook are listed in PLATFORMS but unimplemented.

> Prompt: "Implement upload_to_instagram (Graph API, reels),
> upload_to_tiktok (Content Posting API), upload_to_twitter (v2 media) in
> districts/content/uploader.py following the upload_to_youtube pattern —
> OAuth creds from core/engine/oauth/registry.py, each behind a
> CONFIG-gated dry_run default of True."

## 10. SMALL ITEMS

- `.claude/hooks/pre_commit_gate.py` (was write-protected for Cowork): append
  a call to `scripts/precommit_syntax_gate.py`, blocking on rc!=0 (exit 2).
- Mojibake cleanup: comments contain `Ã¢â‚¬` sequences from an encoding
  accident. Safe approach: only rewrite lines matching the corruption inside
  COMMENTS/docstrings, verify compileall after, commit via the (now installed)
  gate. Cosmetic — do last.
- `frontend/js/voice_stream.js` legacy push-to-talk can be removed once duplex
  is proven (vector-core.js voice WS handler stays — same endpoint serves both).
- Optional: GitHub Actions CI (compileall + pytest) if the repo ever gets a remote.

## DONE THIS SESSION (don't redo)

44 syntax-error files restored · .env untracked · voice Phases 1-5 ·
venture pipeline (SocialMiner/ProblemClusterer/VenturePipeline + weekly cron)
· vendored three.js/MediaPipe (fixed broken 3D city) · approvals + ventures
widgets · speaker verification + enrollment · pre-commit syntax gate ·
running-loop singleton (fixed 2 broken _pending_voice paths) · event-driven
think wake · design/data_analytics registered · nightly self-check cron ·
requires-python 3.12
