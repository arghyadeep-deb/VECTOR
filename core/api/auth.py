"""Authentication and authorization for V.E.C.T.O.R. API.

Security design for a local personal project:
- If VECTOR_API_KEY env var is set: Bearer token required for all non-public endpoints
- If VECTOR_API_KEY is not set (dev mode): auth bypassed for local use
- Public paths: /, /status, /health, /docs, /openapi.json, /redoc
- Auth middleware is handled in middleware.py (not here) to avoid double-wrapping
"""

import sys

__all__ = [
    "security",
    "verify_api_key",
]

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from core.config import CONFIG

security = HTTPBearer(auto_error=False)
_API_KEY: str = os.environ.get("VECTOR_API_KEY", "")


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """FastAPI Depends — verify Bearer token for protected routes.

    Returns True if auth passes (key valid or not configured).
    Raises HTTPException 401 only if key IS configured AND invalid.
    """
    if not _API_KEY:
        logger.warning("[VECTOR][auth] API authentication DISABLED — set VECTOR_API_KEY env var to enable")
        return True

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if credentials.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK" if not _API_KEY else f"API key configured ({len(_API_KEY)} chars)")
