# VECTOR — Cowork Session Handoff (2026-07-28)

Written at the end of a Cowork (desktop Claude, computer-use) session. Picks up
after `SONNET_HANDOFF.md` (2026-07-22) — that file's own priorities (per-district
output polish, eval re-runs) are still open and untouched this session; this file
covers what changed *since* then. Read `KNOWN_ISSUES.md` issue **#34** for the full
technical writeup of the main feature built this session.

## What this session built: WebAuthn/passkey login (Issue #34)

Replaces having to paste `VECTOR_API_KEY` into a browser URL/console for
interactive use — a real key leak into chat earlier this session (now rotated) is
what prompted this. A passkey (Windows Hello / fingerprint) now works as an
alternative credential alongside the static key, never replacing it.

**New/changed files:**
- `core/api/webauthn_store.py` — flat-JSON credential store (`~/.vector_ca/auth/webauthn_credentials.json`)
- `core/api/routers/webauthn_auth.py` — `/auth/webauthn/{register,login}/{options,verify}` + `/status`
- `core/api/middleware.py` — accepts a passkey-issued JWT (`webauthn_session` type) as an
  alternative to the static key; `login/verify` now also sets the `vector_key` cookie
  server-side (mirrors the existing `?key=` cookie flow) so a browser that just logged
  in via passkey can immediately load `/hud/` on the next navigation
- `core/api/app.py` — registers the router + a new **public** `GET /login` route
- `frontend/login.html` — **new, minimal public page**, the fix for a bootstrap gap
  (see below)
- `frontend/js/webauthn.js` — `window.VECTORAuth.{isEnrolled,register,login,getSessionToken,clearSession}`,
  wired into `VECTOR.html` / `VECTOR.prod.html`
- `requirements.txt` — added `webauthn==2.5.2`
- `tests/backend/test_webauthn_auth.py` (3/3 passing — real ES256 crypto round-trip
  via a simulated software authenticator) and
  `tests/backend/test_webauthn_middleware_integration.py` (7/7 passing, incl. a
  type-confusion defense test)

**The bootstrap gap that got fixed:** `/hud/` (the real HUD, all its JS included) is
*deliberately* behind the auth wall — that's original, correct design, not something
this session changed. But that meant a browser with **no** key had no way to even
reach a "sign in with passkey" button. `frontend/login.html` + the public `GET /login`
route fixes this: it's a tiny standalone page (no VECTOR data, no district output)
that offers **only** the passkey LOGIN ceremony, never registration. That split is
deliberate and load-bearing for security: `/auth/webauthn/login/*` is safe to expose
publicly because it can only ever succeed against a credential someone already
enrolled from localhost with the key in hand (see the router's own docstring).
Registration correctly still requires the current key — do not "fix" that; it's not
a bug.

**Verified working, live, right now:**
- `GET /health` → `{"status":"ok","checks":{"ollama":"ok","sqlite":"ok"},...}`
- `GET /login` → loads publicly, correctly shows "No passkey enrolled yet"
- `GET /auth/webauthn/status` → `{"enrolled":false,"count":0,...}`
- `GET /keys/status` still correctly 401s unauthenticated (no auth regression)
- API restarted clean on the new code (`Application startup complete`, no import
  errors — confirms `webauthn` package is actually installed on this machine)

**Not done yet — the one remaining step:**
No passkey is enrolled. To enroll the first one: open the existing bookmarked HUD
URL (`http://localhost:8000/hud/?key=...`) once, then run `VECTORAuth.register()`
in the browser console — this will prompt a real Windows Hello / fingerprint
ceremony. After that, every future login can go through `/login` with no key at
all. **I (the agent) deliberately did not do this myself** — it requires the
owner's existing API key, which should not be typed/pasted by an agent per this
session's own security posture. There's also no in-HUD button for this yet, only
the console call — a small future nicety.

**Constraint to remember:** WebAuthn only works in a secure context — `https://`
or literally `http://localhost`. It will NOT work from a phone hitting the LAN-IP
URL over plain HTTP. That's the reason the owner asked about a Cloudflare Tunnel +
real TLS next (see below) — this is the actual blocker, not a VECTOR bug.

## Repo cleanup done this session

Moved **171 files (~17MB)** from the repo root into `_cleanup_trash_2026-07-28/`
— NOT permanently deleted, just relocated, so it's fully reversible. Delete that
folder yourself whenever you're confident (an agent will not permanently delete
files as a matter of policy). Contents: Python/pytest cache dirs, `test_tmp/`,
the empty `dickens/` dir, all 16 screenshots + ~85 paired `.bat`+`.log` files from
a July 21–23 Instagram-ADB-automation debugging marathon, and stray eval-run
byproducts not referenced anywhere. A subagent grep-verified nothing in
`core/`, `districts/`, `frontend/`, `tests/`, or the specs references any of it.

**Deliberately left alone** (owner said "not sure" / didn't confirm):
- `ponytail/` (root) — looks like a vendored external agent-tooling template
  (`.agents/`, `.claude-plugin/`, `.cursor/`, etc. subfolders). Owner wasn't sure
  what it is. Don't touch until someone confirms its purpose.
- `graphify-out/` (root) — single `manifest.json`, one-time tool output, purpose
  unconfirmed.
- Everything cited by line number in `KNOWN_ISSUES.md` as evidence for a closed
  issue (e.g. `langsmith_eval_final.log`, `repro_final_fixes.log`,
  `install_watchdog3.log`) was **kept on purpose** — owner chose documentation
  value over decluttering for these.

## Other loose ends from this session (owner-side, not code)

- **Watchdog terminal-flash fix**: owner manually edited the `VECTOR-Watchdog`
  Task Scheduler entry (Program: `wscript.exe`, Arguments: quoted path to
  `scripts/watchdog_check_hidden.vbs`) — done, confirmed working.
- **`VECTOR_API_KEY` rotation**: the key was rotated earlier this session after
  being pasted into chat in plaintext once. Current value is in `.env` on the
  machine — never paste it into chat, a URL, or anywhere an agent can see it
  again. The static key still works for API/WS auth exactly as before; only the
  *browser* login path is meant to move to passkeys.
- **Hard technical wall hit repeatedly**: Windows UIPI blocks synthetic
  clicks/keystrokes to *elevated* windows — Task Scheduler and Task Manager on
  this machine both run elevated by default and are **not drivable by
  computer-use automation**, regardless of what access is granted. Console
  windows spawned by `.bat` scripts are NOT elevated and generally *are*
  drivable, but were flaky this session (had to fall back to closing them
  manually). If a future agent needs to manage Task Scheduler/Task Manager,
  don't retry automation — ask the owner to do the 2-click manual action.

## What's next (owner's stated direction, not started)

Owner asked about making the HUD reachable like a normal hosted web app instead
of only `localhost`/LAN. Answer given: the *brain* (Ollama, GPU inference,
hand-tracking, webcam/screen sensing) must stay on this machine — that's load-
bearing for the ₹0 rule, not a config choice. But the *view* can be made properly
reachable without violating that:
1. **Real TLS cert** — `run_vector.py` already reads `VECTOR_TLS_CERTFILE`/
   `VECTOR_TLS_KEYFILE` via `core/runtime/tls.py::uvicorn_ssl_kwargs()`; just
   needs a real cert wired in. Once on, WebAuthn works from any device, not
   just localhost.
2. **Cloudflare Tunnel** (`cloudflared`, free) pointed at port 8000 for a stable
   public HTTPS URL without router port-forwarding. Laptop still has to be on
   and VECTOR still has to be running — this doesn't move the brain anywhere,
   it just gives it a real front door.

Neither has been started. This is the next task if picking up where this
session left off.

## Quick verification checklist for whoever picks this up

```
GET http://localhost:8000/health                 -> {"status":"ok",...}
GET http://localhost:8000/login                   -> loads, shows enrollment state
GET http://localhost:8000/auth/webauthn/status     -> {"enrolled":false,"count":0,...}
GET http://localhost:8000/keys/status  (no auth)   -> 401 (must still fail unauthenticated)
```

Full pytest coverage for the new feature:
`pytest tests/backend/test_webauthn_auth.py tests/backend/test_webauthn_middleware_integration.py -v`
(10/10 passing as of this session, incl. real ES256 crypto and a type-confusion
defense test).
