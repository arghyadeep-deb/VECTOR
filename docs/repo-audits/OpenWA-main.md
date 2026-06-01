# Repo Audit: OpenWA-main
> Audited: 2026-06-01 | Branch: production-hardening-complete
> Auditor: Claude Code (automated read + live test execution)

---

## 5-Line Summary

OpenWA is a TypeScript/NestJS WhatsApp API Gateway (v0.1.6, MIT) built on `whatsapp-web.js` (Puppeteer reverse-engineering). It has 19 backend modules covering multi-session QR auth, send/receive, groups, contacts, media, reactions, labels, channels, catalog, webhooks, plugins, audit logging, and a full React dashboard. The absorption claim of 50 tests passes: `50 passed in 0.68s` — confirmed live. VECTOR absorbed 3 narrowly-scoped Python utilities (HMAC signing, bulk sender, WA Business API extensions) — all three import cleanly and work. What VECTOR does NOT have from OpenWA: the full session lifecycle (QR login, real-time receive loop, message persistence, group management, contact management) — that is still a gap if WhatsApp-as-a-channel is needed beyond fire-and-forget outbound. Verdict: **SAFE TO DELETE** — the 3 absorbed pieces are real Python code; the un-absorbed TypeScript core (Puppeteer, NestJS, React) cannot and should not be ported.

---

## Section 1: Repo Reality

**What OpenWA is:** A self-hosted WhatsApp API gateway. You run it as a Docker container, scan a QR code with your phone, and then control WhatsApp via REST endpoints. Built on `whatsapp-web.js` (Puppeteer — unofficial WhatsApp Web scraping). License: MIT.

**Stack:** TypeScript 5.x · NestJS 11.x · TypeORM (SQLite / PostgreSQL) · React + Vite dashboard · Docker-native.

**Concrete feature inventory (19 NestJS modules):**

| Module | What it does |
|--------|-------------|
| `session/` | Multi-session lifecycle: create, QR auth, READY/DISCONNECTED states, auto-reconnect with exponential backoff, proxy per session, startup reset |
| `message/` | Send text + media (image/video/audio/document/sticker), reactions, forward, star, delete, reply, get history, message-batch entity |
| `group/` | Create group, add/remove participants, change subject/description, promote/demote admin, leave, get info |
| `contact/` | Fetch contacts, block/unblock, check WhatsApp number validity, profile picture |
| `webhook/` | Register webhooks, HMAC-SHA256 signed delivery, retry on 5xx, fan-out, event filtering |
| `channel/` | WhatsApp Channels (newsletter) — create, follow, send posts, list |
| `catalog/` | Product catalog — list products, query with pagination |
| `status/` | WhatsApp Status (Stories) — create text/image/video status |
| `label/` | Create/manage labels, assign to chats |
| `audit/` | Audit log of all API operations (who, what, when) |
| `auth/` | API key management, CIDR IP whitelisting, guards |
| `stats/` | Usage stats per session |
| `events/` | WebSocket gateway for real-time events (NestJS Gateway) |
| `infra/` | Backend-swap controller: SQLite ↔ PostgreSQL, local ↔ S3, memory ↔ Redis |
| `queue/` | Bull queue for async tasks |
| `plugins/` | Plugin system: pre/post hooks on message:sending, message:sent, message:failed, session lifecycle |
| `health/` | Kubernetes-ready health probes |
| `settings/` | Global gateway settings |
| `docker/` | traefik + compose configs for production |

**Engine layer:** A single adapter `whatsapp-web-js.adapter.ts` wraps `whatsapp-web.js` (Puppeteer). QR code generation via `qrcode`. `LocalAuth` for persistent browser session. The engine interface exposes: `sendTextMessage`, `sendMediaMessage`, `sendReaction`, `createGroup`, `getContacts`, `getGroups`, `sendChannelMessage`, `createStatus`, etc.

**Dashboard (React/Vite, 8 pages):** Sessions, Webhooks, API Keys, Infrastructure, Message Tester, Plugins, Logs, Login.

---

## Section 2: VECTOR Parity — Verified by Running

### Live test execution

```
$ python -m pytest tests/test_openwa_absorption.py -v
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-9.0.3
collected 50 items

tests\test_openwa_absorption.py ......................................... [100%]
..........

============================= 50 passed in 0.68s ==============================
```

**Claim verified: 50 tests, 50 passed.**

### Import smoke tests

```
WebhookSigner OK, sig starts: sha256=6edb7e533ff92
BulkSender OK: True
WA Business OK
```

All 3 absorbed modules import cleanly and execute.

---

### Parity matrix — feature by feature

| OpenWA Feature | VECTOR Coverage | Verdict |
|----------------|----------------|---------|
| HMAC-SHA256 webhook signing | `core/engine/webhook/hmac_signer.py` — `WebhookSigner.sign()`, `verify()`, constant-time compare, `signed_headers()` producing X-Signature-256 + X-Delivery-Id + X-Timestamp. `WebhookDelivery` with retry + backoff. Fan-out via `deliver_to_many()`. | ✅ real & working |
| Bulk messaging with rate limits | `vectorcode/src/channels/bulk_sender.py` — `BulkSender(channel)`, per-provider rate limits (WhatsApp 80 msg/s, Telegram 30, Slack 1, Discord 5), `dry_run`, `fail_fast`, `BulkResult` with `success_rate` + `elapsed_seconds`. | ✅ real & working |
| WhatsApp Business Cloud API | `vectorcode/src/channels/whatsapp_business.py` — templates (HSM), image/video/audio/document/sticker, reactions + remove, interactive buttons (≤3 cap), list picker, Channels/Newsletter API. Extends base `WhatsAppChannel`. | ✅ real & working |
| Session lifecycle (QR login) | None. VECTOR has no Puppeteer/browser layer. The base `WhatsAppChannel` (`vectorcode/src/channels/whatsapp.py`) is a Meta Cloud API wrapper — it requires a Business account + phone number ID. It cannot scan a QR code and run as a personal WhatsApp session. | ❌ missing |
| Real-time message receive loop | None. VECTOR cannot receive inbound WhatsApp messages. It can only send outbound via the Cloud API. | ❌ missing |
| Group management | None. No group create/add participant/admin logic in VECTOR. | ❌ missing |
| Contact management | None. No contact fetch/block/profile picture in VECTOR. | ❌ missing |
| Message history + persistence | None. VECTOR has no `Message` entity for WhatsApp conversations. | ❌ missing |
| WhatsApp Status (Stories) | None. | ❌ missing |
| Label management | None. | ❌ missing |
| Product Catalog API | None. | ❌ missing |
| Webhook registry (register + manage) | Partial. `core/engine/webhook/` handles signing and delivery, but there is no persistent webhook endpoint registry (no CRUD, no UI for registering URLs). | ⚠️ partial |
| Plugin/hook system | Partial. `vectorcode/src/guidance.py` has ContinueGate / AuthorityGate. No per-event lifecycle hooks equivalent to OpenWA's HookManager (message:sending → blocking modify → message:sent). | ⚠️ partial |
| Audit logging | `core/audit/` has `MerkleAuditChain` — cryptographic tamper-evident log. Functionally covers OpenWA's audit module, and is stronger. | ✅ real & working |
| Multi-session management | Not applicable. VECTOR is single-owner. | N/A |
| React dashboard (8 pages) | None. `dashboard/src/` is listed as not built in phase_status.md. | ❌ missing |
| Infrastructure backend swap | `core/collections/` handles pluggable storage (local + S3). DB: SQLite → Supabase → Turso chain in config. | ⚠️ partial |

### WhatsApp channel capability gap analysis

This is the most important gap. VECTOR has two distinct WhatsApp modes:

1. **Meta Business Cloud API** (`WhatsAppChannel` + `WhatsAppBusinessChannel`) — requires a verified Meta Business account + phone number registered in Meta Business Manager. Can send templates, media, interactive messages. Cannot receive messages without setting up a Meta webhook endpoint. Requires a paid phone number registration.

2. **Missing: personal QR session** — OpenWA uses `whatsapp-web.js` (Puppeteer reverse-engineering of WhatsApp Web). This is what enables scanning a QR code with a personal phone, receiving all messages in real time, managing groups, viewing contacts, etc. VECTOR has zero equivalent. **This gap matters** if the intent is to use a personal WhatsApp number as a comms channel (the more common use case for an autonomous agent talking to personal contacts).

The absorbed pieces cover the "send a templated message to a customer" use case, not the "act as me on WhatsApp" use case.

---

## Section 3: Frontend Panel Spec

OpenWA ships a complete React/Vite dashboard. Pages:

| Page | Content |
|------|---------|
| Sessions | List active WhatsApp sessions, QR code display, connect/disconnect, status badges |
| Webhooks | Register/edit/delete webhook URLs, event type filters, HMAC secret, delivery log |
| API Keys | Create/revoke API keys, CIDR whitelist per key |
| Infrastructure | Live toggle: SQLite ↔ PostgreSQL, local ↔ S3, memory ↔ Redis |
| Message Tester | Send test messages to any chat ID from the browser |
| Plugins | List installed plugins, enable/disable, plugin config forms |
| Logs | Audit log stream |
| Login | API key authentication gate |

**Build-now value for VECTOR:** Low. VECTOR does not run WhatsApp sessions (QR), so the Sessions + Message Tester pages have no backend to connect to. The Webhooks page is worth adapting if a webhook registry is built. The Infrastructure toggle maps loosely to VECTOR's config system.

If the VECTOR Next.js dashboard is eventually built (currently `dashboard/src` is missing), the Webhooks page (register URL, HMAC secret, event types) is the one panel worth porting as a React component. Estimated: 1 day of work.

---

## Section 4: Verdict

### Absorption fidelity
The 50-test claim is **accurate and confirmed**. The 3 absorbed Python modules are real, non-trivial implementations:
- `hmac_signer.py` — 198 lines, production-quality, constant-time verify, retry delivery
- `bulk_sender.py` — 168 lines, per-provider rate limits, fail_fast, elapsed timing
- `whatsapp_business.py` — 311 lines, 7 message types, graceful no-token degradation

### What was correctly skipped
The core of OpenWA — `whatsapp-web.js` Puppeteer engine, NestJS DI framework, TypeORM session persistence, React dashboard, multi-session management — is TypeScript-only, depends on unofficial WhatsApp Web reverse-engineering, and would violate WhatsApp ToS in a production autonomous agent. Correct decision not to port.

### Outstanding gap (non-blocking for v1)
If VECTOR ever needs personal WhatsApp (receive messages, act on personal contacts, group management), the correct path is **not** to absorb OpenWA's Puppeteer engine — it is to integrate `wa-automate` Python bindings or run OpenWA as a sidecar service and consume its REST API. This is deferred as post-v1.

### Delete-readiness

**SAFE TO DELETE.**

No VECTOR Python file depends on anything in `GitHub/OpenWA-main/`. The 3 absorbed modules are fully self-contained in VECTOR. The TypeScript source has no Python equivalent worth porting. The personal-session gap is a known architecture decision, not an absorption miss.

| Condition | Met? |
|-----------|------|
| All absorbed code runs without reference to source repo | ✅ |
| 50 tests pass with zero source repo files loaded | ✅ |
| No VECTOR import references `OpenWA-main/` path | ✅ |
| Un-absorbed features intentionally skipped (ToS + TypeScript) | ✅ |
| Gap documented (personal QR session) | ✅ |

**Action:** `Remove-Item -Recurse -Force "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\OpenWA-main"` when ready to clean up disk space.
