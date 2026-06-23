"""
Closes the last two open items from docs/repo_analysis/crawl4ai.md's
"Recommendation For Sonnet" (items 2 and 3) — SSRF (item 4's acceptance
criteria) was already closed in an earlier pass (tests/test_ssrf_protection.py):

  2. "Implement a disabled-by-default Crawl4AI provider path or clean-room
     equivalent."
  3. "Normalize outputs into VECTOR research artifacts with citations and
     hashes" — persisted, not just constructed in memory.

Built directly against core/research_engine/content_fetcher/extraction.py
rather than wiring through fetcher.py — fetcher.py (and every other
extraction.py caller checked) transitively imports a missing
core.research_engine.web package in this checkout (confirmed via direct
import attempts; see docs/repo_analysis/_MASTER_TODO.md §3 item 12), a
real, separate, much larger structural gap. extraction.py itself has zero
problematic imports (pure stdlib) and is the doc's actual "VECTOR-native
contract" — these additions extend it without touching the broken chain.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_crawl4ai_provider_unavailable_without_package():
    from core.research_engine.content_fetcher.extraction import Crawl4AIProvider

    provider = Crawl4AIProvider(enabled=True)
    assert provider.available() is False


def test_crawl4ai_provider_unavailable_when_disabled():
    from core.research_engine.content_fetcher.extraction import Crawl4AIProvider

    provider = Crawl4AIProvider(enabled=False)
    assert provider.available() is False


def test_crawl4ai_provider_fetch_raises_clean_error_when_unavailable():
    from core.research_engine.content_fetcher.extraction import Crawl4AIProvider

    provider = Crawl4AIProvider(enabled=True)
    try:
        import asyncio
        asyncio.run(provider.fetch("https://example.com"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "crawl4ai" in str(exc).lower()


def test_crawl4ai_provider_fetch_normalizes_to_webextractionartifact(monkeypatch):
    """When the real package IS available, fetch() must return the same
    WebExtractionArtifact contract every other extraction path uses —
    proves the adapter's normalization without needing the real package
    installed to test it."""
    from core.research_engine.content_fetcher.extraction import (
        Crawl4AIProvider, WebExtractionArtifact,
    )
    import asyncio

    provider = Crawl4AIProvider(enabled=True)

    class _FakeResult:
        markdown = "# Hello\n\nWorld"
        html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        url = "https://example.com"
        links = {"internal": [{"href": "https://example.com/about", "text": "About"}]}
        metadata = {"title": "Hello Page"}

    class _FakeCrawler:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def arun(self, url):
            return _FakeResult()

    monkeypatch.setattr(provider, "_load_crawler", lambda: _FakeCrawler())

    artifact = asyncio.run(provider.fetch("https://example.com", query="hello"))
    assert isinstance(artifact, WebExtractionArtifact)
    assert artifact.extraction_mode == "crawl4ai_clean_markdown"
    assert artifact.title == "Hello Page"
    assert "Hello" in artifact.markdown
    assert artifact.content_hash
    assert any(l["url"] == "https://example.com/about" for l in artifact.links)


def test_persist_extraction_artifact_writes_to_episodic_memory(monkeypatch):
    from core.research_engine.content_fetcher.extraction import (
        build_extraction_artifact, persist_extraction_artifact,
    )

    calls = []

    class _FakeEpisodicMemory:
        def store(self, **kwargs):
            calls.append(kwargs)
            return "fake-id-123"

    monkeypatch.setattr(
        "core.research_engine.content_fetcher.extraction._get_episodic_memory",
        lambda: _FakeEpisodicMemory(),
    )

    artifact = build_extraction_artifact("https://example.com", "<p>hi</p>", query="test")
    handle = persist_extraction_artifact(artifact, query="test")

    assert handle is not None
    assert len(calls) == 1
    assert calls[0]["event_type"] == "web_extraction_artifact"
    assert calls[0]["content"]["content_hash"] == artifact.content_hash
    assert calls[0]["content"]["url"] == "https://example.com"


def test_persist_extraction_artifact_never_raises_on_failure(monkeypatch):
    from core.research_engine.content_fetcher.extraction import (
        build_extraction_artifact, persist_extraction_artifact,
    )

    def _broken():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "core.research_engine.content_fetcher.extraction._get_episodic_memory",
        _broken,
    )

    artifact = build_extraction_artifact("https://example.com", "<p>hi</p>")
    handle = persist_extraction_artifact(artifact)
    assert handle is None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
