"""Runtime is free-tier only (owner decision 2026-07-08): the legacy vectorcode_llm OpenRouter tier must never call a paid model.

Found 2026-09-27: _OPENROUTER_MAP names anthropic/claude-opus-4-7 and claude-sonnet-4-6; the only reason it never charged was that
the OpenRouter account has no credit (HTTP 402, 57 times in one backend session).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from core.inference import vectorcode_llm as vc


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "hi"}}]}


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(vc, "_pool_key", lambda *a, **k: "test-key")
    monkeypatch.setattr(vc, "_is_rate_limited", lambda *a, **k: False)
    monkeypatch.setattr(vc, "_sync_cb_call", lambda name, fn: fn())
    monkeypatch.setattr(vc, "_record_usage", lambda *a, **k: None)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (seen.append(kw["json"]["model"]), _Resp())[1])
    return seen


@pytest.mark.parametrize("hint", ["vector-reasoning", "vector-chairman", "vector-coder", "vector-deep", "unknown-local-model",
                                   "anthropic/claude-sonnet-4-6"])
def test_paid_models_are_never_called(calls, hint):
    assert vc._try_openrouter(hint, [{"role": "user", "content": "x"}], 5) == ""
    assert calls == []


@pytest.mark.parametrize("hint", ["vector-fast", "vector-r1", "qwen/qwen3-next-80b-a3b-instruct:free"])
def test_free_models_still_work(calls, hint):
    assert vc._try_openrouter(hint, [{"role": "user", "content": "x"}], 5) == "hi"
    assert len(calls) == 1 and calls[0].endswith(":free")


def test_the_gemini_default_is_not_the_retired_model():
    assert vc._map_to_gemini_model("anything-unmapped") == "gemini-2.5-flash"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
