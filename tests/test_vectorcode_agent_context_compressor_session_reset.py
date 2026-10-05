"""Regression for ContextCompressor.on_session_reset() not restoring the
configured summary model after a fallback.

_generate_summary() falls back from a broken/unavailable summary_model to
the main model on certain errors, setting self.summary_model = "" and
self._summary_model_fallen_back = True so it only retries once per
failure. But on_session_reset() -- called on /new or /reset against the
SAME long-lived ContextCompressor instance (see run_agent.py's
on_session_reset() call site, which reuses self.context_compressor for
the agent's whole process lifetime) -- never restored summary_model or
cleared the fallen-back flag. A single transient failure of the user's
configured aux summary model (a momentary rate limit or 503) therefore
permanently and silently downgraded every future compression to the
full-price main model, for the rest of the process, even across fresh
/new sessions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))


def _compressor():
    from agent.context_compressor import ContextCompressor

    return ContextCompressor(
        model="gpt-4o-mini",
        summary_model_override="cheap-summary-model",
        quiet_mode=True,
    )


def test_summary_model_override_preserved_on_init():
    cc = _compressor()
    assert cc.summary_model == "cheap-summary-model"
    assert cc._summary_model_override == "cheap-summary-model"
    assert cc._summary_model_fallen_back is False


def test_session_reset_restores_summary_model_after_simulated_fallback():
    cc = _compressor()

    # Simulate what _generate_summary()'s except-block does on a
    # permanent-looking error from the configured aux model.
    cc.summary_model = ""
    cc._summary_model_fallen_back = True

    cc.on_session_reset()

    assert cc.summary_model == "cheap-summary-model", (
        "on_session_reset() must restore the originally-configured "
        "summary model -- otherwise one transient aux-model failure "
        "permanently downgrades every future /new session to the main "
        "model for the whole process lifetime"
    )
    assert cc._summary_model_fallen_back is False


def test_session_reset_is_a_noop_for_summary_model_when_no_fallback_occurred():
    cc = _compressor()
    cc.on_session_reset()
    assert cc.summary_model == "cheap-summary-model"
    assert cc._summary_model_fallen_back is False


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
