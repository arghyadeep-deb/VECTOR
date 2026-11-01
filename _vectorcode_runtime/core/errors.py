"""
core/errors.py — Typed exception hierarchy for VECTOR (Gap 20).

Usage:
    from core.errors import ServiceUnavailableError, ValidationError

    raise ServiceUnavailableError("ollama", "model not loaded")
    raise ValidationError("query", "must not be empty")

All exceptions carry a structured payload so callers can distinguish
retryable errors (ServiceUnavailable, Timeout, RateLimit) from
permanent errors (Validation, Authentication, Forbidden).
"""
from __future__ import annotations

__all__ = [
    "AgentDeadError",
    "AuthenticationError",
    "ConfigurationError",
    "ForbiddenError",
    "VectorMemoryError",
    "ModelNotLoadedError",
    "RateLimitError",
    "ServiceUnavailableError",
    "ValidationError",
    "VectorError",
    "VectorTimeoutError",
]



class VectorError(Exception):
    """Base class for all VECTOR exceptions."""
    retryable: bool = False

    def __init__(self, message: str = "", **context):
        super().__init__(message)
        self.message = message
        self.context = context

    def __repr__(self) -> str:
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{type(self).__name__}({self.message!r}{', ' + ctx if ctx else ''})"


# ── Retryable ─────────────────────────────────────────────────────────────────

class ServiceUnavailableError(VectorError):
    """A downstream service (Ollama, Supabase, Fly.io) is unreachable."""
    retryable = True

    def __init__(self, service: str, detail: str = ""):
        super().__init__(f"{service} unavailable: {detail}", service=service)


class VectorTimeoutError(VectorError):
    """An operation exceeded its time budget."""
    retryable = True

    def __init__(self, operation: str, budget_s: float, elapsed_s: float):
        super().__init__(
            f"{operation} timed out ({elapsed_s:.1f}s > {budget_s:.1f}s budget)",
            operation=operation, budget_s=budget_s, elapsed_s=elapsed_s,
        )


class RateLimitError(VectorError):
    """API rate limit hit. Retry after retry_after seconds."""
    retryable = True

    def __init__(self, service: str, retry_after: float = 60.0):
        super().__init__(
            f"{service} rate limited — retry after {retry_after:.0f}s",
            service=service, retry_after=retry_after,
        )


class ModelNotLoadedError(VectorError):
    """Ollama model is not loaded yet."""
    retryable = True

    def __init__(self, model: str):
        super().__init__(f"Model '{model}' not loaded in Ollama", model=model)


# ── Permanent ─────────────────────────────────────────────────────────────────

class ValidationError(VectorError):
    """Input failed validation. Do not retry."""
    retryable = False

    def __init__(self, field: str, reason: str):
        super().__init__(f"Validation failed for '{field}': {reason}", field=field)


class AuthenticationError(VectorError):
    """Missing or invalid credentials."""
    retryable = False

    def __init__(self, detail: str = ""):
        super().__init__(f"Authentication failed: {detail}")


class ForbiddenError(VectorError):
    """Action blocked by permission gateway (RED tier)."""
    retryable = False

    def __init__(self, action_type: str, reason: str = ""):
        super().__init__(
            f"Action '{action_type}' forbidden: {reason}",
            action_type=action_type,
        )


class AgentDeadError(VectorError):
    """Agent HP reached 0 — cannot execute tasks."""
    retryable = False

    def __init__(self, agent_id: str, agent_name: str):
        super().__init__(
            f"Agent '{agent_name}' ({agent_id}) is dead (HP=0)",
            agent_id=agent_id, agent_name=agent_name,
        )


class VectorMemoryError(VectorError):
    """Episodic or semantic memory operation failed.

    Named VectorMemoryError, not MemoryError, to avoid shadowing Python's
    own builtin MemoryError (the real out-of-memory exception) -- the same
    reasoning this file already applied to VectorTimeoutError vs. the
    builtin TimeoutError. A plain `MemoryError` here meant any
    `except MemoryError:` after `from core.errors import *`/MemoryError
    would silently stop catching real OOM conditions. Zero real callers
    import core.errors today (confirmed via repo-wide grep -- this module
    is itself orphaned, "Gap 20" per its own docstring), so this rename is
    zero-risk.
    """
    retryable = False

    def __init__(self, operation: str, detail: str = ""):
        super().__init__(f"Memory {operation} failed: {detail}", operation=operation)


class ConfigurationError(VectorError):
    """Required configuration key is missing or invalid."""
    retryable = False

    def __init__(self, key: str, detail: str = ""):
        super().__init__(f"Configuration error for '{key}': {detail}", key=key)
