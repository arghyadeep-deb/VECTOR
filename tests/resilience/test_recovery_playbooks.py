import sys

import asyncio
from unittest.mock import patch, AsyncMock
import pytest

from core.resilience.recovery_playbooks import (
    ModelCrashPlaybook, OOMPlaybook, DiskFullPlaybook,
    NetworkPartitionPlaybook, GPUFailurePlaybook,
    ProcessHangPlaybook, ConfigCorruptPlaybook,
    DBCorruptionPlaybook, PLAYBOOK_REGISTRY, run_all_playbooks,
    RecoveryPlaybook, PlaybookResult,
)


def _mock_async_client(status_code=200):
    """Build a mock for `async with httpx.AsyncClient(...) as client` whose
    client.get()/post() resolve to a response with the given status_code."""
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client
    mock_client_cm.__aexit__.return_value = False
    return mock_client_cm, mock_client


@pytest.mark.asyncio
async def test_model_crash_playbook():
    playbook = ModelCrashPlaybook()
    mock_cm, mock_client = _mock_async_client(status_code=200)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await playbook.run()
        assert result.success is True
        assert result.name == "model_crash"
        # A healthy ping must NOT trigger an Ollama restart.
        assert "Ollama model healthy" in result.actions_taken
        assert "Attempting Ollama restart" not in result.actions_taken


@pytest.mark.asyncio
async def test_model_crash_playbook_restarts_when_unreachable():
    playbook = ModelCrashPlaybook()
    with patch("httpx.AsyncClient", side_effect=OSError("connection refused")):
        with patch("subprocess.run") as mock_run:
            result = await playbook.run()
        assert result.success is True
        assert "Attempting Ollama restart" in result.actions_taken
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_oom_playbook():
    playbook = OOMPlaybook()
    with patch("torch.cuda.is_available", return_value=True):
        with patch("torch.cuda.empty_cache") as mock_empty:
            result = await playbook.run()
            assert result.success is True
            assert result.name == "oom_recovery"
            mock_empty.assert_called_once()


@pytest.mark.asyncio
async def test_oom_playbook_no_gpu():
    playbook = OOMPlaybook()
    with patch("torch.cuda.is_available", return_value=False):
        result = await playbook.run()
        assert result.success is True


@pytest.mark.asyncio
async def test_disk_full_playbook():
    playbook = DiskFullPlaybook()
    result = await playbook.run()
    assert result.success is True
    assert result.name == "disk_full"


@pytest.mark.asyncio
async def test_network_partition_playbook():
    playbook = NetworkPartitionPlaybook()
    mock_cm, mock_client = _mock_async_client(status_code=200)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        result = await playbook.run()
        assert result.success is True
        assert all("OK" in a for a in result.actions_taken)


@pytest.mark.asyncio
async def test_network_partition_playbook_reports_unreachable():
    playbook = NetworkPartitionPlaybook()
    with patch("httpx.AsyncClient", side_effect=OSError("connection refused")):
        result = await playbook.run()
        assert result.success is True
        assert all("unreachable" in a for a in result.actions_taken)


@pytest.mark.asyncio
async def test_gpu_failure_playbook():
    playbook = GPUFailurePlaybook()
    with patch("torch.cuda.is_available", return_value=True):
        with patch("torch.cuda.synchronize"):
            with patch("torch.cuda.get_device_name", return_value="RTX 5070 Ti"):
                result = await playbook.run()
                assert result.success is True
                assert "RTX 5070 Ti" in result.actions_taken[0]


@pytest.mark.asyncio
async def test_gpu_failure_playbook_no_torch():
    playbook = GPUFailurePlaybook()
    with patch.dict("sys.modules", {"torch": None}):
        pass
    result = await playbook.run()
    assert result.success is True


@pytest.mark.asyncio
async def test_process_hang_playbook():
    playbook = ProcessHangPlaybook()
    with patch("psutil.process_iter", return_value=[]):
        result = await playbook.run()
        assert result.success is True


@pytest.mark.asyncio
async def test_config_corrupt_playbook():
    playbook = ConfigCorruptPlaybook()
    with patch("core.config.CONFIG", {"ollama_host": "http://localhost:11434"}):
        result = await playbook.run()
        assert result.success is True


@pytest.mark.asyncio
async def test_config_corrupt_playbook_failure():
    playbook = ConfigCorruptPlaybook()
    with patch("core.config.CONFIG", {}):
        result = await playbook.run()
        assert result.success is False


@pytest.mark.asyncio
async def test_db_corruption_playbook():
    playbook = DBCorruptionPlaybook()
    with patch("pathlib.Path.exists", return_value=False):
        result = await playbook.run()
        assert result.success is True


@pytest.mark.asyncio
async def test_playbook_registry_contents():
    assert "model_crash" in PLAYBOOK_REGISTRY
    assert "oom" in PLAYBOOK_REGISTRY
    assert "disk_full" in PLAYBOOK_REGISTRY
    assert "network_partition" in PLAYBOOK_REGISTRY
    assert "gpu_failure" in PLAYBOOK_REGISTRY
    assert "process_hang" in PLAYBOOK_REGISTRY
    assert "config_corrupt" in PLAYBOOK_REGISTRY
    assert "db_corruption" in PLAYBOOK_REGISTRY
    assert len(PLAYBOOK_REGISTRY) >= 8


@pytest.mark.asyncio
async def test_run_all_playbooks():
    with patch.object(ModelCrashPlaybook, "run", new_callable=AsyncMock) as mock_mc:
        mock_mc.return_value = PlaybookResult(name="model_crash", success=True)
        with patch.object(OOMPlaybook, "run", new_callable=AsyncMock) as mock_oom:
            mock_oom.return_value = PlaybookResult(name="oom_recovery", success=True)
            results = await run_all_playbooks()
            assert len(results) == len(PLAYBOOK_REGISTRY)


@pytest.mark.asyncio
async def test_playbook_result_dataclass():
    result = PlaybookResult(name="test", success=True, duration_s=1.5, actions_taken=["step1"], error="")
    assert result.name == "test"
    assert result.success is True
    assert result.duration_s == 1.5


class NoopPlaybook(RecoveryPlaybook):
    name = "noop"
    async def run(self) -> PlaybookResult:
        return PlaybookResult(name=self.name, success=True)


@pytest.mark.asyncio
async def test_custom_playbook():
    playbook = NoopPlaybook()
    result = await playbook.run()
    assert result.success is True
    assert result.name == "noop"