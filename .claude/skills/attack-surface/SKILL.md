---
name: attack-surface
description: Load when assessing or updating VECTOR's security exposure across deployed services, hosts, vendors, and APIs — maintaining the running attack-surface inventory or assessing one surface. Triggers: "attack surface", "security exposure", "what's deployed", "assess security", "attacksurface.md", "am I exposed", "audit deployment".
---

# Attack Surface (VECTOR)

Maintain and assess VECTOR's total attack surface. The running inventory lives in
`attacksurface.md` at the repo root. Ground truth 2026-07-07.

## When NOT to use this skill
For prompt-injection specifically use `plans/security/prompt-injection-map.md`.
For the security *code* use `core/security/` + `vector-architecture-contract`.

## Two capabilities

### 1. Maintain `attacksurface.md` (the running inventory)
Keep `attacksurface.md` current. For EACH deployed thing record: tech stack;
self-hosted vs third-party; how you authenticate into it; common
misconfigurations/CVE classes for that platform; what VECTOR has deployed there;
type (web / DB / API); defenses in place; exposure per audience (public /
internal / VPN / token-required / OAuth). When a service is added, changed, or
retired, update the file.

### 2. AssessAttackSurface workflow (assess ONE surface thoroughly)
Steps for any single surface:
1. Identify tech + hosting + auth model (from attacksurface.md or by inspection).
2. Enumerate exposure: who can reach it, on what ports/paths, with what auth.
3. Map platform-specific misconfig classes (e.g. Cloudflare Worker: leaked
   secrets in wrangler.toml, over-broad D1 access, missing auth on routes;
   Supabase: RLS disabled, service_role key exposure; GitHub: token scope,
   Actions injection).
4. Check VECTOR's defenses vs each (auth middleware, SSRF guard, secret storage,
   RLS, rate limits).
5. Rate residual risk (Low/Med/High) + recommend a testing frequency by
   criticality × cost (see table below).
6. Record findings back into attacksurface.md with a date.

## Testing frequency guide (criticality × cost)
| Criticality | Change rate | Suggested cadence |
|---|---|---|
| Public + auth-bearing (Cloudflare Worker API) | high | monthly automated + on every deploy |
| Cloud DB with owner data (Supabase/Turso) | medium | quarterly + on schema change |
| Third-party APIs (LLM providers, GitHub) | low | semi-annual + on key rotation |
| Local-only (Ollama, HUD localhost) | low | annual / on config change |

## Provenance and maintenance
2026-07-07. The inventory is `attacksurface.md`. Re-verify a service is live
before asserting its state (e.g. `curl -s <worker>/health`). Update the file's
"last assessed" date per service when you run AssessAttackSurface.
