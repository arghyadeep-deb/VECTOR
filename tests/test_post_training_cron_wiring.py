import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_post_training_disabled_by_default():
    from core.config import CONFIG
    assert CONFIG["training"]["post_training_enabled"] is False


async def test_job_post_training_run_skips_when_disabled(monkeypatch):
    from core.loop.cron_jobs import job_post_training_run
    from core.config import CONFIG
    monkeypatch.setitem(CONFIG["training"], "post_training_enabled", False)
    result = await job_post_training_run()
    assert result["status"] == "disabled"


async def test_job_post_training_run_calls_sft_and_dpo_when_enabled(monkeypatch):
    from core.loop import cron_jobs
    from core.config import CONFIG

    monkeypatch.setitem(CONFIG["training"], "post_training_enabled", True)
    monkeypatch.setitem(CONFIG["training"], "post_training_base_model", "dummy/model")

    calls = {"sft": False, "dpo": False}
    monkeypatch.setattr(cron_jobs, "run_sft", lambda **kw: calls.__setitem__("sft", True) or {"status": "skipped"})
    monkeypatch.setattr(cron_jobs, "run_dpo", lambda **kw: calls.__setitem__("dpo", True) or {"status": "skipped"})

    result = await cron_jobs.job_post_training_run()
    assert calls["sft"] is True
    assert calls["dpo"] is True
    assert result["status"] == "ok"


def test_post_training_job_registered_in_default_jobs():
    import inspect
    from core.loop import cron_jobs
    src = inspect.getsource(cron_jobs.register_default_jobs)
    assert "job_post_training_run" in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
