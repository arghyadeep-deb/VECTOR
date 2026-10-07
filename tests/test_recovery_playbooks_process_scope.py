from __future__ import annotations

from dataclasses import dataclass

import psutil
import pytest

from core.resilience.recovery_playbooks import ProcessHangPlaybook


@dataclass
class FakeProcess:
    pid: int
    process_name: str
    cpu_usage: float
    killed: bool = False

    def name(self) -> str:
        return self.process_name

    def cpu_percent(self) -> float:
        return self.cpu_usage

    def kill(self) -> None:
        self.killed = True


class FakeCurrentProcess:
    def __init__(self, children: list[FakeProcess]) -> None:
        self._children = children
        self.recursive_requested = False

    def children(self, recursive: bool = False) -> list[FakeProcess]:
        self.recursive_requested = recursive
        return self._children


@pytest.mark.asyncio
async def test_process_hang_only_kills_high_cpu_vector_descendants(monkeypatch: pytest.MonkeyPatch) -> None:
    child = FakeProcess(pid=101, process_name="vector-child", cpu_usage=95.0)
    outside = FakeProcess(pid=202, process_name="unrelated-render", cpu_usage=99.0)
    current = FakeCurrentProcess([child])

    monkeypatch.setattr(psutil, "Process", lambda: current)

    def reject_system_wide_scan(*args: object, **kwargs: object) -> None:
        raise AssertionError("ProcessHangPlaybook must not scan system-wide processes")

    monkeypatch.setattr(psutil, "process_iter", reject_system_wide_scan)

    result = await ProcessHangPlaybook().run()

    assert result.success is True
    assert current.recursive_requested is True
    assert child.killed is True
    assert outside.killed is False
    assert len(result.actions_taken) == 1
    assert result.actions_taken[0].startswith("High CPU: vector-child (PID 101)")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
