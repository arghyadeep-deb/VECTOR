# VECTOR — Open Issues (reconciled 2026-06-29)

Single clean list of what is **genuinely still open**, checked against current
code/state. The headline: **there is no open code work** — everything buildable
has been built, tested, and (for cloud) deployed. Every item below is
owner-gated: physical hardware, a paid/verified account, a deploy step, or a
decision only you can make.

This file is the single owner-facing source of truth. Full per-item evidence
(the detailed 31-repo absorption + open-issues audit with file:line proof) lives
in git history — the in-tree `repo_analysis/` archives were removed once their
open items were folded in here.

---

## A. This session's follow-ups (2026-06-29)

1. **Force-push the rewritten history.** Git history was rewritten twice this
   session to strip >100MB blobs (293MB cmake artifact + ONNX models) and the
   `finagent/qt/build/` cruft — GitHub push is now unblocked but needs a force:
   `git push -u origin production-hardening-complete --force`.
2. **Delete the safety backups once the push is confirmed** (~3.4GB total):
   `../vector_git_backup_20260629_180411`, `../vector_git_backup2_*`, and
   `vector_memory.db.premaint.bak.20260629_135132`.

## B. Physical hardware / OS settings (cannot be done from code)

3. **Termux node:** run `bash phone_node/setup.sh` on the Android device — needed
   before the phone↔Legion command relay can be tested end-to-end.
4. **Legion Wake-on-LAN:** enable WoL in BIOS/UEFI + network-adapter settings,
   then set `LEGION_HOST` to Legion's LAN IP in `phone_config.env`. Code
   (`core/control/wake_on_lan.py`, `ambient_server.py`) is built/tested against
   local sockets; only firmware WoL is missing.
5. **`face_recognition`:** installed, but its native `dlib` DLL is blocked by a
   Windows Application Control policy (`ImportError: ... blocked by an Application
   Control policy`). This is an OS security setting only you can change — not a
   missing package. Camera/face features fall back to neutral until then.
6. **"Hey VECTOR" wake word** — PIPELINE COMPLETE; blocked on owner's real voice
   data (2026-07-04). Full openWakeWord train->export->load pipeline runs end-to-end
   (gen_wake_synthetic.py + train_wake_word_synthetic.py); 5 env bugs fixed
   (torchvision-first import, cp1252 stdout, mmap_batch_generator {label:path},
   empty-val-history, export_to_onnx empty output). Voice diversity solved via
   multi-speaker libritts (904 voices) -> FIXED false-triggering (silence 0.97->0.01).
   But the real wall is RECALL on the OWNER's actual voice: synthetic TTS voices don't
   transfer to the owner's real voice/mic -- best ~13% recall (2/15 real clips fire)
   across every config (5k/20k steps, 32-64 pos/batch). Quality gate fixed to measure
   real-clip RECALL FRACTION (>=50% must fire), not a lucky max -- so synthetic-only
   models are correctly REJECTED and core/voice/wake_word.py keeps working Whisper
   keyword-spotting (NO regression, verified). ONE remaining need is OWNER-GATED:
   ~50-100 real "Hey VECTOR" recordings (record via scripts/train_wake_word.py, drop
   into models/wake/samples/, re-run the synthetic trainer -- it installs only if
   recall clears 50%). Full ~17GB ACAV negatives would NOT help (problem is recall).

## C. Cloud deploy (needs your Cloudflare account/credentials)

7. **`cloud/email` Worker deploy** (separate from the already-live API Worker):
   needs a Cloudflare account/domain, Email Routing, R2 bucket `vector-email`,
   Workers AI, Cloudflare Access, and Worker secrets `POLICY_AUD`/`TEAM_DOMAIN`.
8. **`cloud/email` dependency advisories** — ✅ **RESOLVED (2026-07-01).** `npm audit`
   = **0 vulnerabilities** (was 4). The `echarts` XSS moderate was cleared by a safe
   `npm audit fix`; the 3 high `react-router` turbo-stream RCEs were fixed by upgrading
   `react-router`/`@react-router/dev`/`@react-router/node` 7.13.1 → **7.18.1** (in the
   7.x line — vite-6 compatible, no toolchain cascade; only `@latest` 8.x needed vite 7).
   `npm run typecheck` passes (EXIT=0). No remaining advisories.
9. **Cloudflare Worker parity tests** (`api/test/smoke.test.ts`): the harness is
   real and correct but `workerd`'s module loader can't resolve modules because
   this repo's path contains a literal space (`V.E.C.T.O.R. Codebase`). It runs
   in CI (Linux) or any space-free clone path — an upstream tooling limitation,
   not a code bug.

## D. Paid / verified API keys (optional — only for the `last30days` research brief)

10. **Twitter/X, TikTok, Instagram, Polymarket** connectors need paid tiers or
    app-review/business verification. Three free connectors (HackerNews, Reddit,
    GitHub) already work today; the rest stay disabled until you provide keys.

## E. Decisions that need no code — just your choice

11. **Post-training:** flip `post_training_enabled` in `core/config.py` and decide
    when the weekly Sat-04:00 run (`cron_jobs.py::job_post_training_run()`) should
    fire. Gated OFF by default; zero heavy imports until flipped.
12. **Voice engine default:** all engines (Kokoro/OmniVoice/Supertonic) are
    installed with weights downloaded; only Kokoro has real benchmark numbers so
    far. Defaults unchanged (`live_engine="kokoro"`, `cloning_engine="chatterbox"`).
    A/B listening + any default flip is your call.
13. **Optional integrations** (all have disabled-by-default seams; enable only if
    wanted): HelixDB graph-vector mirroring, LongCat-Video, Evolution-API
    (WhatsApp), Cal.diy calendar booking.

---

## F. Runtime config flags (reference — not work, just knobs)

These env-var flags gate live services / model calls / mutable resources out of
default runs. They are **off by default on purpose** (so tests never hit live
LLMs/services); flip one when you want that feature live. A feature behind a flag
isn't "proven in production" until you supply the service/device and run it live.

| Flag | Default | Enables |
|---|---:|---|
| `VECTOR_LIVE_TESTS=1` | off | Live network/model integration proofs in `tests/integration/test_capability_live.py`. |
| `VECTOR_RESEARCH_LLM_DESIGN=1` | off | Ollama-backed research experiment design (`core/research_engine/experiment_designer.py`); else rule-based. |
| `VECTOR_TRAINING_REAL=1` | off | Real PEFT/Unsloth LoRA training (`core/training/lora_trainer.py`); else simulated/dry-run. |
| `VECTOR_PREDICTIVE_USE_MEMORY=1` | off | Predictive analytics mining of live episodic memory history. |
| `VECTOR_DB_RECOVERY_CHECK=1` | off | Live memory-DB integrity check + recovery playbook. Keep off unless DB is backed up. |
| `VECTOR_OBSIDIAN_RAG_QUERY=1` | off | Obsidian/LightRAG query during context hydration. |
| `VECTOR_FASTAPI_REVIEW_LLM=1` | off | LLM-backed FastAPI code review. |
| `VECTOR_PYTHON_REVIEW_LLM=1` | off | LLM-backed Python code review. |
| `VECTOR_SECURITY_REVIEW_LLM=1` | off | LLM-backed security review. |
| `VECTOR_SEO_LLM=1` | off | LLM-backed SEO synthesis/schema/keyword work. |
| `VECTOR_GOOGLE_ADS_LLM=1` | off | LLM-backed Google Ads audit/copy/landing-page reasoning. |
| `VECTOR_FEEDBACK_LLM=1` | off | LLM-backed interview feedback analysis. |
| `VECTOR_STYLE_LLM=1` | off | Ollama-backed persona style rewrites. |
| `VECTOR_WEB_SCOUT_LLM=1` | off | LLM-backed WebScout research summaries. |
| `VECTOR_REDDIT_MINER_LLM=1` | off | LLM-backed RedditMiner opportunity extraction. |
| `VECTOR_SKILLS_LLM=1` | off | LLM-backed skills gap analysis, prioritization, learning paths. |

---

*All code-side work is closed. Update this file in place as owner actions land.*
