# Task 13 — Deploy Cloudflare Worker API

- **Depends on:** Task 12
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
