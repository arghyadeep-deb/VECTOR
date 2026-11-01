# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by the API auth middleware (validates VECTOR_API_KEY) and core/api/routers/auth_jwt.py. Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""Authentication and authorization for V.E.C.T.O.R. API.

Security design for a local personal project:
- If VECTOR_API_KEY env var is set: Bearer token required for all non-public endpoints
- If VECTOR_API_KEY is not set: middleware allows localhost only and rejects remote access
- Public paths: /, /status, /health, /docs, /openapi.json, /redoc
- Auth middleware is handled in middleware.py (not here) to avoid double-wrapping
"""

import sys

__all__ = [
    "security",
    "verify_api_key",
]

import hmac
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from core.config import CONFIG

security = HTTPBearer(auto_error=False)
_AUTH_DISABLED_WARNED = False


def _api_key() -> str:
    """Read the key at call time — middleware.py already does; a module-global
    frozen at import made the documented no-key/localhost mode unreachable once
    the process imported with .env loaded (and untestable via monkeypatch).
    Uses get_secret() so keyring is checked as fallback (not just env)."""
    from core.security.secrets_manager import get_secret
    return get_secret("VECTOR_API_KEY")


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """FastAPI Depends — verify Bearer token for protected routes.

    Returns True if auth passes (key valid or not configured).
    Network-level localhost-only enforcement lives in middleware.py.
    Raises HTTPException 401 only if key IS configured AND invalid.
    """
    global _AUTH_DISABLED_WARNED
    api_key = _api_key()
    if not api_key:
        if not _AUTH_DISABLED_WARNED:
            logger.warning("[VECTOR][auth] API authentication DISABLED — set VECTOR_API_KEY env var to enable (remote access blocked to localhost by middleware)")
            _AUTH_DISABLED_WARNED = True
        return True

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Constant-time comparison — avoids leaking the key via response timing.
    if not hmac.compare_digest(credentials.credentials, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK" if not _api_key() else f"API key configured ({len(_api_key())} chars)")
