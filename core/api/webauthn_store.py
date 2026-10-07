"""Local storage for VECTOR's WebAuthn (passkey / fingerprint / Windows Hello)
credentials.

Single-user, single-machine personal project — this is deliberately a flat
JSON file, not a database table, matching the existing ~/.vector_ca/<area>/
convention used elsewhere (e.g. core/metering/quota_ledger.py). A registered
credential's PUBLIC key lives here; the private key never leaves the
authenticator (the fingerprint sensor / Windows Hello / phone), by design —
that's the whole point of WebAuthn over a shared secret like VECTOR_API_KEY.

Added as part of the per-district/subsystem polish pass (2026-07-27) after
the owner asked for biometric auth instead of pasting a static key around.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

__all__ = [
    "load_credentials",
    "save_credential",
    "get_credential",
    "update_sign_count",
    "delete_credential",
    "credentials_path",
]

_LOCK = Lock()


def credentials_path() -> Path:
    vector_home = os.environ.get("VECTOR_HOME") or str(Path.home() / ".vector_ca")
    return Path(vector_home) / "auth" / "webauthn_credentials.json"


def _read_raw() -> dict[str, Any]:
    path = credentials_path()
    if not path.exists():
        return {"credentials": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "credentials" not in data:
            return {"credentials": {}}
        return data
    except Exception as e:
        logger.warning("[VECTOR][webauthn_store] failed to read {}: {}", path, e)
        return {"credentials": {}}


def _write_raw(data: dict[str, Any]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # atomic on both Windows and POSIX


def load_credentials() -> dict[str, dict[str, Any]]:
    """Return {credential_id_b64url: {public_key_b64url, sign_count, name, created_at}}."""
    with _LOCK:
        return dict(_read_raw().get("credentials", {}))


def save_credential(credential_id_b64url: str, public_key_b64url: str,
                     sign_count: int, name: str = "passkey") -> None:
    with _LOCK:
        data = _read_raw()
        data.setdefault("credentials", {})[credential_id_b64url] = {
            "public_key": public_key_b64url,
            "sign_count": sign_count,
            "name": name,
            "created_at": time.time(),
        }
        _write_raw(data)
    logger.info("[VECTOR][webauthn_store] credential registered: {}", credential_id_b64url[:12] + "...")


def get_credential(credential_id_b64url: str) -> dict[str, Any] | None:
    with _LOCK:
        return _read_raw().get("credentials", {}).get(credential_id_b64url)


def update_sign_count(credential_id_b64url: str, new_count: int) -> None:
    with _LOCK:
        data = _read_raw()
        cred = data.get("credentials", {}).get(credential_id_b64url)
        if cred is not None:
            cred["sign_count"] = new_count
            _write_raw(data)


def delete_credential(credential_id_b64url: str) -> bool:
    with _LOCK:
        data = _read_raw()
        if credential_id_b64url in data.get("credentials", {}):
            del data["credentials"][credential_id_b64url]
            _write_raw(data)
            return True
        return False


if __name__ == "__main__":
    import sys as _sys
    import tempfile
    _sys.stdout.reconfigure(encoding="utf-8")

    # Smoke test against a throwaway VECTOR_HOME so we never touch the real store.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["VECTOR_HOME"] = tmp
        assert load_credentials() == {}
        save_credential("cred-abc", "pubkey-xyz", sign_count=0, name="Windows Hello")
        creds = load_credentials()
        assert "cred-abc" in creds and creds["cred-abc"]["sign_count"] == 0
        update_sign_count("cred-abc", 5)
        assert get_credential("cred-abc")["sign_count"] == 5
        assert get_credential("missing") is None
        assert delete_credential("cred-abc") is True
        assert delete_credential("cred-abc") is False
        assert load_credentials() == {}
    print("[OK] webauthn_store.py OK")
