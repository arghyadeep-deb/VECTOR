"""
SSRF protection regression tests for the research-engine content fetcher.

docs/repo_analysis/crawl4ai.md's own acceptance criteria: "No crawler can
read local files or internal URLs unless explicitly allowed." The guard
(core/research_engine/security/ssrf_validator.py::validate_url) and its
call site (ContentFetcher.fetch():181) both already existed and were wired
— confirmed via grep before writing these tests — but had zero test
coverage anywhere in the suite. This was the doc's own "Next" item
("add SSRF/rate-limit tests for live web extraction path"), closed here
without touching the (already-correct) guard logic itself.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_validate_url_blocks_aws_metadata_endpoint():
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("http://169.254.169.254/latest/meta-data/") is False


def test_validate_url_blocks_localhost_by_default():
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("http://localhost:8000/admin") is False
    assert validate_url("http://127.0.0.1/admin") is False


def test_validate_url_blocks_private_ip_ranges_by_default():
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("http://192.168.1.1/") is False
    assert validate_url("http://10.0.0.5/") is False
    assert validate_url("http://172.16.0.1/") is False


def test_validate_url_blocks_metadata_ip_even_with_allow_private_ips():
    """Cloud metadata endpoints are ALWAYS blocked regardless of the
    allow_localhost/allow_private_ips flags — this is the doc's own stated
    invariant ("ALWAYS blocked regardless of these flags")."""
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("http://169.254.169.254/", allow_private_ips=True) is False
    assert validate_url("http://169.254.169.254/", allow_localhost=True) is False


def test_validate_url_rejects_non_http_schemes():
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("file:///etc/passwd") is False
    assert validate_url("ftp://example.com/") is False


def test_validate_url_allows_normal_public_url():
    from core.research_engine.security.ssrf_validator import validate_url
    assert validate_url("https://example.com/page") is True


def test_content_fetcher_blocks_metadata_url_without_network_call(monkeypatch):
    """End-to-end: ContentFetcher.fetch() must refuse a metadata-IP URL
    BEFORE reaching any downloader — confirmed by spying on
    _get_downloader and asserting it is never called.

    Previously skipped: importing ContentFetcher hit a missing
    core.research_engine.web package. That structural gap is now fixed
    (clean-room core.research_engine.web.models.settings rebuilt from the
    real usage contract in settings/manager.py, plus guarding the
    Flask-blueprint imports research_library/__init__.py never needed --
    see docs/repo_analysis/_MASTER_TODO.md §3 item 12) — this test now
    runs for real instead of documenting an intended future contract.
    """
    from core.research_engine.content_fetcher.fetcher import ContentFetcher

    fetcher = ContentFetcher()
    called = {"downloader_requested": False}

    def _spy_get_downloader(self, url_type):
        called["downloader_requested"] = True
        return None

    monkeypatch.setattr(ContentFetcher, "_get_downloader", _spy_get_downloader)

    result = fetcher.fetch("http://169.254.169.254/latest/meta-data/")
    assert result["status"] == "error"
    assert "SSRF" in result["error"] or "security validation" in result["error"]
    assert called["downloader_requested"] is False


def test_content_fetcher_blocks_localhost_url_without_network_call(monkeypatch):
    """See docstring on test_content_fetcher_blocks_metadata_url_without_network_call
    -- the missing-package gap that previously skipped this is now fixed."""
    from core.research_engine.content_fetcher.fetcher import ContentFetcher

    fetcher = ContentFetcher()
    called = {"downloader_requested": False}

    def _spy_get_downloader(self, url_type):
        called["downloader_requested"] = True
        return None

    monkeypatch.setattr(ContentFetcher, "_get_downloader", _spy_get_downloader)

    result = fetcher.fetch("http://127.0.0.1:8000/internal-admin")
    assert result["status"] == "error"
    assert called["downloader_requested"] is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
