"""Regression for vectorcode/src/agent/account_usage.py's fetch_account_usage():

the outer except Exception: return None swallowed ANY failure (network
error, auth failure, API schema change, a bug in this code itself) with
zero logging -- an operator debugging "why does account usage show
unavailable" had no diagnostic trail at all. Also fixed a narrower inner
swallow in _fetch_openrouter_account_usage's optional /key lookup the
same way.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from loguru import logger

from agent import account_usage


def test_fetch_account_usage_logs_on_failure():
    logged = []
    handler_id = logger.add(lambda msg: logged.append(str(msg)), level="WARNING")
    try:
        with patch.object(
            account_usage,
            "_fetch_anthropic_account_usage",
            side_effect=RuntimeError("boom"),
        ):
            result = account_usage.fetch_account_usage("anthropic")
    finally:
        logger.remove(handler_id)

    assert result is None
    assert any("Failed to fetch account usage" in line for line in logged)
    assert any("boom" in line for line in logged)


def test_openrouter_key_lookup_failure_logs_and_still_returns_credits():
    logged = []
    handler_id = logger.add(lambda msg: logged.append(str(msg)), level="DEBUG")
    try:
        import httpx

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None):
                if url.endswith("/credits"):
                    resp = httpx.Response(
                        200, json={"data": {"total_credits": 10.0, "total_usage": 2.0}}
                    )
                    resp.raise_for_status = lambda: None
                    return resp
                raise RuntimeError("key endpoint down")

        with patch.object(account_usage.httpx, "Client", _FakeClient), patch.object(
            account_usage,
            "resolve_runtime_provider",
            return_value={"api_key": "sk-test", "base_url": "https://openrouter.ai/api/v1"},
        ):
            result = account_usage._fetch_openrouter_account_usage(None, None)
    finally:
        logger.remove(handler_id)

    assert result is not None
    assert result.details  # credits-only detail still populated
    assert any("key endpoint down" in line for line in logged)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
