"""
RR-3.7C (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
RR3_7C_FINAL_INGRESS_AUTHORIZATION_FREEZE_REPORT.md): closes the real
Gemini API-key log leak first observed during RR-3.7B.1's own live
production validation.

Root cause: httpx.Response.raise_for_status() builds its HTTPStatusError
message as "{error_type} '{status} {reason}' for url '{url}'..." (confirmed
by direct read of the installed httpx's own _models.py source) -- the full
request URL, including any credential embedded as a query parameter.
Gemini's REST API requires the key as a `?key=<value>` query parameter (no
header-based alternative for the endpoint VECTOR calls), so both
core/inference/vectorcode_llm.py::_try_gemini() and
core/inference/provider_client.py::_call_with_retry() construct a request
URL carrying the real key, and both files' exception-logging paths
(`logger.warning(f"...{e}")` / `last_error = str(e)`) put the raw
exception string -- URL and all -- into logs.

Fixed with a small, purpose-built, shared sanitizer
(core/inference/error_sanitize.py::sanitize_provider_error()) that redacts
known credential-bearing URL query-parameter forms actually used by
VECTOR's own provider code (confirmed via source read: `key=`), applied at
the point each string is first captured for logging in both files.

Only synthetic secrets are used in this file -- no real credential value
ever appears here or in test output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SYNTHETIC_SECRET = "AIzaSyDfakeTestKeyDoNotUse1234567890"


def test_rr3_7c_sanitizer_redacts_gemini_key_query_param():
    from core.inference.error_sanitize import sanitize_provider_error
    text = (
        f"Client error '404 Not Found' for url "
        f"'https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={SYNTHETIC_SECRET}'\n"
        f"For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404"
    )
    out = sanitize_provider_error(text)
    assert SYNTHETIC_SECRET not in out, out
    # diagnostic context preserved
    assert "404 Not Found" in out
    assert "generateContent" in out
    assert "generativelanguage.googleapis.com" in out


def test_rr3_7c_sanitizer_redacts_partial_key_prefix_too():
    """A truncated/partial prefix of the secret must not survive either --
    not just the full value."""
    from core.inference.error_sanitize import sanitize_provider_error
    text = f"...generateContent?key={SYNTHETIC_SECRET}..."
    out = sanitize_provider_error(text)
    assert SYNTHETIC_SECRET[:8] not in out
    assert SYNTHETIC_SECRET not in out


def test_rr3_7c_sanitizer_redacts_api_key_and_access_token_forms():
    from core.inference.error_sanitize import sanitize_provider_error
    for param in ("key", "api_key", "apikey", "access_token"):
        text = f"https://example.com/v1/x?{param}={SYNTHETIC_SECRET}&other=1"
        out = sanitize_provider_error(text)
        assert SYNTHETIC_SECRET not in out, f"{param} form leaked: {out}"
        assert "other=1" in out  # unrelated query params preserved


def test_rr3_7c_sanitizer_redacts_bearer_token_form():
    """Defense-in-depth for the header-shaped form, even though no
    confirmed VECTOR call site logs it today (httpx's own
    HTTPStatusError message never includes headers)."""
    from core.inference.error_sanitize import sanitize_provider_error
    text = f"Authorization: Bearer {SYNTHETIC_SECRET}"
    out = sanitize_provider_error(text)
    assert SYNTHETIC_SECRET not in out
    assert "Bearer" in out


def test_rr3_7c_sanitizer_never_raises_on_malformed_input():
    from core.inference.error_sanitize import sanitize_provider_error
    assert sanitize_provider_error("") == ""
    assert sanitize_provider_error(None) is None
    assert sanitize_provider_error("no secrets here") == "no secrets here"


def test_rr3_7c_sanitizer_preserves_unrelated_query_params():
    from core.inference.error_sanitize import sanitize_provider_error
    text = f"https://x.com/a?model=gemini-2.0-flash&key={SYNTHETIC_SECRET}&stream=true"
    out = sanitize_provider_error(text)
    assert "model=gemini-2.0-flash" in out
    assert "stream=true" in out
    assert SYNTHETIC_SECRET not in out


# ============================================================
# Exploit-shape reproduction against the real, unmodified logging call
# sites (mocked HTTP layer only -- no real network call, no real secret)
# ============================================================

def test_rr3_7c_vectorcode_llm_gemini_failure_log_is_sanitized():
    """Reproduces the exact real-world shape: a Gemini request fails with a
    non-200 status, httpx.raise_for_status() embeds the URL (with the
    synthetic key) in its exception, and the real, unmodified
    _try_gemini() exception handler must not leak it into the log.

    vectorcode_llm.py uses loguru (not stdlib logging), which pytest's
    caplog fixture does not capture by default -- patch logger.warning
    directly and inspect its actual call arguments instead."""
    from unittest.mock import patch
    import core.inference.vectorcode_llm as vc_llm

    class _FakeResp:
        status_code = 404
        def raise_for_status(self):
            import httpx
            req = httpx.Request("POST", (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={SYNTHETIC_SECRET}"
            ))
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("Client error '404 Not Found' for url "
                                         f"'{req.url}'", request=req, response=resp)

    captured_calls = []
    with patch.object(vc_llm, "_pool_key", return_value=SYNTHETIC_SECRET), \
         patch.object(vc_llm, "_is_rate_limited", return_value=False), \
         patch("httpx.post", return_value=_FakeResp()), \
         patch.object(vc_llm, "_sync_cb_call", side_effect=lambda name, fn: fn()), \
         patch.object(vc_llm.logger, "warning", side_effect=lambda *a, **k: captured_calls.append((a, k))):
        result = vc_llm._try_gemini("vector-focus", [{"role": "user", "content": "hi"}], timeout=5.0)

    assert result == ""
    full_log = " ".join(str(a) for call in captured_calls for a in call[0])
    assert SYNTHETIC_SECRET not in full_log, f"secret leaked into log: {full_log}"
    assert "404" in full_log or "Not Found" in full_log, "diagnostic context should be preserved"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], cwd=str(Path(__file__).parent.parent))
    print("OK test_rr3_7c_secret_log_redaction.py" if result.returncode == 0 else "FAILED")
