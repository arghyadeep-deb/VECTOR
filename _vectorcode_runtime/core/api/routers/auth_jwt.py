"""JWT authentication endpoints for VECTOR API.

Provides proper JWT auth with access + refresh tokens, replacing the need
to expose the static VECTOR_API_KEY for interactive use.

Endpoints:
    POST /auth/jwt/login       — authenticate with API key or password → token pair
    POST /auth/jwt/refresh     — exchange refresh token for new pair
    POST /auth/jwt/revoke      — revoke a refresh token (or all sessions)
    POST /auth/jwt/logout      — alias for revoke (revokes current session)
    GET  /auth/jwt/sessions    — list active sessions (info only)
    GET  /auth/jwt/me          — get current identity from access token

Security design:
    - Login accepts the VECTOR_API_KEY (static key) or a configured owner password
    - On successful login, returns access + refresh tokens
    - Access tokens: short-lived (15min default), used as Bearer token
    - Refresh tokens: long-lived (14 days default), used only at /auth/jwt/refresh
    - Revoked tokens are checked via core.security.token_blacklist
    - The middleware (core/api/middleware.py) accepts JWT access tokens as
      an alternative to the static key, so all existing endpoints work

The static VECTOR_API_KEY still works for service-to-service auth.
JWT is the recommended auth method for interactive use (HUD, phone, API clients).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prevent core/api/routers/ from shadowing stdlib when run as direct script.
_this_dir = str(Path(__file__).resolve().parent)
if _this_dir in sys.path:
    sys.path.remove(_this_dir)
_repo_root = str(Path(__file__).resolve().parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

__all__ = ["router"]

import hmac
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG
from core.collections.auth import JWTManager, PasswordHasher, AuthError
from core.security.token_blacklist import get_blacklist, generate_jti

router = APIRouter(prefix="/auth/jwt", tags=["jwt-auth"])
_security = HTTPBearer(auto_error=False)


# ── Request / Response Models ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Login with either the static API key or a password."""
    api_key: str | None = Field(None, description="VECTOR_API_KEY for authentication")
    password: str | None = Field(None, description="Owner password (if configured)")
    device: str | None = Field(None, description="Device identifier (for session tracking)")


class TokenResponse(BaseModel):
    """JWT token pair."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")
    refresh_expires_in: int = Field(description="Refresh token TTL in seconds")
    device: str | None = None


class RefreshRequest(BaseModel):
    """Exchange a refresh token for a new token pair."""
    refresh_token: str


class RevokeRequest(BaseModel):
    """Revoke a refresh token or all sessions."""
    refresh_token: str | None = Field(None, description="Specific refresh token to revoke")
    all_sessions: bool = Field(False, description="Revoke ALL sessions (force logout)")
    reason: str = Field("manual", description="Reason for revocation")


class SessionInfo(BaseModel):
    """Information about a session."""
    device: str | None
    issued_at: str
    expires_at: str
    token_type: str
    jti: str


class SessionsResponse(BaseModel):
    """Active sessions info."""
    sessions: list[SessionInfo]
    blacklisted_count: int


class IdentityResponse(BaseModel):
    """Current identity from access token."""
    sub: str
    device: str | None
    issued_at: str
    expires_at: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_jwt_manager() -> JWTManager:
    """Get a JWTManager configured from VECTOR's config."""
    from core.security.secrets_manager import get_secret

    jwt_cfg = (CONFIG.get("collections", {}) or {}).get("jwt", {}) or {}
    # Use get_secret() so keyring is checked as fallback (not just env)
    secret = jwt_cfg.get("secret") or get_secret("VECTOR_JWT_SECRET")
    access_ttl = jwt_cfg.get("access_ttl_sec", 900)
    refresh_ttl = jwt_cfg.get("refresh_ttl_sec", 1_209_600)

    if not secret:
        # Let JWTManager resolve its own persistent secret
        return JWTManager(access_ttl=access_ttl, refresh_ttl=refresh_ttl)

    return JWTManager(secret=secret, access_ttl=access_ttl, refresh_ttl=refresh_ttl)


def _verify_api_key(provided_key: str) -> bool:
    """Verify against VECTOR_API_KEY using constant-time comparison."""
    from core.security.secrets_manager import get_secret
    expected = get_secret("VECTOR_API_KEY")
    if not expected:
        return False
    return hmac.compare_digest(provided_key, expected)


def _verify_owner_password(password: str) -> bool:
    """Verify against VECTOR_OWNER_PASSWORD_HASH if configured."""
    pw_hash = os.environ.get("VECTOR_OWNER_PASSWORD_HASH", "")
    if not pw_hash:
        return False
    return PasswordHasher.verify(password, pw_hash)


def _extract_claims(token: str, expected_type: str) -> dict:
    """Verify a JWT and return claims. Raises HTTPException on failure."""
    blacklist = get_blacklist()

    # Check global revoke
    if blacklist.is_globally_revoked():
        raise HTTPException(status_code=401, detail="All sessions revoked — please re-authenticate")

    try:
        jwt_mgr = _get_jwt_manager()
        claims = jwt_mgr.verify(token, expected_type=expected_type)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # V1 STAGE 6 CLOSURE: owner access tokens and collection-scoped access
    # tokens (core/collections/auth.py's JWTManager.issue_pair) both use
    # type="access" with no other claim previously distinguishing them.
    # This endpoint family (/me, /sessions, /revoke, /logout) is owner-only
    # -- require the owner-only scope explicitly rather than relying on
    # expected_type="access" alone, which is exactly the collision being
    # closed.
    if expected_type == "access" and (
        claims.get("token_scope") != "owner_api"
        or claims.get("sub") != "owner"
        or "collection" in claims
        or not claims.get("jti")
    ):
        raise HTTPException(status_code=401, detail="Not a valid owner access token")

    # Check individual token revocation
    jti = claims.get("jti", "")
    if jti and blacklist.is_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return claims


def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """FastAPI dependency — extract and verify JWT from Authorization header."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    if token.count(".") != 2:
        raise HTTPException(status_code=401, detail="Invalid token format")

    return _extract_claims(token, expected_type="access")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request):
    """Authenticate and receive a JWT token pair.

    Accepts either:
    - api_key: the VECTOR_API_KEY static token
    - password: the owner password (if VECTOR_OWNER_PASSWORD_HASH is set)

    Returns access_token (short-lived) + refresh_token (long-lived).
    """
    authenticated = False
    auth_method = ""

    # Try API key first
    if body.api_key and _verify_api_key(body.api_key):
        authenticated = True
        auth_method = "api_key"

    # Try password
    elif body.password and _verify_owner_password(body.password):
        authenticated = True
        auth_method = "password"

    # If no API key is configured, allow localhost login (trust the network)
    elif not _configured_owner_credentials():
        client_ip = request.client.host if request.client else ""
        if client_ip in ("127.0.0.1", "::1", "localhost", "testclient"):
            authenticated = True
            auth_method = "localhost"

    if not authenticated:
        logger.warning("[VECTOR][auth] failed login attempt from {}", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Issue token pair
    jwt_mgr = _get_jwt_manager()
    device = body.device or "unknown"
    jti_access = generate_jti()
    jti_refresh = generate_jti()

    now = datetime.now(timezone.utc)
    access_claims = {
        "sub": "owner",
        "device": device,
        "auth_method": auth_method,
        "jti": jti_access,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + jwt_mgr.access_ttl,
        "type": "access",
        # V1 STAGE 6 CLOSURE: distinguishes this owner token from a
        # collection-scoped access token (core/collections/auth.py's
        # issue_pair), which also uses type="access" but never sets this.
        "token_scope": "owner_api",
    }
    refresh_claims = {
        "sub": "owner",
        "device": device,
        "jti": jti_refresh,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + jwt_mgr.refresh_ttl,
        "type": "refresh",
        # V1 STAGE 6 CLOSURE (round 2 — second independent review finding):
        # the refresh token must ALSO carry the owner-scope marker. Without
        # this, refresh()'s rotation (below) drops the "collection" claim
        # while keeping sub=="owner", so a two-step refresh chain (rotate
        # once to shed "collection", rotate again) could otherwise
        # manufacture a scoped owner access token from a collection
        # refresh token. Marking scope HERE, at the only real point of
        # owner authentication, and requiring it to already be present on
        # the INCOMING refresh token (see refresh(), which checks
        # claims.get("token_scope") rather than re-deriving from sub) means
        # no rotation can ever create it out of nothing.
        "token_scope": "owner_api",
    }

    import jwt as pyjwt
    access_token = pyjwt.encode(access_claims, jwt_mgr.secret, algorithm="HS256")
    refresh_token = pyjwt.encode(refresh_claims, jwt_mgr.secret, algorithm="HS256")

    logger.info(
        "[VECTOR][auth] login successful: method={} device={} jti_access={} jti_refresh={}",
        auth_method, device, jti_access[:12], jti_refresh[:12],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=jwt_mgr.access_ttl,
        refresh_expires_in=jwt_mgr.refresh_ttl,
        device=device,
    )


def _configured_owner_credentials() -> bool:
    """Whether any owner login credential exists, including keyring secrets."""
    from core.security.secrets_manager import get_secret
    return bool(get_secret("VECTOR_API_KEY") or os.environ.get("VECTOR_OWNER_PASSWORD_HASH"))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """Exchange a valid refresh token for a new token pair.

    The old refresh token is revoked (rotation). The old access token
    remains valid until its natural expiry.
    """
    claims = _extract_claims(body.refresh_token, expected_type="refresh")

    # V1 STAGE 6 CLOSURE (round 3 hardening, 2026-09-23): this is the OWNER
    # JWT refresh endpoint. A collection-issued refresh token (carries a
    # "collection" claim — see core/collections/auth.py's issue_pair) was
    # previously still accepted here and processed all the way through to
    # issuing a new (unscoped, owner-unusable) pair -- never an owner-scope
    # escalation given the is_owner_refresh invariant below, but a
    # boundary-clarity gap Codex's round-3 review flagged: this endpoint has
    # no legitimate reason to process a collection token at all. Reject it
    # outright instead of silently minting it a useless pair.
    if "collection" in claims:
        raise HTTPException(status_code=401, detail="Not an owner refresh token")

    # Revoke the old refresh token (rotation)
    old_jti = claims.get("jti", "")
    if old_jti:
        blacklist = get_blacklist()
        blacklist.revoke(
            jti=old_jti,
            expires_at=claims.get("exp", 0),
            token_type="refresh",
            reason="refresh_rotation",
        )

    # Issue new pair
    jwt_mgr = _get_jwt_manager()
    device = claims.get("device", "unknown")
    new_jti_access = generate_jti()
    new_jti_refresh = generate_jti()

    now = datetime.now(timezone.utc)
    import jwt as pyjwt
    access_claims = {
        "sub": claims.get("sub", "owner"),
        "device": device,
        "jti": new_jti_access,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + jwt_mgr.access_ttl,
        "type": "access",
    }
    # V1 STAGE 6 CLOSURE (round 2 — a second independent review round found
    # the round-1 fix incomplete): propagate owner scope only when the
    # INCOMING refresh token already carries token_scope=="owner_api" —
    # never re-derive it from sub/collection on each hop. Round 1 checked
    # sub=="owner" and "collection" not in claims, which correctly rejected
    # the immediate access token from an adversarial issue_pair("owner",
    # "users") collection refresh token, but the ROTATED refresh token this
    # endpoint issued for that same request dropped "collection" while
    # keeping sub=="owner" — so a SECOND call to /refresh with that rotated
    # token would satisfy the sub/collection check and mint a genuinely
    # scoped owner access token. Real owner refresh tokens now carry
    # token_scope="owner_api" from the moment they're first issued at
    # /login (the only real point of owner authentication); collection
    # issuance (core/collections/auth.py's issue_pair) never sets it and
    # never can, so no length of rotation can manufacture it. Scope is
    # propagated onto BOTH the new access token and the new refresh token,
    # so legitimate owner sessions keep refreshing indefinitely.
    is_owner_refresh = (
        claims.get("token_scope") == "owner_api"
        and claims.get("sub") == "owner"
        and "collection" not in claims
        and bool(claims.get("jti"))
    )
    if is_owner_refresh:
        access_claims["token_scope"] = "owner_api"
    refresh_claims = {
        "sub": claims.get("sub", "owner"),
        "device": device,
        "jti": new_jti_refresh,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + jwt_mgr.refresh_ttl,
        "type": "refresh",
    }
    if is_owner_refresh:
        refresh_claims["token_scope"] = "owner_api"

    access_token = pyjwt.encode(access_claims, jwt_mgr.secret, algorithm="HS256")
    new_refresh_token = pyjwt.encode(refresh_claims, jwt_mgr.secret, algorithm="HS256")

    logger.info(
        "[VECTOR][auth] token refresh: device={} old_jti={} new_jti={}",
        device, old_jti[:12] if old_jti else "none", new_jti_refresh[:12],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=jwt_mgr.access_ttl,
        refresh_expires_in=jwt_mgr.refresh_ttl,
        device=device,
    )


@router.post("/revoke")
async def revoke(body: RevokeRequest, claims: dict = Depends(_require_auth)):
    """Revoke a refresh token or all sessions.

    Requires a valid access token to call.
    """
    blacklist = get_blacklist()

    if body.all_sessions:
        count = blacklist.revoke_all_sessions(reason=body.reason)
        return {
            "revoked": "all_sessions",
            "reason": body.reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    if not body.refresh_token:
        raise HTTPException(status_code=400, detail="Provide refresh_token or set all_sessions=true")

    # Verify the token to get its jti and expiry
    try:
        jwt_mgr = _get_jwt_manager()
        token_claims = jwt_mgr.verify(body.refresh_token, expected_type="refresh")
    except AuthError as e:
        raise HTTPException(status_code=400, detail=f"Invalid refresh token: {e}")

    jti = token_claims.get("jti", "")
    if jti:
        blacklist.revoke(
            jti=jti,
            expires_at=token_claims.get("exp", 0),
            token_type="refresh",
            reason=body.reason,
        )

    return {
        "revoked": "single",
        "jti": jti[:12] if jti else "unknown",
        "reason": body.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/logout")
async def logout(body: RefreshRequest, claims: dict = Depends(_require_auth)):
    """Logout — revoke the current refresh token. Alias for /revoke with a single token."""
    revoke_body = RevokeRequest(refresh_token=body.refresh_token, all_sessions=False, reason="logout")
    return await revoke(revoke_body, claims)


@router.get("/sessions", response_model=SessionsResponse)
async def sessions(claims: dict = Depends(_require_auth)):
    """List active sessions (blacklist info).

    Requires a valid access token.
    """
    blacklist = get_blacklist()
    active_count = blacklist.count_active()

    # Return the current session info from the access token
    current_session = SessionInfo(
        device=claims.get("device"),
        issued_at=datetime.fromtimestamp(claims.get("iat", 0), tz=timezone.utc).isoformat(),
        expires_at=datetime.fromtimestamp(claims.get("exp", 0), tz=timezone.utc).isoformat(),
        token_type="access",
        jti=claims.get("jti", "")[:12],
    )

    return SessionsResponse(
        sessions=[current_session],
        blacklisted_count=active_count,
    )


@router.get("/me", response_model=IdentityResponse)
async def me(claims: dict = Depends(_require_auth)):
    """Get current identity from the access token."""
    return IdentityResponse(
        sub=claims.get("sub", "unknown"),
        device=claims.get("device"),
        issued_at=datetime.fromtimestamp(claims.get("iat", 0), tz=timezone.utc).isoformat(),
        expires_at=datetime.fromtimestamp(claims.get("exp", 0), tz=timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Self-test: verify the router can be imported and models work
    req = LoginRequest(api_key="test")
    resp = TokenResponse(
        access_token="a", refresh_token="r",
        expires_in=900, refresh_expires_in=1209600,
    )
    assert resp.token_type == "bearer"
    print("✅ auth_jwt.py OK")
