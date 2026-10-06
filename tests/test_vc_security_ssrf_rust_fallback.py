"""Regression for vectorcode/src/vc_security/ssrf.py's check_ssrf():

check_ssrf() called `_rust.check_ssrf(url)` unconditionally after
`_rust = get_rust_module()`. When the Rust extension isn't built,
get_rust_module() returns None (confirmed on this machine), so every call
raised AttributeError instead of falling back to the pure-Python
implementation (_check_ssrf_python) that already existed in the same file.
This crashed every caller: vc_tools/http_request.py, vc_tools/browser.py,
vc_tools/web_search.py -- none of them catch the exception, so the SSRF
check's absence didn't silently allow unsafe URLs through (fail-closed by
accident), but it did make outbound HTTP entirely unusable without the
Rust extension.
"""
from __future__ import annotations

from unittest import mock

from vectorcode.src.vc_security import ssrf


def test_check_ssrf_falls_back_to_python_when_rust_module_is_none():
    with mock.patch(
        "vectorcode.src._rust_bridge.get_rust_module", return_value=None
    ):
        # A cloud metadata endpoint must still be blocked via the Python
        # fallback, not crash with AttributeError.
        result = ssrf.check_ssrf("http://169.254.169.254/latest/meta-data/")
    assert result is not None
    assert "metadata" in result.lower() or "private" in result.lower()


def test_check_ssrf_falls_back_to_python_when_rust_module_is_unimportable():
    with mock.patch(
        "vectorcode.src._rust_bridge.get_rust_module", side_effect=ImportError
    ):
        result = ssrf.check_ssrf("http://169.254.169.254/latest/meta-data/")
    assert result is not None


def test_check_ssrf_allows_a_safe_public_url_via_python_fallback():
    with mock.patch(
        "vectorcode.src._rust_bridge.get_rust_module", return_value=None
    ):
        result = ssrf.check_ssrf("https://example.com/path")
    assert result is None
