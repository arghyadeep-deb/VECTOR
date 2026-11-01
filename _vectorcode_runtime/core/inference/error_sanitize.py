"""RR-3.7C (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
RR3_7C_FINAL_INGRESS_AUTHORIZATION_FREEZE_REPORT.md): a real API key was
observed in production logs. Root cause: httpx.Response.raise_for_status()
builds its HTTPStatusError message as
"{error_type} '{status} {reason}' for url '{url}'..." (confirmed by direct
read of httpx's own _models.py source) -- the FULL request URL, including
any credential embedded as a query parameter. Gemini's REST API requires
the key as a `?key=<value>` query parameter (there is no header-based
alternative for the plain REST endpoint VECTOR calls), so
core/inference/vectorcode_llm.py and core/inference/provider_client.py both
construct a request URL of the form
".../generateContent?key=<real_key>" -- when that request fails, the
raised exception's own string representation carries the real key, and
both files' `except Exception as e: logger.warning(f"...{e}")` /
`last_error = str(e)` patterns put it straight into logs.

This is NOT a general-purpose secret scanner. It sanitizes exactly the
credential-bearing query-parameter forms actually constructed by VECTOR's
own provider call sites (confirmed via direct source read, not guessed)
before any exception-derived string reaches a logger -- diagnostic value
(status code, reason phrase, host, path) is preserved; only the parameter
VALUE is redacted.
"""
from __future__ import annotations

__all__ = ["sanitize_provider_error"]

import re

# Query-parameter names VECTOR's own provider code actually uses to carry a
# credential in a URL (currently: Gemini's `?key=`). Extendable if another
# provider adapter is ever found to do the same -- keep this list to
# confirmed, real cases, not speculative ones.
_CREDENTIAL_QUERY_PARAM_RE = re.compile(
    r"(?i)([?&](?:key|api_key|apikey|access_token)=)[^&\s'\"]+"
)

# Defense-in-depth for the header-based form (Authorization: Bearer <token>)
# -- no confirmed VECTOR call site logs this today (httpx's own
# HTTPStatusError message never includes request headers, verified by
# direct source read), but sanitizing it costs nothing and matches the
# credential shape PermissionGateway/provider code could plausibly log in
# the future via a different exception type.
_BEARER_TOKEN_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9\-._~+/]+=*")


def sanitize_provider_error(text: str) -> str:
    """Redact credential-bearing URL query params and Bearer tokens from a
    provider error/exception string before it is logged. Never raises --
    returns the input unchanged on any internal failure so a sanitization
    bug can never itself break the calling logger.warning()/error() call."""
    if not text:
        return text
    try:
        redacted = _CREDENTIAL_QUERY_PARAM_RE.sub(r"\1<REDACTED>", text)
        redacted = _BEARER_TOKEN_RE.sub(r"\1<REDACTED>", redacted)
        return redacted
    except Exception:
        return text


if __name__ == "__main__":
    _sample = (
        "Client error '404 Not Found' for url "
        "'https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent?key=AIzaSyDfakeTestKeyDoNotUse1234'\n"
        "For more information check: https://developer.mozilla.org/..."
    )
    _out = sanitize_provider_error(_sample)
    assert "AIzaSyDfakeTestKeyDoNotUse1234" not in _out, _out
    assert "404 Not Found" in _out
    assert "generateContent" in _out
    print("OK error_sanitize.py")
