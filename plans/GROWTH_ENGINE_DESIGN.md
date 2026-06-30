# VECTOR Autonomous Growth Engine — Design Spec (2026-06-30)

> Approved design. Pairs with `plans/GROWTH_ENGINE_AUDIT.md` (Phase 0) and
> `plans/PROMPT_growth_engine.md` (origin prompt). Next step: `writing-plans`.

## Goal
A self-running growth arm: **ARM A** (daily brand reels) + **ARM B** (issue→software→beta)
running as two parallel never-die asyncio coroutines, reusing the ~90% of agents that
already exist. Every outward action is permission-gated; nothing auto-publishes by default.

## Architecture
```
districts/growth/
  __init__.py
  growth_orchestrator.py  — conductor: 2 never-die coroutines (ARM A daily, ARM B per validated issue)
  content_arm.py          — ARM A pipeline (chains existing content agents)
  software_arm.py         — ARM B pipeline + reviewer↔fix loop controller
  hud_recorder.py         — NEW media component (Playwright HUD capture → ffmpeg)
  beta_signup.py          — signup logic over core/collections (encrypted, privacy-gated, activation-gated)
core/api/routers/growth.py — public consent form (GET) + signup POST
core/config.py             — "growth" CONFIG section (all knobs)
tests/test_growth_*.py
plans/GROWTH_ENGINE_STATUS.md — Phase 2 final state
```

## ARM A — Content / Brand (daily, one reel)
Pipeline: **script → narration → HUD recording → assemble → (gated) upload.**

1. **Script** (`script_generator`) — **truthful only**, drawn from TWO wells:
   - *"work done today"* — from VECTOR's real action log (episodic/reasoning memory).
   - *"capability showcase"* — demo an existing feature, used as fallback when no
     reel-worthy work happened that day. Prevents thin/fabricated content.
2. **Narration** — Kokoro `bf_emma` (the JARVIS voice, `core/voice/tts.py`). Generate
   first; its duration sets the recording window.
3. **HUD recording** (`hud_recorder.py`, NEW) — **Playwright page-video recording** of
   `frontend/VECTOR.html` at a **1080×1920 vertical viewport** (9:16 for Reels/Shorts).
   - **Hard part (explicit):** the recorder must **trigger a real task and have the HUD
     reflect it live** (via the existing websocket/event feed) for the capture window —
     not record an idle HUD. This coordination is the core engineering, not the capture.
   - **Prerequisite flagged:** confirm/build a **vertical HUD layout** that renders
     acceptably at 1080×1920 before this ships; if the HUD is 16:9-only, add a vertical
     mode or crop/letterbox. Owner-confirm before first reel.
   - **Sync model (v1):** narration-over-broll — voice describes generally while the HUD
     shows activity. **No frame-accurate alignment** (deliberately out of scope).
4. **Assemble** — `video_merger`/ffmpeg muxes narration audio over the HUD webm,
   `caption_generator` burns captions → 9:16 mp4.
5. **Upload** — **gated**:
   - **YouTube Shorts:** `uploader.upload_to_youtube` (official YouTube Data API). Auto,
     but still behind the permission gate (YELLOW).
   - **Instagram Reels:** **NOT auto-`instagrapi`** (unofficial, reverse-engineered,
     ToS-violating; daily posting from a fresh datacenter-IP account = fast ban — flagged).
     Default = **human-in-the-loop**: VECTOR renders the reel and Pushover-notifies the
     owner to post manually. Configurable upgrade: **official Instagram Graph API Content
     Publishing** (Business/Creator account + Facebook app review — owner action).
6. Bio/description carries the brand line + (when a beta is live) the signup form link.

## ARM B — Software Factory (per validated issue)
Pipeline: **research specs → build → review↔fix loop → security audit → release candidate.**

1. **Trigger** — `market_scanner` + `idea_validator` find a software-solvable issue.
2. **Specs** — from `districts/research/*`.
3. **Build** — `architect_bot` / `rapid_prototyper` (frontend + backend).
4. **Review loop** (`software_arm.py` controller) — `code_reviewer` + `bug_hunter` →
   fix → repeat **until reviewer sign-off**, with a **max-iteration cap** and never-die
   error handling. Exits only on approve (or cap → escalate to owner).
5. **Security audit** — `districts/coding/security_reviewer` + `core/security/*`.
6. **Output is a BETA CANDIDATE, not guaranteed-secure software.** Explicitly framed as
   "owner-security-reviewed candidate," never "can't-be-hacked product."
7. While building, ARM A can post about the problem + solution-in-progress (gated).

## Beta Signup (collections-backed, privacy-gated, ACTIVATION-gated)
- `core/api/routers/growth.py`: public **consent form** (GET) + **POST** handler.
- POST → `core/collections` store, **SQLCipher-encrypted**, through
  `districts/privacy/privacy_enforcer` gate. Explicit consent text on the form.
- 1-month-free flag issued on release.
- **Critical amendment:** signup-form **activation is gated to the SAME owner approval as
  release.** Signups can NOT open on software that hasn't passed a human security check —
  the permission gate covers "activate signup form," not just "publish." This is a real
  liability boundary (collecting real users' PII for unvetted software).

## Guardrails (baked into code)
1. **Permission gate** (`permission_gateway`, YELLOW default) on: every publish, every
   release, **beta-signup activation**, and brand/ownership claims. `auto_publish` config
   flag defaults OFF; never hard-wired auto-post.
2. **Privacy:** all PII through `districts/privacy/`, SQLCipher-encrypted, local-first,
   explicit consent. No user data leaves device except to the consented service.
3. **Config, not magic strings:** IG/YT handles, cadence, voice profile, viewport, form
   URL, consent text, feature flags → `core/config.py` `growth` section.
4. **Truthful claims only:** script generator pulls from the real action log; the
   capability-showcase well demos real features. No fabricated capabilities.
5. **Platform ToS:** official APIs (YouTube Data API; IG Graph API or human-in-loop);
   rate-limit + retry; ToS risks flagged in this spec, not silently automated around.

## Config (`core/config.py` → `growth`)
`brand_line` ("VECTOR — Arghyadeep's personal AI Intelligence"), `youtube_handle`,
`instagram_handle`, `instagram_mode` ("manual" | "graph_api"), `post_cadence`,
`voice_profile`, `hud_viewport` ([1080,1920]), `signup_form_url`, `consent_text`,
`auto_publish` (False), `review_loop_max_iterations`, `enabled` (False).

## Testing (Phase 2)
- orchestrator starts both tracks (never-die);
- ARM A stage handoff script→voice→video→assemble→upload (mocked uploads, mocked recorder);
- ARM B review loop **exits only on reviewer-approve** (and caps → escalates);
- permission-gate **blocks unapproved publish AND unapproved signup-activation**;
- beta-form writes **encrypted + privacy-checked**, consent required;
- IG default path does **not** auto-post (asserts human-in-loop notify, not instagrapi call).

## Build order
config → hud_recorder → content_arm → software_arm → beta_signup + route → orchestrator →
tests → rename audit-companion to `GROWTH_ENGINE_STATUS.md` with final EXISTS/BUILT/owner-action.

## Owner-action prerequisites (cannot be coded)
1. Decide IG path: stay human-in-loop, or set up Business/Creator account + Facebook app
   review for the official Graph API.
2. Confirm/approve the vertical (9:16) HUD layout before the first reel.
3. Real IG/YouTube handles + final brand copy into config before anything posts.
4. `enabled` + `auto_publish` flags stay OFF until owner flips them.
