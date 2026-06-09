import asyncio


def test_pc_control_actions_are_classified_yellow():
    from core.loop.permission_gateway import PermissionGateway

    gateway = PermissionGateway()
    for action_type in ("pc_screenshot", "pc_type", "pc_click", "pc_launch_app"):
        assert gateway._classify(action_type) == "YELLOW"


def test_pc_control_does_not_dispatch_when_gateway_blocks(monkeypatch):
    from core.api.routers import control
    from core.city import governor
    from core.loop import permission_gateway

    async def deny(self, action):
        return permission_gateway.GatewayResult(
            approved=False,
            level="YELLOW",
            executed=False,
            result={},
            reason="Rejected by owner",
        )

    async def dispatch_should_not_run(self, task):
        raise AssertionError("Governor dispatch should not run when gateway blocks")

    monkeypatch.setattr(permission_gateway.PermissionGateway, "execute", deny)
    monkeypatch.setattr(governor.GovernorCouncil, "dispatch", dispatch_should_not_run)

    response = asyncio.run(control.pc_type(control.PcTypeReq(text="hello")))

    assert response["status"] == "blocked"
    assert response["action"] == "pc_type"
    assert response["gateway"]["approved"] is False
    assert response["gateway"]["reason"] == "Rejected by owner"


def test_pc_control_dispatches_after_gateway_approval(monkeypatch):
    from core.api.routers import control
    from core.city import governor
    from core.loop import permission_gateway

    async def approve(self, action):
        return permission_gateway.GatewayResult(
            approved=True,
            level="YELLOW",
            executed=True,
            result={"status": "executed"},
            reason="Executed after YELLOW window",
        )

    async def dispatch(self, task):
        return {"status": "ok", "task": task}

    monkeypatch.setattr(permission_gateway.PermissionGateway, "execute", approve)
    monkeypatch.setattr(governor.GovernorCouncil, "dispatch", dispatch)

    response = asyncio.run(control.pc_click(control.PcClickReq(x=10, y=20)))

    assert response["status"] == "ok"
    assert response["task"] == {
        "type": "pc_click",
        "params": {"x": 10, "y": 20, "button": "left"},
    }
