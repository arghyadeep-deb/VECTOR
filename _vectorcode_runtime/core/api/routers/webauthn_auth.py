"""VECTOR WebAuthn (passkey / fingerprint / Windows Hello) authentication.

Adds a second way to authenticate to the API besides the static VECTOR_API_KEY
bearer token: a real biometric-backed credential via the browser's WebAuthn
API (navigator.credentials.create/get). The authenticator's private key never
leaves the device (fingerprint sensor, Windows Hello, phone Face/Touch ID) —
only a signed public-key assertion crosses the wire, so there is no long-lived
shared secret to leak (the exact problem a static API key has, and the exact
thing that prompted this: the owner pasted VECTOR_API_KEY in plaintext into a
chat transcript this session).

Endpoints:
    POST /auth/webauthn/register/options  (localhost-only) — start enrolling
        a new authenticator.
    POST /auth/webauthn/register/verify   (localhost-only) — finish enrolling;
        stores the public key.
    POST /auth/webauthn/login/options     (PUBLIC) — start a login ceremony.
        Must be public: this is how you authenticate *without* already
        holding VECTOR_API_KEY, so it can't itself require that key.
    POST /auth/webauthn/login/verify      (PUBLIC) — finish login; on success
        issues a short-lived JWT (signed with VECTOR_JWT_SECRET, reusing
        core.collections.auth.JWTManager) that middleware.auth_middleware
        accepts as an alternative to the static key.

Registration stays localhost-only (same posture as /keys/* in keys.py) so a
remote attacker on the LAN/internet can't enroll their own fingerprint as a
trusted credential — only someone with physical/localhost access to the
laptop can add a new passkey.

IMPORTANT — not yet live-tested. Built without access to a running backend or
a real browser+authenticator this session (see KNOWN_ISSUES.md). Needs, in
order: `pip install -r requirements.txt` (for the `webauthn` package),
a real registration ceremony in a browser at http://localhost:8000, then a
login ceremony, then confirming a request using the returned JWT as a Bearer
token passes auth_middleware.

WebAuthn browser constraint (real, not a VECTOR limitation): browsers only
allow WebAuthn on "secure contexts" — https://, or the special-cased
http://localhost. It will NOT work over the LAN firewall's http://<LAN-IP>:8000
URL from your phone unless VECTOR is also running with TLS (uvicorn_ssl_kwargs
in run_vector.py already supports this — see docs there for cert setup). Until
TLS is configured, passkey login only works from the browser on the machine
running VECTOR itself; phone/LAN access still needs the static API key.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from core.api import webauthn_store

router = APIRouter(prefix="/auth/webauthn", tags=["webauthn"])

# rp_id must be a domain the browser is actually loading the page from — the
# "localhost" special-case is what makes this work over plain HTTP without
# TLS. Override via env if VECTOR is served from a real domain behind TLS.
_RP_ID = os.environ.get("VECTOR_WEBAUTHN_RP_ID", "localhost")
_RP_NAME = "VECTOR"
_ORIGIN = os.environ.get("VECTOR_WEBAUTHN_ORIGIN", "http://localhost:8000")
_OWNER_USER_ID = b"vector-owner"  # single-user system — one fixed identity
_OWNER_USER_NAME = "owner"
_CHALLENGE_TTL_SEC = 300  # 5 minutes to complete a ceremony

# Single-slot pending-challenge state — fine for a single-user, single-process
# system (same simplification middleware.py's own CSRF store already uses).
_pending: dict[str, tuple[bytes, float]] = {}


def _require_localhost(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Passkey enrollment is localhost-only")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _from_b64url(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _store_challenge(kind: str, challenge: bytes) -> None:
    now = time.time()
    # opportunistic cleanup of stale entries
    for k in [k for k, (_, ts) in _pending.items() if now - ts > _CHALLENGE_TTL_SEC]:
        del _pending[k]
    _pending[kind] = (challenge, now)


def _pop_challenge(kind: str) -> bytes:
    entry = _pending.pop(kind, None)
    if entry is None:
        raise HTTPException(status_code=400, detail="No pending ceremony — call the options endpoint first")
    challenge, ts = entry
    if time.time() - ts > _CHALLENGE_TTL_SEC:
        raise HTTPException(status_code=400, detail="Ceremony expired — start over")
    return challenge


# ── Registration (enroll a new passkey) — localhost-only ──────────────────

@router.post("/register/options")
async def register_options(request: Request):
    _require_localhost(request)
    try:
        import webauthn
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    except ImportError as e:
        raise HTTPException(status_code=501,
                             detail=f"webauthn package not installed: {e}. Run: pip install webauthn") from e

    existing_ids = [_from_b64url(cid) for cid in webauthn_store.load_credentials().keys()]
    options = webauthn.generate_registration_options(
        rp_id=_RP_ID,
        rp_name=_RP_NAME,
        user_id=_OWNER_USER_ID,
        user_name=_OWNER_USER_NAME,
        user_display_name="VECTOR owner",
        exclude_credentials=[PublicKeyCredentialDescriptor(id=cid) for cid in existing_ids],
    )
    _store_challenge("register", options.challenge)
    # options_to_json() already returns a JSON STRING — returning it as-is
    # from a FastAPI endpoint double-encodes it into a quoted string body
    # instead of a JSON object (caught by tests/backend/test_webauthn_auth.py).
    # Parse it back into a dict so FastAPI serializes it as a real object.
    import json as _json
    return _json.loads(webauthn.options_to_json(options))


@router.post("/register/verify")
async def register_verify(request: Request):
    _require_localhost(request)
    try:
        import webauthn
        from webauthn.helpers import parse_registration_credential_json
    except ImportError as e:
        raise HTTPException(status_code=501,
                             detail=f"webauthn package not installed: {e}. Run: pip install webauthn") from e

    # Read the raw body ONCE — this is the browser's PublicKeyCredential
    # response JSON as-is (navigator.credentials.create() result), not a
    # custom wrapper, so it can be handed straight to the library's own
    # parser. A friendly label comes from the User-Agent instead of a body
    # field, to avoid inventing a non-standard wire shape the frontend would
    # have to match.
    raw_body = await request.body()
    challenge = _pop_challenge("register")
    try:
        # parse_registration_credential_json wants str or dict, not bytes.
        credential = parse_registration_credential_json(raw_body.decode("utf-8"))
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_RP_ID,
            expected_origin=_ORIGIN,
        )
    except Exception as e:
        logger.warning("[VECTOR][webauthn] registration verify failed: {}", e)
        raise HTTPException(status_code=400, detail=f"Registration verification failed: {e}") from e

    ua = request.headers.get("user-agent", "")
    label = "Windows Hello" if "Windows" in ua else ("Touch ID / Face ID" if "Mac" in ua or "iPhone" in ua else "passkey")

    webauthn_store.save_credential(
        credential_id_b64url=_b64url(verification.credential_id),
        public_key_b64url=_b64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        name=label,
    )
    return {"status": "registered", "name": label}


# ── Login (authenticate with an enrolled passkey) — PUBLIC ────────────────
# Must be public: this is the credential-free entry point. Registration
# above stays gated so only someone at the machine can add a trusted
# authenticator in the first place; login only ever succeeds against an
# already-enrolled credential's public key, so opening this endpoint up
# doesn't let a stranger create access — it lets an *enrolled* device use it.

@router.post("/login/options")
async def login_options():
    try:
        import webauthn
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    except ImportError as e:
        raise HTTPException(status_code=501,
                             detail=f"webauthn package not installed: {e}. Run: pip install webauthn") from e

    creds = webauthn_store.load_credentials()
    if not creds:
        raise HTTPException(status_code=404, detail="No passkey enrolled yet — register one from localhost first")

    allow_credentials = [PublicKeyCredentialDescriptor(id=_from_b64url(cid)) for cid in creds.keys()]
    options = webauthn.generate_authentication_options(
        rp_id=_RP_ID,
        allow_credentials=allow_credentials,
    )
    _store_challenge("login", options.challenge)
    import json as _json
    return _json.loads(webauthn.options_to_json(options))


@router.post("/login/verify")
async def login_verify(request: Request):
    try:
        import webauthn
        from webauthn.helpers import parse_authentication_credential_json
    except ImportError as e:
        raise HTTPException(status_code=501,
                             detail=f"webauthn package not installed: {e}. Run: pip install webauthn") from e

    challenge = _pop_challenge("login")
    raw_body = await request.body()
    try:
        # parse_authentication_credential_json wants str or dict, not bytes.
        credential = parse_authentication_credential_json(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed credential: {e}") from e

    cred_id_b64url = _b64url(credential.raw_id)
    stored = webauthn_store.get_credential(cred_id_b64url)
    if stored is None:
        raise HTTPException(status_code=401, detail="Unknown credential")

    try:
        verification = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_RP_ID,
            expected_origin=_ORIGIN,
            credential_public_key=_from_b64url(stored["public_key"]),
            credential_current_sign_count=stored["sign_count"],
        )
    except Exception as e:
        logger.warning("[VECTOR][webauthn] login verify failed: {}", e)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}") from e

    # Clone-authenticator detection: a legitimate authenticator's sign_count
    # strictly increases on every use. If a stored/cloned authenticator ever
    # produces a count <= what we last saw, someone duplicated it.
    webauthn_store.update_sign_count(cred_id_b64url, verification.new_sign_count)

    from core.collections.auth import JWTManager
    jwt_mgr = JWTManager(access_ttl=3600 * 12)  # 12h session, re-auth via passkey after
    token = jwt_mgr.issue({"sub": "vector-owner", "via": "webauthn"}, jwt_mgr.access_ttl, "webauthn_session")

    resp = JSONResponse({"token": token, "expires_in": jwt_mgr.access_ttl, "token_type": "Bearer"})
    # Also drop the session as the vector_key cookie — mirrors the ?key= flow
    # in middleware.auth_middleware. Without this, a browser that just logged
    # in via passkey still can't load /hud/ itself on the NEXT navigation: the
    # page's own GET request goes through auth_middleware server-side, before
    # any client JS runs, so sessionStorage/window.VECTOR_CONFIG (set by
    # webauthn.js) can't help — only a cookie the browser sends automatically
    # does. HttpOnly so page JS can't read it (same posture as the query-param
    # cookie); short-lived to match the JWT's own 12h TTL rather than the
    # query-param cookie's 30 days, since re-auth here is just a passkey tap.
    resp.set_cookie(
        "vector_key", token,
        max_age=jwt_mgr.access_ttl,
        httponly=True, samesite="lax", path="/",
    )
    return resp


@router.get("/status")
async def webauthn_status(request: Request):
    """Whether any passkey is enrolled yet (no secrets returned)."""
    creds = webauthn_store.load_credentials()
    return {
        "enrolled": len(creds) > 0,
        "count": len(creds),
        "names": [c.get("name", "passkey") for c in creds.values()],
        "rp_id": _RP_ID,
        "note": "WebAuthn only works from a secure context: https://, or "
                "http://localhost specifically. LAN-IP access still needs "
                "VECTOR_API_KEY until TLS is configured.",
    }


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    print("[OK] webauthn_auth.py router module loads (webauthn/pypi package availability not checked here)")
