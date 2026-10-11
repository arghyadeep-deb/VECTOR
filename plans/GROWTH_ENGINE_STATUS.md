# Growth Engine — Final Status (2026-06-30)

Phase 2 output. Supersedes the audit's "MISSING" rows. Verified: **13/13 growth
tests pass**, smoke 38/38, integration 51/51, no regression.

## BUILT this pass
| Component | File | Tests |
|---|---|---|
| Config (gated defaults) | `core/config.py` → `growth` section | `test_growth_config.py` ✅ |
| HUD screen-video recorder | `districts/growth/hud_recorder.py` (Playwright 9:16 → ffmpeg) | `test_growth_hud_recorder.py` ✅ (×2) |
| ARM A content pipeline | `districts/growth/content_arm.py` (2 wells, gated, IG human-in-loop) | `test_growth_content_arm.py` ✅ (×3) |
| ARM B software factory | `districts/growth/software_arm.py` (review↔fix loop, cap+escalate) | `test_growth_software_arm.py` ✅ (×2) |
| Beta signup | `districts/growth/beta_signup.py` (consent+privacy+encrypted, activation-gated) | `test_growth_beta_signup.py` ✅ (×3) |
| Public signup route | `core/api/routers/growth.py` + app/middleware wiring | `test_growth_router.py` ✅ |
| Orchestrator | `districts/growth/growth_orchestrator.py` (2 never-die arms) | `test_growth_orchestrator.py` ✅ |

## Guardrails verified in code
- **Current checkout:** `CONFIG.growth.enabled = True` and `auto_publish = False`. The local content arm may run, while external publication remains owner-gated through the existing approval path.
- Instagram default `instagram_mode = "manual"` → `_notify_owner_to_post`; **`instagrapi` is never called** (test asserts this).
- Beta-signup `active = False` by default; `activate()` raises `PermissionError` without owner approval (same gate as release); consent required; privacy-checked; SQLCipher-encrypted store.
- Public signup path auth+CSRF-exempt but **gated by `BetaSignup`** (POST → 403 while inactive).
- ARM B output tagged `beta_candidate` (never "secure product"); review loop exits only on approve, caps → escalates.
- Truthful-claims-only: script pulls from the real action log / demos real features; two wells avoid thin/fabricated content.

## Reused (not rebuilt) — per the audit
`districts/content/*` (script/voice/video/uploader/captions/post_job), `core/voice/tts.py`
(Kokoro `bf_emma`), `districts/coding/*` (architect/prototyper/reviewer/bug_hunter/security),
`districts/startups/*`, `districts/research/*`, `districts/privacy/*`, `core/collections/*`,
`core/loop/permission_gateway.py`.

## Owner-action prerequisites (before any external publication)
1. **Keep publication gated:** `auto_publish` must remain `False` until the owner has reviewed a real daily media run and explicitly accepts the upload path. `growth.enabled` already enables the local content arm in the current checkout.
2. **Instagram:** stay `manual` (VECTOR renders + Pushovers you to post), or set up a
   Business/Creator account + Facebook app review and set `instagram_mode = "graph_api"`.
   Do NOT route IG through `instagrapi` (ToS/ban risk).
3. **Vertical HUD:** confirm/build a 9:16 HUD layout that renders well at 1080×1920 before
   the first reel (the recorder captures whatever the HUD shows).
4. **Real handles + brand copy** into `CONFIG.growth` (`youtube_handle`, `instagram_handle`,
   `signup_form_url`).
5. **Release/signup gate:** only call `BetaSignup.activate(owner_approved=True)` after a
   human security review of the ARM B output.

## Deferred or still fail-closed (not accepted as autonomous product building)
- Real wiring of the gateway approval → actual upload firing (uploads are log-only no-ops now).
- Real `_next_validated_issue()` feed from market_scanner/idea_validator output.
- ARM B build/review/fix/security stages remain scaffolds and do not select, build, or ship products.
- Frame-accurate audio↔video sync (v1 is narration-over-broll by design).

**Net:** the conductor + the one new media component + the gated signup flow are built,
tested, and wired — fully reusing the ~90% that existed. Nothing publishes or collects PII
until the owner flips the gates above.
