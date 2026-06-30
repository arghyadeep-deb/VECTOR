# Growth Engine — PHASE 0 Audit (reuse-vs-build map)

> Per `plans/PROMPT_growth_engine.md` Phase 0. EXISTS / PARTIAL / MISSING with
> file:line evidence. Verdict at the bottom. **No code written yet** — this is
> the audit the prompt requires before building.

## Headline
The **component agents almost all exist and are reusable** (~90%). What's missing
is exactly what the prompt predicted: **the conductor** (the two-arm orchestrator),
the **screen-video recorder**, the **beta-signup flow**, the **config flags**, and
the **tests**. Neither end-to-end pipeline is wired today — the parts are there, the
workflow that chains them is not.

---

## ARM A — Content / Brand pipeline

| Stage | Module | Status | Evidence |
|---|---|---|---|
| Script (LLM) | `districts/content/script_generator.py` | ✅ EXISTS | class at L11 |
| Voice (Kokoro JARVIS) | `core/voice/tts.py` | ✅ EXISTS | `_KOKORO_VOICE_MAP={"en":"bf_emma"}` L32-33 — exact JARVIS voice the prompt asks for |
| Voice gen agent | `districts/content/voice_generator.py` | ✅ EXISTS | L15 |
| **Video = screen recording of VECTOR working** | `core/sensing/screen_observer.py` | ❌ **MISSING (capability)** | L3-18: it captures a single frame + **OCRs** + classifies activity (mss screenshot). **No video recording** (no `.mp4`/ffmpeg capture/time-aligned narration). This is the prompt's predicted gap. |
| Video gen (avatar/SadTalker) | `districts/content/video_generator.py`, `comfyui_adapter.py` | ✅ EXISTS | L11 / L34 |
| Edit/assemble (ffmpeg) | `districts/content/video_merger.py` | 🟡 PARTIAL | ffmpeg merge + transitions L15, `_check_ffmpeg` L33; **CUDA/nvenc accel + caption burn-in not confirmed** in this file (captions live in `caption_generator.py` L12 — separate, not chained) |
| Captions | `districts/content/caption_generator.py` | ✅ EXISTS | L12 |
| Upload — IG Reels + YT Shorts | `districts/content/uploader.py` | ✅ EXISTS (real API) | `upload_to_youtube` L47 (`googleapiclient` `MediaFileUpload` L91, `videos().insert` L93), `upload_to_instagram` L135, also tiktok/twitter; `PLATFORMS` L25 |
| Upload tracking | `districts/content/post_job.py`, `analytics_retriever.py`, `blog_publisher.py` | ✅ EXISTS | L51 / L43 / L44 |
| Brand strategy | `districts/marketing/{social_media_strategist,content_creator,growth_hacker,seo_specialist}.py`, `districts/agency/{content_strategist,client_manager,performance_tracker}.py` | ✅ EXISTS | all present (L36/33/25/34, L14/13/14) |

**ARM A end-to-end achievable today?** ❌ No. Every stage exists **except the
screen-video recorder**, and nothing chains script→voice→video→edit→upload as one
daily pipeline. ~85% of parts present.

---

## ARM B — Software Factory pipeline

| Stage | Module | Status | Evidence |
|---|---|---|---|
| Specs from research | `districts/research/{deep_researcher,agent,news_aggregator,last30days}.py` | ✅ EXISTS | present |
| Market issue detection | `districts/startups/{market_scanner,idea_validator,competitor_spy,revenue_modeler}.py` | ✅ EXISTS | L17/14/17/15 |
| Build (architect/prototype) | `districts/coding/{architect_bot,rapid_prototyper,minimal_change_engineer}.py` | ✅ EXISTS | L14/114/38 |
| Code review + supervisor | `districts/coding/{code_reviewer,bug_hunter,test_writer}.py` | ✅ EXISTS | L91/15/15 |
| Security audit | `districts/security/{alert_manager,data_redactor,detection_rules}.py`, `core/security/*` | ✅ EXISTS | present |
| Git/release | `districts/coding/git_bot.py` | ✅ EXISTS | L15 |
| **Reviewer↔fix loop until sign-off** | — | ❌ **MISSING** | no orchestrated review-cycle controller; the reviewer/fixer agents exist but nothing loops them to a sign-off gate |
| **Beta-signup form (collections, privacy-gated, consent)** | `core/collections/{schema,store,storage,auth,migrations}.py` exist; the **form/flow does not** | 🟡 PARTIAL | collections engine present (can store registrations encrypted via SQLCipher); **no beta-signup module, no consent form, no "1-month free" issuance** |
| Privacy gating for PII | `districts/privacy/{data_flow_auditor,privacy_enforcer}.py` | ✅ EXISTS | present |

**ARM B end-to-end achievable today?** ❌ No. Build/review/security agents all
exist, but the **review→fix→sign-off loop**, the **beta-signup flow**, and the
**release conductor** are missing.

---

## Cross-cutting

| Item | Status | Evidence |
|---|---|---|
| **Orchestrator (the two-arm conductor)** | ❌ **MISSING** | no `districts/growth/`, no `growth_orchestrator.py` anywhere |
| Permission gateway (gate public actions) | ✅ EXISTS | `core/loop/permission_gateway.py` L23 — to be wired YELLOW for every publish |
| Scheduling (daily cadence, 2AM, cron) | ✅ EXISTS | `core/loop/cron_jobs.py` L32 |
| Config flags (`auto_publish`, IG handle, cadence, form URL, voice profile) | ❌ MISSING | none in `core/config.py` |
| Tests (orchestrator, stage handoff, review loop, gate-blocks-publish, encrypted beta form) | ❌ MISSING | none |
| Status doc | ❌ MISSING | this audit is Phase 0; `GROWTH_ENGINE_STATUS.md` is the Phase 2 output |

---

## What must actually be BUILT (the gaps)
1. **`districts/growth/growth_orchestrator.py`** — the two-arm asyncio conductor (never-die coroutines), triggered by `market_scanner`+`idea_validator` finding a software-solvable issue.
2. **Screen-video recorder** — ffmpeg/mss video capture of a scripted demo run, time-aligned with the Kokoro narration track. (The single genuinely-new media component.)
3. **ARM A chain** — script→voice→video→edit(ffmpeg+captions)→upload(IG Reels + YT Shorts), one/day, brand line + beta-signup link in bio.
4. **ARM B chain** — specs→build→review↔fix loop (exits only on reviewer sign-off)→security audit→release.
5. **Beta-signup flow** — collections-backed, privacy-gated, explicit consent text, encrypted (SQLCipher), 1-month-free issuance.
6. **Config** — `growth` section in `core/config.py`: IG handle, cadence, voice profile, form URL, `auto_publish` flag (default off / YELLOW).
7. **Guardrails baked in** — every publish through `permission_gateway` (YELLOW default), PII through `districts/privacy/`, truthful claims pulled from VECTOR's real action log, official-API rate-limit+retry.
8. **Tests** (Phase 2) + rename this to `GROWTH_ENGINE_STATUS.md` with final state.

## Reuse ratio
**~90% of the agents exist and are reusable.** The build is genuinely a
**conductor + one new media component (screen recorder) + a signup flow + glue +
guardrails + tests** — not a from-scratch effort. This matches the prompt's thesis
exactly: *"the parts exist, the conductor doesn't."*
