"""API error classifier — absorbed from reference agent/error_classifier.py.

Structured taxonomy of API errors with priority-ordered classification pipeline.
Determines the correct recovery action: retry, rotate credential, compress context, or abort.
"""
import sys
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional



class FailoverReason(enum.Enum):
    """Why an API call failed — determines recovery strategy."""
    auth               = "auth"              # 401/403 transient — refresh/rotate
    auth_permanent     = "auth_permanent"    # Auth failed after refresh — abort
    billing            = "billing"           # 402 / credit exhaustion — rotate
    rate_limit         = "rate_limit"        # 429 / quota — backoff then rotate
    overloaded         = "overloaded"        # 503/529 — provider overloaded
    server_error       = "server_error"      # 500/502 — retry
    timeout            = "timeout"           # Connection timeout
    context_overflow   = "context_overflow"  # Context too large — compress
    payload_too_large  = "payload_too_large" # 413 — compress payload
    image_too_large    = "image_too_large"   # Image exceeds provider limit
    model_not_found    = "model_not_found"   # 404 / invalid model — fallback
    format_error       = "format_error"      # 400 bad request
    unknown            = "unknown"           # Unclassifiable — retry


@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: Dict[str, Any] = field(default_factory=dict)
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in (FailoverReason.auth, FailoverReason.auth_permanent)


# ── Pattern banks (from reference) ───────────────────────────────────────────────

_BILLING_PATTERNS = [
    "insufficient credits", "insufficient_quota", "credit balance",
    "credits have been exhausted", "top up your credits", "payment required",
    "billing hard limit", "exceeded your current quota", "account is deactivated",
    "plan does not include",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit", "rate_limit", "too many requests", "throttled",
    "requests per minute", "tokens per minute", "requests per day",
    "try again in", "please retry after", "resource_exhausted",
    "rate increased too quickly", "throttlingexception",
    "too many concurrent requests", "servicequotaexceededexception",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context length", "context window", "context_length_exceeded",
    "maximum context", "tokens exceed", "reduce the length",
    "input too long", "prompt is too long", "max_tokens_exceeded",
    "prompt tokens", "exceeds the limit",
]

_MODEL_NOT_FOUND_PATTERNS = [
    "model not found", "model_not_found", "no such model",
    "invalid model", "model does not exist", "unknown model",
    "model is not available", "no endpoints",
]

_AUTH_PATTERNS = [
    "invalid api key", "api key", "unauthorized", "forbidden",
    "authentication failed", "invalid_api_key", "no api key",
    "api key not found",
]


def _body_lower(exc: Exception) -> str:
    """Extract normalized lowercase text from an exception."""
    parts = [str(exc).lower()]
    # httpx / requests response bodies
    for attr in ("response", "text", "body", "message"):
        val = getattr(exc, attr, None)
        if val:
            parts.append(str(val).lower())
    return " ".join(parts)


def classify_error(
    exc: Exception,
    status_code: Optional[int] = None,
    provider: str = "",
    model: str = "",
) -> ClassifiedError:
    """Classify an API exception into a FailoverReason with recovery hints."""
    body = _body_lower(exc)
    sc = status_code

    # Infer status code from exception if not given
    if sc is None:
        for attr in ("status_code", "code", "status"):
            val = getattr(exc, attr, None) or getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(val, int):
                sc = val
                break

    def _make(reason, **kw) -> ClassifiedError:
        return ClassifiedError(reason=reason, status_code=sc, provider=provider,
                               model=model, message=str(exc)[:300], **kw)

    # 402 Billing
    if sc == 402 or any(p in body for p in _BILLING_PATTERNS):
        return _make(FailoverReason.billing, should_rotate_credential=True)

    # 429 Rate limit
    if sc == 429 or any(p in body for p in _RATE_LIMIT_PATTERNS):
        return _make(FailoverReason.rate_limit)

    # 401/403 Auth
    if sc in (401, 403) or any(p in body for p in _AUTH_PATTERNS):
        return _make(FailoverReason.auth, should_rotate_credential=True)

    # 404 Model not found
    if sc == 404 or any(p in body for p in _MODEL_NOT_FOUND_PATTERNS):
        return _make(FailoverReason.model_not_found, should_fallback=True)

    # 413 Payload too large
    if sc == 413:
        return _make(FailoverReason.payload_too_large, should_compress=True)

    # 500/502 Server error
    if sc in (500, 502):
        return _make(FailoverReason.server_error)

    # 503/529 Overloaded
    if sc in (503, 529):
        return _make(FailoverReason.overloaded)

    # Context overflow (check after status codes)
    if any(p in body for p in _CONTEXT_OVERFLOW_PATTERNS):
        return _make(FailoverReason.context_overflow, should_compress=True, retryable=False)

    # Timeout
    exc_type = type(exc).__name__.lower()
    if "timeout" in exc_type or "timeout" in body:
        return _make(FailoverReason.timeout)

    return _make(FailoverReason.unknown)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Rate limit
    ce = classify_error(Exception("rate limit exceeded"), status_code=429, provider="anthropic")
    assert ce.reason == FailoverReason.rate_limit
    assert ce.retryable

    # Billing
    ce2 = classify_error(Exception("insufficient credits"), provider="openai")
    assert ce2.reason == FailoverReason.billing
    assert ce2.should_rotate_credential

    # Context overflow
    ce3 = classify_error(Exception("context length exceeded"), provider="groq")
    assert ce3.reason == FailoverReason.context_overflow
    assert ce3.should_compress and not ce3.retryable

    # Auth
    ce4 = classify_error(Exception("invalid api key"), status_code=401)
    assert ce4.is_auth

    # Model not found
    ce5 = classify_error(Exception("model not found"), status_code=404)
    assert ce5.reason == FailoverReason.model_not_found
    assert ce5.should_fallback

    # Unknown
    ce6 = classify_error(Exception("something weird happened"))
    assert ce6.reason == FailoverReason.unknown

    print("errors.py OK")


