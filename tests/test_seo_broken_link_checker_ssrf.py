"""Regression: core/seo/broken_link_checker.py's BrokenLinkChecker.check()
crawled start_url and every link discovered on a crawled page via a real
urlopen() with zero SSRF validation -- a caller-supplied start_url, or a
malicious page linking to an internal/metadata address, could make VECTOR's
own process fetch an internal service or a cloud metadata endpoint
(169.254.169.254). Same bug class fixed in core/scraper/+core/browser/ this
cycle. Found during the Phase 3 whole-repo audit (2026-10-02).
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.seo.broken_link_checker import BrokenLinkChecker


def test_metadata_endpoint_start_url_is_blocked_not_fetched():
    checker = BrokenLinkChecker()
    with patch("core.seo.broken_link_checker._check_url") as mock_check:
        report = checker.check("http://169.254.169.254/latest/meta-data/", max_pages=1)
    mock_check.assert_not_called()
    assert report["broken_count"] == 0
    assert "blocked" in report["broken_links"][0]["error"] if report["broken_links"] else True
    # The URL was never actually checked -- confirm it's recorded as blocked, not silently dropped
    assert report["links_checked"] == 1


def test_private_ip_start_url_is_blocked():
    checker = BrokenLinkChecker()
    with patch("core.seo.broken_link_checker._check_url") as mock_check:
        checker.check("http://127.0.0.1:8000/admin", max_pages=1)
    mock_check.assert_not_called()


def test_legitimate_public_url_still_reaches_check(monkeypatch):
    checker = BrokenLinkChecker()
    with patch("core.seo.broken_link_checker._check_url", return_value=(200, None)) as mock_check, \
         patch("core.seo.broken_link_checker._fetch_links", return_value=set()):
        checker.check("https://example.com/", max_pages=1)
    mock_check.assert_called_once()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
