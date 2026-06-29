# Cloudflare Worker — Local `wrangler dev` Verification Script

**Current status (2026-06-27):** `npm.cmd test` from `api/` now works from this Windows repo
path. The package script uses `api/scripts/run-vitest-no-space.mjs` to copy the
Worker test tree to a temporary space-free path when the real path contains
spaces, then runs Vitest there. Verified locally: 1 Worker smoke test file,
5/5 tests passed.

**Status of this doc:** originally satisfied a now-deleted source doc's item 6
("Add Worker tests using the repo's TypeScript/Cloudflare test setup, **or**
document and add a minimal local `wrangler dev` verification script") via the
explicitly-sanctioned lighter alternative — this manual script.

**Update (2026-06-23):** the real `@cloudflare/vitest-pool-workers` harness
described as future work below was actually built (`api/package.json`,
`api/vitest.config.ts`, `api/test/smoke.test.ts`) — see
`docs/repo_analysis/_MASTER_TODO.md` §3 item 6. It's real, correct scaffolding
and is now locally runnable through `npm test`. Direct Vitest execution is
still sensitive to the space in this checkout's path, so the package script
copies the API package to a temporary space-free path first. Verified locally
on 2026-06-27.

**What this verifies:** the command-queue flow end to end, against a
**local-only** emulated D1 + KV (never the real provisioned IDs in
`wrangler.toml` — `--local` / `--persist-to` keep everything on-disk in a
temp dir). Confirmed available in this environment: `wrangler 4.101.0`,
`node v24.15.0`. Not run as part of this session (starting a long-lived dev
server is an operator action, not something to leave running unattended) —
this is the script for whoever runs it next (owner or a future session with
explicit go-ahead).

## Setup

**Step 0 — create the local D1 schema first (REQUIRED).** The emulated local D1
starts empty; without this, steps 3–8 fail with
`D1_ERROR: no such table: command_queue`. Apply the schema to the local
(`--local`) database before starting the dev server:

```powershell
cd api
npx wrangler d1 execute vector-brain --local --persist-to ./.wrangler-local-state --file=schema.sql
```

`schema.sql` already includes the `target_node`/`result`/`error`/… columns, so a
fresh apply is all you need. `migrations/0002_command_node_results.sql` is only
for an *older* D1 created before those columns existed — applying it on top of a
fresh `schema.sql` errors with "duplicate column" (harmless, just skip it
locally). Then start the server:

```powershell
npx wrangler dev --local --persist-to=./.wrangler-local-state --port 8787
```

`--local` means D1/KV are emulated entirely on disk under
`./.wrangler-local-state` — the real `database_id`/KV `id` in `wrangler.toml`
are never contacted. Set a throwaway local secret first so auth tests have
something to check against:

```powershell
# In a SEPARATE terminal, with the dev server above still running:
$env:VECTOR_API_KEY = "local-dev-test-key"
```

(`wrangler dev --local` reads `.dev.vars` for secrets, or you can hardcode a
temporary value in `index.ts` for this local-only session — never commit a
real key.)

## 1. Public endpoints — no auth required

```powershell
curl http://127.0.0.1:8787/status
curl http://127.0.0.1:8787/health
```
Expect: `200`, `{"status":"online",...}` / `{"status":"healthy"}`.

## 2. Auth enforcement — missing/wrong Bearer token

```powershell
curl -i http://127.0.0.1:8787/heartbeat -X POST
# Expect: 401 {"error":"unauthorized"}

curl -i http://127.0.0.1:8787/heartbeat -X POST -H "Authorization: Bearer wrong-key"
# Expect: 403 {"error":"forbidden"}
```

## 3. Submit a command (queue)

```powershell
curl -i http://127.0.0.1:8787/command -X POST `
  -H "Authorization: Bearer local-dev-test-key" `
  -H "Content-Type: application/json" `
  -d '{"type":"search_web","params":{"query":"test"},"target_node":"legion-heavy-node"}'
# Expect: 200 {"ok":true,"command_id":"...","target_node":"legion-heavy-node","status":"queued"}
```
Save the returned `command_id` for the next steps.

## 4. Heartbeat drains the queued command

```powershell
curl -i http://127.0.0.1:8787/heartbeat -X POST `
  -H "Authorization: Bearer local-dev-test-key" `
  -H "Content-Type: application/json" `
  -d '{"node_id":"legion-heavy-node"}'
# Expect: 200 {"ok":true,"received_at":"...","commands":[{"id":"<command_id>","type":"search_web",...}]}
```
Confirm the command moved to `status='delivered'`:
```powershell
curl http://127.0.0.1:8787/command/<command_id> -H "Authorization: Bearer local-dev-test-key"
# Expect: {"found":true,"status":"delivered",...}
```

## 5. Node-targeted poll (Termux/Legion-specific drain)

```powershell
curl -i http://127.0.0.1:8787/command -X POST `
  -H "Authorization: Bearer local-dev-test-key" `
  -H "Content-Type: application/json" `
  -d '{"type":"chat","params":{"text":"hi"},"target_node":"termux-room-node"}'

curl -i http://127.0.0.1:8787/nodes/termux-room-node/poll -X POST `
  -H "Authorization: Bearer local-dev-test-key" `
  -H "Content-Type: application/json" `
  -d '{}'
# Expect: the chat command appears here, NOT in a legion-heavy-node heartbeat —
# confirms target_node routing keeps node queues isolated.
```

## 6. Post a result, confirm status transition

```powershell
curl -i http://127.0.0.1:8787/commands/<command_id>/result -X POST `
  -H "Authorization: Bearer local-dev-test-key" `
  -H "Content-Type: application/json" `
  -d '{"status":"done","result":{"answer":"42"}}'

curl http://127.0.0.1:8787/command/<command_id> -H "Authorization: Bearer local-dev-test-key"
# Expect: {"found":true,"status":"done","result":"{\"answer\":\"42\"}",...}
```

## 7. Rate limiting (10 req/min per IP)

```powershell
1..12 | ForEach-Object {
  curl -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8787/status
}
# /status is unauthenticated AND unrated (only non-public paths hit checkRateLimit
# in index.ts) — re-run against an authenticated path (e.g. /heartbeat) to see
# the 11th+ request return 429.
```

## 8. Degraded-bindings behavior (Supabase unconfigured)

With no `SUPABASE_URL`/`SUPABASE_KEY` set in `.dev.vars`:
```powershell
curl http://127.0.0.1:8787/memory/recent -H "Authorization: Bearer local-dev-test-key"
# Expect: {"events":[],"count":0,"source":"unconfigured"} — graceful, not a 500.
```

## Cleanup

```powershell
# Ctrl+C the dev server, then:
Remove-Item -Recurse -Force ./.wrangler-local-state
```

## Automated Harness

`@cloudflare/vitest-pool-workers` is built: `api/package.json`,
`api/vitest.config.ts` (isolated local-only Miniflare D1/KV bindings,
deliberately not the real provisioned IDs in `wrangler.toml`),
`api/test/smoke.test.ts`. `npm install` succeeded.

Run it with:

```powershell
cd api
npm.cmd test
```

Direct Vitest execution is still sensitive to this checkout's space-containing
path. The `npm test` wrapper copies the API package to a temporary space-free
path before invoking Vitest. Verified locally on 2026-06-27:
`test/smoke.test.ts` passed 5/5 tests.

## Cloud Email Worker Verification

Separate from the API Worker above, `cloud/email` is the Agentic Inbox
Cloudflare Worker app (`vector-email`) with Durable Objects, R2, Email Routing,
Workers AI, and Cloudflare Access enforcement.

Verified locally on 2026-06-27:

```powershell
cd cloud/email
npm.cmd ci
npm.cmd run typecheck
```

Result: dependency install completed, `wrangler types`, `react-router typegen`,
and `tsc -b` all passed.

Security caveat from the same run: `npm.cmd audit --json` reports 27 known
advisories in this dependency tree (2 low, 9 moderate, 16 high, 0 critical).
Notable direct vulnerable packages include `@cloudflare/vite-plugin`,
`@react-router/dev`, `dompurify`, `drizzle-orm`, `hono`, `react-router`,
`vite`, and `wrangler`. I did not run `npm audit fix`; dependency upgrades
need a separate compatibility pass.

Not verified here: `npm run deploy`. That command would build and deploy the
real Cloudflare email app and may provision or mutate account resources. A real
production deploy also requires a Cloudflare account/domain, Email Routing,
R2 bucket `vector-email`, Workers AI, Cloudflare Access, and Worker secrets
`POLICY_AUD` plus `TEAM_DOMAIN`. Treat deploy verification as owner-gated until
those account settings are explicitly available and authorized.

**Update (2026-06-24):** the Worker is now actually deployed
(`https://vector-api.arghyadeepdeb020703.workers.dev`, see
`docs/repo_analysis/OWNER_ACTIONS_NEEDED.md` §5), and was verified
directly against the **real** production endpoint with live curl
requests — auth fails closed, the command queue genuinely works (after
fixing a missing migration), Supabase reads work (after fixing two
malformed secret names). So this doc's local-only steps are no longer
the *only* way to verify the Worker — they're the right tool for testing
changes safely **before** redeploying, without touching the real D1/KV.
