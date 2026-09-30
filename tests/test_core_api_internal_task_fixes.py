"""Regression tests for 2 real bugs found in a deep-verify pass on core/api/'s
top-level shared infrastructure files (Phase 3 whole-repo audit, Claude/Codex
50/50 split, 2026-09-30).

1. core/api/tasks.py's VECTOR_INTERNAL_TOKEN was read into a module-global at
   import time (`_INTERNAL_TOKEN = os.environ.get(...)`) -- the exact
   anti-pattern core/api/auth.py's own _api_key() docstring already explains
   was a bug there: a frozen module-global "made the documented no-key/
   localhost mode unreachable once the process imported with .env loaded
   (and untestable via monkeypatch)". Fixed by reading at call time via a
   new _internal_token() helper, matching auth.py's established fix.

2. core/api/app.py's /metrics endpoint had 2 more instances of the
   "[VECTOR] silent swallow" placeholder-logging bug already fixed 19 times
   elsewhere this cycle -- the episodic-stats and agent-registry metric
   blocks logged a useless fixed string with zero exception info on failure.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_internal_token_env_var_read_at_call_time_not_import_time(monkeypatch):
    """The old module-global would still be "" here even after monkeypatching
    the env var post-import, since it was frozen at first import. Reload with
    the var UNSET first to simulate "imported before .env loaded", then set
    it and confirm the live helper picks up the new value without a reimport."""
    monkeypatch.delenv("VECTOR_INTERNAL_TOKEN", raising=False)
    if "core.api.tasks" in sys.modules:
        importlib.reload(sys.modules["core.api.tasks"])
    else:
        import core.api.tasks  # noqa: F401

    from core.api.tasks import _internal_token

    assert _internal_token() == ""

    monkeypatch.setenv("VECTOR_INTERNAL_TOKEN", "test-secret-token")
    assert _internal_token() == "test-secret-token"


@pytest.mark.asyncio
async def test_submit_task_rejects_when_token_set_after_import(monkeypatch):
    """End-to-end: the actual route handler must see a token set AFTER this
    module was first imported (the real-world .env-loaded-late scenario),
    not just the helper function in isolation."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    import core.api.tasks as tasks_module

    monkeypatch.setenv("VECTOR_INTERNAL_TOKEN", "live-token-set-after-import")

    app = FastAPI()
    app.include_router(tasks_module.router)
    client = TestClient(app)

    # Wrong token -> 403 (proves the env var IS being read live, not "" from
    # a stale frozen import -- a stale "" would 503 instead, never reaching
    # the token-comparison branch at all).
    resp = client.post(
        "/api/v1/tasks",
        json={"action_type": "noop", "params": {}, "source": "test"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 403


def test_api_app_metrics_silent_swallow_placeholder_is_gone():
    """Golden test: the literal placeholder string must never reappear in
    core/api/app.py's /metrics handler."""
    src = Path(__file__).parent.parent / "core" / "api" / "app.py"
    text = src.read_text(encoding="utf-8")
    assert '"[VECTOR] silent swallow"' not in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
