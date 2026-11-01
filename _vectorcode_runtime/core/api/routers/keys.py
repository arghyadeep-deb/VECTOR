"""
VECTOR API Key Management — localhost-only key lifecycle endpoints.
Allows rotating/revoking the VECTOR_API_KEY without restarting the server.
"""
from pathlib import Path
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import os
import secrets
from typing import Iterable
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

router = APIRouter(prefix="/keys", tags=["keys"])

# Third-party provider keys the HUD is allowed to set. Deliberately excludes
# VECTOR's own internal secrets (VECTOR_DB_KEY, VECTOR_JWT_SECRET,
# MCP_KERNEL_SECRET, VECTOR_OFP_SECRET, VECTOR_BRAIN_API_KEY) and OAuth client
# secrets (separate OAuth flow). Without this allowlist, a "set any env var"
# endpoint would be a remote-code-execution-adjacent footgun.
_PROVIDER_KEY_ALLOWLIST: dict[str, str] = {
    "anthropic": "ANTHROPIC_KEY",
    "gemini": "GEMINI_KEY",
    "github": "GITHUB_TOKEN",
    "pushover": "PUSHOVER_TOKEN",
    "supabase": "SUPABASE_KEY",
    "virustotal": "VIRUSTOTAL_KEY",
    "newsapi": "NEWSAPI_KEY",
    "stripe": "STRIPE_KEY",
    "instagram": "INSTAGRAM_ACCESS_TOKEN",
    "elevenlabs": "ELEVENLABS_KEY",
    "openrouter": "OPENROUTER_KEY",
    "mistral": "MISTRAL_KEY",
    "pagespeed": "PAGESPEED_API_KEY",
    "hass": "HASS_TOKEN",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "honcho": "HONCHO_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "azure_anthropic": "AZURE_ANTHROPIC_KEY",
    "azure_foundry": "AZURE_FOUNDRY_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openai_codex": "OPENAI_CODEX_API_KEY",
    "hindsight": "HINDSIGHT_API_KEY",
    "browserbase": "BROWSERBASE_API_KEY",
    "turso": "TURSO_TOKEN",
}

_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"


def _write_env_var(name: str, value: str) -> bool:
    """Set/replace a single KEY=value line in .env. Returns True if the file was updated."""
    if not _ENV_PATH.exists():
        return False
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    prefix = f"{name}="
    new_lines = []
    updated = False
    for line in lines:
        if line.startswith(prefix):
            new_lines.append(f"{name}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{name}={value}")
    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def _remove_env_var(name: str) -> bool:
    """Remove a KEY=... line from .env entirely. Returns True if the file was updated."""
    if not _ENV_PATH.exists():
        return False
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = [l for l in lines if not l.startswith(f"{name}=")]
    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


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
    env_updated = _write_env_var("VECTOR_API_KEY", new_key)

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
    _remove_env_var("VECTOR_API_KEY")

    logger.warning("[VECTOR][keys] API key revoked — server now localhost-only")
    return {"status": "revoked", "message": "Server is now accessible from localhost only"}


@router.get("/providers")
async def list_provider_keys(request: Request):
    """List allowlisted third-party provider keys and whether each is configured.
    Never returns the actual values — just a short hint, like /status."""
    _require_localhost(request)
    providers = {}
    for provider, env_name in _PROVIDER_KEY_ALLOWLIST.items():
        val = os.environ.get(env_name, "")
        providers[provider] = {
            "env_name": env_name,
            "configured": bool(val),
            "hint": (val[:4] + "...") if len(val) > 4 else ("set" if val else "not set"),
        }
    return {"providers": providers}


@router.post("/providers/{provider}")
async def set_provider_key(provider: str, request: Request):
    """Set or update a third-party provider API key. Body: {"value": "..."}.
    Allowlisted providers only — this can never write an arbitrary env var."""
    _require_localhost(request)
    _require_current_key_if_configured(request)

    env_name = _PROVIDER_KEY_ALLOWLIST.get(provider.lower())
    if not env_name:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider '{provider}'. Allowed: {sorted(_PROVIDER_KEY_ALLOWLIST)}",
        )

    body = await request.json()
    value = str(body.get("value", "")).strip()
    if not value:
        raise HTTPException(status_code=400, detail="'value' is required and cannot be empty")
    if "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail="'value' cannot contain newlines")

    os.environ[env_name] = value
    env_updated = _write_env_var(env_name, value)

    logger.info(f"[VECTOR][keys] provider key set: {provider} ({env_name})")
    return {"status": "set", "provider": provider, "env_name": env_name, "env_updated": env_updated}


@router.delete("/providers/{provider}")
async def clear_provider_key(provider: str, request: Request):
    """Clear a third-party provider API key."""
    _require_localhost(request)
    _require_current_key_if_configured(request)

    env_name = _PROVIDER_KEY_ALLOWLIST.get(provider.lower())
    if not env_name:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider '{provider}'. Allowed: {sorted(_PROVIDER_KEY_ALLOWLIST)}",
        )

    os.environ[env_name] = ""
    env_updated = _remove_env_var(env_name)

    logger.info(f"[VECTOR][keys] provider key cleared: {provider} ({env_name})")
    return {"status": "cleared", "provider": provider, "env_name": env_name, "env_updated": env_updated}


if __name__ == "__main__":
    print("✅ keys.py OK")
