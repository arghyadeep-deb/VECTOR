# Task 15 — Comms service deploy

> Updated: Task 12 (Fly.io) was cancelled — no longer a dependency.

- **Depends on:** Task 01 (rotated channel creds)
- **Who:** me
- **Effort:** ~45 min

## Objective

`cloud/comms_service/` deployed: the VectorCode gateway bridge routes
outbound messages (Telegram first) and inbound commands back to the loop.

## Implementation

1. `cd cloud/comms_service && fly deploy` (fly.toml present).
2. Set channel secrets (Telegram bot token at minimum) via fly secrets.
3. Wire webhook → inbound router; verify gateway on port 9001 expectation or
   adjust to deployed URL.

## Tests

`POST /send {channel: telegram, ...}` delivers; inbound Telegram message
reaches the governor as a task.

## Demo

Text the Telegram bot "status" → VECTOR replies with loop status.

## Acceptance

- [ ] /status → 200 on deployed service
- [ ] Outbound Telegram message delivered
- [ ] Inbound command round-trips to governor and back
