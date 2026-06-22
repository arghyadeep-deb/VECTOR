# OmniRoute-main - VECTOR Absorption Review

**Verdict:** IMPLEMENT narrow provider-router hardening only. Do not absorb the product.

**Priority:** HIGH for provider resilience, LOW for full product absorption

**Effort:** 1-2 sessions for clean-room provider health/circuit/quota upgrades

**License:** MIT

**Repo size inspected:** ~6,863 files / ~117.90 MB excluding `node_modules`, build, dist, and `.git`

## What It Is

OmniRoute is a large TypeScript/Next.js AI gateway. It presents one OpenAI-compatible endpoint over many providers, with:

- provider catalogs and model aliases
- OpenAI/Claude/Gemini/Responses translation
- automatic fallback and routing strategies
- quota and free-tier tracking
- circuit breakers, cooldowns, lockouts, and provider health dashboards
- token compression strategies
- API keys, scopes, auth, audit, dashboards, PWA, Electron, MCP/A2A, and tests

It is a complete gateway product, not a small library.

## VECTOR Already Has

- `core/inference/provider_client.py` provider abstraction
- local Ollama routing and cloud-provider fallbacks
- telemetry/token accounting pieces
- API auth and device-token direction
- OpenAI-compatible gateway recommendation from `open-webui.md`
- Cloudflare queue + Termux/laptop device routing
- PermissionGateway and action governance
- frontend provider/status widgets

VECTOR's gap is not "no router". The gap is production-grade routing reliability and provider observability.

## Overlap

Approximate overlap: **65-75%**.

OmniRoute is stronger at provider/account/model routing, dashboards, health matrices, and protocol translation.

VECTOR is stronger at personal-agent orchestration, local-first execution, permissions, device mesh, voice, memory, missions, and JARVIS-style autonomy.

## Risk Boundary

Do not absorb or reproduce:

- consumer IDE OAuth bypass flows
- TLS fingerprint stealth
- provider scraping or traffic interception
- "free tier aggregation" behavior that may violate provider terms
- large TypeScript/Next.js dashboard surfaces
- provider-specific header spoofing

VECTOR should be boring and reliable here: owner-owned keys, explicit provider configs, clean fallback, transparent cost/quota, no stealth.

## Real Value For VECTOR

### 1. Provider health and circuit breakers

Add a lightweight health layer around VECTOR's existing provider client:

- per-provider success/failure counters
- rolling latency
- cooldown after repeated 429/5xx/network failures
- half-open probe after cooldown
- model-level lockout separate from provider-level lockout

### 2. Quota and budget awareness

Track:

- monthly token usage by provider/model
- daily spend estimate where pricing is known
- remaining configured owner budget
- provider disabled state when budget is exhausted

This should connect to existing telemetry, not create a second metrics island.

### 3. Compatibility endpoint

The Open WebUI analysis already recommended a VECTOR `/v1` compatibility API. OmniRoute confirms this is high-value:

- `GET /v1/models`
- `POST /v1/chat/completions`
- optional streaming SSE

Keep this endpoint as a frontend/client compatibility layer, not a full external gateway product.

### 4. Provider capability registry

Add a simple registry for:

- text generation
- reasoning
- tool calling
- embeddings
- image generation
- TTS/STT
- context length
- streaming support
- local/cloud
- cost tier

This also helps media model routing from the Pixelle review.

## What Not To Absorb

- Do not port the Next.js app.
- Do not import the provider catalog wholesale.
- Do not add 200+ providers just because the list exists.
- Do not route through unowned "free" accounts.
- Do not add TLS/traffic-stealth features.
- Do not make provider routing bypass PermissionGateway.
- Do not put API keys in frontend/mobile clients.

## Implementation Plan For Sonnet

Build a small Python-first provider resilience layer.

1. Add `core/inference/provider_registry.py`.
   - Define provider/model capability records.
   - Start with only VECTOR's existing configured providers.
   - Add fields: `supports_stream`, `supports_tools`, `context_window`, `cost_tier`, `local`, `priority`.

2. Add `core/inference/provider_health.py`.
   - State: `healthy`, `cooldown`, `half_open`, `disabled`.
   - Track provider-level and model-level failures separately.
   - Expose `record_success`, `record_failure`, `can_try`, `next_retry_at`.

3. Wrap `provider_client`.
   - Before a call, choose only healthy candidates.
   - On failure, record typed reason: `rate_limit`, `auth`, `server_error`, `network`, `bad_request`.
   - Never retry non-idempotent action/tool execution automatically.

4. Add telemetry.
   - Persist token usage and estimated cost per provider/model.
   - Expose a small `/providers/routes` or `/providers/health` API shape if not already complete.

5. Add tests.
   - rate-limit failure cools down a model
   - auth failure disables a provider until config changes
   - server error opens circuit after threshold
   - half-open success recovers provider
   - PermissionGateway action prompts are not retried into a different provider after approval-sensitive failure

## Acceptance Criteria

- Existing provider behavior remains backward compatible.
- No secrets are exposed in logs or frontend.
- Router state is visible in a status endpoint.
- The fallback chain is deterministic and testable.
- No OmniRoute code, provider lists, headers, or stealth behavior is copied.

## Final Recommendation

Use OmniRoute as evidence that VECTOR needs a more mature provider router, not as code to import. The right implementation is a compact, transparent, Python-native provider health/quota/capability layer around VECTOR's existing inference path.
