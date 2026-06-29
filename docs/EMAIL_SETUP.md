# VECTOR Email — Setup & Future Work

> Decision (2026-06-29): **No custom domain for now → use Gmail.** The Cloudflare
> `vector-email` Worker (dedicated domain inbox) is **deferred**, not deleted.
> This doc records how Gmail connects today and what to do later for the cloud inbox.

---

## The two email paths (and which one applies)

| Path | What it is | Needs | Status |
|---|---|---|---|
| **A — Gmail** (✅ use this) | VECTOR reads/triages/sends via your existing `arghyadeepdeb020703@gmail.com` through the Gmail API + the Python `EmailAgent` | Google OAuth (free, no domain) | Code ready; **needs one-time owner OAuth** (below) |
| **B — Cloudflare `vector-email`** (⏸ deferred) | A dedicated 24/7 inbox VECTOR *owns* on a domain you control (`vector@yourdomain.com`), serverless | A **registered domain** on Cloudflare + Email Routing + Access | Deferred — no domain yet |

You can't use a `@gmail.com` address with Path B: Cloudflare Email Routing needs a
domain whose **MX records you control**, and Google owns `gmail.com`. So Path B
requires buying a domain. Until then, Path A covers everything.

---

## Path A — connect Gmail (do this when ready; one-time)

Code is in place (`districts/communications/email_intelligence.py::_get_gmail_service`
reads an authorized-user token; `core/integrations/gmail_auth.py` runs the OAuth flow).
Step 1 below is **already done** (library installed + pinned). Only steps 2–3 remain,
and they need your Google account so they can't be done from code:

1. ✅ **DONE — OAuth library installed** (`google-auth-oauthlib==1.4.0`, pinned in `requirements.txt`).
2. **Create an OAuth client (Google Cloud Console):**
   - New project → enable the **Gmail API**.
   - OAuth consent screen → **External** → add `arghyadeepdeb020703@gmail.com` as a *test user*.
   - Credentials → **OAuth client ID** → type **Desktop app** → download the JSON.
   - Save it as `~/.vector/google_credentials.json` (i.e. `C:\Users\Arghyadeep\.vector\google_credentials.json`).
3. **Run the auth flow** (opens a browser once, you approve, token is saved):
   ```
   python -m core.integrations.gmail_auth
   ```
   → writes `~/.vector/gmail_token.json`. After this, VECTOR reads + (gated) sends your Gmail.

**Scopes requested:** `gmail.modify` (read + mark-read/label) + `gmail.send` (outbound,
which VECTOR only does through the permission gateway). Narrow to read-only in
`core/integrations/gmail_auth.py::SCOPES` if you prefer VECTOR never sends.

**Verify it's connected:**
```
python -c "from core.integrations.gmail_auth import is_connected; print(is_connected())"
```

### Current Gmail wiring status (2026-06-29) — ✅ CONNECTED & LIVE
- `googleapiclient` / `google.oauth2` installed ✅
- Read path present (`fetch_recent_threads`, `extract_intelligence`) ✅
- Auth helper `core/integrations/gmail_auth.py` built ✅
- `google-auth-oauthlib==1.4.0` installed + pinned ✅
- From-address uses `CONFIG["owner_email"]` (default `arghyadeepdeb020703@gmail.com`, override `VECTOR_OWNER_EMAIL`) ✅
- `~/.vector/google_credentials.json` (Desktop OAuth client) **placed** ✅
- `~/.vector/gmail_token.json` **created via OAuth consent** ✅ — scopes `gmail.modify` + `gmail.send`
- **End-to-end verified 2026-06-29:** `EmailIntelligence().fetch_recent_threads()` returned real inbox threads. VECTOR reads Gmail; sending is permission-gated (`EmailAgent.send_reply` → RED `send_email`).

**To re-authorize / switch account:** delete `~/.vector/gmail_token.json` and re-run `python -m core.integrations.gmail_auth`.

---

## Bridge status (cloud inbox ↔ brain) — `plans/cloud-inbox-brain-bridge.md`

Built so that *if* you ever deploy Path B, it actually feeds VECTOR's brain instead
of being an isolated webmail app:
- **Phase 1 (ingress)** — DONE: `core/loop/handlers/email_received.py` (HMAC fail-closed, injection-scanned, → episodic memory). Off unless `VECTOR_EMAIL_BRIDGE=1`.
- **Phase 2 (gated send)** — DONE: `EmailAgent.send_reply()` routes through the permission gateway (RED `send_email`), fail-closed, injectable transport.
- **Phase 3 (TS Worker hook + `/api/v1/agent/send`)** — deferred (only needed at deploy).
- Tests: `tests/test_email_bridge.py` (14, green).

These Phase 1–2 pieces also benefit **Path A** — Gmail events can be routed through
the same ingress handler / gated send.

---

## Path B — future: deploy the Cloudflare `vector-email` Worker

Revisit **only if you buy a domain.** When you do, in order:

1. Register a domain and add it to your Cloudflare account (Cloudflare Registrar is at-cost).
2. **Email Routing** on that domain → catch-all rule forwarding to the `vector-email` Worker + verify MX records.
3. Enable **Workers AI** and the **Email Service** (`send_email` binding).
4. **Cloudflare Access (Zero Trust)** → create an Access app on the Worker → copy `POLICY_AUD` + `TEAM_DOMAIN`.
5. Edit `cloud/email/wrangler.jsonc`: replace `DOMAINS="example.com"` with your domain.
6. `wrangler r2 bucket create vector-email`
7. `wrangler secret put POLICY_AUD` / `TEAM_DOMAIN` / `EMAIL_BRIDGE_SECRET` (the last on both Workers + local `.env`).
8. `cd cloud/email && wrangler deploy`.
9. Then have VECTOR's Phase 3 built + the bridge enabled (`VECTOR_EMAIL_BRIDGE=1`).

Already done so this is a clean flip later: npm audit on `cloud/email` (27→3 dev-only
advisories), typecheck green, the absorbed Python port + 13 MCP tools, and bridge Phases 1–2.
The live `vector-api` Worker (`VECTOR_BRAIN_URL`) is **separate and already deployed** —
this is only about the email Worker.

---

## TL;DR
- **Now:** when you want VECTOR on email, do Path A steps 1–3 (free, ~10 min). No domain needed.
- **Later (optional):** buy a domain → Path B for a dedicated 24/7 VECTOR-owned inbox.
