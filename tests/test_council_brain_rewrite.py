"""Regression tests for the 2026-09-24 external review's Phase 2 finding:
CouncilBrain's original design had a 5.0s hardcoded timeout (measured 58%
timeout rate against real deliberations in data/council_log.jsonl), ranked
member responses by len() instead of extracting a real vote, and hardcoded
confidence to exactly 0.75 -- since permission_gateway.py's auto-proceed
gate is `confidence >= 0.75`, the gate never filtered anything.

Real ollama.Client is never called here (per .claude/rules/testing.md,
external LLM boundaries are a legitimate mock point) -- what's tested is
real: vote parsing, majority/tie logic, confidence computation, the
configurable timeout, and the safety fallback to defer on any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.brain.council import CouncilBrain, _parse_vote


def _fake_ollama_client(responses: list[str]):
    """Mimics ollama.Client(...).chat(...) returning responses in order,
    one per call, matching the real {"message": {"content": ...}} shape."""
    calls = iter(responses)

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def chat(self, **kwargs):
            return {"message": {"content": next(calls)}}
    return _FakeClient


# ── Vote parsing ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("PROCEED. This is safe.", "proceed"),
    ("I think we should REJECT this.", "reject"),
    ("Let's DEFER to the owner.", "defer"),
    ("proceed with caution", "proceed"),
    ("This response has no clear vote at all.", "defer"),  # fail-closed
    ("", "defer"),
])
def test_parse_vote_extracts_keyword_fail_closed(text, expected):
    assert _parse_vote(text) == expected


# ── Real majority / confidence computation ─────────────────────────────────

@pytest.mark.asyncio
async def test_unanimous_vote_skips_chairman_and_gives_max_confidence():
    cb = CouncilBrain()
    fake_cls = _fake_ollama_client(["PROCEED. Safe.", "PROCEED. Fine.", "PROCEED. OK."])
    with patch("ollama.Client", new=fake_cls):
        result = await cb.deliberate("proceed?")
    assert result["verdict"] == "proceed"
    assert result["confidence"] == 1.0
    assert result["votes"] == ["proceed", "proceed", "proceed"]


@pytest.mark.asyncio
async def test_2_1_majority_skips_chairman_and_gives_partial_confidence():
    cb = CouncilBrain()
    fake_cls = _fake_ollama_client(["PROCEED.", "PROCEED.", "REJECT."])
    with patch("ollama.Client", new=fake_cls):
        result = await cb.deliberate("proceed?")
    assert result["verdict"] == "proceed"
    assert result["confidence"] == round(0.5 + 0.5 * (2 / 3), 2)
    assert result["votes"] == ["proceed", "proceed", "reject"]


@pytest.mark.asyncio
async def test_genuine_split_calls_chairman_for_tiebreak():
    """3-way split (proceed/reject/defer) -- no majority, chairman must be
    called, and confidence must be conservative (0.5), not the old
    hardcoded 0.75 that always passed the auto-proceed gate."""
    cb = CouncilBrain()
    member_replies = iter(["PROCEED.", "REJECT.", "DEFER."])
    chairman_calls = []

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def chat(self, *, model, **kwargs):
            if model == cb._council_model:
                chairman_calls.append(kwargs)
                return {"message": {"content": "REJECT. The split council should not auto-proceed."}}
            return {"message": {"content": next(member_replies)}}

    with patch("ollama.Client", new=_FakeClient):
        result = await cb.deliberate("proceed?")

    assert len(chairman_calls) == 1, "a genuine 3-way split must call the chairman"
    assert result["verdict"] == "reject"
    assert result["confidence"] == 0.5


@pytest.mark.asyncio
async def test_all_defer_never_auto_proceeds():
    cb = CouncilBrain()
    fake_cls = _fake_ollama_client(["DEFER.", "DEFER.", "DEFER."])
    with patch("ollama.Client", new=fake_cls):
        result = await cb.deliberate("proceed?")
    assert result["verdict"] == "defer"
    assert result["confidence"] == 1.0  # unanimous defer -- correctly never reaches the proceed gate


# ── Failure safety (unchanged behaviour) ───────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_exception_returns_error_dict_not_a_crash():
    cb = CouncilBrain()
    with patch("ollama.Client", side_effect=RuntimeError("connection refused")):
        result = await cb.deliberate("proceed?")
    assert "error" in result


@pytest.mark.asyncio
async def test_deliberate_action_defers_on_deliberate_error():
    cb = CouncilBrain()
    with patch.object(CouncilBrain, "deliberate", return_value={"error": "boom"}):
        result = await cb.deliberate_action("send_email", {})
    assert result["verdict"] == "defer"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_deliberate_action_exception_still_defers():
    cb = CouncilBrain()
    with patch.object(CouncilBrain, "deliberate", side_effect=RuntimeError("boom")):
        result = await cb.deliberate_action("send_email", {})
    assert result["verdict"] == "defer"
    assert result["confidence"] == 0.0


# ── Configurable timeout (was hardcoded to 5.0) ────────────────────────────

def test_timeout_is_configurable_and_no_longer_hardcoded_to_5s():
    cb = CouncilBrain()
    assert cb._timeout() != 5.0
    with patch("core.brain.council.CONFIG", {"council": {"deliberation_timeout": 45.0}}):
        assert cb._timeout() == 45.0


@pytest.mark.asyncio
async def test_deliberate_passes_configured_timeout_to_ollama_client():
    cb = CouncilBrain()
    seen_timeouts = []

    class _CapturingClient:
        def __init__(self, *a, **kw):
            seen_timeouts.append(kw.get("timeout"))
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def chat(self, **kwargs):
            return {"message": {"content": "PROCEED."}}

    with patch("core.brain.council.CONFIG", {
        "ollama_host": "http://127.0.0.1:11434",
        "models": {"chairman": "vector-chairman", "reasoning": "vector-reasoning"},
        "council": {"deliberation_timeout": 42.0},
    }), patch("ollama.Client", new=_CapturingClient):
        await cb.deliberate("proceed?")

    assert 42.0 in seen_timeouts, f"expected configured timeout 42.0, got {seen_timeouts}"


# ── permission_gateway.py contract preserved ───────────────────────────────

@pytest.mark.asyncio
async def test_deliberate_action_return_shape_matches_gateway_contract():
    """permission_gateway.py's _handle_red_tier reads exactly these 4 keys."""
    cb = CouncilBrain()
    fake_cls = _fake_ollama_client(["PROCEED.", "PROCEED.", "PROCEED."])
    with patch("ollama.Client", new=fake_cls):
        result = await cb.deliberate_action("run_tests", {"suite": "unit"})
    assert set(result.keys()) >= {"verdict", "votes", "rationale", "confidence"}
    assert result["verdict"] in ("proceed", "reject", "defer")
    assert isinstance(result["confidence"], float)
    assert isinstance(result["votes"], list)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
