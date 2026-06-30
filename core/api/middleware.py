"""Custom middleware for V.E.C.T.O.R. API.

Middleware execution order (FastAPI applies in reverse order):
1. error_handling_middleware (innermost)
2. rate_limiting_middleware
3. timing_middleware
4. logging_middleware
5. auth_middleware (outermost)
"""

import sys

__all__ = [
    "auth_middleware",
    "csrf_middleware",
    "error_handling_middleware",
    "generate_csrf_token",
    "logging_middleware",
    "rate_limiting_middleware",
    "security_headers_middleware",
    "timing_middleware",
    "validate_csrf_token",
]

import os
import hmac
import time
import datetime
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import uuid
import threading


# ── Configuration ───────────────────────────────────────

# FIX #7: When no API key is set, enforce localhost-only access instead of open access
_REQUIRE_LOCALHOST_WHEN_NO_KEY: bool = True

_RATE_LIMIT_WINDOW: int = 60  # seconds
_RATE_LIMIT_MAX: dict[str, int] = {
    "default": 100,
    "/command": 20,
    "/ws/command": 20,
    "/council": 10,
    "/memory/recent": 50,
}

_RATE_LIMIT_WINDOW_SEC: int = 60
_RATE_LIMIT_MAX_DEFAULT: int = 100

# Thread-safe rate limiting storage
# NOTE (#6): This is per-process. For multi-worker deployments, use Redis-backed
# rate limiting (e.g. slowapi with Redis backend). Acceptable for single-user local system.
_rate_limit_lock = threading.Lock()
_rate_limit_data: dict[str, list[float]] = defaultdict(list)

# Public paths (no auth required)
_PUBLIC_PATHS = {"/", "/status", "/health", "/docs", "/openapi.json", "/redoc",
                 "/csrf-token",  # CSRF token endpoint is public
                 "/growth/signup"}  # public beta-signup form (gated by BetaSignup, not auth/CSRF)

# Allowed origins — localhost only (no external origins)
_ALLOWED_ORIGINS = {
    "https://localhost:8000",
    "https://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}

# CSRF tokens are kept purely in-memory (no disk persistence).
# Storing tokens on disk leaks them to any process that can read the filesystem.
# Tokens are short-lived (1h TTL) and regenerated cheaply on each request.
_csrf_tokens: dict[str, float] = {}
_csrf_lock = threading.Lock()
_CSRF_TOKEN_TTL = 3600  # 1 hour

# Security headers
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

# ── Rate Limiting ──────────────────────────────────────


def _is_rate_limited(path: str, client_ip: str) -> bool:
    """Check if a client is rate limited for a given path."""
    window = _RATE_LIMIT_WINDOW
    max_requests = _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
    
    now = time.time()
    cutoff = now - window
    
    key = f"{path}:{client_ip}"
    
    with _rate_limit_lock:
        # Clean old entries
        _rate_limit_data[key] = [t for t in _rate_limit_data[key] if t > cutoff]
        
        if len(_rate_limit_data[key]) >= max_requests:
            return True
        
        _rate_limit_data[key].append(now)
        return False


async def rate_limiting_middleware(request: Request, call_next):
    """Rate limit requests per client per endpoint."""
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    
    # Skip rate limiting for public paths and health checks
    if path in _PUBLIC_PATHS or path.startswith("/_next"):
        return await call_next(request)
    
    if _is_rate_limited(path, client_ip):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(_RATE_LIMIT_WINDOW)},
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Retry after {_RATE_LIMIT_WINDOW}s",
                "retry_after": _RATE_LIMIT_WINDOW,
            },
        )
    
    response = await call_next(request)
    
    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(
        _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
    )
    response.headers["X-RateLimit-Remaining"] = str(max(
        0,
        _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
        - len(_rate_limit_data.get(f"{path}:{client_ip}", []))
    ))
    
    return response


# ── Authentication ─────────────────────────────────────


async def auth_middleware(request: Request, call_next):
    """Require Bearer token for all non-public endpoints.
    FIX #7: When no API key is set, only allow localhost connections (not any process).
    """
    api_key = os.environ.get("VECTOR_API_KEY", "")
    api_key_enabled = bool(api_key)

    # Skip auth for public paths
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    
    # Skip auth for health check and static assets
    if request.url.path.startswith("/_next") or request.url.path == "/health":
        return await call_next(request)
    
    # When API key not configured: enforce localhost-only access
    if not api_key_enabled:
        if _REQUIRE_LOCALHOST_WHEN_NO_KEY:
            client_ip = request.client.host if request.client else ""
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Remote access requires VECTOR_API_KEY to be configured."},
                )
        return await call_next(request)
    
    auth = request.headers.get("Authorization", "")
    # Constant-time comparison — avoids leaking the key via response timing.
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], api_key):
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"detail": "Unauthorized. Valid API key required."},
        )
    
    return await call_next(request)


# ── Logging ────────────────────────────────────────────


async def logging_middleware(request: Request, call_next):
    """Log all incoming requests with timing."""
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    
    logger.info(
        f"[VECTOR][api][{request_id}] {request.method} {request.url.path}"
    )
    
    response = await call_next(request)
    
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log_level = (
        "ERROR"
        if response.status_code >= 500
        else         "WARNING" if response.status_code >= 400 else "INFO"
    )
    logger.log(
        log_level,
        f"[VECTOR][api][{request_id}] {request.method} {request.url.path} "
            f"-> {response.status_code} ({elapsed_ms}ms)",
    )
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    
    return response


# ── Timing ─────────────────────────────────────────────


async def timing_middleware(request: Request, call_next):
    """Add timing header to all responses."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = str(int((time.perf_counter() - start) * 1000))
    return response


# ── Error Handling ─────────────────────────────────────


async def error_handling_middleware(request: Request, call_next):
    """Catch and format unhandled exceptions. Only expose details to localhost."""
    try:
        return await call_next(request)
    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions
    except Exception as e:
        logger.error(f"[VECTOR][api] Unhandled exception: {e}")
        # FIX #16: Only expose error details to localhost clients, never remote
        client_ip = request.client.host if request.client else ""
        is_local = client_ip in ("127.0.0.1", "::1", "localhost")
        show_detail = is_local and os.environ.get("VECTOR_DEBUG")
        return JSONResponse(
            status_code=500,
            headers={
                "X-Error-Type": type(e).__name__,
                "X-Error-Timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            content={
                "error": "Internal server error",
                "detail": str(e) if show_detail else "An error occurred",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )


# ── Security Headers ───────────────────────────────────


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value

    # Strict CSP — only allow same-origin, no inline scripts from external sources
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # unsafe-inline needed for React
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' wss://localhost:8000 ws://localhost:8000; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )

    from core.config import CONFIG
    response.headers["X-System-Version"] = CONFIG.get("version", "unknown")

    return response


def generate_csrf_token() -> str:
    """Generate a new CSRF token and store it in-memory."""
    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    with _csrf_lock:
        # Clean expired tokens
        now = time.time()
        expired = [k for k, v in _csrf_tokens.items() if now - v > _CSRF_TOKEN_TTL]
        for k in expired:
            del _csrf_tokens[k]
        _csrf_tokens[token] = now
    return token


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token. Returns True if valid."""
    if not token:
        return False
    with _csrf_lock:
        issued_at = _csrf_tokens.get(token)
        if issued_at is None:
            return False
        if time.time() - issued_at > _CSRF_TOKEN_TTL:
            del _csrf_tokens[token]
            return False
    return True


async def csrf_middleware(request: Request, call_next):
    """
    Validate CSRF token on state-changing requests (POST/PUT/DELETE/PATCH).
    GET requests are safe and don't need CSRF protection.
    The dashboard fetches a token from /csrf-token and includes it as X-CSRF-Token header.
    """
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Skip CSRF for API key authenticated requests (non-browser clients)
        if os.environ.get("VECTOR_API_KEY", "") and request.headers.get("Authorization", "").startswith("Bearer "):
            return await call_next(request)

        # Skip CSRF for WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not validate_csrf_token(csrf_token):
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid or missing CSRF token", "detail": "Include X-CSRF-Token header"},
            )

    return await call_next(request)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ middleware.py OK")
