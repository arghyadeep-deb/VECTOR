# Owner Actions Needed

**Date:** 2026-06-23. Single consolidated list of everything from the 2026-06-23
repo-analysis audit (`_MASTER_TODO.md`) that genuinely requires action only
the owner can take — a heavy install, a credential/account, physical hardware,
or a deploy decision. Everything that was buildable as code has been built and
tested this session; nothing below is blocked on more code from me.

Grouped by what kind of action it needs. Each item links back to its
`_MASTER_TODO.md` section for full evidence/context.

---

## 1. Heavy package installs (pip install + model weights)

None of these are required for VECTOR to work today — all are optional
upgrades with complete, tested, disabled-by-default code seams already in
place. Install only if you want the specific capability.

| Package(s) | Unlocks | Where the seam lives |
|---|---|---|
| `pip install peft trl` | Real LoRA SFT/DPO training instead of the simulated-but-real pipeline | `core/training/post_training/` — §1c |
| `pip install omnivoice` + model weights | Real comparative voice-engine benchmark numbers vs. Kokoro/VoxCPM/Supertonic; multilingual (600+ lang) high-quality voice studio generation | `core/voice/engines/omnivoice_engine.py`, `districts/content/voice_generator.py::generate_voice_studio()` — §2 #6 |
| `pip install supervision ultralytics` + `yolo11n.pt` weights | Real YOLO+ByteTrack ambient presence detection (upgrade over frontal-face-only check) | `core/sensing/presence_detector.py` — §2 #9 |
| `pip install supertonic` + ~260MB model + build/pick a persona voice JSON | CPU-only, zero-VRAM live-conversation TTS alternative to Kokoro; better Hindi/Japanese quality, no cloud round-trip | `core/voice/supertonic_tts.py` — §2 #14. **After installing:** A/B listen against Kokoro's `bf_emma`, then flip `CONFIG["voice"]["live_engine"] = "supertonic"` if you like it better. |

## 2. Decisions that don't need new code, just a choice

| Decision | What it affects |
|---|---|
| Flip `post_training_enabled` in `core/config.py`, and decide when the weekly Sat-04:00 training run should actually fire | `core/loop/cron_jobs.py::job_post_training_run()` — already gated OFF by default, zero heavy imports until flipped |
| `core/voice/cloning.py::cloning_engine` is `"chatterbox"` — stays unless you decide OmniVoice's eventual benchmark beats it for cloning/voice-design | No action needed unless OmniVoice underperforms |
| Doctor sidecar warnings: `LibreChat` path unset, `ComfyUI` health unreachable (both `required: false`, `doctor` reports `degraded` but not blocking) | Either configure both (`VECTOR_LIBRECHAT_PATH`, start the ComfyUI service) or explicitly document them as intentionally-disabled to silence the warning — §3 item 2 |
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
