"""FL-031 — camera start/stop must go through a real PermissionGateway decision.

Before this fix, core/api/routers/camera.py's start_camera()/stop_camera()
flipped the module-level _camera_active flag directly. The route had HTTP
auth, but no governance decision gated the actual hardware activation.
Follows the fake-gateway test pattern already used in
tests/test_red_tier_destructive_action_gating.py.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.loop.permission_gateway import GatewayResult, PermissionGateway


class _Gateway:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.calls: list[tuple[str, dict, str]] = []

    async def evaluate_external(self, action_type: str, params: dict, source: str):
        self.calls.append((action_type, params, source))
        return GatewayResult(
            approved=self.approved,
            level="YELLOW",
            executed=False,
            result={},
            reason="owner rejected" if not self.approved else "owner approved",
        )


def _install_gateway(monkeypatch, approved: bool) -> _Gateway:
    from core.loop.autonomous_loop import AutonomousLoop

    gateway = _Gateway(approved)
    loop = SimpleNamespace(_get_gateway=lambda: gateway)
    monkeypatch.setattr(AutonomousLoop, "get_instance", staticmethod(lambda: loop))
    return gateway


def test_camera_action_types_are_yellow() -> None:
    gateway = PermissionGateway()
    assert gateway._classify("camera_activate") == "YELLOW"
    assert gateway._classify("camera_deactivate") == "YELLOW"


@pytest.mark.asyncio
async def test_denied_decision_prevents_camera_activation(monkeypatch):
    import core.api.routers.camera as camera

    camera._camera_active = False
    gateway = _install_gateway(monkeypatch, approved=False)

    result = await camera.start_camera(index=0)

    assert result["status"] == "blocked"
    assert camera._camera_active is False
    assert gateway.calls == [("camera_activate", {"index": 0}, "api_camera")]


@pytest.mark.asyncio
async def test_approved_decision_allows_camera_activation(monkeypatch):
    import core.api.routers.camera as camera

    camera._camera_active = False
    gateway = _install_gateway(monkeypatch, approved=True)

    result = await camera.start_camera(index=0)

    assert result["status"] == "started"
    assert camera._camera_active is True
    assert gateway.calls == [("camera_activate", {"index": 0}, "api_camera")]


@pytest.mark.asyncio
async def test_denied_decision_prevents_camera_deactivation(monkeypatch):
    import core.api.routers.camera as camera

    camera._camera_active = True
    gateway = _install_gateway(monkeypatch, approved=False)

    result = await camera.stop_camera()

    assert result["status"] == "blocked"
    assert camera._camera_active is True


@pytest.mark.asyncio
async def test_approved_decision_allows_camera_deactivation(monkeypatch):
    import core.api.routers.camera as camera

    camera._camera_active = True
    gateway = _install_gateway(monkeypatch, approved=True)

    result = await camera.stop_camera()

    assert result["status"] == "stopped"
    assert camera._camera_active is False
