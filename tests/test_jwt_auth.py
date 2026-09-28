"""Tests for JWT authentication system.

Tests the full JWT auth flow:
- Token blacklist (revocation)
- JWT login endpoint
- JWT refresh endpoint
- JWT revoke endpoint
- Middleware integration (JWT access tokens accepted)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Token Blacklist Tests ─────────────────────────────────────────────────────

class TestTokenBlacklist:
    """Test the token revocation blacklist."""

    def test_import(self):
        from core.security.token_blacklist import TokenBlacklist, get_blacklist, generate_jti
        assert TokenBlacklist is not None
        assert get_blacklist is not None
        assert generate_jti is not None

    def test_revoke_and_check(self):
        from core.security.token_blacklist import TokenBlacklist
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            bl = TokenBlacklist(db_path=tmp_path)
            bl.revoke("test-jti-1", expires_at=9999999999, token_type="refresh")
            assert bl.is_revoked("test-jti-1") is True
            assert bl.is_revoked("nonexistent") is False
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_expired_entry_not_found(self):
        from core.security.token_blacklist import TokenBlacklist
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            bl = TokenBlacklist(db_path=tmp_path)
            bl.revoke("expired-jti", expires_at=1, token_type="access")
            # Expired entries should not be found
            assert bl.is_revoked("expired-jti") is False
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_global_revoke(self):
        from core.security.token_blacklist import TokenBlacklist
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            bl = TokenBlacklist(db_path=tmp_path)
            bl.revoke_all_sessions(reason="test")
            assert bl.is_globally_revoked() is True
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_count_active(self):
        from core.security.token_blacklist import TokenBlacklist
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            bl = TokenBlacklist(db_path=tmp_path)
            bl.revoke("jti-1", expires_at=9999999999)
            bl.revoke("jti-2", expires_at=9999999999)
            assert bl.count_active() >= 2
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_generate_jti_unique(self):
        from core.security.token_blacklist import generate_jti
        jtis = {generate_jti() for _ in range(100)}
        assert len(jtis) == 100, "all JTIs should be unique"

    def test_empty_jti_not_revoked(self):
        from core.security.token_blacklist import TokenBlacklist
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)
        try:
            bl = TokenBlacklist(db_path=tmp_path)
            assert bl.is_revoked("") is False
        finally:
            tmp_path.unlink(missing_ok=True)


# ── JWT Auth Router Tests ─────────────────────────────────────────────────────

class TestAuthJWTRouter:
    """Test the JWT auth endpoints."""

    def test_import(self):
        from core.api.routers.auth_jwt import router, LoginRequest, TokenResponse
        assert router is not None
        assert router.prefix == "/auth/jwt"

    def test_login_request_model(self):
        from core.api.routers.auth_jwt import LoginRequest
        req = LoginRequest(api_key="test-key", device="laptop")
        assert req.api_key == "test-key"
        assert req.device == "laptop"

    def test_token_response_model(self):
        from core.api.routers.auth_jwt import TokenResponse
        resp = TokenResponse(
            access_token="a",
            refresh_token="r",
            expires_in=900,
            refresh_expires_in=1209600,
        )
        assert resp.token_type == "bearer"
        assert resp.expires_in == 900

    def test_refresh_request_model(self):
        from core.api.routers.auth_jwt import RefreshRequest
        req = RefreshRequest(refresh_token="test-token")
        assert req.refresh_token == "test-token"

    def test_revoke_request_model(self):
        from core.api.routers.auth_jwt import RevokeRequest
        req = RevokeRequest(all_sessions=True, reason="compromised")
        assert req.all_sessions is True
        assert req.reason == "compromised"


# ── JWT Integration Tests ─────────────────────────────────────────────────────

class TestJWTIntegration:
    """Integration tests for JWT with the API."""

    def test_jwt_manager_issue_and_verify(self):
        """Test that JWTManager can issue and verify tokens."""
        from core.collections.auth import JWTManager, AuthError

        jm = JWTManager(secret="test-secret-" + "x" * 30, access_ttl=300, refresh_ttl=86400)
        pair = jm.issue_pair("owner", "users", extra={"device": "laptop"})

        assert "token" in pair
        assert "refresh_token" in pair

        # Verify access token
        claims = jm.verify(pair["token"], expected_type="access")
        assert claims["sub"] == "owner"
        assert claims["device"] == "laptop"

        # Verify refresh token
        claims = jm.verify(pair["refresh_token"], expected_type="refresh")
        assert claims["sub"] == "owner"

    def test_jwt_manager_refresh(self):
        """Test token refresh flow."""
        from core.collections.auth import JWTManager

        jm = JWTManager(secret="test-secret-" + "x" * 30, access_ttl=300, refresh_ttl=86400)
        pair = jm.issue_pair("owner", "users")

        # Refresh should return a valid new pair
        new_pair = jm.refresh(pair["refresh_token"])
        assert "token" in new_pair
        assert "refresh_token" in new_pair
        # New tokens should be verifiable
        claims = jm.verify(new_pair["token"], expected_type="access")
        assert claims["sub"] == "owner"

    def test_jwt_expired_token_rejected(self):
        """Test that expired tokens are rejected."""
        from core.collections.auth import JWTManager, AuthError

        jm = JWTManager(secret="test-secret-" + "x" * 30, access_ttl=-10, refresh_ttl=-10)
        pair = jm.issue_pair("owner", "users")

        with pytest.raises(AuthError, match="expired"):
            jm.verify(pair["token"], expected_type="access")

    def test_jwt_wrong_type_rejected(self):
        """Test that tokens with wrong type are rejected."""
        from core.collections.auth import JWTManager, AuthError

        jm = JWTManager(secret="test-secret-" + "x" * 30, access_ttl=300, refresh_ttl=86400)
        pair = jm.issue_pair("owner", "users")

        # Try to verify access token as refresh
        with pytest.raises(AuthError, match="expected refresh"):
            jm.verify(pair["token"], expected_type="refresh")

    def test_jwt_invalid_signature_rejected(self):
        """Test that tokens with wrong signature are rejected."""
        from core.collections.auth import JWTManager, AuthError

        jm1 = JWTManager(secret="secret-one-" + "x" * 30, access_ttl=300)
        jm2 = JWTManager(secret="secret-two-" + "x" * 30, access_ttl=300)

        pair = jm1.issue_pair("owner", "users")

        # Verify with different secret should fail
        with pytest.raises(AuthError):
            jm2.verify(pair["token"], expected_type="access")


# ── Middleware Integration Tests ──────────────────────────────────────────────

class TestMiddlewareJWT:
    """Test that middleware accepts JWT access tokens."""

    def test_verify_jwt_access_token_function_exists(self):
        """Test that the middleware has the JWT verifier."""
        from core.api.middleware import _verify_jwt_access_token
        assert callable(_verify_jwt_access_token)

    def test_non_jwt_returns_false(self):
        """Test that non-JWT strings return False."""
        from core.api.middleware import _verify_jwt_access_token
        assert _verify_jwt_access_token("not-a-jwt") is False
        assert _verify_jwt_access_token("static-api-key") is False
        assert _verify_jwt_access_token("") is False

    def test_invalid_jwt_returns_false(self):
        """Test that invalid JWT returns False."""
        from core.api.middleware import _verify_jwt_access_token
        # JWT-shaped but invalid
        assert _verify_jwt_access_token("a.b.c") is False

    def test_public_paths_includes_jwt_login(self):
        """Test that /auth/jwt/login is in public paths."""
        from core.api.middleware import _PUBLIC_PATHS
        assert "/auth/jwt/login" in _PUBLIC_PATHS


# ── V1 Stage 6: Owner/Collection JWT Scope Closure ─────────────────────────────
#
# Root vulnerability (real, demonstrated, pre-fix): owner API JWTs and
# collection-scoped JWTs (core/collections/auth.py's JWTManager.issue_pair)
# both used the identical type="access" claim with nothing else
# distinguishing them, and core/api/middleware.py's _verify_jwt_access_token()
# only checked expected_type="access" plus revocation. A collection JWT
# therefore authenticated as full owner-equivalent global API access.
# Closure: owner tokens now carry token_scope="owner_api"; the middleware
# (and core/api/routers/auth_jwt.py's _extract_claims) additionally require
# token_scope=="owner_api", sub=="owner", no "collection" claim, and a
# non-empty jti.

class TestStage6OwnerCollectionScopeClosure:
    """Proves the owner/collection JWT collision is actually closed."""

    def test_real_collection_jwt_rejected_by_middleware(self):
        """The actual vulnerability: a genuinely-issued collection JWT
        (same shape any real POST /api/collections/{name}/auth-with-password
        response produces) must be rejected by the global API auth gate."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token

        jm = JWTManager()  # default construction — same secret resolution
        # the middleware's own JWTManager() call uses in production.
        pair = jm.issue_pair("rec_some_user", "users", extra={"email": "a@b.com"})

        assert _verify_jwt_access_token(pair["token"]) is False

    def test_correctly_scoped_owner_token_accepted(self):
        """A real owner token, shaped exactly like /auth/jwt/login issues
        it post-fix, must still be accepted."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token
        from core.security.token_blacklist import generate_jti
        import jwt as pyjwt
        import time

        jm = JWTManager()
        claims = {
            "sub": "owner",
            "device": "test-device",
            "auth_method": "api_key",
            "jti": generate_jti(),
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "type": "access",
            "token_scope": "owner_api",
        }
        token = pyjwt.encode(claims, jm.secret, algorithm="HS256")

        assert _verify_jwt_access_token(token) is True

    def test_owner_token_missing_scope_claim_rejected(self):
        """A pre-fix-shaped owner token (sub=owner, type=access, but no
        token_scope) must now be rejected too — expected_type="access"
        alone is exactly the collision being closed, so it can't be the
        sole bar even for a token that happens to be sub=="owner"."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token
        from core.security.token_blacklist import generate_jti
        import jwt as pyjwt
        import time

        jm = JWTManager()
        claims = {
            "sub": "owner",
            "jti": generate_jti(),
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "type": "access",
        }
        token = pyjwt.encode(claims, jm.secret, algorithm="HS256")

        assert _verify_jwt_access_token(token) is False

    def test_owner_scoped_token_without_jti_rejected(self):
        """jti used to be optional (a token with none silently skipped
        revocation checking); it is now mandatory."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token
        import jwt as pyjwt
        import time

        jm = JWTManager()
        claims = {
            "sub": "owner",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "type": "access",
            "token_scope": "owner_api",
        }
        token = pyjwt.encode(claims, jm.secret, algorithm="HS256")

        assert _verify_jwt_access_token(token) is False

    def test_collection_jwt_rejected_by_extract_claims(self):
        """core/api/routers/auth_jwt.py's _extract_claims (used by /me,
        /sessions, /revoke, /logout) must reject a real collection JWT."""
        from core.collections.auth import JWTManager
        from core.api.routers.auth_jwt import _extract_claims
        from fastapi import HTTPException

        jm = JWTManager()
        pair = jm.issue_pair("rec_some_user", "users")

        with pytest.raises(HTTPException) as exc_info:
            _extract_claims(pair["token"], expected_type="access")
        assert exc_info.value.status_code == 401

    def test_owner_token_accepted_by_extract_claims(self):
        from core.collections.auth import JWTManager
        from core.api.routers.auth_jwt import _extract_claims
        from core.security.token_blacklist import generate_jti
        import jwt as pyjwt
        import time

        jm = JWTManager()
        claims_in = {
            "sub": "owner",
            "jti": generate_jti(),
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "type": "access",
            "token_scope": "owner_api",
        }
        token = pyjwt.encode(claims_in, jm.secret, algorithm="HS256")

        claims_out = _extract_claims(token, expected_type="access")
        assert claims_out["sub"] == "owner"

    def test_refresh_tokens_still_never_authenticate_as_access(self):
        """Unchanged guarantee, reconfirmed: a refresh token (owner or
        collection) must never pass as an access token."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token

        jm = JWTManager()
        pair = jm.issue_pair("owner", "users")

        assert _verify_jwt_access_token(pair["refresh_token"]) is False

    def test_refresh_endpoint_does_not_propagate_owner_scope_to_collection_token(self):
        """A collection refresh token exchanged at /auth/jwt/refresh must be
        rejected outright (round-3 hardening, 2026-09-23) -- this is the
        OWNER refresh endpoint and has no legitimate reason to process a
        collection token at all."""
        from core.collections.auth import JWTManager
        import asyncio
        from fastapi import HTTPException

        jm = JWTManager()
        collection_pair = jm.issue_pair("rec_some_user", "users")

        import core.api.routers.auth_jwt as auth_jwt_mod
        with patch.object(auth_jwt_mod, "_get_jwt_manager", return_value=jm):
            from core.api.routers.auth_jwt import refresh, RefreshRequest
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(refresh(RefreshRequest(refresh_token=collection_pair["refresh_token"])))
        assert exc_info.value.status_code == 401

    def test_refresh_endpoint_rejects_owner_sub_collection_token(self):
        """Adversarial case an independent review caught: a collection
        refresh token issued with sub="owner" (issue_pair("owner", "users")
        — a collection record literally named/id'd "owner") carries both
        sub=="owner" AND a "collection" claim. Checking sub alone would
        wrongly treat this as an owner refresh token. Round-3 hardening:
        this is now rejected outright rather than merely minted an unscoped
        (still owner-unusable) pair."""
        from core.collections.auth import JWTManager
        import asyncio
        from fastapi import HTTPException

        jm = JWTManager()
        adversarial_pair = jm.issue_pair("owner", "users")
        assert "collection" in jm.verify(adversarial_pair["refresh_token"], expected_type="refresh")

        import core.api.routers.auth_jwt as auth_jwt_mod
        with patch.object(auth_jwt_mod, "_get_jwt_manager", return_value=jm):
            from core.api.routers.auth_jwt import refresh, RefreshRequest
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(refresh(RefreshRequest(refresh_token=adversarial_pair["refresh_token"])))
        assert exc_info.value.status_code == 401

    def test_refresh_chain_cannot_manufacture_owner_scope(self):
        """Second independent-review finding: rotating an adversarial
        sub="owner"+collection="users" refresh token once used to drop the
        "collection" claim from the ROTATED refresh token while keeping
        sub=="owner" — a naive sub/collection re-check on the next hop
        would then treat that rotated refresh token as a real owner token
        and mint a scoped access token on a SECOND refresh call. Real
        owner refresh tokens now carry token_scope=="owner_api" from the
        moment they're issued at /login and that marker (not a re-derived
        sub/collection check) is what propagates on each hop, so no
        rotation depth can manufacture it from a collection token. Round-3
        hardening: the FIRST hop is now rejected outright (still has a
        "collection" claim), so the chain never gets a rotated token to
        retry with in the first place."""
        from core.collections.auth import JWTManager
        import asyncio
        from fastapi import HTTPException

        jm = JWTManager()
        adversarial_pair = jm.issue_pair("owner", "users")

        import core.api.routers.auth_jwt as auth_jwt_mod
        with patch.object(auth_jwt_mod, "_get_jwt_manager", return_value=jm):
            from core.api.routers.auth_jwt import refresh, RefreshRequest

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(refresh(RefreshRequest(refresh_token=adversarial_pair["refresh_token"])))
            assert exc_info.value.status_code == 401

    def test_genuine_owner_refresh_chain_keeps_working(self):
        """Control: a REAL owner refresh token (as /login actually issues
        it, token_scope="owner_api" included) must keep minting valid
        scoped access tokens across repeated rotation -- the round-2 fix
        must not break legitimate long-lived owner sessions."""
        from core.collections.auth import JWTManager
        from core.api.middleware import _verify_jwt_access_token
        from core.security.token_blacklist import generate_jti
        import jwt as pyjwt
        import asyncio
        import time

        jm = JWTManager()
        owner_refresh_claims = {
            "sub": "owner",
            "device": "test",
            "jti": generate_jti(),
            "iat": int(time.time()),
            "exp": int(time.time()) + 86400,
            "type": "refresh",
            "token_scope": "owner_api",
        }
        refresh_token = pyjwt.encode(owner_refresh_claims, jm.secret, algorithm="HS256")

        import core.api.routers.auth_jwt as auth_jwt_mod
        with patch.object(auth_jwt_mod, "_get_jwt_manager", return_value=jm):
            from core.api.routers.auth_jwt import refresh, RefreshRequest

            first = asyncio.run(refresh(RefreshRequest(refresh_token=refresh_token)))
            assert _verify_jwt_access_token(first.access_token) is True

            second = asyncio.run(refresh(RefreshRequest(refresh_token=first.refresh_token)))
            assert _verify_jwt_access_token(second.access_token) is True


# ── Full Flow Test ────────────────────────────────────────────────────────────

class TestFullJWTFlow:
    """End-to-end JWT flow test."""

    def test_full_login_refresh_revoke_flow(self):
        """Test the complete JWT lifecycle: login → refresh → revoke."""
        from core.collections.auth import JWTManager
        from core.security.token_blacklist import TokenBlacklist, generate_jti
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            # Setup
            secret = "test-secret-" + "x" * 30
            jm = JWTManager(secret=secret, access_ttl=300, refresh_ttl=86400)
            bl = TokenBlacklist(db_path=tmp_path)

            # 1. Login — issue token pair WITH jti (like auth_jwt.py does)
            now = datetime.now(timezone.utc)
            jti_access = generate_jti()
            jti_refresh = generate_jti()

            access_claims = {
                "sub": "owner", "device": "laptop", "jti": jti_access,
                "iat": int(now.timestamp()),
                "exp": int(now.timestamp()) + 300,
                "type": "access",
            }
            refresh_claims = {
                "sub": "owner", "device": "laptop", "jti": jti_refresh,
                "iat": int(now.timestamp()),
                "exp": int(now.timestamp()) + 86400,
                "type": "refresh",
            }
            access_token = pyjwt.encode(access_claims, secret, algorithm="HS256")
            refresh_token = pyjwt.encode(refresh_claims, secret, algorithm="HS256")

            # 2. Verify access token works
            claims = jm.verify(access_token, expected_type="access")
            assert claims["sub"] == "owner"
            assert claims["jti"] == jti_access

            # 3. Revoke the refresh token by jti
            bl.revoke(jti_refresh, expires_at=refresh_claims["exp"], reason="logout")

            # 4. Revoked token should be detected
            assert bl.is_revoked(jti_refresh) is True

            # 5. Access token should NOT be revoked (different jti)
            assert bl.is_revoked(jti_access) is False

        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    # Run self-tests
    pytest.main([__file__, "-v", "--tb=short"])
