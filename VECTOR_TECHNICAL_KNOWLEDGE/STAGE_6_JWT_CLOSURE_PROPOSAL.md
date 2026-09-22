# VECTOR V1 Stage 6 — JWT / Authorization Security Closure (PROPOSAL ONLY)

Date: 2026-09-22. Branch `production-hardening-complete` (current code, no
changes made). **This is a proposal for owner approval, not an
implementation.** Nothing has been changed.

Investigation by Codex (read-only), independently re-verified line-by-line
by Claude directly against the real code before writing this document.
Every file:line citation below was personally confirmed, not relayed
uncritically.

## 1. Exact demonstrated vulnerability

**A collection-scoped JWT can authenticate as full owner-equivalent global
API access**, because owner access tokens and collection access tokens
share the identical `type="access"` claim namespace, and the middleware's
JWT check never verifies anything beyond that shared type.

Confirmed directly:

- `core/api/middleware.py:195-217` (`_verify_jwt_access_token`) calls
  `JWTManager.verify(token, expected_type="access")`, checks revocation via
  `jti` (optional — a token with no `jti` skips the revocation check
  entirely), and returns `True` on success. **Nothing else is checked** —
  no `sub`, no absence-of-`collection`, no scope claim.
- `core/api/middleware.py:264-274` (`auth_middleware`): `jwt_valid =
  _verify_jwt_access_token(provided) or _verify_webauthn_jwt(provided)`. If
  `jwt_valid`, the request proceeds with the same trust level as the static
  `VECTOR_API_KEY`.
- `core/collections/auth.py:128-132` (`JWTManager.issue_pair`): collection
  tokens are issued as `{"sub": sub, "collection": collection, "type":
  "access", ...}` — a `"collection"` claim is present, `sub` is an arbitrary
  collection-user identifier.
- `core/api/routers/auth_jwt.py:227-234`: owner tokens are issued as
  `{"sub": "owner", "device": ..., "jti": ..., "type": "access", ...}` — no
  `"collection"` claim, but **no distinguishing scope claim either** — the
  only structural difference from a collection token is the absence of one
  optional field.
- `core/collections/auth.py:134-146` (`JWTManager.verify`): `expected_type`
  only ever checks the shared `"type"` string. It has no concept of "owner"
  vs "collection" at all.

Net effect: any valid collection-password-holder (`POST
/api/collections/{name}/auth-with-password`,
`core/api/routers/collections.py:201`) receives a JWT that will pass
`auth_middleware`'s global gate exactly like an owner JWT or the static API
key, for every non-public endpoint in the API — not just endpoints scoped
to that collection.

## 2. Affected code path

**Issuance:** `POST /api/collections/{name}/auth-with-password` →
`core/api/routers/collections.py:201` → `AuthService.authenticate()`
(`core/collections/auth.py:343`) → `JWTManager.issue_pair()`
(`core/collections/auth.py:128`).

**Misuse:** any non-public request → `core/api/middleware.py:258` (bearer
extraction) → `_verify_jwt_access_token()` (`core/api/middleware.py:195`) →
`JWTManager.verify(..., expected_type="access")` → request accepted as
owner-equivalent.

**Also affected:** `core/api/routers/auth_jwt.py:149` (`_extract_claims`,
used by `/auth/jwt/me`, `/sessions`, `/revoke`, `/logout`) has the same
"only checks `expected_type`" gap.

## 3. Proposed bounded repair

Make owner API JWTs semantically distinct from collection JWTs, and require
that distinction wherever a JWT is accepted in place of `VECTOR_API_KEY`:

- Add an owner-only claim to tokens issued by `/auth/jwt/login` and
  `/auth/jwt/refresh` (e.g. `token_scope="owner_api"`).
- In `core/api/middleware.py`'s `_verify_jwt_access_token()`, after the
  existing `expected_type="access"` check, additionally require:
  `claims.get("token_scope") == "owner_api"`, `claims.get("sub") ==
  "owner"`, no `"collection"` claim present, and a non-empty `jti`.
- Apply the identical owner-token predicate in
  `core/api/routers/auth_jwt.py`'s `_extract_claims()` (covers `/me`,
  `/sessions`, `/revoke`, `/logout`).
- Collection token issuance and collection-rule authentication are
  **unchanged** — a collection JWT continues to work exactly as it does
  today for its own collection-scoped endpoints.

This will invalidate already-issued owner JWTs that lack the new scope
claim (they simply won't authenticate anymore). Acceptable: the owner can
mint a fresh one immediately via password/localhost login, same as today.

## 4. Allowed files (minimal fix surface)

- `core/api/middleware.py`
- `core/api/routers/auth_jwt.py`
- `tests/test_jwt_auth.py`
- `tests/backend/test_webauthn_middleware_integration.py`

Optional, only if separately approved: `core/collections/auth.py`, to make
`expected_type` mandatory (non-`None`) in `JWTManager.verify()` generally —
useful defense-in-depth, but does not by itself close the owner/collection
collision above, so it is not required for this closure.

## 5. Expected security semantics after the fix

- A collection JWT must never authenticate as owner API access.
- A collection JWT continues to authenticate as its own collection identity
  for collection-rule evaluation (unchanged).
- An owner JWT is accepted by middleware only when explicitly scoped as
  owner API access.
- A WebAuthn session JWT remains its own separate `type="webauthn_session"`
  path (unchanged).
- Refresh tokens must never authenticate as access tokens (already true;
  regression-tested to confirm it stays true).

## 6. Regression tests

Must still pass, unmodified behavior: `tests/test_collections.py::
test_jwt_issue_verify_refresh`, `tests/test_collections.py::
test_api_auth_flow`, `tests/test_jwt_auth.py`,
`tests/backend/test_webauthn_auth.py`.

New/adjusted:
- Middleware rejects a real collection token (from
  `JWTManager.issue_pair(...)`) even though it is correctly signed and has
  `type="access"`.
- Middleware accepts a correctly-scoped owner token from `/auth/jwt/login`.
- `/auth/jwt/me`, `/sessions`, `/revoke`, `/logout` reject collection
  tokens.
- `tests/backend/test_webauthn_middleware_integration.py:70` needs
  correcting: it currently constructs a `type="access"` token that the
  *current* (vulnerable) middleware path accepts before ever reaching the
  WebAuthn-specific check — this test should be updated to reflect the
  fixed, scoped behavior.

## 7. What approval authorizes / does not authorize

**Authorizes only:**
- distinguishing owner API JWTs from collection JWTs via one new claim;
- enforcing that distinction in `core/api/middleware.py` and
  `core/api/routers/auth_jwt.py`;
- regression tests proving a collection JWT can no longer become an owner
  API credential.

**Does NOT authorize:**
- any broader authorization/session redesign;
- new token families or login flows beyond the one scope marker above;
- changes to collection-rule semantics, WebAuthn ceremonies, or Permission
  Gateway behavior;
- replacing `JWTManager`.

---

**Nothing has been implemented.** Per this project's own `POLICY.md` §14
and the original V1 directive, this closure requires explicit owner
approval before any code changes. Reporting `V1_OWNER_APPROVAL_REQUIRED`.
