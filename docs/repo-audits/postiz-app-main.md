# Repo Audit — postiz-app-main

**Audited:** 2026-06-01 · **Auditor:** Claude (read + run only, no VECTOR code modified)
**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\postiz-app-main`
**License:** AGPL-3.0 · **Stack:** pnpm monorepo / NestJS (backend) / Next.js (frontend) / Prisma+PostgreSQL / Temporal / Resend
**Prior claim:** phase_status.md (2026-05-28) — "3 Python-portable gaps absorbed (analytics_retriever, blog_publisher, post_job), 69 tests."

---

## Section 1 — Repo Reality

Postiz is an **AGPL open-source self-hosted social-media scheduling SaaS** — an alternative to Buffer / Hypefury. It is a full TypeScript product: a Next.js dashboard + NestJS API + Prisma/PostgreSQL + Temporal durable workflows + Resend email. Apps: `backend`, `frontend`, `commands`, `extension`, `orchestrator`, `sdk`.

### Concrete features (counted)

**Multi-platform posting — 35 provider integrations** (`libraries/nestjs-libraries/src/integrations/social/`):
X, Instagram, Instagram-standalone, YouTube, LinkedIn, LinkedIn-page, Facebook, TikTok, Pinterest, Threads, Reddit, Discord, Slack, Telegram, Mastodon, Mastodon-custom, Bluesky, Nostr, Farcaster, VK, Dribbble, Kick, Twitch, Lemmy, Mewe, Skool, Whop, Listmonk, GMB (Google My Business), Moltbook, Skool — **plus 4 blog/long-form**: Dev.to, Hashnode, Medium, WordPress.

**Product feature set (15+):**
1. Schedule posts across all 35 platforms
2. Visual **calendar** (week/day/grid views — `launches/calendar.tsx`, `calendar.context.tsx`)
3. **Post composer** with per-platform preview (`new.post.tsx`, `preview/`, `provider-preview/`)
4. **AI content generation** — AI image (`ai.image.tsx`), AI video (`ai.video.tsx`), generator
5. **Analytics** — charts, per-social charts, stars/forks (`analytics/`, `platform-analytics/`)
6. **Team / workspace** collaboration — invite, comment, buy/sell posts (`customer.modal.tsx`, comments)
7. **Repeat / recurring** posts (`repeat.component.tsx`)
8. **Media library** + Polotno design editor (`media/`, `polonto.tsx`)
9. **Webhooks** (`webhooks/`)
10. **Public API + SDK** (NodeJS SDK, N8N node, Make.com, Zapier)
11. **Billing** (Stripe) (`billing/`)
12. **Autopost / plugs** automation (`autopost/`, `plugs/`)
13. **Agents** (`agents/`) + browser extension
14. **Sets** (post groupings), signatures, third-party integrations
15. **Onboarding, settings, admin, developer portal**

Postiz core loop: **compose → schedule on calendar → Temporal publishes to N platforms at time → fetch analytics**.

---

## Section 2 — VECTOR Parity (VERIFIED BY RUNNING)

### Absorption claim verification — PASS

```
$ python -m pytest tests/test_postiz_absorption.py -q
.....................................................................   [100%]
69 passed in 1.12s

$ python -X utf8 -c "from districts.content.analytics_retriever import AnalyticsRetriever; \
  from districts.content.blog_publisher import BlogPublisher; \
  from districts.content.post_job import PostJobTracker; print('all 3 import')"
all 3 import
```

**The 69-test claim is REAL.** All three modules exist, import cleanly, and 69/69 tests pass. Module reality:
- `analytics_retriever.py` (270 L) — `AnalyticsRetriever` + `PostMetrics`/`PostRef` dataclasses; YouTube Data API v3 + Analytics API v2, Instagram Graph API; `engagement_rate` auto-computed; graceful no-creds degrade. **Real.**
- `blog_publisher.py` (356 L) — `BlogPublisher` for Dev.to (REST), Hashnode (GraphQL), Medium (2-step); `publish_all()`; tags capped per platform; graceful no-key degrade. **Real.**
- `post_job.py` (367 L) — `PostJobTracker` SQLite-WAL state machine PENDING→PUBLISHING→PUBLISHED/RETRYING/FAILED/CANCELLED; auto-fail at max_retries; error log; `update_metrics()`. **Real, well-built.**

> **Caveat (honest):** all three modules are standalone and tested, but they are **NOT wired** into the content district. `districts/content/__init__.py` exports only the 8 video/voice agents (ScriptGenerator, VideoGenerator, CaptionGenerator, Uploader, VideoMerger, VoiceGenerator, ComfyUIAdapter, MediaStudioAgent). `post_job`/`analytics_retriever`/`blog_publisher` have **zero callers** outside their own files and tests (`grep` across `districts/` + `core/` found none). They are absorbed but inert — library code waiting for an orchestrator.

### Feature-by-feature parity

| Postiz feature | VECTOR equivalent | Verdict |
|---|---|---|
| Multi-platform **chat/social posting** (Telegram, Discord, Slack, Mastodon, Reddit, Twitter, Nostr, Signal, WhatsApp, Teams, Matrix… 37 channels) | `vectorcode/src/channels/` (37 channel modules) + adapters (bluesky, linkedin, mastodon, twitch, youtube) | ✅ real & working (messaging-grade) |
| **Video upload** YouTube/Instagram/TikTok | `districts/content/uploader.py` — real YouTube Data API + IG Graph API, simulate fallback | ✅ real & working |
| **Blog** publish (Dev.to/Hashnode/Medium) | `districts/content/blog_publisher.py` | ✅ real & working (untwired) |
| **Post analytics** (views/likes/reach/engagement) | `districts/content/analytics_retriever.py` (YT+IG) | ⚠️ real but YT/IG only; no LinkedIn/X/TikTok metrics; untwired |
| **Post job tracking / retry state machine** | `districts/content/post_job.py` | ✅ real & working (untwired) |
| **AI content generation** (script/caption/image/video) | `script_generator.py`, `caption_generator.py`, `video_generator.py`, `comfyui_adapter.py`, `voice_generator.py` | ✅ real & working — exceeds Postiz (local SadTalker/ComfyUI/voice clone) |
| **Schedule single upload** | `uploader.schedule_upload()` + `execute_scheduled_uploads()` (in-memory list, no persistence, no driver) | ⚠️ present but stub (in-RAM, lost on restart, nothing calls it) |
| **Scheduling CALENDAR** (week/day grid, multi-platform timeline) | — | ❌ missing |
| **Recurring / repeat** posts | — | ❌ missing |
| **Cross-platform fan-out** ("post once → publish to N social platforms") as one orchestrated action | `vectorcode/src/channels/bulk_sender.py` does fan-out for messaging; **no single content-post → N-social-platform orchestrator** ties uploader+blog+channels+post_job+analytics together | ❌ missing (the integration glue) |
| **Team / workspace / buy-sell posts** | — (single-owner system, N/A by design) | ❌ missing (intentional) |
| **Web dashboard** (calendar/composer/analytics charts) | — | ❌ missing |
| Billing / Stripe | `core/collections` + finance district (unrelated) | ❌ missing (intentional, single-owner) |

### Does VECTOR do schedule → publish-to-N → track analytics end-to-end?

**Partially, and not as one pipeline.** Every *piece* exists and most pieces work:
- publish to social (messaging channels) ✅
- upload video to YT/IG ✅
- publish blog to 3 platforms ✅
- track job state ✅
- fetch analytics ✅

**What's missing for true end-to-end content scheduling:**
1. **An orchestrator** that chains `post_job` → `uploader`/`blog_publisher`/`channels` → `analytics_retriever` → `update_metrics`. Today they're disconnected modules.
2. **Durable scheduling.** `uploader.schedule_upload()` stores in a Python list (lost on restart) and nothing drives `execute_scheduled_uploads()`. Postiz uses Temporal; VECTOR has APScheduler available but no content-scheduling job registered.
3. **A unified social-content posting path.** `bulk_sender` posts *messages*; there is no "publish this content (text+media) to X+LinkedIn+Threads+IG at 9am" action.
4. **Analytics breadth** — only YouTube + Instagram; no X/LinkedIn/TikTok metrics.
5. **Calendar / timeline view** of scheduled content.

---

## Section 3 — Frontend → "Content Scheduler" Panel Spec

Postiz's dashboard is its strongest asset. Mapped to a VECTOR HUD panel:

**Layout (3-zone):**
- **Left rail — Channels manager:** connected platforms as avatar chips (YouTube, IG, X, LinkedIn, blogs…), connection health dot (green/amber/red), add-channel button.
- **Center — Calendar:** week/day grid, scheduled posts as draggable cards colored by platform, "+" per slot opens composer. Status overlay per card: pending / publishing / published / failed (drives off `post_job` states — VECTOR already has this state machine).
- **Right drawer — Composer / Analytics:**
  - *Composer:* text body + media drop + per-platform preview tabs + "schedule for" datetime + target-platform toggles.
  - *Analytics:* per-post `PostMetrics` (views/likes/comments/engagement_rate) as small charts; pull from `analytics_retriever`.

**Brand tokens (VECTOR HUD, from `docs/frontend-spec.md`):** dark base `#0a0e14`, cyan accent `#00d9ff`, status greens/ambers/reds for job states, monospace labels. Platform chips use each platform's brand color.

**Is it worth building NOW?** **Yes — medium priority.** The user *does* content creation (voice, scripts, video — content district is the most-built district). VECTOR already owns the hard backend pieces (uploader, blog_publisher, post_job state machine, analytics_retriever, 37 channels). A panel would turn 5 disconnected modules into a usable product surface and is the natural place to expose the missing **scheduling calendar** + **fan-out composer**. Per VECTOR's "valuable frontends → panel now" rule, this clears the bar. Build the orchestrator (Section 2 gap #1–#3) and the panel together.

---

## Section 4 — Verdict + Delete-Readiness

### Verdict: **DELETE-AFTER** (safe to delete the cloned repo; do NOT delete VECTOR's absorbed modules)

The postiz repo itself is **SAFE TO DELETE** as source — it is AGPL TypeScript/NestJS/Temporal, not absorbable wholesale, and the genuine Python-portable gaps were correctly extracted and verified (69 tests green). Nothing in VECTOR imports from the repo path. Recommend tracker status **DELETE-AFTER** the two follow-ups below are filed (so we don't lose the panel/orchestrator design intent the repo documents).

### Honest gap assessment — what's left

The absorption was **accurate but incomplete in integration**. Three correct modules, but they sit unwired. To get postiz-grade end-to-end content scheduling, VECTOR needs (none of these block deleting the repo):

1. **PATCH — wire the modules.** `districts/content/__init__.py:10-17` exports 8 agents but not the 3 absorbed modules. Add `PostJobTracker`, `AnalyticsRetriever`, `BlogPublisher` to `__all__` and the `agents`/exports dict so the district actually uses them.
2. **INTEGRATE — content scheduling orchestrator.** New `districts/content/content_scheduler.py`: persist scheduled posts in `post_job` (replacing `uploader.py:27` in-memory `_scheduled_uploads` list), register an APScheduler job that polls `post_job.list_pending()` and dispatches to uploader/blog_publisher/channels, then calls `analytics_retriever` + `update_metrics`. This closes the publish→track loop.
3. **INTEGRATE — content scheduler HUD panel** (Section 3) once the orchestrator exists.
4. Optional: extend `analytics_retriever` beyond YouTube/Instagram (X, LinkedIn, TikTok).

**Bottom line:** the 69-test claim is honest and the modules are real and well-built — but "postiz absorbed" overstates it. VECTOR has the *organs* of a scheduler, not the *body*: no durable calendar, no fan-out orchestrator, and the 3 absorbed modules are dead code until wired.

---

## 5-Line Summary
1. **Features counted:** 35 platform integrations + 15+ product features (calendar, composer, AI gen, analytics, team, recurring, webhooks, public API, billing, dashboard).
2. **69 tests:** ✅ PASS — `69 passed in 1.12s`; all 3 modules import cleanly. Claim is real.
3. **Verdicts:** ✅ 6 real & working · ⚠️ 3 stub/partial (schedule_upload in-RAM, analytics YT/IG-only, modules untwired) · ❌ 5 missing (calendar, recurring, fan-out orchestrator, team, dashboard).
4. **Missing for end-to-end scheduling:** an orchestrator chaining post_job→publishers→analytics, durable/persisted scheduling (uploader uses an in-memory list nothing drives), a unified social fan-out post action, and the calendar.
5. **Verdict:** **DELETE-AFTER** (repo safe to delete; modules absorbed + green). Follow-ups: PATCH `__init__.py` to wire the 3 modules, INTEGRATE a content_scheduler + HUD panel (worth building — user does content).
