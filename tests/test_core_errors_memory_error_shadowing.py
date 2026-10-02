"""Regression: core/errors.py's memory-operation exception used to be
named MemoryError, shadowing Python's own builtin MemoryError (the real
out-of-memory exception) -- the same risk this file already correctly
avoided for VectorTimeoutError vs. builtin TimeoutError. Renamed to
VectorMemoryError. Zero real callers existed (confirmed via repo-wide
grep), so this is a zero-risk rename, found during the Phase 3 whole-repo
audit (2026-10-02).
"""
import builtins
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.errors import VectorMemoryError, VectorError


def test_vector_memory_error_does_not_shadow_builtin():
    assert VectorMemoryError is not builtins.MemoryError
    assert not issubclass(VectorMemoryError, builtins.MemoryError)


def test_vector_memory_error_is_a_vector_error():
    assert issubclass(VectorMemoryError, VectorError)
    e = VectorMemoryError("store", "disk full")
    assert "store" in str(e)
    assert e.retryable is False


def test_catching_builtin_memory_error_still_works():
    # The whole point: a real OOM condition must still be catchable as
    # the builtin, not accidentally swallowed by a same-named custom class.
    try:
        raise MemoryError("real OOM")
    except MemoryError as e:
        assert not isinstance(e, VectorError)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
