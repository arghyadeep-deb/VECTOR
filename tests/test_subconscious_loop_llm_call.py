"""SubconsciousLoop.run_once() called ProviderClient.complete() with an unsupported shape and failed on every run."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.inference.provider_client import ProviderClient


@pytest.mark.asyncio
async def test_run_once_calls_the_real_complete_signature(isolated_vector_db, monkeypatch):
    from districts.chief_of_staff.subconscious_loop import SubconsciousLoop

    seen = {}

    class Fake(ProviderClient):
        def __init__(self):
            pass

        async def chat(self, messages, **kwargs):
            seen["messages"], seen["kwargs"] = messages, kwargs
            return SimpleNamespace(content="noop")

    monkeypatch.setattr("core.inference.provider_client.get_client", lambda: Fake())
    out = await SubconsciousLoop().run_once()
    assert out.get("error") is None, out
    assert out["decision"] == "noop"
    assert seen["messages"][-1]["role"] == "user" and "subconscious reflection layer" in seen["messages"][-1]["content"]
    assert seen["kwargs"]["district"] == "chief_of_staff"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
