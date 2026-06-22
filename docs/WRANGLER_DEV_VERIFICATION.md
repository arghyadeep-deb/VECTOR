# Cloudflare Worker — Local `wrangler dev` Verification Script

**Status of this doc:** satisfies `docs/CLAUDE_CODE_REMAINING_ISSUES.md` item 6
("Add Worker tests using the repo's TypeScript/Cloudflare test setup, **or**
document and add a minimal local `wrangler dev` verification script") via the
explicitly-sanctioned lighter alternative. There is currently no
`package.json`/test runner in `api/` at all — setting up a full
`@cloudflare/vitest-pool-workers` harness from scratch is real, separate work
(estimate: 1-2 sessions) and was not started this pass, since it's a bigger
investment than the rest of this checklist and the real D1/KV IDs already
provisioned in `wrangler.toml` make it worth doing deliberately rather than
as a drive-by addition.

**What this verifies:** the command-queue flow end to end, against a
**local-only** emulated D1 + KV (never the real provisioned IDs in
`wrangler.toml` — `--local` / `--persist-to` keep everything on-disk in a
temp dir). Confirmed available in this environment: `wrangler 4.101.0`,
`node v24.15.0`. Not run as part of this session (starting a long-lived dev
server is an operator action, not something to leave running unattended) —
this is the script for whoever runs it next (owner or a future session with
explicit go-ahead).

## Setup

```powershell
cd api
# No package.json exists yet — wrangler can still run via npx without one,
# but for repeated local dev a minimal package.json is worth adding:
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

## If a full automated harness is wanted later

`@cloudflare/vitest-pool-workers` (Cloudflare's official, currently-recommended
approach — runs Worker code in the real `workerd` runtime, not a Node shim) is
the right tool: `npm install -D vitest @cloudflare/vitest-pool-workers`,
configure `vitest.config.ts` with the pool, write tests against `SELF.fetch()`
with D1/KV bindings provided by `env` in the test context. This doc's manual
steps map directly to what those tests would assert — worth doing as its own
scoped session, not bundled into this pass.
