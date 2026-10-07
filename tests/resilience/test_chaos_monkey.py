
import asyncio
from unittest.mock import patch, AsyncMock
import pytest

from core.resilience.chaos_monkey import ChaosMonkey
from core.resilience.injectors.base import ChaosExperiment, FailureInjector


class FakeInjector(FailureInjector):
    name = "fake_injector"
    description = "A fake injector for testing"

    def __init__(self, should_pass=True, recovery_time=0.5):
        self.should_pass = should_pass
        self._recovery_time = recovery_time

    async def verify_healthy(self) -> bool:
        return True

    async def inject(self) -> None:
        pass

    async def verify_recovery(self) -> tuple[bool, float]:
        return self.should_pass, self._recovery_time

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def chaos():
    c = ChaosMonkey()
    c.enabled = True
    c.injectors = [FakeInjector(should_pass=True)]
    return c


@pytest.mark.asyncio
async def test_experiment_lifecycle(chaos):
    injector = FakeInjector(should_pass=True)
    result = await chaos.run_experiment(injector)
    assert isinstance(result, ChaosExperiment)
    assert result.injector_name == "fake_injector"
    assert result.passed is True
    assert result.recovery_time_s == 0.5


@pytest.mark.asyncio
async def test_experiment_failure(chaos):
    injector = FakeInjector(should_pass=False, recovery_time=2.0)
    result = await chaos.run_experiment(injector)
    assert result.passed is False
    assert result.recovery_time_s == 2.0


@pytest.mark.asyncio
async def test_scheduled_execution(chaos):
    chaos.enabled = True
    chaos.schedule_interval_h = 24
    with patch.object(chaos, "run_all_experiments", new_callable=AsyncMock) as mock_run:
        await chaos.run_scheduled()
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_disabled(chaos):
    chaos.enabled = False
    with patch.object(chaos, "run_all_experiments", new_callable=AsyncMock) as mock_run:
        await chaos.run_scheduled()
        mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_public_execution_entry_points_are_inert_when_disabled(chaos):
    chaos.enabled = False
    injector = FakeInjector(should_pass=True)

    direct_result = await chaos.run_experiment(injector)
    random_result = await chaos.run_random_experiment()
    all_results = await chaos.run_all_experiments()
    scheduled_result = await chaos.run_scheduled()

    assert direct_result is None
    assert random_result is None
    assert all_results == []
    assert scheduled_result is None
    assert chaos.results == []


@pytest.mark.asyncio
async def test_run_all_experiments(chaos):
    chaos.injectors = [
        FakeInjector(should_pass=True, recovery_time=0.3),
        FakeInjector(should_pass=False, recovery_time=0.5),
    ]
    results = await chaos.run_all_experiments()
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False


@pytest.mark.asyncio
async def test_random_experiment(chaos):
    with patch.object(chaos, "run_experiment", new_callable=AsyncMock) as mock_run:
        await chaos.run_random_experiment()
        mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_generation(chaos):
    injector = FakeInjector(should_pass=True, recovery_time=0.5)
    await chaos.run_experiment(injector)
    report = chaos.generate_report()
    assert "fake_injector" in report
    assert "100%" in report
    assert "0.5" in report


@pytest.mark.asyncio
async def test_report_empty(chaos):
    report = chaos.generate_report()
    assert "No chaos experiments run yet." in report


@pytest.mark.asyncio
async def test_on_result_callback(chaos):
    triggered = []
    def cb(result):
        triggered.append(result)
    chaos.on_result(cb)
    injector = FakeInjector(should_pass=True)
    await chaos.run_experiment(injector)
    assert len(triggered) == 1
    assert triggered[0].passed is True


@pytest.mark.asyncio
async def test_experiment_error_handling():
    class BrokenInjector(FailureInjector):
        name = "broken"
        description = "Always fails verification"

        async def verify_healthy(self) -> bool:
            raise RuntimeError("verification crash")

        async def inject(self) -> None:
            pass

        async def verify_recovery(self) -> tuple[bool, float]:
            return True, 0.0

        async def cleanup(self) -> None:
            pass

    chaos = ChaosMonkey()
    chaos.enabled = True
    chaos.injectors = [BrokenInjector()]
    result = await chaos.run_experiment(BrokenInjector())
    assert result.passed is False
    assert "verification crash" in result.error
