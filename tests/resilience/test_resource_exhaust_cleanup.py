"""Regression test: ResourceExhaustInjector.cleanup() left its disk-exhaustion
temp file on disk forever (NamedTemporaryFile(delete=False) + close() does
not delete the file). Found during the Phase 3 audit of core/resilience
(2026-10-01) -- every disk-exhaustion chaos run (up to ~5GB) leaked
permanently instead of being reclaimed by cleanup().
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.resilience.injectors.resource_exhaust import ResourceExhaustInjector


@pytest.mark.asyncio
async def test_cleanup_deletes_leftover_chaos_temp_file():
    injector = ResourceExhaustInjector()
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".chaos")
    f.write(b"0" * 1024)
    injector._allocations.append(f)
    path = f.name
    assert os.path.exists(path)

    await injector.cleanup()

    assert not os.path.exists(path), "cleanup() must unlink delete=False temp files, not just close() them"
    assert injector._allocations == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
