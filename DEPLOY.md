# VECTOR Deployment Runbook — Cloudflare-brain (no Fly, no card)

Architecture: **laptop brain (Ollama)** + **Cloudflare Worker** (unified relay:
command queue in D1, heartbeat in KV, memory reads from Supabase) + **memory mesh**
(local SQLite + Supabase + Turso, reconciled every 24h) + **phone ambient node**.

Fly.io is **not used** (it now requires a card). Everything below is free-tier.

> Fill in your own secret values where you see `<...>`. Never commit `.env`.

---

## Step 0 — VECTOR's own secrets (laptop)
```powershell
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python -c "import secrets; print('VECTOR_API_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('VECTOR_JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('MCP_KERNEL_SECRET=' + secrets.token_urlsafe(32))"
```
Put these 3 lines in `.env`, plus `PUSHOVER_TOKEN=<from pushover.net>` and
`PUSHOVER_USER=<your pushover user key>` (owner approval for RED actions —
HumanLayer was removed in favor of this).
Keep `VECTOR_API_KEY` handy — the **same value** is used by the laptop, the Worker, and the phone.

## Step 1 — Supabase (memory DB #1 + what the Worker reads)
1. Project already exists: `https://jgdzdwvxxaflpdzrgqut.supabase.co`.
2. Settings → API → copy the **service_role** key (not anon).
3. SQL Editor → paste `deploy/supabase_schema.sql` → Run (creates the 6 tables).
4. In `.env`:
   ```
   SUPABASE_URL=https://jgdzdwvxxaflpdzrgqut.supabase.co
   SUPABASE_KEY=<service_role key>
   ```

## Step 2 — Turso (memory DB #2)
```powershell
# install once
irm https://tur.so/install.ps1 | iex      # or: scoop install turso
turso auth login
turso db create vector
turso db show vector --url                 # → TURSO_URL
turso db tokens create vector              # → TURSO_TOKEN
turso db shell vector < deploy/sqlite_schema.sql   # create the 6 tables
```
In `.env`: `TURSO_URL=<...>` and `TURSO_TOKEN=<...>`.

## Step 3 — Cloudflare Worker (the brain) + D1 (memory DB #3 + command queue)
```powershell
npm install -g wrangler
wrangler login
cd api

# KV (heartbeat + rate limit)
wrangler kv namespace create RATE_LIMIT_KV     # → copy the id
#   paste it into api/wrangler.toml  → kv_namespaces.id

# D1 (command queue + memory mesh DB #3)
wrangler d1 create vector-brain                # → copy database_id
#   paste it into api/wrangler.toml  → d1_databases.database_id
wrangler d1 execute vector-brain --remote --file=schema.sql              # command_queue
wrangler d1 execute vector-brain --remote --file=../deploy/sqlite_schema.sql   # 6 memory tables

# Secrets
wrangler secret put VECTOR_API_KEY     # same value as .env
wrangler secret put SUPABASE_URL       # https://jgdzdwvxxaflpdzrgqut.supabase.co
wrangler secret put SUPABASE_KEY       # service_role key

wrangler deploy                        # → prints https://vector-api.<you>.workers.dev
```
Copy that Worker URL.

## Step 4 — Point the laptop at the Worker
In `.env`:
```
VECTOR_BRAIN_URL=https://vector-api.<you>.workers.dev
```
Then verify + run:
```powershell
$env:VECTOR_ENV="production"; python run_vector.py doctor   # all 4 secrets must be ✅
python run_vector.py                                         # or install the service (below)
```
Always-on (Admin PowerShell): `powershell -File scripts/install_service.ps1`

## Step 5 — Phone ambient node (old Android, Termux)
```bash
bash phone_node/setup.sh
# edit ~/.vector/phone_config.env:
#   VECTOR_BRAIN_URL=https://vector-api.<you>.workers.dev
#   VECTOR_API_KEY=<same key>
```

## Step 6 — Verify end-to-end
```powershell
# Worker is live (public):
curl https://vector-api.<you>.workers.dev/status

# Submit a command from "any device" (authed):
curl -X POST https://vector-api.<you>.workers.dev/command `
  -H "Authorization: Bearer <VECTOR_API_KEY>" -H "Content-Type: application/json" `
  -d '{"text":"open goals"}'
# → within ~3s the laptop's command poll drains it and runs it through the gateway.

# Quarantine a DB from anywhere (MCP tool db_quarantine, or):
#   the security district auto-quarantines on a malware alert.
```

---

## What each layer holds
| Layer | Role | Free? |
|---|---|---|
| Laptop SQLite (SQLCipher) | hot/critical tier, always-on, offline-safe | ✓ |
| Supabase | memory mesh DB + what the Worker serves remotely | ✓ |
| Turso | memory mesh DB (independent redundancy) | ✓ |
| Cloudflare D1 | command queue + memory mesh DB #3 | ✓ |
| Cloudflare Worker | unified brain: heartbeat, command relay, memory reads | ✓ |
| Phone (Termux) | ambient sensor + relay | ✓ |

## Honest notes
- The Worker (TypeScript) is **not** covered by the Python test suite — verify it with
  `wrangler dev` locally and the Step 6 curls after deploy.
- The 24h memory mesh currently merges **local + Supabase + Turso**. Cloudflare D1 is
  wired as the command queue; using D1 as a third *memory* sync target is a follow-up
  (the laptop's D1 memory-write path is not yet enabled).
- The old Fly brain (`cloud/brain_server/`) has been removed entirely — the
  Cloudflare Worker has full endpoint parity and is the only cloud brain now.
