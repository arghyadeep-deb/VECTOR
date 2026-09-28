"""Sub-project B: previously unreachable core/ modules that are now wired in
(repo hygiene -> ci_gate, OAuth proactive refresh + cloud heartbeat -> cron)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ci_gate():
    spec = importlib.util.spec_from_file_location("ci_gate_under_test", ROOT / "tools" / "ci_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ci_gate_runs_the_hygiene_check_and_current_tree_is_clean():
    gate = _ci_gate()
    gate._check_repo_hygiene()  # must not raise on the real tracked files
    assert "_check_repo_hygiene()" in (ROOT / "tools" / "ci_gate.py").read_text(encoding="utf-8")


def test_ci_gate_hygiene_fails_on_a_tracked_secret(monkeypatch):
    gate = _ci_gate()
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *a, **k: ".env\ncore/x.py\n")
    with pytest.raises(SystemExit) as exc:
        gate._check_repo_hygiene()
    assert ".env" in str(exc.value) and "sensitive" in str(exc.value)


def test_new_jobs_are_registered_as_intervals(monkeypatch):
    import core.loop.cron_jobs as cj

    seen = {}
    monkeypatch.setattr(cj, "_try_register", lambda *a, **k: True)
    monkeypatch.setattr(cj, "_try_register_interval", lambda sched, jid, minutes, fn: seen.setdefault(jid, minutes) or True)
    cj.register_default_jobs(object())
    assert seen["oauth-refresh"] == 30 and seen["cloud-heartbeat"] == 5


@pytest.mark.asyncio
async def test_oauth_refresh_job_calls_refresh_expiring_tokens():
    import core.loop.cron_jobs as cj

    mgr = MagicMock()
    mgr.refresh_expiring_tokens.return_value = ["google"]
    with patch("core.engine.oauth.flows.OAuthFlowManager", return_value=mgr):
        r = await cj.job_oauth_refresh()
    mgr.refresh_expiring_tokens.assert_called_once_with(60)
    assert r == {"status": "ok", "refreshed": ["google"]}


@pytest.mark.asyncio
async def test_oauth_refresh_job_never_raises():
    import core.loop.cron_jobs as cj

    with patch("core.engine.oauth.flows.OAuthFlowManager", side_effect=RuntimeError("boom")):
        r = await cj.job_oauth_refresh()
    assert r["status"] == "error" and "boom" in r["error"]


@pytest.mark.asyncio
async def test_cloud_heartbeat_is_a_noop_without_a_brain_url(monkeypatch):
    import core.loop.cron_jobs as cj
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG, "cloud", {"brain_url": "", "api_key": ""})
    assert (await cj.job_cloud_heartbeat()) == {"status": "disabled"}


@pytest.mark.asyncio
async def test_cloud_heartbeat_sends_when_configured(monkeypatch):
    import core.loop.cron_jobs as cj
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG, "cloud", {"brain_url": "https://brain.example", "api_key": "k"})
    with patch("core.cloud.heartbeat.CloudBrainHeartbeat.send", new=AsyncMock(return_value=True)) as send:
        r = await cj.job_cloud_heartbeat()
    send.assert_awaited_once()
    assert r == {"status": "ok"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
