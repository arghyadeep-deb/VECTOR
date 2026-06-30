"""Task 7 — orchestrator runs both arms as never-die coroutines (ARM A errors
must not kill the loop)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_orchestrator_starts_both_arms_and_survives_errors(monkeypatch):
    from districts.growth.growth_orchestrator import GrowthOrchestrator
    o = GrowthOrchestrator()
    ran = {"a": 0, "b": 0}

    async def a():
        ran["a"] += 1
        raise RuntimeError("boom")   # ARM A keeps crashing — loop must survive

    async def b():
        ran["b"] += 1

    monkeypatch.setattr(o, "_content_tick", a)
    monkeypatch.setattr(o, "_software_tick", b)
    monkeypatch.setattr(o, "_backoff_s", 0)
    await o.run_for(ticks=2)   # bounded test runner
    assert ran["a"] >= 2 and ran["b"] >= 2


if __name__ == "__main__":
    print("run via pytest")
