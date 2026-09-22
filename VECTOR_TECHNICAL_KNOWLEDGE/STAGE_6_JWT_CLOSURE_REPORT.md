# VECTOR V1 Stage 6 — JWT / Authorization Security Closure (IMPLEMENTED)

Date: 2026-09-22. Branch `production-hardening-complete` (working tree,
uncommitted — the owner has not yet decided to commit/promote). Owner
explicitly approved the proposal in `STAGE_6_JWT_CLOSURE_PROPOSAL.md` before
any of this work began.

**VERDICT: STAGE_6_PASS**, closed after three real, substantive rounds of
independent adversarial review — each round found a genuine, distinct gap
in the previous round's fix. This is not a formality; the vulnerability
class (implicit claim-based scope) is genuinely subtle, and the review
process caught two real escalation paths a single pass would have missed.

## 1. Governance

The bridge's own automated approval gate (`tools/vector_dev_orchestrator`)
correctly refused to self-authorize this package — `ApprovalPolicy`'s
keyword-triggered `requires_human` check fires on any security-sensitive
task description, by design, with no override mechanism (matching
`POLICY.md` §14: "No model may self-authorize a human-gated action"). Since
the owner had already explicitly approved the work in direct conversation,
implementation proceeded directly (Claude), with Codex as the independent
reviewer — the same dual-provider discipline the bridge would have enforced,
executed manually because the bridge's gate is intentionally not
bypassable. The bridge program (`prog-2428f583`) remains parked in
`needs_human`, an honest, correct record that it did exactly what it was
designed to do.

## 2. The original vulnerability (recap, independently verified before any fix)

Owner API JWTs and collection-scoped JWTs (`core/collections/auth.py`'s
`JWTManager.issue_pair`) shared the identical `type="access"` claim with
nothing else distinguishing them. `core/api/middleware.py`'s
`_verify_jwt_access_token()` only checked `expected_type="access"` plus
revocation. A collection JWT (from `POST /api/collections/{name}/
auth-with-password`) therefore authenticated as full owner-equivalent
global API access.

## 3. The fix, and the three-round review that hardened it

**Round 1 fix (initial implementation):** add `token_scope="owner_api"` to
owner access tokens (`/auth/jwt/login`, `/auth/jwt/refresh`); require
`token_scope=="owner_api"` + `sub=="owner"` + no `"collection"` claim + a
non-empty `jti` in `middleware.py`'s `_verify_jwt_access_token()` and
`auth_jwt.py`'s `_extract_claims()`. 96 tests passing (47 pre-existing + 9
new).

**Round 1 review finding (real, CHANGES_REQUIRED):** `refresh()`'s
propagation check was `claims.get("sub") == "owner"` alone. A collection
refresh token from `JWTManager.issue_pair("owner", "users")` — a collection
record literally id'd `"owner"` — has `sub="owner"` **and** `collection=
"users"`. The sub-only check would have wrongly minted a scoped owner
access token from it.

**Round 1 correction:** require `sub=="owner"` **and** `"collection" not in
claims` **and** a real `jti` before propagating scope in `refresh()`. New
adversarial test (`test_refresh_endpoint_rejects_owner_sub_collection_token`)
using exactly that `issue_pair("owner", "users")` shape. 97 tests passing.

**Round 2 review finding (real, CHANGES_REQUIRED):** the rotated *refresh*
token `refresh()` issues drops the `"collection"` claim while keeping
`sub=="owner"` — so a **second** call to `/auth/jwt/refresh` with that
rotated token would satisfy the sub/collection check and mint a genuinely
scoped owner access token. A two-hop escalation the round-1 fix and its test
both missed (the test only checked the first hop's *access* token, never
exchanged the returned *refresh* token again).

**Round 2 correction:** stop re-deriving owner-ness from `sub`/`collection`
on every hop. Real owner refresh tokens now carry `token_scope="owner_api"`
from the moment they are first issued at `/login` — the only real point of
owner authentication. `refresh()` now checks whether the **incoming**
refresh token already carries that marker, and only then propagates it onto
**both** the new access token and the new refresh token. Collection
issuance never sets this claim and structurally cannot. Two new tests:
`test_refresh_chain_cannot_manufacture_owner_scope` (two-hop adversarial
rotation, both resulting access tokens rejected) and
`test_genuine_owner_refresh_chain_keeps_working` (control: a real owner
session survives repeated rotation). 99 tests passing.

**Round 3 review (PASS):** confirmed the two-hop closure, then explicitly
traced the invariant for arbitrary rotation depth: a token lacking
`token_scope` can never have it added by any hop, so 3, 10, or unbounded
rotations still cannot manufacture owner scope from a collection token.
Additionally swept every JWT issuance/re-issuance site in the codebase
(`core/collections/auth.py`'s `issue_pair`/`refresh`, `core/api/routers/
webauthn_auth.py`'s session-token issuance) and confirmed none of them can
produce `token_scope="owner_api"` outside the one real owner-login path. No
further findings.

## 4. Final state

| File | Change |
|---|---|
| `core/api/middleware.py` | `_verify_jwt_access_token()` requires `token_scope=="owner_api"`, `sub=="owner"`, no `collection` claim, non-empty `jti` (previously: `expected_type="access"` alone; `jti` was optional) |
| `core/api/routers/auth_jwt.py` | `login()` sets `token_scope="owner_api"` on both issued tokens; `refresh()` propagates it only when the incoming refresh token already carries it (transitively safe, not re-derived); `_extract_claims()` enforces the same owner predicate for `/me`, `/sessions`, `/revoke`, `/logout` |
| `tests/test_jwt_auth.py` | 12 new tests: the original collision closed, the sub/collection adversarial case, the two-hop rotation escalation, and a control proving genuine owner sessions keep working |

**99/99 tests passing** (`tests/test_collections.py`, `tests/test_jwt_auth.py`,
`tests/backend/test_webauthn_auth.py`, `tests/backend/
test_webauthn_middleware_integration.py`) — zero regressions across three
rounds of fixes.

## 5. What this does NOT do

Nothing has been committed or pushed. Nothing has been merged into
`vector-integration` or promoted to a live deployment. Existing owner JWTs
issued before this fix (lacking `token_scope`) will stop authenticating —
expected and accepted per the original approval; a fresh login immediately
mints a correctly-scoped one. No broader auth redesign, new token types, or
changes to collection-rule/WebAuthn/Permission-Gateway behavior — exactly
the scope the owner approved, nothing more.

---

**STAGE_6_PASS.**
