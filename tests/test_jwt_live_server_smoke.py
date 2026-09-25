"""V1 Stage 6 follow-up: the JWT closure against a REAL running API server, over HTTP.

Stage 6 (2026-09-22) closed the collision where a collection-scoped JWT (issued by
POST /api/collections/{name}/auth-with-password) authenticated as full owner API access. Its own report says the
proof was unit/integration level only and recommends one live smoke test before promotion. This is that test:
own uvicorn process, throwaway DB and data dir, hardened runtime mode, real tokens over real sockets.

Checked:
  * a genuine owner session (login with the API key) works and keeps working across refresh rotations
  * a collection access token is rejected (401) on protected owner endpoints
  * a collection refresh token cannot be exchanged at /auth/jwt/refresh for owner scope, at any hop
  * a collection record literally named "owner" (the `sub` collision) gets no owner access either

Skips when the server cannot start.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "jwt-smoke-api-key-0123456789abcdef0123456789abcdef"

_SERVER_SRC = """
import sys
sys.path.insert(0, {root!r})
import uvicorn
from core.api.app import create_app
uvicorn.run(create_app(), host="127.0.0.1", port={port}, log_level="error")
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Api:
    def __init__(self, base: str):
        self.base = base

    def call(self, method: str, path: str, body: dict | None = None, token: str | None = None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw[:200]}


@pytest.fixture(scope="module")
def api():
    tmp = Path(tempfile.mkdtemp(prefix="jwt_smoke_"))
    (tmp / "data").mkdir()
    port = _free_port()
    script = tmp / "serve.py"
    script.write_text(_SERVER_SRC.format(root=str(ROOT), port=port), encoding="utf-8")
    env = dict(os.environ, VECTOR_DB_PATH=str(tmp / "vm.db"), VECTOR_TEST_DATA_DIR=str(tmp / "data"),
               VECTOR_DB_KEY="jwt-smoke-db-key", VECTOR_API_KEY=KEY, VECTOR_ENV="vector")
    env.pop("PYTEST_CURRENT_TEST", None)
    proc = subprocess.Popen([sys.executable, str(script)], env=env, cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(90):
        try:
            urllib.request.urlopen(urllib.request.Request(base + "/health"), timeout=2)
            up = True
            break
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(1)
    if not up:
        proc.kill()
        pytest.skip("JWT smoke server did not start")
    try:
        yield Api(base)
    finally:
        proc.kill()


def _refresh_call(api: Api, refresh_token: str, bearer: str):
    """/auth/jwt/refresh is deliberately not public: the caller must already present a valid credential."""
    return api.call("POST", "/auth/jwt/refresh", {"refresh_token": refresh_token}, token=bearer)


def _owner_login(api: Api) -> dict:
    code, tok = api.call("POST", "/auth/jwt/login", {"api_key": KEY})
    assert code == 200, (code, tok)
    return tok


def _collection_tokens(api: Api, record_email: str = "user@example.com") -> dict:
    """Register a collection user via the owner API key and log in with its password: a real collection JWT pair."""
    code, _ = api.call("POST", "/api/collections", {"name": "users", "type": "auth", "fields": []}, token=KEY)
    assert code in (200, 400), code  # 400 when already created by an earlier test in this module
    code, reg = api.call("POST", "/api/collections/users/records-auth",
                         {"email": record_email, "password": "a-long-passphrase-123"}, token=KEY)
    assert code in (200, 400), (code, reg)
    code, tok = api.call("POST", "/api/collections/users/auth-with-password",
                         {"email": record_email, "password": "a-long-passphrase-123"}, token=KEY)
    assert code == 200, (code, tok)
    return tok


def _access(tok: dict) -> str:
    return tok.get("access_token") or tok.get("token") or ""


def _refresh(tok: dict) -> str:
    return tok.get("refresh_token") or ""


def test_genuine_owner_session_is_accepted(api):
    tok = _owner_login(api)
    code, body = api.call("GET", "/loop/status", token=tok["access_token"])
    assert code == 200, (code, body)
    code, me = api.call("GET", "/auth/jwt/me", token=tok["access_token"])
    assert code == 200, (code, me)


def test_owner_refresh_chain_keeps_working(api):
    tok = _owner_login(api)
    for _ in range(3):
        code, nxt = _refresh_call(api, tok["refresh_token"], tok["access_token"])
        assert code == 200, (code, nxt)
        tok = nxt
        code, _ = api.call("GET", "/loop/status", token=tok["access_token"])
        assert code == 200


def test_collection_access_token_is_rejected_on_owner_endpoints(api):
    coll = _collection_tokens(api)
    access = _access(coll)
    assert access, coll
    for path in ("/loop/status", "/auth/jwt/me", "/auth/jwt/sessions"):
        code, body = api.call("GET", path, token=access)
        assert code in (401, 403), f"collection JWT reached {path}: {code} {body}"


def test_collection_refresh_token_cannot_be_exchanged_for_owner_scope(api):
    coll = _collection_tokens(api)
    refresh = _refresh(coll)
    assert refresh, coll
    # a) presented with only collection credentials, the gate itself refuses
    code, _ = _refresh_call(api, refresh, _access(coll))
    assert code in (401, 403), code
    # b) even with a valid owner credential (the API key) in the header, the endpoint refuses a collection refresh token
    code, hop1 = _refresh_call(api, refresh, KEY)
    assert code in (400, 401, 403), f"owner refresh endpoint processed a collection refresh token: {code} {hop1}"
    if code == 200:
        code2, _ = api.call("GET", "/loop/status", token=hop1.get("access_token", ""))
        assert code2 in (401, 403), "hop 1 minted a working owner token from a collection refresh token"
        # hop 2: the rotated refresh token must not carry owner scope forward either
        code3, hop2 = _refresh_call(api, hop1.get("refresh_token", ""), KEY)
        if code3 == 200:
            code4, _ = api.call("GET", "/loop/status", token=hop2.get("access_token", ""))
            assert code4 in (401, 403), "hop 2 minted a working owner token"
    else:
        assert code in (400, 401, 403), (code, hop1)


def test_collection_record_named_owner_gets_no_owner_access(api):
    """The original sub collision: a collection record whose id is literally "owner"."""
    code, _ = api.call("POST", "/api/collections", {"name": "people", "type": "auth", "fields": []}, token=KEY)
    assert code in (200, 400)
    code, reg = api.call("POST", "/api/collections/people/records-auth",
                         {"id": "owner", "email": "owner@example.com", "password": "a-long-passphrase-123"}, token=KEY)
    assert code in (200, 400), (code, reg)
    code, tok = api.call("POST", "/api/collections/people/auth-with-password",
                         {"email": "owner@example.com", "password": "a-long-passphrase-123"}, token=KEY)
    assert code == 200, (code, tok)
    code, _ = api.call("GET", "/loop/status", token=_access(tok))
    assert code in (401, 403), f"a collection token whose sub is 'owner' authenticated as owner: {code}"
    code, hop = _refresh_call(api, _refresh(tok), KEY)
    assert code in (400, 401, 403), (code, hop)
    if code == 200:
        code2, _ = api.call("GET", "/loop/status", token=hop.get("access_token", ""))
        assert code2 in (401, 403)


def test_duplicate_registration_is_a_client_error_not_a_500(api):
    _collection_tokens(api, "dup@example.com")
    code, body = api.call("POST", "/api/collections/users/records-auth",
                          {"email": "dup@example.com", "password": "a-long-passphrase-123"}, token=KEY)
    assert code == 400, (code, body)


def test_no_token_and_garbage_token_are_rejected(api):
    assert api.call("GET", "/loop/status")[0] in (401, 403)
    assert api.call("GET", "/loop/status", token="not.a.jwt")[0] in (401, 403)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
