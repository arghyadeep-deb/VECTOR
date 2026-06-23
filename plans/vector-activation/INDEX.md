# VECTOR Activation — Task Index

Goal: from "code-complete" to a running, talking, seeing, cloud-connected
VECTOR. Created 2026-06-11. Status legend: ⬜ todo · 🟨 in progress · ✅ done · ❌ cancelled.

> **Updated 2026-06-24** — Task 03's dependency-install status was stale
> (torch is confirmed CUDA, mediapipe/openwakeword confirmed working as of
> this session). Task 12 (Fly.io) is now ❌ cancelled — Fly.io was declined
> (requires a card) and `cloud/brain_server/` was removed entirely; the
> Cloudflare Worker has full parity and is the only cloud brain. Tasks
> 13/14/15's dependency chain updated accordingly (no longer gated on 12).
> `docs/repo_analysis/OWNER_ACTIONS_NEEDED.md` is the live, current tracker
> for what's actually still pending — this file is the older, detailed
> per-task breakdown, useful for the *how*, not the current *what's left*.

| Task | Who | Demo | Status |
|------|-----|------|--------|
| [01](./task-01-rotate-keys.md) Rotate all API keys | OWNER | new keys in .env, old ones revoked | ⬜ |
| [02](./task-02-github-history-push.md) GitHub scrubbed-history push | OWNER → me | `git log --all -- .env` empty ON GITHUB | ⬜ — blocked: GitHub push rejects history >100MB blobs; scrubbed locally, owner decision needed on how to proceed |
| [03](./task-03-voice-vision-deps.md) Install voice/vision deps | me | `import whisper, kokoro_onnx, openwakeword, mediapipe, face_recognition` | 🟨 torch confirmed CUDA (cu128), mediapipe + openwakeword confirmed working (2026-06-23). `face_recognition` is pip-installed but its `dlib` native DLL is blocked by a Windows Application Control policy — needs an owner security-settings change, not a pip action |
| [04](./task-04-enroll-voiceprint.md) Enroll owner voiceprint | OWNER | speaker_verify gates a YELLOW voice command | ⬜ |
| [05](./task-05-train-wake-word.md) Train "Hey Vector" wake word | OWNER | custom .onnx loads, openwakeword path active | ⬜ |
| [06](./task-06-first-conversation.md) First HUD duplex conversation + tuning | OWNER + me | full talk-listen-interrupt loop at /hud/ | ⬜ |
| [07](./task-07-face-id.md) Face ID activation | OWNER + me | camera names the owner | ⬜ — blocked on Task 03's `face_recognition`/Windows policy issue |
| [08](./task-08-windows-service.md) Install Windows service | OWNER (admin) | service survives reboot, loop runs | ⬜ |
| [09](./task-09-venture-live-run.md) Venture pipeline first live run | OWNER | venture report in data/venture/ + HUD widget | ⬜ |
| [10](./task-10-brain-write-verify.md) Verify autonomous brain writes | me | 2AM journal note in vault | ⬜ |
| [11](./task-11-budget-check.md) Budget sanity after 24h | me | per-agent spend report ≈ ₹0 | ⬜ |
| [12](./task-12-fly-deploy.md) Deploy cloud brain (Fly.io) | OWNER login → me | `https://<app>.fly.dev/status` → 200 | ❌ cancelled — Fly.io declined, see `DEPLOY.md` for the Fly-free path |
| [13](./task-13-wrangler-deploy.md) Deploy Cloudflare API | OWNER login → me | worker URL serves /status | ⬜ |
| [14](./task-14-phone-node.md) Phone ambient node (Termux) | OWNER | phone heartbeats reach the loop | ⬜ |
| [15](./task-15-comms-service.md) Comms service deploy | me | /send routes to Telegram | ⬜ |

## Dependency chain

```
01 → 02            (rotate before re-publishing anything)
03 → 04 → 06       (deps → voiceprint → conversation)
03 → 05 → 06       (deps → wake word → conversation)
03 → 07            (deps → face ID)
06 → 08            (prove voice manually before always-on)
08 → 09, 10, 11    (always-on enables live pipeline + nightly verification)
01 → 13, 15        (rotated keys before any cloud deploy -- Task 12/Fly removed from this chain)
13 → 14            (phone node talks to the Cloudflare Worker, not a Fly brain)
```

## Done outside the numbered tasks

- **Frontend hardening 2026-06-11** (audit follow-up): XSS defense-in-depth
  (esc/escapeHtml on all innerHTML data paths + safeUrl for external links),
  duplex `wake`/IDLE WS events wired, Google Fonts vendored + Leaflet/CartoDB
  CDNs dropped (served HUD = zero external hosts). Frontend security ~78→~93,
  the only "leak" closed. Verified live (HUD/fonts 200, no CDN in served HTML).

## Out of scope (tracked elsewhere)

OpenMythos/LoRA training, dedup (verdict: keep separate — HANDOFF item 7),
multi-region HA, voice tuning beyond first pass.
