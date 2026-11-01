"""Shared TLS launch helpers for VECTOR HTTP services."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TLSConfig:
    enabled: bool
    terminated: bool
    certfile: str = ""
    keyfile: str = ""
    ca_certs: str = ""
    detail: str = ""

    @property
    def scheme(self) -> str:
        return "https" if self.enabled else "http"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUE_VALUES


def _resolve_existing_file(raw: str) -> str:
    path = Path(raw).expanduser()
    return str(path) if path.is_file() else ""


def load_tls_config(env: Mapping[str, str] | None = None) -> TLSConfig:
    """Read VECTOR TLS launch settings without exposing secret material.

    Supported env vars:
    - VECTOR_TLS_CERTFILE: PEM certificate path for uvicorn.
    - VECTOR_TLS_KEYFILE: PEM private key path for uvicorn.
    - VECTOR_TLS_CA_CERTS: optional CA bundle path for client cert validation.
    - VECTOR_TLS_TERMINATED: set to 1/true when a proxy handles HTTPS.
    """
    source = os.environ if env is None else env
    cert_raw = str(source.get("VECTOR_TLS_CERTFILE", "")).strip()
    key_raw = str(source.get("VECTOR_TLS_KEYFILE", "")).strip()
    ca_raw = str(source.get("VECTOR_TLS_CA_CERTS", "")).strip()
    terminated = _truthy(source.get("VECTOR_TLS_TERMINATED"))

    if not cert_raw and not key_raw:
        detail = "TLS handled by upstream proxy" if terminated else "TLS cert/key not configured"
        return TLSConfig(False, terminated, detail=detail)

    certfile = _resolve_existing_file(cert_raw) if cert_raw else ""
    keyfile = _resolve_existing_file(key_raw) if key_raw else ""
    ca_certs = _resolve_existing_file(ca_raw) if ca_raw else ""

    if certfile and keyfile:
        detail = "TLS enabled with local certificate and key"
        if ca_raw and not ca_certs:
            detail += "; VECTOR_TLS_CA_CERTS path does not exist"
        return TLSConfig(True, terminated, certfile=certfile, keyfile=keyfile, ca_certs=ca_certs, detail=detail)

    missing: list[str] = []
    if not cert_raw:
        missing.append("VECTOR_TLS_CERTFILE")
    elif not certfile:
        missing.append("VECTOR_TLS_CERTFILE file")
    if not key_raw:
        missing.append("VECTOR_TLS_KEYFILE")
    elif not keyfile:
        missing.append("VECTOR_TLS_KEYFILE file")
    return TLSConfig(False, terminated, detail="TLS misconfigured: missing " + ", ".join(missing))


def uvicorn_ssl_kwargs(env: Mapping[str, str] | None = None) -> dict[str, str]:
    config = load_tls_config(env)
    if not config.enabled:
        return {}
    kwargs = {"ssl_certfile": config.certfile, "ssl_keyfile": config.keyfile}
    if config.ca_certs:
        kwargs["ssl_ca_certs"] = config.ca_certs
    return kwargs
