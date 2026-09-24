# VECTOR — Open Issues (reconciled 2026-06-29; engineering section added 2026-09-24)

**This is the single current status file.** `KNOWN_ISSUES.md` holds the detailed
root-cause traces for the engineering items in section 0; sections A–F below are
owner-gated items (hardware, accounts, deploys, decisions).

The old headline ("there is no open code work") was wrong once `KNOWN_ISSUES.md`
grew open engineering items; section 0 lists them.

## 0. Open engineering work (as of 2026-09-24)

1. **Autonomous loop thread freeze** (`KNOWN_ISSUES.md` #0) — live-observed 2026-08-05.
   One root cause found and fixed 2026-09-24 (`script_generator._llm()` blocking the
   event loop for up to 120s; also the council's sync Ollama calls). **Not yet
   re-verified against a live multi-hour run.**
2. **Live re-verification** of the Phase 1–6 fixes (`KNOWN_ISSUES.md` #9) and of the
   2026-09-24 review fixes — needs a live backend.
3. **`Governor.dispatch()` trusts a caller-supplied `district`** for task types outside
   `DISTRICT_TASK_MAP` (e.g. `{"type":"cleanup_logs","district":"ops"}` runs with no
   receipt). Confirmed, deliberately unfixed pending an adversarial (Codex) review
   after its quota resets 2026-09-27.
4. **Permission-tier coverage**: 134 action-shaped manifest capabilities have no tier
   (blocked, fail-closed). Proposals in `VECTOR_TECHNICAL_KNOWLEDGE/PHASE4_TIER_COVERAGE_REPORT.md`;
   owner approval required before any change.
5. **Routing**: `KNOWN_ISSUES.md` #10 ("remember X" misroute) is **resolved** in code
   (`_authoritative_district_from_text` + honest `no_capable_agent`); the entry is kept for history.
6. **Content pipeline** (2026-09-24): a daily `content-plan` cron job now plans script -> `schedule_post`
   (only for platforms with a configured key); the 09:00 publish job still needs owner approval per post.
   Still open: live `post_jobs.db` holds 37 junk "Test Post" rows (owner approval needed to cancel);
   interrupted renders are listed by `list_resumable_jobs()` but resuming an upload is an owner action;
   publishing credentials (Dev.to key, YouTube OAuth, Instagram token) are owner-side.
7. **Test-suite items**: `test_lifecycle_unvalidated_to_validated` needs a confidence-semantics
   decision; `test_fresh_domain_no_penalty` is fragile against the live causal graph;
   `test_phase_a7_council_red_tier` expects `push_github` council auto-proceed (policy question).
   The full-suite baseline (5,012 / 13 / 36) has not been re-run since the review fixes.
8. **Dead code** (owner direction 2026-09-24: keep everything): nothing deleted. `docs/design/core-module-triage.md`
   classifies the unreachable `core/` modules; useful ones were wired (repo-hygiene gate, OAuth refresh and
   cloud heartbeat cron jobs), ten duplicates carry a DORMANT banner. Follow-up designs listed at the end of
   that file (token_juice, semantic_cache, engine agents, secrets providers, sound classifier).
9. **Licensing**: `THIRD_PARTY_NOTICES.md` + LICENSE files added; `vector_finagent` headers corrected. Still
   open: several vendored trees (shadowbroker_server, vector_backtest, hedgebot, vector_mlops, mining) have
   no identifiable upstream/license.
10. **Uncommitted earlier work**: `core/loop/autonomous_loop.py`, `core/city/agent_base.py`,
    `core/inference/provider_client.py`, `core/runtime/executor.py` (the 2026-09-23 audit, incl. the
    plan-starvation fix) sit uncommitted in the working tree. With them present,
    `tests/test_r26_cognitive_integration.py::...ablation...` and 3 tests in
    `tests/test_r13_production_learning_validation.py` fail; at committed HEAD r26 passes and r13 fails 2 of
    3 (a pre-existing reward-arithmetic drift). Review and commit or revert that work.
12. **Test isolation** (2026-09-24): every pytest session now uses a fresh temp DB/data dir and fails any test
    that resolves to live state. Verified: 0 live files changed across a 15-batch run. The last batch of
    that run (and part of batch 10) was killed by the memory guard, so a complete post-change baseline
    comparison (5,012 / 13 / 36) is still owed — re-run when the machine has headroom.
11. **HP bonus for a no-API-keys future** (agents' non-API reward) — on hold until the owner decides.
13. **HUD honesty + vectorcode repair (2026-09-24, commits ffc5554db..001dd53d3)** — DONE: the HUD no longer
    presents demo seed data as live (honest "NO DATA"/UNKNOWN states, verified in a real browser); vectorcode's
    shell tools, agent loop, `run`/`auto`, CLI subcommands, tool registry, skills, tui_gateway imports now work
    (see the fix report). **Still open in vectorcode**: `agent/context_compressor.py` needs an
    `agent.context_engine.ContextEngine` base that was never vendored, so the legacy `run_agent.py` path cannot
    import (the live agent is `engine/agent_loop.py`, which does not use it); `batch_runner` needs the `fire`
    package; `pty_bridge` is Unix-only; `acp_adapter` needs `agent-client-protocol`; non-Ollama providers are
    text-only (no tool calling) so `vector run/auto` need a local Ollama model; `mining.vllm_pearl` is missing.
14. **Code intelligence is not built** (`vectorcode/code_intel` has no `dist/`; it also needs Node, Qdrant and an
    embedding model). `/code-intel/*` now answers 503 with the build command and no longer docks agent HP.
    Building it is an owner decision (Node/Qdrant install).
15. **Stray test write in the live home** — while adding the router tests, one child process inherited the real
    `VECTOR_HOME` and wrote a single line ("vector test fact") to `~/.vector/memories/MEMORY.md` (new dir, only
    that file + `MEMORY.md.lock`). Test fixtures are fixed so it cannot recur; the file itself is left for the
    owner to delete (the auto-mode classifier blocked me from removing it).
16. **HUD side panels**: ComfyUI / Media Studio / Hyperframes now say "not running" (via `/media/sidecars`) when
    their local servers are down; the servers themselves are owner-started.

This file is the single owner-facing source of truth. Full per-item evidence
(the detailed 31-repo absorption + open-issues audit with file:line proof) lives
in git history — the in-tree `repo_analysis/` archives were removed once their
open items were folded in here.

---

## A. This session's follow-ups (2026-06-29)

1. **Force-push the rewritten history.** ✅ **DONE 2026-07-05.** Pushed
   `production-hardening-complete` to github.com/arghyadeep-deb/VECTOR;
   remote HEAD == local (06d6d208), largest blob now 27MB (kokoro voices,
   well under GitHub's 100MB). The >100MB-blob history is gone from the
   pushed tree.
2. **Delete the safety backups.** ✅ **DONE** — `vector_git_backup*` and
   `vector_memory.db.premaint.bak.*` were already removed in a prior session;
   confirmed none remain.

## B. Physical hardware / OS settings (cannot be done from code)

3. **Termux node:** run `bash phone_node/setup.sh` on the Android device — needed
   before the phone↔Legion command relay can be tested end-to-end.
4. **Legion Wake-on-LAN:** enable WoL in BIOS/UEFI + network-adapter settings,
   then set `LEGION_HOST` to Legion's LAN IP in `phone_config.env`. Code
   (`core/control/wake_on_lan.py`, `ambient_server.py`) is built/tested against
   local sockets; only firmware WoL is missing.
5. **`face_recognition`:** ✅ **RESOLVED** — `import face_recognition` succeeds (verified 2026-09-24);
   the earlier Application Control block no longer applies.
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

*Section 0 is the open engineering list; update this file in place as items land.*
