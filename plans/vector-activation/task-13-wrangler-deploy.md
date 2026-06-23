# Task 13 — Deploy Cloudflare Worker API

> Updated: Task 12 (Fly.io) was cancelled — this task no longer depends on
> it. Cloudflare is the only cloud brain now; see `DEPLOY.md` for the
> current step-by-step (Supabase + Turso + Cloudflare D1/KV, no Fly).

- **Depends on:** Task 01 (rotated keys only)
- **Who:** OWNER login → me
- **Effort:** ~30 min

## Objective

`api/` worker live on Cloudflare with D1/R2/KV provisioned per `wrangler.toml`.

## Implementation

1. OWNER: `npx wrangler login`.
2. me: provision D1 database + R2 bucket + KV namespace, fill the binding ids
   in `wrangler.toml`, `npx wrangler deploy`.

## Tests

Worker URL `/status` → 200; a KV round-trip via the worker.

## Acceptance

- [ ] Worker deployed and reachable
- [ ] D1/R2/KV bindings resolve (no 1101 errors)
- [ ] Binding ids committed in wrangler.toml (no secrets)
