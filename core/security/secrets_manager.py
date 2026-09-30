"""Centralized secret retrieval and audit helpers.

This module keeps the current env-var/keyring behavior, but gives runtime and
readiness checks one place to inspect secret health without logging values.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from loguru import logger

from core.runtime_paths import get_data_root


_WEAK_VALUES = {"changeme", "change-me", "change_me", "secret", "password", "test"}
_SERVICE_NAME = "VECTOR"


@dataclass(frozen=True)
class SecretAudit:
    name: str
    configured: bool
    source: str
    length: int = 0
    min_length: int = 32
    strong: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _keyring_get(name: str) -> str:
    try:
        import keyring

        return (keyring.get_password(_SERVICE_NAME, name) or "").strip()
    except Exception as exc:
        logger.warning("[VECTOR][secrets] keyring lookup failed for {}: {}", name, exc)
        return ""


def _keyring_set(name: str, value: str) -> bool:
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, name, value)
        return True
    except Exception as exc:
        logger.warning("[VECTOR][secrets] keyring write failed for {}: {}", name, exc)
        return False


def _audit_path() -> Path:
    return get_data_root() / "security" / "secrets_audit.jsonl"


def record_secret_event(action: str, name: str, source: str, ok: bool) -> None:
    """Append metadata-only secret events; never stores secret values."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "name": name,
        "source": source,
        "ok": bool(ok),
    }
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:
        # Secret access must not fail because the metadata audit sink is down.
        logger.warning("[VECTOR][secrets] secret audit write failed: {}", exc)
        return


def get_secret(name: str, default: str = "", *, allow_keyring: bool = True) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if allow_keyring:
        value = _keyring_get(name)
        if value:
            return value
    return default


def audit_secret(name: str, *, min_length: int = 32, allow_keyring: bool = True) -> SecretAudit:
    env_value = os.environ.get(name, "").strip()
    if env_value:
        lower = env_value.lower()
        strong = len(env_value) >= min_length and lower not in _WEAK_VALUES
        return SecretAudit(
            name=name,
            configured=True,
            source="env",
            length=len(env_value),
            min_length=min_length,
            strong=strong,
            detail="configured in environment" if strong else "configured but weak or short",
        )

    keyring_value = _keyring_get(name) if allow_keyring else ""
    if keyring_value:
        lower = keyring_value.lower()
        strong = len(keyring_value) >= min_length and lower not in _WEAK_VALUES
        return SecretAudit(
            name=name,
            configured=True,
            source="keyring",
            length=len(keyring_value),
            min_length=min_length,
            strong=strong,
            detail="configured in OS keyring" if strong else "configured in OS keyring but weak or short",
        )

    return SecretAudit(
        name=name,
        configured=False,
        source="missing",
        min_length=min_length,
        detail="not configured",
    )


def audit_secrets(names: Iterable[str], *, min_length: int = 32) -> list[SecretAudit]:
    return [audit_secret(name, min_length=min_length) for name in names]


def generate_secret(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def rotate_secret(name: str, *, length: int = 48, backend: str = "keyring") -> SecretAudit:
    value = generate_secret(length)
    if backend != "keyring":
        record_secret_event("rotate", name, backend, False)
        raise ValueError("Only keyring rotation is supported; env secrets must be rotated by deployment tooling")
    ok = _keyring_set(name, value)
    record_secret_event("rotate", name, backend, ok)
    if not ok:
        raise RuntimeError("OS keyring is unavailable; rotate this secret in your deployment environment")
    return audit_secret(name, min_length=length, allow_keyring=True)
