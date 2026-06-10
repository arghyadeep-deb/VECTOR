"""
VECTOR API Key Management — localhost-only key lifecycle endpoints.
Allows rotating/revoking the VECTOR_API_KEY without restarting the server.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os
import secrets
from typing import Iterable
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

router = APIRouter(prefix="/keys", tags=["keys"])

def _require_localhost(request: Request) -> None:
    """Enforce localhost-only access for key management."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Key management available from localhost only")


def _extract_bearer(authorization_values: Iterable[str]) -> str:
    for value in authorization_values:
        scheme, _, token = str(value).partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
    return ""


def _require_current_key_if_configured(request: Request) -> None:
    """Require the current VECTOR_API_KEY for key mutation when one is configured."""
    current = os.environ.get("VECTOR_API_KEY", "")
    if not current:
        return
    supplied = _extract_bearer(request.headers.getlist("authorization"))
    if not supplied or not secrets.compare_digest(supplied, current):
        raise HTTPException(status_code=401, detail="Current VECTOR_API_KEY bearer token required")


@router.get("/status")
async def key_status(request: Request):
    """Check if API key is configured (does NOT return the key value)."""
    _require_localhost(request)
    key = os.environ.get("VECTOR_API_KEY", "")
    return {
        "configured": bool(key),
        "length": len(key) if key else 0,
        "hint": key[:4] + "..." if len(key) > 4 else "not set",
    }


@router.post("/rotate")
async def rotate_key(request: Request):
    """
    Generate a new API key, update the environment, and write to .env file.
    Returns the new key ONCE — store it securely.
    Requires the current key as Bearer token (or localhost-only if no key set).
    """
    _require_localhost(request)
    _require_current_key_if_configured(request)

    new_key = secrets.token_urlsafe(32)

    # Update running process
    os.environ["VECTOR_API_KEY"] = new_key

    # Write to .env file if it exists
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    env_updated = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("VECTOR_API_KEY="):
                new_lines.append(f"VECTOR_API_KEY={new_key}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"VECTOR_API_KEY={new_key}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        env_updated = True

    logger.info("[VECTOR][keys] API key rotated via /keys/rotate")
    return {
        "status": "rotated",
        "new_key": new_key,
        "message": "Store this key securely — it will not be shown again",
        "env_updated": env_updated,
    }


@router.post("/revoke")
async def revoke_key(request: Request):
    """
    Clear the API key — server becomes accessible from localhost only.
    Useful for maintenance mode.
    """
    _require_localhost(request)
    _require_current_key_if_configured(request)

    os.environ["VECTOR_API_KEY"] = ""

    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        new_lines = [l for l in lines if not l.startswith("VECTOR_API_KEY=")]
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    logger.warning("[VECTOR][keys] API key revoked — server now localhost-only")
    return {"status": "revoked", "message": "Server is now accessible from localhost only"}


if __name__ == "__main__":
    print("✅ keys.py OK")
