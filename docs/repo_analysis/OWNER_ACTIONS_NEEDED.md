# Owner Actions Needed

**Date:** 2026-06-23. Single consolidated list of everything from the 2026-06-23
repo-analysis audit (`_MASTER_TODO.md`) that genuinely requires action only
the owner can take — a heavy install, a credential/account, physical hardware,
or a deploy decision. Everything that was buildable as code has been built and
tested this session; nothing below is blocked on more code from me.

Grouped by what kind of action it needs. Each item links back to its
`_MASTER_TODO.md` section for full evidence/context.

---

## 1. Heavy package installs — ✅ DONE (2026-06-23)

All 6 packages installed and verified importable: `peft` 0.19.1, `trl` 1.6.0,
`supervision` 0.29.0, `ultralytics` 8.4.75, `omnivoice` 0.1.5, `supertonic`
1.3.1. Zero VECTOR regressions — full project regression (51/51 integration
checks, 209/209 voice tests, smoke) stays green after each install.

**Two real bugs found and fixed while verifying** (both wrappers were
written before the packages existed, so their assumed APIs were guesses —
now confirmed and corrected against the real installed code):
- `core/voice/supertonic_tts.py` called a nonexistent `supertonic.load_model()`
  — the real entry point is `supertonic.TTS(...)`. Also added an explicit
  `auto_download=False` default so the wrapper never silently triggers the
  ~260MB weight download — that stays a separate, deliberate opt-in
  (`CONFIG["voice"]["supertonic_auto_download"]`).
- `core/voice/engines/omnivoice_engine.py` called `generate()` with
  `profile`/`num_step`/`output_path` kwargs that don't exist on the real
  method, and assumed it saved a file itself — it actually returns
  `list[numpy.ndarray]` and the caller must save it. Fixed to call only
  real parameters and save via `soundfile` using the model's own
  `model.sampling_rate` attribute (the package's own docstring documents
  this exact pattern).

**Still open, deliberately not done — model weight downloads** are a
separate, larger action from installing the package (omnivoice's are
multi-GB, supertonic's are ~260MB) and weren't attempted:
- `supertonic`: weights download is now safely gated behind
  `auto_download=True` (or set `CONFIG["voice"]["supertonic_auto_download"] = True`)
  — currently defaults to a clean error instead of a silent download.
  **After downloading:** A/B listen against Kokoro's `bf_emma`, then flip
  `CONFIG["voice"]["live_engine"] = "supertonic"` if you like it better.
- `omnivoice`: real model weights not yet fetched (no equivalent
  `auto_download` guard exists in its own API at the level I could verify
  without triggering a real download to check) — first real
  `synthesize_to_file()`/benchmark call will attempt to fetch them from
  HuggingFace Hub. Worth knowing before triggering it.
- `supervision`/`ultralytics`: the YOLO weights file (`yolo11n.pt`) downloads
  automatically on first real detection call (~6MB, small) — not attempted
  here since `presence_detector.py` was only verified via the package
  import, not a live camera frame.

## 2. Decisions that don't need new code, just a choice

| Decision | What it affects |
|---|---|
| Flip `post_training_enabled` in `core/config.py`, and decide when the weekly Sat-04:00 training run should actually fire | `core/loop/cron_jobs.py::job_post_training_run()` — already gated OFF by default, zero heavy imports until flipped |
| `core/voice/cloning.py::cloning_engine` is `"chatterbox"` — stays unless you decide OmniVoice's eventual benchmark beats it for cloning/voice-design | No action needed unless OmniVoice underperforms |
| ✅ **ComfyUI sidecar — DONE (2026-06-23)**: started (`python main.py` in `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\ComfyUI`), confirmed responding (`http://127.0.0.1:8188/system_stats` → 200, RTX 5070 Ti detected, 11.5GB VRAM free). Doctor now reports `sidecar:comfyui_health: ok`. It's a foreground/background process, not a persistent service — restart it after a reboot. | Resolved this session |
| **LibreChat sidecar — still open, your call.** You asked what it does (an optional self-hostable ChatGPT-style web UI, same conceptual role as `open-webui`, which VECTOR already has a compatibility gateway for) but haven't decided whether you actually want it. | Either give me a local install path to set `VECTOR_LIBRECHAT_PATH` to, or say "don't use it" and I'll document the warning as intentionally-disabled rather than leave it ambiguous |
| External accounts for HelixDB / LongCat-Video / Evolution API (WhatsApp) / Cal.diy — all have complete, disabled-by-default seams, none auto-enable | Only relevant if you actually want graph-vector mirroring, long-video generation, WhatsApp messaging, or real calendar booking integration — §2 #17-20 |

## 3. Paid API keys (not installable, not free)

| Source | Used by | Status |
|---|---|---|
| Twitter/X API | `last30days` research brief | Needs paid tier for meaningful access — not configured |
| TikTok API | same | Needs app review + business verification |
| Instagram API | same | Needs app review + business verification |
| Polymarket API | same | Needs a wallet/API key |

3 free, no-auth connectors already work today: HackerNews, Reddit, GitHub
(`districts/research/last30days_connectors.py`). I deliberately did not
build a Bluesky connector — its public API contract can't be verified
without live network access in this environment, and shipping an unverified
integration risked silently being wrong.

## 4. Restarting the autonomous loop

`python run_vector.py loop` — the loop is not currently running. A
persistent file log sink now exists (`data/logs/vector_{mode}.log`,
10MB/5 files rotating) so the *next* stoppage will actually be diagnosable,
unlike the last one (no recoverable crash trace existed). I'm blocked from
restarting this myself by the harness's own permission classifier, which
correctly read "don't restart the loop just to test" as covering this too.

## 5. Physical hardware / real deployment

None of this is buildable from a coding session — it requires your physical
machine, your phone, and real cloud credentials.

| Action | Why |
|---|---|
| `fly launch && fly deploy` — **N/A, already decided against.** Fly.io requires a card; you declined. Cloudflare Worker has full endpoint parity already, confirmed live. | Historical — no action needed, just noting it's resolved, not pending |
| `wrangler deploy` in `api/` against the real D1/KV already provisioned in `wrangler.toml` | Command-queue code is fully built and verified secure (Bearer auth fails closed, zero TODO markers) — it just isn't deployed |
| `wrangler secret put` for any secrets that should live on the Worker side, as part of the "Worker Secrets split" | The Python-side secret providers (env/keyring/Vault/AWS) are all real and complete; this is the one piece that's inherently a deployment-time action, not a missing Python class |
| `bash phone_node/setup.sh` on the Termux Android device | Needed before phone↔Legion command relay can be tested end-to-end |
| Enable Wake-on-LAN in Windows BIOS/UEFI + network adapter settings on the Legion machine | `core/control/wake_on_lan.py` (send) + `phone_node/ambient_server.py::_check_legion_reachable()`/`wake_legion()` (check + send, the actual deployment target) are built and tested against local sockets — but nothing can wake a real machine without WoL enabled in firmware first |
| Train the "Hey VECTOR" wake-word ONNX model from the 15 already-recorded samples | `core/voice/wake_word.py` already checks for a custom `.onnx` model and falls back to Whisper-chunk keyword spotting if absent — code is done, the model itself isn't trained |
| `pip install face-recognition mediapipe openwakeword` | Activates face ID + fatigue scoring + wake-word training pipeline (currently degrade gracefully without them) |

---

## What's explicitly NOT on this list (correctly closed, no action needed)

- Kokoro TTS — already installed and working (confirmed: real 911ms/412ms latency benchmarks captured this session)
- `sqlalchemy_utc`, `beartype` pins — already installed/verified
- Cloudflare Worker code, command queue, node status model, Worker auth — all code-complete and tested, only the deploy step above is pending
- 24 of 31 repos in the absorption list — fully done, see `_DONE.md`
