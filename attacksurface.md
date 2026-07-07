# VECTOR — Attack Surface Inventory
> Running record, maintained via the `attack-surface` skill. Update on any
> deploy/change/retire. Re-verify "live" before trusting. Last full pass: 2026-07-07.

## Legend
Exposure: PUBLIC | INTERNAL | LOCAL | TOKEN | OAUTH. Type: WEB | DB | API | LOCAL.
Residual risk: Low / Med / High.

## Deployed services

### 1. Cloudflare Worker API — `vector-api.arghyadeepdeb020703.workers.dev`
- Type: WEB/API. Exposure: PUBLIC (auth-bearing). Third-party (Cloudflare).
- Tech: Workers + D1 (command queue, 7 tables) + KV (rate-limit/heartbeat).
- Auth into it: `VECTOR_API_KEY` bearer (wrangler secret); routes gated.
- Deployed: `/health`, `/status`, `/heartbeat`, `/command`(+D1 queue),
  `/memory/recent`, `/agents`, `/goals` (`api/src/router.ts`).
- Common misconfig class: secrets in wrangler.toml (checked — uses `wrangler
  secret put`, not inline); missing route auth; over-broad D1.
- Defenses: bearer auth; D1 parameterized; KV rate-limit window.
- Residual risk: **Med** (public + auth). Cadence: monthly + every deploy.
- Last assessed: 2026-07-07 (live, `/health` → 200).

### 2. Supabase — cloud memory (primary)
- Type: DB. Exposure: TOKEN. Third-party.
- Auth: `SUPABASE_URL` + `SUPABASE_KEY` (SecretStr in .env).
- Deployed: memory-sync tables (multi_db_manager writes semantic/episodic).
- Misconfig class: RLS disabled, service_role key exposure.
- Defenses: keys in .env (gitignored), not client-exposed; local SQLite is source.
- Residual risk: **Med** (owner data). Cadence: quarterly + on schema change.
- Last assessed: 2026-07-02 (health OK).

### 3. Turso — cloud memory (secondary)
- Type: DB. Exposure: TOKEN. Third-party. Auth: `TURSO_URL`+`TURSO_TOKEN`.
- Deployed: memory-sync mirror. Defenses: token in .env. Risk: **Med**.
- Last assessed: 2026-07-02 (health OK, ~1s latency).

### 4. GitHub — `github.com/arghyadeep-deb/VECTOR` (PUBLIC repo)
- Type: WEB/API. Exposure: PUBLIC (repo) + TOKEN (API via GITHUB_TOKEN).
- Misconfig class: **secrets committed to a public repo** (history was rewritten
  2026-06-29 to strip >100MB blobs; .env is gitignored — verify no key ever
  committed), Actions injection (`.claude/rules` warn on GH Actions injection),
  token scope. GITHUB_TOKEN also used as a free LLM provider (GitHub Models).
- Defenses: .env + *.db + model weights gitignored; syntax-gate commit hook.
- Residual risk: **Med-High** (public repo — any leaked secret is exposed).
  Cadence: on every push + semi-annual secret scan.
- Last assessed: 2026-07-05 (force-push clean, largest blob 27MB).

### 5. LLM provider APIs (13 free-tier)
- Type: API. Exposure: TOKEN. Third-party (Groq, Cerebras, Cloudflare, Mistral,
  NVIDIA, GitHub Models, OpenRouter, Gemini, ZAI, LLM7, Cohere, DeepSeek, OpenCode Zen).
- Auth: per-provider API key in .env (SecretStr). Misconfig: key leakage, and
  **OpenCode Zen/ZAI keys can reach PAID models** — mitigated by locked_models
  whitelist clamp (verified). Defense: SSRF guard on all outbound; sensitivity
  gate keeps secrets local. Risk: **Low-Med**. Cadence: semi-annual + on rotation.

### 6. FastAPI HUD/API server (local)
- Type: WEB/API. Exposure: LOCAL (localhost-only when no VECTOR_API_KEY; else
  bearer). Self-hosted. Auth: 7-layer middleware (error/rate-limit/CSRF/auth/
  logging/timing/security-headers). Fail-safe: no key → refuses non-localhost.
  Frontend HTML-escapes ingested content. Risk: **Low** (local). Cadence: annual.

### 7. Ollama (local inference)
- Type: LOCAL API (127.0.0.1:11434). Exposure: LOCAL. Self-hosted. Risk: **Low**.

### 8. Phone node (Termux, Android) — NOT YET DEPLOYED
- Would be: INTERNAL (LAN). Auth added (bearer). Assess when deployed.

### 9. cloud/email Worker — NOT YET DEPLOYED
- Would be PUBLIC. Needs Email Routing + R2 + Access. npm audit = 0 vulns (2026-07-01).

## Not deployed / retired
- Fly.io brain server — removed (owner declined card). Cloudflare Worker has parity.
- Paid video (MuAPI/Runway/Pika) — deleted 2026-07-04 (local-only now).

## Provenance
2026-07-07. Re-verify Worker: `curl -s https://vector-api.arghyadeepdeb020703.workers.dev/health`.
Re-verify cloud DB: `python core/memory/multi_db_manager.py`. Secret scan:
`git log -p | grep -iE "api_key|secret|token" | grep -v gitignore` (should find none in tree).
