# Task 12 — Deploy cloud brain (Fly.io)

- **Depends on:** Task 01 (rotated keys only)
- **Who:** OWNER login → me
- **Effort:** ~30 min

## Objective

`cloud/brain_server/` live at `https://<app>.fly.dev` — VECTOR's reachable
cloud node (heartbeat target for `CloudBrainHeartbeat`, phone node upstream).

## Implementation

1. OWNER: `fly auth login` (or `! fly auth login` in a Claude session).
2. me: `cd cloud/brain_server && fly launch --copy-config --no-deploy` then
   `fly secrets set` for required env vars (new keys only) and `fly deploy`.
3. Point `CONFIG` cloud_brain_url at the deployed app.

## Tests

`curl https://<app>.fly.dev/health` → 200; `/status` returns JSON.

## Demo

Local loop log shows successful heartbeat to the fly app.

## Acceptance

- [ ] /health and /status → 200
- [ ] Heartbeat from the local loop arrives (sync loop log)
- [ ] No secrets in fly.toml (set via fly secrets)
