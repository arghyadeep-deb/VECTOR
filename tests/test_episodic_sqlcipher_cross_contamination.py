"""
Regression guard for a real cross-contamination bug found while fixing
docs/repo_analysis/_MASTER_TODO.md §3 item 12 (the missing
core.research_engine.web package).

Root cause: SQLCipher's `cipher_default_page_size` (and the other
`cipher_default_*` pragmas) are PROCESS-WIDE, not scoped to one connection.
core/research_engine/database/sqlcipher_utils.py::apply_cipher_defaults_before_key()
sets `PRAGMA cipher_default_page_size = 16384` for its OWN, separate
database -- but core/memory/episodic.py's `_open_sqlcipher_connection()`
never explicitly set its own page size, silently inheriting whatever the
ambient process-wide default was. Importing core.research_engine anywhere
earlier in the same process (confirmed: just importing ContentFetcher is
enough) broke vector_memory.db's HMAC verification on the very next
connection open -- "hmac check failed for pgno=1" -- a real, reproducible
failure (confirmed before the fix: 4/4 failures, deterministic, not flaky).

Fixed by having episodic.py explicitly set `PRAGMA cipher_page_size = 4096`
(SQLCipher 4's stock default, matching what vector_memory.db was actually
created under) on every connection, making it immune to whatever else has
run earlier in the process.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_episodic_memory_survives_research_engine_import_in_same_process():
    """The actual real-world scenario that broke before the fix: import
    something from core.research_engine (which sets process-wide SQLCipher
    defaults), THEN open VECTOR's own main memory DB."""
    from core.research_engine.content_fetcher.fetcher import ContentFetcher  # noqa: F401

    from core.memory.episodic import EpisodicMemory

    memory = EpisodicMemory()
    # A real read against the real DB -- if the HMAC mismatch regresses,
    # this raises MemoryDatabaseUnavailable instead of returning a count.
    stats = memory.get_stats()
    assert isinstance(stats, dict)


def test_open_sqlcipher_connection_sets_explicit_page_size():
    import inspect
    from core.memory import episodic

    src = inspect.getsource(episodic._open_sqlcipher_connection)
    assert "cipher_page_size" in src, "explicit page-size pragma was removed — reintroduces the cross-contamination bug"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
