# ADR-0007: JWT Authentication with Refresh Tokens

**Date:** 2026-08-06

**Status:** Accepted

## Problem

VECTOR's API was authenticated only via a static `VECTOR_API_KEY` Bearer token. This had several issues:

1. **No expiration** — a leaked key works forever
2. **No revocation** — can't invalidate a compromised key without changing it everywhere
3. **No session isolation** — laptop and phone share the same key
4. **No device tracking** — can't tell which device is making requests
5. **Owner had to paste the static key** into chat transcripts and bookmarks (real leak incident 2026-07)

The system already had partial JWT infrastructure (`core/collections/auth.py` JWTManager, WebAuthn JWT flow) but no top-level JWT auth endpoints for general API use.

## Context

- VECTOR is a single-owner system (Arghyadeep) accessed from laptop + phone via Tailscale
- 27 LLM provider API keys in `.env` — unauthorized API access could trigger expensive calls
- Free-tier quotas tracked in `quota_ledger.py` — unauthorized calls burn quota
- Existing auth: `VECTOR_API_KEY` (static, HMAC constant-time check), WebAuthn passkeys (JWT but WebAuthn-only)
- `PyJWT` already in dependencies
- `JWTManager` in `core/collections/auth.py` already supports access + refresh tokens with HS256

## Options Considered

### Option A: Keep static key only
- No change
- ❌ All problems above remain

### Option B: Add JWT with refresh tokens (chosen)
- New `/auth/jwt/*` endpoints
- Short-lived access tokens (15min)
- Long-lived refresh tokens (14 days)
- SQLite-backed token revocation blacklist
- Static key preserved as fallback for service-to-service auth

### Option C: OAuth2 with external provider
- Full OAuth2 flow with Google/GitHub
- ❌ Overkill for single-owner system
- ❌ External dependency for auth

### Option D: Session cookies only
- HttpOnly session cookies
- ❌ Doesn't work well for API clients and phone access
- ❌ CSRF complexity

## Decision

**Option B: JWT with access + refresh tokens.**

Implementation:

1. **`core/security/token_blacklist.py`** — SQLite-backed token revocation
   - Stores revoked JWT IDs (jti) with expiry timestamps
   - Supports per-token revocation and global revoke-all
   - Lazy expiration pruning (every 100 checks)
   - Separate DB from encrypted episodic memory (no SQLCipher coupling)

2. **`core/api/routers/auth_jwt.py`** — JWT auth endpoints
   - `POST /auth/jwt/login` — authenticate with API key, password, or localhost trust → token pair
   - `POST /auth/jwt/refresh` — exchange refresh token for new pair (with rotation)
   - `POST /auth/jwt/revoke` — revoke a specific token or all sessions
   - `POST /auth/jwt/logout` — alias for single-token revoke
   - `GET /auth/jwt/sessions` — list active sessions
   - `GET /auth/jwt/me` — get current identity

3. **`core/api/middleware.py`** — updated to accept JWT access tokens
   - New `_verify_jwt_access_token()` function
   - Checks signature, expiry, type, AND revocation blacklist
   - Static key + WebAuthn JWT + JWT access tokens all accepted

4. **`core/api/app.py`** — registered `auth_jwt.router`

5. **`tests/test_jwt_auth.py`** — 22 tests covering blacklist, router models, JWT flow, middleware integration

## Tradeoffs

- ✅ **Token expiration** — access tokens expire in 15min, limiting leak window
- ✅ **Revocation** — can revoke individual tokens or all sessions
- ✅ **Device tracking** — each token carries a `device` claim
- ✅ **No password needed** — can authenticate with existing `VECTOR_API_KEY`
- ✅ **Backward compatible** — static key still works, no breaking changes
- ✅ **Lightweight** — SQLite blacklist, no Redis dependency
- ❌ **New complexity** — refresh token rotation, blacklist pruning
- ❌ **Separate DB file** — `data/token_blacklist.db` (not encrypted, but contains no sensitive data — just JWT IDs)
- ❌ **Clock sensitivity** — JWT expiry depends on system clock

## Consequences

### Immediate
- Login flow: `POST /auth/jwt/login` with `{"api_key": "..."}` → get access + refresh tokens
- Use access token as `Authorization: Bearer <token>` for all API calls
- Refresh before expiry: `POST /auth/jwt/refresh` with `{"refresh_token": "..."}`
- Logout: `POST /auth/jwt/logout` with refresh token

### Future
- Can add owner password auth (`VECTOR_OWNER_PASSWORD_HASH` env var)
- Can add device-specific revocation
- Can add session limits (max N active sessions)
- Can integrate with HUD login page for token-based auth

## Related

- `core/api/auth.py` — original static key auth (preserved)
- `core/api/routers/webauthn_auth.py` — WebAuthn passkey auth (JWT-based)
- `core/collections/auth.py` — JWTManager (shared infrastructure)
- `core/api/middleware.py` — auth middleware (now accepts 3 auth methods)
- ADR-003 (Permission Gateway) — auth is the outer layer, gateway is the inner layer
