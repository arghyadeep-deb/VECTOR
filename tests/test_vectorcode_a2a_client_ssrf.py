"""Regression for vectorcode/src/a2a/client.py: A2AClient(base_url) made
real outbound httpx calls to a caller-supplied base_url with zero SSRF
confinement -- same bug class fixed in core/browser/ and
core/vision_control/browser_controller.py this cycle. Dormant today (zero
real callers anywhere, confirmed via repo-wide grep), fixed anyway per
this cycle's established bar for narrow, no-legitimate-caller-risk fixes.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.a2a.client import A2AClient


def test_metadata_endpoint_blocked():
    with pytest.raises(ValueError, match="SSRF"):
        A2AClient("http://169.254.169.254/latest/meta-data/")


def test_private_ip_blocked_by_default():
    with pytest.raises(ValueError, match="SSRF"):
        A2AClient("http://127.0.0.1:9999")


def test_private_ip_allowed_with_explicit_opt_in():
    client = A2AClient("http://127.0.0.1:9999", allow_private=True)
    assert client._base_url == "http://127.0.0.1:9999"


def test_legitimate_public_url_still_works():
    client = A2AClient("https://example.com/")
    assert client._base_url == "https://example.com"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
