"""
Regression guard for a real, reproducible import break found during the
2026-06-23 repo-analysis audit: `import langchain_anthropic` raised
`ImportError: cannot import name 'ContextOverflowError' from
'langchain_core.exceptions'`.

Root cause: requirements.txt declared an internally INCONSISTENT set of
langchain-* pins -- langchain-core==1.3.2 (the 1.x line) alongside
langchain-openai==0.3.35 (the 0.x line, which structurally requires
langchain-core<1.0.0). The installed environment had drifted even further:
langchain-anthropic was never pinned at all (pip always installed latest,
1.4.3, which needs langchain-core>=1.x), while langchain/langchain-core
themselves were stuck on stale 0.3.x installs.

Fixed by bumping langchain-openai (0.3.35 -> 1.3.3), langchain-text-splitters
(0.3.11 -> 1.1.2), langchain-core (1.3.2 -> 1.4.8), langchain-protocol
(0.0.14 -> 0.0.18), and pinning langchain-anthropic explicitly (1.4.3) so it
can't silently drift to an incompatible version again. Verified every real
VECTOR call site (ChatOpenAI, OpenAIEmbeddings, AzureChatOpenAI,
RecursiveCharacterTextSplitter, TokenTextSplitter,
SentenceTransformersTokenTextSplitter -- all stable, long-standing classes
present in both old and new lines) still imports correctly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_langchain_anthropic_imports_cleanly():
    import langchain_anthropic
    from langchain_anthropic import ChatAnthropic
    assert ChatAnthropic is not None


def test_langchain_core_exceptions_has_context_overflow_error():
    """The specific symbol langchain_anthropic needed and couldn't find."""
    from langchain_core.exceptions import ContextOverflowError
    assert ContextOverflowError is not None


def test_langchain_openai_imports_cleanly():
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings, AzureChatOpenAI
    assert ChatOpenAI is not None
    assert OpenAIEmbeddings is not None
    assert AzureChatOpenAI is not None


def test_langchain_text_splitters_imports_cleanly():
    from langchain_text_splitters import (
        RecursiveCharacterTextSplitter,
        TokenTextSplitter,
        SentenceTransformersTokenTextSplitter,
    )
    assert RecursiveCharacterTextSplitter is not None


def test_real_vector_call_sites_import_cleanly():
    """Every real VECTOR module that touches the upgraded packages."""
    from core.research_engine.config.llm_config import get_llm  # noqa: F401
    from core.research_engine.llm.providers.openai_base import ChatOpenAI  # noqa: F401
    from core.research_engine.embeddings.splitters.text_splitter_registry import (  # noqa: F401
        VALID_SPLITTER_TYPES,
    )
    from core.trading.llm_clients.openai_client import OpenAIClient  # noqa: F401


def test_full_search_module_importable():
    """The exact module whose import was confirmed broken during the
    original audit (docs/repo_analysis/_MASTER_TODO.md §3 item 12's
    'honest scope note')."""
    from core.research_engine.web_search_engines.engines import full_search
    assert full_search is not None


def test_requirements_txt_pins_are_internally_consistent():
    """Static guard: langchain-openai must not regress to the 0.x line
    while langchain-core stays on 1.x -- that exact combination was the
    root cause of the original break."""
    req_path = Path(__file__).parent.parent / "requirements.txt"
    text = req_path.read_text(encoding="utf-8")
    assert "langchain-openai==0.3" not in text, "langchain-openai regressed to the 0.x line, incompatible with langchain-core 1.x"
    assert "langchain-core==0." not in text, "langchain-core regressed to the 0.x line"
    assert "langchain-anthropic==" in text, "langchain-anthropic must stay explicitly pinned, not left to drift to latest"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
