"""End-to-end test for core/api/routers/webauthn_auth.py using a simulated
software authenticator (real ES256 crypto, real CBOR attestation/assertion
objects) — the same shape a browser's navigator.credentials.create()/get()
would send, hand-built here since there's no real browser+fingerprint sensor
available in this test environment.

This exercises the exact verify_registration_response / verify_authentication_
response calls the live endpoints use, not just their surrounding HTTP glue —
if this test passes, the cryptographic path is proven correct; what's NOT
proven is a real browser's exact JSON serialization quirks or an actual
physical authenticator ceremony (see KNOWN_ISSUES.md — still flagged as
needing one real live registration+login from an actual browser).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _from_b64url(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _cose_key(pub_numbers) -> bytes:
    x = pub_numbers.x.to_bytes(32, "big")
    y = pub_numbers.y.to_bytes(32, "big")
    return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: x, -3: y})  # EC2 / ES256 / P-256


def _auth_data(rp_id: str, sign_count: int, *, attested_cred: tuple[bytes, bytes] | None,
                user_verified: bool = True) -> bytes:
    rp_id_hash = hashlib.sha256(rp_id.encode()).digest()
    flags = 0x01  # UP
    if user_verified:
        flags |= 0x04  # UV
    body = rp_id_hash + bytes([flags]) + sign_count.to_bytes(4, "big")
    if attested_cred is not None:
        cred_id, cose_pubkey = attested_cred
        flags_byte = bytes([flags | 0x40])  # AT
        body = rp_id_hash + flags_byte + sign_count.to_bytes(4, "big")
        body += b"\x00" * 16  # aaguid
        body += len(cred_id).to_bytes(2, "big")
        body += cred_id
        body += cose_pubkey
    return body


@pytest.fixture()
def app_client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("VECTOR_HOME", tmp)
    monkeypatch.setenv("VECTOR_JWT_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.setenv("VECTOR_WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setenv("VECTOR_WEBAUTHN_ORIGIN", "http://localhost:8000")

    # Import after env vars are set so the router picks up the test RP config.
    import importlib
    from core.api.routers import webauthn_auth as wa
    importlib.reload(wa)
    from core.api import webauthn_store
    importlib.reload(webauthn_store)

    app = FastAPI()
    app.include_router(wa.router)
    client = TestClient(app)
    yield client, wa


def test_full_registration_and_login_ceremony(app_client):
    client, wa = app_client

    # ── Registration ────────────────────────────────────────────────
    options_resp = client.post("/auth/webauthn/register/options")
    assert options_resp.status_code == 200, options_resp.text
    options = options_resp.json()
    challenge = options["challenge"]

    private_key = ec.generate_private_key(ec.SECP256R1())
    credential_id = os.urandom(32)
    cose_pubkey = _cose_key(private_key.public_key().public_numbers())

    client_data = json.dumps({
        "type": "webauthn.create",
        "challenge": challenge,
        "origin": "http://localhost:8000",
        "crossOrigin": False,
    }).encode()

    auth_data = _auth_data("localhost", sign_count=0, attested_cred=(credential_id, cose_pubkey))
    attestation_object = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})

    reg_body = {
        "id": _b64url(credential_id),
        "rawId": _b64url(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": _b64url(client_data),
            "attestationObject": _b64url(attestation_object),
        },
    }
    verify_resp = client.post("/auth/webauthn/register/verify", content=json.dumps(reg_body))
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["status"] == "registered"

    status_resp = client.get("/auth/webauthn/status")
    assert status_resp.json()["enrolled"] is True
    assert status_resp.json()["count"] == 1

    # Replaying the same registration challenge must fail (already consumed).
    replay = client.post("/auth/webauthn/register/verify", content=json.dumps(reg_body))
    assert replay.status_code == 400

    # ── Login ───────────────────────────────────────────────────────
    login_opts_resp = client.post("/auth/webauthn/login/options")
    assert login_opts_resp.status_code == 200, login_opts_resp.text
    login_challenge = login_opts_resp.json()["challenge"]

    login_client_data = json.dumps({
        "type": "webauthn.get",
        "challenge": login_challenge,
        "origin": "http://localhost:8000",
        "crossOrigin": False,
    }).encode()
    login_auth_data = _auth_data("localhost", sign_count=1, attested_cred=None)
    signed_payload = login_auth_data + hashlib.sha256(login_client_data).digest()
    signature = private_key.sign(signed_payload, ec.ECDSA(hashes.SHA256()))

    login_body = {
        "id": _b64url(credential_id),
        "rawId": _b64url(credential_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": _b64url(login_client_data),
            "authenticatorData": _b64url(login_auth_data),
            "signature": _b64url(signature),
        },
    }
    login_verify_resp = client.post("/auth/webauthn/login/verify", content=json.dumps(login_body))
    assert login_verify_resp.status_code == 200, login_verify_resp.text
    payload = login_verify_resp.json()
    assert payload["token_type"] == "Bearer"
    assert isinstance(payload["token"], str) and len(payload["token"]) > 20

    # The issued token must actually verify against JWTManager (what
    # middleware.auth_middleware will use to accept it as an alternative to
    # the static VECTOR_API_KEY).
    from core.collections.auth import JWTManager
    claims = JWTManager().verify(payload["token"], expected_type="webauthn_session")
    assert claims["sub"] == "vector-owner"


def test_login_rejects_unknown_credential(app_client):
    client, wa = app_client
    # No registration happened — login/options should 404 (nothing enrolled).
    resp = client.post("/auth/webauthn/login/options")
    assert resp.status_code == 404


def test_registration_is_localhost_only(app_client):
    client, wa = app_client
    resp = client.post(
        "/auth/webauthn/register/options",
        headers={"X-Forwarded-For": "8.8.8.8"},
    )
    # TestClient's request.client.host is "testclient" regardless of headers
    # (no real proxy in front of it), so this documents the intent rather
    # than proving remote-IP rejection — the same limitation keys.py's own
    # _require_localhost has under TestClient. Real enforcement is the
    # request.client.host check itself, unit-provable directly:
    from core.api.routers.webauthn_auth import _require_localhost
    from fastapi import HTTPException
    class _FakeClient:
        host = "203.0.113.5"
    class _FakeRequest:
        client = _FakeClient()
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(_FakeRequest())
    assert exc_info.value.status_code == 403


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
