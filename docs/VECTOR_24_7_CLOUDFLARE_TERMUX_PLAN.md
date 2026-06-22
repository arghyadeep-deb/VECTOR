# VECTOR 24/7 Cloudflare + Termux Plan

This is the target design for keeping VECTOR available from any device even when the Legion laptop is off.

## Goal

Use the old OPPO A31 as an always-on lightweight VECTOR node in the room. Use Cloudflare as the secure public relay, queue, and secret boundary. Use the Legion only for heavy work when it is online.

## Recommended Architecture

```text
Daily phone / browser / any device
  -> Cloudflare Pages or simple client UI
  -> Cloudflare Worker secure API
  -> Cloudflare D1/KV command queue and state
  -> OPPO A31 Termux lightweight node
  -> Legion VECTOR heavy node when online
```

## What Runs Where

### Cloudflare

- Public HTTPS API for commands and results.
- Authentication for every client and node request.
- D1 or KV queue for pending commands.
- Worker Secrets for AI provider keys needed by the 24/7 assistant path.
- Optional Pages-hosted web UI or PWA.

### OPPO A31 Termux Node

- Always-on lightweight executor.
- Polls Cloudflare for commands.
- Sends Wake-on-LAN on the local network when a command requires the Legion and the Legion is asleep.
- Handles everyday API-backed work:
  - chat/question answering
  - notes and reminders
  - summaries and drafts
  - status checks
  - notifications
- Defers heavy work to Legion when needed.
- Does not need to run heavy local models.

### Legion Laptop

- Full VECTOR brain/heavy executor when online.
- Drains heavy commands from Cloudflare after it wakes and VECTOR starts/resumes.
- Keeps laptop-only secrets in the laptop `.env`.
- Handles:
  - PC control
  - local files/apps
  - GPU/local model work
  - browser automation
  - heavyweight multi-agent jobs

## Secret Handling

Never put provider API keys in frontend code.

Use this split:

| Secret type | Where it should live |
|-------------|----------------------|
| Frontend public config | Cloudflare Pages public env only if non-secret |
| VECTOR client auth token | Cloudflare Worker Secret or generated device token |
| AI keys needed for 24/7 lightweight assistant | Cloudflare Worker Secrets |
| Termux node token | `~/.vector/phone_config.env` on OPPO |
| Laptop-only keys | laptop `.env` only |
| Provider keys not needed 24/7 | laptop `.env` only |

Do not copy the full laptop `.env` to the phone or to frontend hosting.

## Cloudflare Worker Required Routes

Minimum routes:

- `GET /health`
- `GET /status`
- `POST /commands`
- `GET /commands/:id`
- `POST /nodes/:node_id/poll`
- `POST /commands/:id/result`
- `POST /heartbeat`
- `POST /nodes/legion-heavy-node/wake` or equivalent command type

Implemented route shape in `api/src/router.ts`:

- `POST /command` and `POST /commands` submit commands.
- `POST /nodes/:node_id/poll` lets OPPO/Legion nodes claim targeted commands.
- `POST /commands/:id/result` stores command results.
- `GET /command/:id` and `GET /commands/:id` read status.

All routes except `GET /health` should require auth.

## Command State Model

Suggested command states:

- `queued`
- `assigned`
- `running`
- `done`
- `failed`
- `deferred`

Suggested command capability labels:

- `lightweight`
- `requires_legion`
- `requires_termux`
- `cloud_only`

Suggested node states:

- `online`
- `asleep`
- `offline`
- `unknown`

## Heavy Task Flow From Daily Phone

The OnePlus Nord CE2 Lite or any other daily-use device should submit commands to Cloudflare. It should not talk directly to the Legion or hold provider API keys.

```text
OnePlus submits heavy command
  -> Worker stores command as requires_legion
  -> OPPO Termux sees Legion is not online
  -> OPPO sends Wake-on-LAN on local WiFi/LAN
  -> command remains queued/deferred
  -> Legion wakes, VECTOR resumes, heartbeat starts
  -> Legion drains command from Worker
  -> permission gateway approves/blocks/runs
  -> result is posted back to Worker
  -> OnePlus reads result
```

This requires Wake-on-LAN support in BIOS/UEFI, Windows network adapter settings, and the local network. It works for sleep more reliably than full shutdown or hibernate.

Current Legion wake config discovered from Windows:

```env
LEGION_NODE_ID=legion-heavy-node
LEGION_WAKE_BROADCAST=10.208.79.255
LEGION_WIFI_MAC=14-B5-CD-3C-EC-99
LEGION_ETHERNET_MAC=E8-97-44-2E-A9-3C
LEGION_WAKE_PORT=9
```

Software primitive now exists:

- `core/control/wake_on_lan.py` builds/sends Wake-on-LAN magic packets.
- `core/control/legion_wake.py` reads the configured Legion MAC/broadcast and sends the packet.

WiFi wake can be attempted with the current hardware. Ethernet is still more reliable if available later.

## Why Not Vercel + Render First

Vercel is good for frontend apps, but it does not solve the always-on command queue by itself.

Render is useful for a Python backend, but the free web service tier can spin down when idle. Use Render only if VECTOR needs a paid always-on Python service or a workload that cannot fit Cloudflare Workers.

Cloudflare-first is simpler for this project because the repo is already moving toward Workers, D1, KV, and Worker Secrets.

## Implementation Checklist

1. Confirm the Cloudflare Worker project path and bindings.
2. Add D1/KV schema for command queue and node heartbeat.
3. Add Worker auth middleware.
4. Add command submit, poll, result, and status routes.
5. Add Worker tests for auth, queue, heartbeat, and degraded bindings.
6. Add Termux polling loop. Basic loop exists in `phone_node/ambient_server.py`.
7. Add lightweight Termux task router.
8. Add Legion heavy-node polling.
9. Add clear setup docs for Worker Secrets.
10. Add Wake-on-LAN support for sleep-to-heavy-task routing.
11. Add end-to-end smoke test:

```text
phone/browser submits command
  -> Worker stores command
  -> Termux polls and executes
  -> Worker stores result
  -> phone/browser reads result
```

12. Add end-to-end heavy command smoke test:

```text
OnePlus/browser submits requires_legion command
  -> Termux sends wake request if Legion is asleep
  -> Legion heartbeat resumes
  -> Legion executes command through permission gateway
  -> Worker stores result
```
