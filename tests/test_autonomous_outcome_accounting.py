"""Regression tests for shared non-completion outcome interpretation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "unavailable"},
        {"status": "needs_config"},
        {"status": "incomplete"},
        {"status": "failed", "error": "provider failed"},
    ],
)
def test_shared_outcome_assessment_rejects_non_completion(payload):
    from core.runtime.executor import AutonomousExecutor

    gateway_result = SimpleNamespace(
        approved=True,
        executed=True,
        result=payload,
        reason="approved",
        level="GREEN",
    )

    verification = AutonomousExecutor._verify_gateway_result(gateway_result)

    assert verification["ok"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
