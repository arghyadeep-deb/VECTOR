"""API error classification for smart failover and recovery.

Provides a structured taxonomy of API errors and a priority-ordered
classification pipeline that determines the correct recovery action
(retry, rotate credential, fallback to another provider, compress
context, or abort).
"""

import enum
from dataclasses import dataclass, field
from typing import Optional


class FailoverReason(enum.Enum):
    auth = "auth"
    auth_permanent = "auth_permanent"
    billing = "billing"
    rate_limit = "rate_limit"
    overloaded = "overloaded"
    server_error = "server_error"
    timeout = "timeout"
    context_overflow = "context_overflow"
    payload_too_large = "payload_too_large"
    image_too_large = "image_too_large"
    model_not_found = "model_not_found"
    provider_policy_blocked = "provider_policy_blocked"
    format_error = "format_error"
    thinking_signature = "thinking_signature"
    long_context_tier = "long_context_tier"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: dict = field(default_factory=dict)
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in (FailoverReason.auth, FailoverReason.auth_permanent)


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

_USAGE_LIMIT_PATTERNS = ["usage limit", "quota", "limit exceeded", "key limit exceeded"]
_USAGE_LIMIT_TRANSIENT_SIGNALS = ["try again", "retry", "resets at", "reset in", "wait", "requests remaining", "periodic", "window"]
_PAYLOAD_TOO_LARGE_PATTERNS = ["request entity too large", "payload too large", "error code: 413"]
_IMAGE_TOO_LARGE_PATTERNS = ["image exceeds", "image too large", "image_too_large", "image size exceeds"]
_CONTEXT_OVERFLOW_PATTERNS = [
    "context length", "context size", "maximum context", "token limit",
    "too many tokens", "reduce the length", "exceeds the limit",
    "context window", "prompt is too long", "prompt exceeds max length",
    "max_tokens", "maximum number of tokens", "exceeds the max_model_len",
    "max_model_len", "input is too long", "maximum model length",
    "context length exceeded", "truncating input",
]
_MODEL_NOT_FOUND_PATTERNS = [
    "is not a valid model", "invalid model", "model not found",
    "model_not_found", "does not exist", "no such model",
    "unknown model", "unsupported model",
]
_AUTH_PATTERNS = [
    "invalid api key", "invalid_api_key", "authentication",
    "unauthorized", "forbidden", "invalid token", "token expired",
    "token revoked", "access denied",
]
_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout", "ConnectError",
    "RemoteProtocolError", "ConnectionError", "ConnectionResetError",
    "ConnectionAbortedError", "BrokenPipeError", "TimeoutError",
    "ReadError", "ServerDisconnectedError", "SSLError",
    "APIConnectionError", "APITimeoutError",
})


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
    approx_tokens: int = 0,
    context_length: int = 200000,
    num_messages: int = 0,
) -> ClassifiedError:
    status_code = _extract_status_code(error)
    error_type = type(error).__name__
    if status_code is None and error_type == "RateLimitError":
        status_code = 429
    body = _extract_error_body(error)
    error_code = _extract_error_code(body)
    error_msg = _build_error_msg(error, body)
    provider_lower = (provider or "").strip().lower()

    def _result(reason: FailoverReason, **overrides) -> ClassifiedError:
        defaults = {
            "reason": reason, "status_code": status_code,
            "provider": provider, "model": model,
            "message": _extract_message(error, body),
        }
        defaults.update(overrides)
        return ClassifiedError(**defaults)

    # 1. Provider-specific patterns
    if status_code == 400 and "signature" in error_msg and "thinking" in error_msg:
        return _result(FailoverReason.thinking_signature)
    if status_code == 429 and "extra usage" in error_msg and "long context" in error_msg:
        return _result(FailoverReason.long_context_tier, should_compress=True)

    # 2. HTTP status code
    if status_code is not None:
        classified = _classify_by_status(status_code, error_msg, error_code, body, provider_lower, approx_tokens, context_length, num_messages, _result)
        if classified: return classified

    # 3. Error code
    if error_code:
        classified = _classify_by_error_code(error_code, error_msg, _result)
        if classified: return classified

    # 4. Message patterns
    classified = _classify_by_message(error_msg, approx_tokens, context_length, _result)
    if classified: return classified

    # 5. Transport errors
    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return _result(FailoverReason.timeout)

    return _result(FailoverReason.unknown)


def _classify_by_status(status_code, error_msg, error_code, body, provider, approx_tokens, context_length, num_messages, result_fn):
    if status_code == 401:
        return result_fn(FailoverReason.auth, retryable=False, should_rotate_credential=True, should_fallback=True)
    if status_code == 403:
        if "key limit exceeded" in error_msg or "spending limit" in error_msg:
            return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
        return result_fn(FailoverReason.auth, retryable=False, should_fallback=True)
    if status_code == 402:
        has_ul = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS)
        has_ts = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)
        if has_ul and has_ts:
            return result_fn(FailoverReason.rate_limit, retryable=True, should_rotate_credential=True, should_fallback=True)
        return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
    if status_code == 404:
        if any(p in error_msg for p in ["no endpoints available"]):
            return result_fn(FailoverReason.provider_policy_blocked, retryable=False, should_fallback=False)
        if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
            return result_fn(FailoverReason.model_not_found, retryable=False, should_fallback=True)
        return result_fn(FailoverReason.unknown)
    if status_code == 413:
        return result_fn(FailoverReason.payload_too_large, should_compress=True)
    if status_code == 429:
        return result_fn(FailoverReason.rate_limit, should_rotate_credential=True, should_fallback=True)
    if status_code == 400:
        return _classify_400(error_msg, error_code, body, provider, approx_tokens, context_length, num_messages, result_fn)
    if status_code in (500, 502):
        return result_fn(FailoverReason.server_error)
    if status_code in (503, 529):
        return result_fn(FailoverReason.overloaded)
    if 400 <= status_code < 500:
        return result_fn(FailoverReason.format_error, retryable=False, should_fallback=True)
    if 500 <= status_code < 600:
        return result_fn(FailoverReason.server_error)
    return None


def _classify_400(error_msg, error_code, body, provider, approx_tokens, context_length, num_messages, result_fn):
    if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
        return result_fn(FailoverReason.image_too_large)
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(FailoverReason.context_overflow, should_compress=True)
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(FailoverReason.rate_limit, should_rotate_credential=True, should_fallback=True)
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
    is_large = approx_tokens > context_length * 0.4 or approx_tokens > 80000 or num_messages > 80
    if is_large:
        return result_fn(FailoverReason.context_overflow, should_compress=True)
    return result_fn(FailoverReason.format_error, retryable=False, should_fallback=True)


def _classify_by_error_code(error_code, error_msg, result_fn):
    code = error_code.lower()
    if code in ("resource_exhausted", "throttled", "rate_limit_exceeded"):
        return result_fn(FailoverReason.rate_limit, should_rotate_credential=True)
    if code in ("insufficient_quota", "billing_not_active", "payment_required"):
        return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
    if code in ("model_not_found", "model_not_available", "invalid_model"):
        return result_fn(FailoverReason.model_not_found, retryable=False, should_fallback=True)
    if code in ("context_length_exceeded", "max_tokens_exceeded"):
        return result_fn(FailoverReason.context_overflow, should_compress=True)
    return None


def _classify_by_message(error_msg, approx_tokens, context_length, result_fn):
    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):
        return result_fn(FailoverReason.payload_too_large, should_compress=True)
    if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
        return result_fn(FailoverReason.image_too_large)
    # Rate limit patterns MUST be checked before usage limit patterns because
    # "rate limit exceeded" matches "limit exceeded" in usage patterns but is
    # NOT a billing issue.
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(FailoverReason.rate_limit, should_rotate_credential=True, should_fallback=True)
    has_ul = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS)
    if has_ul:
        has_ts = any(p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS)
        if has_ts: return result_fn(FailoverReason.rate_limit, should_rotate_credential=True, should_fallback=True)
        return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
    if any(p in error_msg for p in _BILLING_PATTERNS):
        return result_fn(FailoverReason.billing, retryable=False, should_rotate_credential=True, should_fallback=True)
    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return result_fn(FailoverReason.rate_limit, should_rotate_credential=True, should_fallback=True)
    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return result_fn(FailoverReason.context_overflow, should_compress=True)
    if any(p in error_msg for p in _AUTH_PATTERNS):
        return result_fn(FailoverReason.auth, retryable=False, should_rotate_credential=True, should_fallback=True)
    return None


def _build_error_msg(error, body):
    raw = str(error).lower()
    parts = [raw]
    if isinstance(body, dict):
        err_obj = body.get("error", {})
        if isinstance(err_obj, dict):
            msg = str(err_obj.get("message") or "").lower()
            if msg and msg not in raw:
                parts.append(msg)
    return " ".join(parts)


def _extract_status_code(error):
    current = error
    for _ in range(5):
        code = getattr(current, "status_code", None)
        if isinstance(code, int): return code
        code = getattr(current, "status", None)
        if isinstance(code, int) and 100 <= code < 600: return code
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause is None or cause is current: break
        current = cause
    return None


def _extract_error_body(error):
    body = getattr(error, "body", None)
    if isinstance(body, dict): return body
    response = getattr(error, "response", None)
    if response is not None:
        try:
            j = response.json()
            if isinstance(j, dict): return j
        except Exception as e:
            from loguru import logger
            logger.debug("[VECTOR][error_classifier] response body extraction skipped: {}", e)
    return {}


def _extract_error_code(body):
    if not body: return ""
    err = body.get("error", {})
    if isinstance(err, dict):
        code = err.get("code") or err.get("type") or ""
        if isinstance(code, str) and code.strip(): return code.strip()
    code = body.get("code") or body.get("error_code") or ""
    return str(code).strip() if isinstance(code, (str, int)) else ""


def _extract_message(error, body):
    if body:
        err = body.get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", "")
            if isinstance(msg, str) and msg.strip(): return msg.strip()[:500]
        msg = body.get("message", "")
        if isinstance(msg, str) and msg.strip(): return msg.strip()[:500]
    return str(error)[:500]
