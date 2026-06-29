# Plan — Cloud Inbox ↔ VECTOR Brain Bridge

> Status: SPEC (not started). Planned by Opus 2026-06-29; execute with Sonnet/Codex, TDD.
> One-line goal: turn the standalone `vector-email` Cloudflare Worker into a real 24/7
> autonomous channel that feeds VECTOR's brain (episodic memory + governor + permission
> gateway), instead of an isolated webmail app — so deploying it actually makes VECTOR
> more capable, not just adds infra.

## Why this exists (the problem)

The `cloud/email/` Worker ("Agentic Inbox", `vector-email`) stores every email in its own
**isolated Durable Object SQLite** (`MailboxDO`). Nothing flows into VECTOR's mind. VECTOR's
intelligence lives in local SQLCipher episodic memory + the live `vector-api` Worker's D1.
So deploying `vector-email` as-is = a separate AI webmail product sitting *next to* VECTOR,
not part of it. The email capability that IS wired into VECTOR's runtime is the **Python
port** (`districts/communications/email_agent.py` — 13 tools on `EpisodicMemory`, used by
the governor, permission gateway, and MCP tools). This plan builds the missing link.

## What already exists (verified, file:line — reuse, don't rebuild)

| Seam | Where | Role in the bridge |
|---|---|---|
| Live brain command queue | `api/src/router.ts:84` `POST /command`, `:86` `/commands/{id}/result`, `:93` `/nodes/{id}/poll`; Bearer auth (verified live: protected routes 401 w/o key, 200 w/ key) | **Ingress transport** — cloud inbox enqueues `email_received` here |
| Local command drain | `core/loop/autonomous_loop.py:1559` `command_poll_loop` (~3s) → `_command_poll_tick()` | Pulls queued email events into the local brain within ~3s |
| HMAC webhook signer | `core/engine/webhook/hmac_signer.py` (absorbed from OpenWA) | Sign/verify the inbox→brain payload (constant-time) |
| Python EmailAgent | `districts/communications/email_agent.py` — `list_emails`/`get_email`/`search_emails`/`draft_reply`/`draft_email` on `EpisodicMemory` | Triage + draft on VECTOR's own memory |
| Email intelligence district | `districts/communications/email_intelligence.py` (238 LOC) | Classify/prioritize incoming mail |
| Permission gateway | `core/loop/permission_gateway.py` (RED list in `core/config.py`, Pushover owner approval) | **Gate outbound send** (outward action) |
| Cloud email Worker | `cloud/email/` (`vector-email`): `MailboxDO`, `EmailAgent`(DO), `EmailMCP`(DO), R2 `BUCKET`, Workers AI, Email Routing | The 24/7 inbox endpoint; gains a forward-to-brain hook + a guarded send endpoint |

## Goal / Non-goals

**Goal:** every email the cloud inbox receives lands in VECTOR's episodic memory and is
triaged by the governor within seconds; any reply VECTOR composes is sent **only** after
permission-gateway approval. Survives Legion being off (cloud-side buffers; local drains
when up).

**Non-goals:** replacing Gmail (the Python port already reads it); real-time per-token
streaming; multi-user mailboxes; rebuilding the webmail UI.

## Architecture — data flow

### Ingress (inbox → brain)
1. Email arrives → Cloudflare Email Routing → `vector-email` Worker (`MailboxDO`), stored + attachments to R2 (unchanged upstream behavior).
2. **NEW:** a post-store hook in `MailboxDO` POSTs a compact, HMAC-signed `email_received` event to `VECTOR_BRAIN_URL/command` (body = message id, from, subject, snippet, mailbox, R2 keys — **not** full body; brain fetches on demand). Bearer = `VECTOR_API_KEY`; `X-Signature-256` = HMAC over body with a shared `EMAIL_BRIDGE_SECRET`.
3. If the brain is unreachable, the event is appended to a Durable Object **outbox** and retried with backoff (so Legion-off doesn't lose mail).
4. Local `command_poll_loop` drains the `email_received` command → handler verifies HMAC → writes an `episodic_memory` row (`event_type="email_received"`, tags `["email","inbox"]`, source `"cloud_inbox"`) → routes to `email_intelligence` for classify/prioritize → governor decides (reply / file / ignore) like any other event.

### Egress (brain → send), permission-gated
5. When VECTOR composes a reply, `EmailAgent.draft_reply()` produces it locally.
6. Sending is an **outward action** → `permission_gateway` RED/YELLOW: owner gets a Pushover with from/subject/preview; sends **only** on approval; **fail-closed** if the gateway is unreachable.
7. On approval, brain POSTs a signed `send_email` command to a **new authenticated** `vector-email` endpoint (`POST /api/v1/agent/send`, Bearer + HMAC), which uses the Worker's `send_email` binding. Result reported back via `/commands/{id}/result`.

## Security model (non-negotiable)
- Ingress: Bearer (`VECTOR_API_KEY`) **and** HMAC (`EMAIL_BRIDGE_SECRET`) — reuse `hmac_signer.py`. Reject on either failure.
- Egress send endpoint on the Worker: Bearer + HMAC too (never an open send relay).
- Outbound send always through `permission_gateway` (`"email_send"` added to `core/config.py` `permission.red`), fail-closed.
- Prompt-injection scan (`scan_text`) on incoming subject/body before any LLM triage (the inbox is attacker-controlled) — reuse the existing API-boundary scanner.
- Secrets: `EMAIL_BRIDGE_SECRET` via `wrangler secret put` on both Workers + local `.env`; never in `wrangler.jsonc`.

## Implementation tasks (TDD, each lands with tests)

**Phase 1 — Ingress (no deploy needed to test)**
- T1.1 Local handler `core/loop/handlers/email_received.py`: verify HMAC → store episodic → route to `email_intelligence`. Tests: signed payload stored + classified; bad signature rejected; malformed payload no-crash.
- T1.2 Register `email_received` in `_command_poll_tick` dispatch. Test: queued command reaches handler.
- T1.3 Prompt-injection scan on incoming fields; CRITICAL → quarantine (store, flag, no auto-LLM). Test.

**Phase 2 — Egress (gated send)**
- T2.1 `EmailAgent.send_reply()` wrapper that calls `permission_gateway` first (RED `"email_send"`), fail-closed. Tests: approved→send call made; denied→no send; gateway-down→no send.
- T2.2 Add `"email_send"` to `core/config.py` `permission.red`; RED notification shows from/subject/preview. Test.

**Phase 3 — Worker-side (TypeScript, tested via vitest harness `api/scripts/run-vitest-no-space.mjs`)**
- T3.1 `MailboxDO` post-store hook → signed POST to brain `/command`; DO outbox + retry on failure. Tests (Miniflare): hook fires; retry on 5xx; outbox drains.
- T3.2 `POST /api/v1/agent/send` on `vector-email`: Bearer+HMAC, uses `send_email` binding. Tests: unauth→401; bad HMAC→403; valid→send invoked.

**Phase 4 — Wiring + docs**
- T4.1 Config: `EMAIL_BRIDGE_SECRET`, `email_bridge_enabled` (default **False**) in `core/config.py`; bridge no-ops when off.
- T4.2 Update `cloud/email/wrangler.jsonc` (real `DOMAINS`, vars), `docs/repo_analysis/OWNER_ACTIONS_NEEDED.md`, `_MASTER_TODO.md`.

## Owner-gated prerequisites (can't be done from code — needed before deploy, not before building)
1. A real domain on Cloudflare (replaces `DOMAINS="example.com"`).
2. Email Routing enabled + catch-all rule → `vector-email` Worker + MX records.
3. Workers AI + `send_email` (Email Service) enabled.
4. Cloudflare Access (Zero Trust) app → `POLICY_AUD` + `TEAM_DOMAIN` secrets.
5. `wrangler secret put EMAIL_BRIDGE_SECRET` on both Workers (+ local `.env`), and confirm the API token has R2 + Workers + Email perms.

Phases 1–2 (the parts that make VECTOR smarter) are fully buildable + testable **now**,
locally, with zero owner infra. Phase 3 needs the Miniflare harness (already present).
Only the final deploy needs the 5 prerequisites above.

## Acceptance criteria
- A signed `email_received` event → an `episodic_memory` row + an `email_intelligence` classification, within one `command_poll_loop` cycle. (Phase 1, local test.)
- A reply send is **blocked** without owner approval and **fail-closed** if the gateway is unreachable. (Phase 2, local test.)
- Bad HMAC / missing Bearer rejected on both ingress and the send endpoint. (Phases 1 & 3.)
- `email_bridge_enabled=False` → entire bridge is a no-op (no behavior change for users who don't want the cloud inbox).

## Recommendation on sequencing
Build Phases 1–2 whenever (they're pure local upside and make the Python EmailAgent
brain-integrated regardless of the cloud worker). Do Phase 3 + deploy only once you have a
domain you want VECTOR to own an inbox on. Until then this plan sits ready, and `cloud/email`
stays as the clean reference it is.
