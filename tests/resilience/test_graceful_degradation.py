import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import time
from unittest.mock import patch
import pytest

from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier


@pytest.fixture
def degradation():
    d = GracefulDegradation()
    d._cooldown_sec = 0.0
    return d


@pytest.mark.asyncio
async def test_initial_tier_full(degradation):
    assert degradation.current_tier == ServiceTier.FULL


@pytest.mark.asyncio
async def test_survival_tier(degradation):
    with patch.object(degradation, "_check_ollama", return_value=False):
        with patch.object(degradation, "_check_network", return_value=False):
            with patch.object(degradation, "_check_ram", return_value=False):
                tier = await degradation.evaluate_tier()
                assert tier == ServiceTier.SURVIVAL


@pytest.mark.asyncio
async def test_emergency_tier(degradation):
    with patch.object(degradation, "_check_ollama", return_value=False):
        with patch.object(degradation, "_check_network", return_value=False):
            with patch.object(degradation, "_check_ram", return_value=True):
                tier = await degradation.evaluate_tier()
                assert tier == ServiceTier.EMERGENCY


@pytest.mark.asyncio
async def test_minimal_tier(degradation):
    with patch.object(degradation, "_check_ollama", return_value=False):
        with patch.object(degradation, "_check_network", return_value=True):
            with patch.object(degradation, "_check_ram", return_value=False):
                tier = await degradation.evaluate_tier()
                assert tier == ServiceTier.MINIMAL


@pytest.mark.asyncio
async def test_degraded_tier(degradation):
    with patch.object(degradation, "_check_gpu", return_value=False):
        with patch.object(degradation, "_check_ram", return_value=False):
            with patch.object(degradation, "_check_ollama", return_value=True):
                tier = await degradation.evaluate_tier()
                assert tier == ServiceTier.DEGRADED


@pytest.mark.asyncio
async def test_reduced_tier(degradation):
    with patch.object(degradation, "_check_gpu", return_value=False):
        with patch.object(degradation, "_check_ram", return_value=True):
            with patch.object(degradation, "_check_ollama", return_value=True):
                tier = await degradation.evaluate_tier()
                assert tier == ServiceTier.REDUCED


@pytest.mark.asyncio
async def test_full_tier_all_healthy(degradation):
    with patch.object(degradation, "_check_gpu", return_value=True):
        with patch.object(degradation, "_check_ram", return_value=True):
            with patch.object(degradation, "_check_disk", return_value=True):
                with patch.object(degradation, "_check_network", return_value=True):
                    with patch.object(degradation, "_check_ollama", return_value=True):
                        tier = await degradation.evaluate_tier()
                        assert tier == ServiceTier.FULL


@pytest.mark.asyncio
async def test_cooldown_hysteresis(degradation):
    degradation._cooldown_sec = 60.0
    degradation._last_tier_change = time.time()
    result = await degradation.auto_degrade()
    assert result is None


@pytest.mark.asyncio
async def test_service_limits_by_tier(degradation):
    degradation.current_tier = ServiceTier.MINIMAL
    limits = degradation.get_service_limits("inference")
    assert limits["batch_size"] == 1
    assert limits["model_size"] == "small"
    degradation.current_tier = ServiceTier.FULL
    limits = degradation.get_service_limits("inference")
    assert limits["batch_size"] == 8


@pytest.mark.asyncio
async def test_on_change_callback(degradation):
    triggered = []
    def cb(old, new):
        triggered.append((old, new))
    degradation.on_change(cb)
    degradation._notify_change(ServiceTier.FULL, ServiceTier.REDUCED)
    assert len(triggered) == 1
    assert triggered[0] == (ServiceTier.FULL, ServiceTier.REDUCED)


@pytest.mark.asyncio
async def test_resource_detection(degradation):
    with patch("psutil.virtual_memory") as mock_vm:
        mock_vm.return_value.available = 100 * 1024 * 1024
        ram_ok = await degradation._check_ram()
        assert ram_ok is False
        mock_vm.return_value.available = 1024 * 1024 * 1024
        ram_ok = await degradation._check_ram()
        assert ram_ok is True