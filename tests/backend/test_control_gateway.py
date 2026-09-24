import asyncio


def test_pc_control_actions_are_gateway_classified():
    """PC-control actions must be gated — and the *writing* ones must be RED.

    2026-08-04 hardening: `pc_type`/`pc_click`/`pc_launch_app` were promoted
    YELLOW -> RED. As YELLOW they auto-executed after a ~10s window with no
    owner confirmation whenever VECTOR_YELLOW_AUTO_CONFIRM=1 (the owner's
    live .env) — synthetic keyboard/mouse input and app launch driven by an
    LLM-invented task_type that can originate in untrusted ingested text.

    `pc_screenshot` stays YELLOW deliberately: read-only, no owner-invisible
    side effect, and gating it would add friction for no security gain.

    This test previously asserted all four were YELLOW — i.e. it encoded the
    pre-hardening (insecure) contract. Updated to assert the intended one.
    See tests/test_red_interactive_tools_bypass.py for the full lock-in.
    """
    from core.loop.permission_gateway import PermissionGateway

    gateway = PermissionGateway()

    # Read-only — stays YELLOW.
    assert gateway._classify("pc_screenshot") == "YELLOW"

    # Input injection / app launch — must require explicit owner approval.
    for action_type in ("pc_type", "pc_click", "pc_launch_app"):
        assert gateway._classify(action_type) == "RED", (
            f"{action_type} must be RED — as YELLOW it auto-executes under "
            f"VECTOR_YELLOW_AUTO_CONFIRM=1"
        )


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


def test_pc_control_returns_the_real_gateway_result_after_approval(monkeypatch):
    """2026-09-23 (fix, item 6 -- independent review finding): this test
    used to ALSO mock GovernorCouncil.dispatch() and assert the response
    matched THAT mock's return value -- but production code discarded
    the real gate.result and called Governor.dispatch() a second time,
    and Governor has no real handler for pc_click/pc_type/pc_screenshot/
    pc_launch_app at all (confirmed: no DISTRICT_TASK_MAP entry, no
    agent-manifest capability). That made this test pass while hiding a
    real bug -- the response it asserted could never have come from a
    real click actually happening. Fixed: _dispatch_pc_action() now
    returns `gate.result` directly (PermissionGateway._execute_action()
    has a real pc_click branch that calls PCController().click()) and
    never calls Governor a second time -- lock that in here."""
    from core.api.routers import control
    from core.city import governor
    from core.loop import permission_gateway

    async def approve(self, action):
        return permission_gateway.GatewayResult(
            approved=True,
            level="RED",
            executed=True,
            result={"status": "ok", "clicked": True},
            reason="Owner confirmed",
        )

    async def dispatch_should_not_run(self, task):
        raise AssertionError(
            "Governor.dispatch() must never run for pc_click -- the real "
            "execution now happens inside PermissionGateway._execute_action() "
            "itself; a second dispatch call would be the exact double-"
            "execution/no-real-handler bug this fix closes"
        )

    monkeypatch.setattr(permission_gateway.PermissionGateway, "execute", approve)
    monkeypatch.setattr(governor.GovernorCouncil, "dispatch", dispatch_should_not_run)

    response = asyncio.run(control.pc_click(control.PcClickReq(x=10, y=20)))

    assert response == {"status": "ok", "clicked": True}
