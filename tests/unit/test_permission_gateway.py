
import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from core.loop.permission_gateway import PermissionGateway, Action, GatewayResult
from core.metering.rate_limiter import GCRARateLimiter, operation_cost


GREEN_ACTIONS = ["search_web", "play_music", "set_timer", "read_calendar",
                 "take_screenshot", "check_weather", "check_attendance",
                 "respond", "widget_open"]
# NOTE: these lists are a hand-maintained copy of the tiers in core/config.py.
# That duplication is deliberate (they assert real gateway BEHAVIOUR per tier,
# not just that config equals itself) but it means a tier change in config must
# be mirrored here — otherwise this file fails with a confusing
# "assert 'RED' == 'YELLOW'".
YELLOW_ACTIONS = ["create_calendar_event", "commit_code",
                  "set_reminder", "write_note_personal", "run_tests"]
RED_ACTIONS = ["send_email", "delete_files", "execute_code",
               "financial_transaction", "push_github", "deploy_production",
               "overwrite_note_personal",
               # 2026-08-05 hardening — both promoted YELLOW -> RED because as
               # YELLOW they auto-executed with no owner confirmation under
               # VECTOR_YELLOW_AUTO_CONFIRM=1:
               #   download_file          — arbitrary fetch-to-disk
               #   send_message_routine   — sends a real message to a real person
               # See tests/test_red_interactive_tools_bypass.py for the full
               # lock-in of that change.
               "download_file", "send_message_routine"]
FORBIDDEN_ACTIONS = ["format_drive", "mass_delete", "share_private_data"]
ALL_ACTIONS = GREEN_ACTIONS + YELLOW_ACTIONS + RED_ACTIONS + FORBIDDEN_ACTIONS


def make_action(action_type, params=None, proposed_by="test_agent"):
    return Action(action_type=action_type, params=params or {}, proposed_by=proposed_by)


@pytest.fixture
def gateway():
    g = PermissionGateway()
    g._notify = AsyncMock()
    g._execute_action = AsyncMock(return_value={"status": "ok"})
    g._check_capability = MagicMock(return_value=(True, "mock capability ok"))
    g._wait_for_confirmation = AsyncMock(return_value=False)
    # Without this every RED action ran a real CouncilBrain deliberation (live LLM calls, ~30s each): the file took
    # three minutes and its result depended on which providers happened to answer. "defer" is the council's own
    # fail-safe verdict, so the owner-confirmation path under test is unchanged. The council itself is covered in
    # tests/integration/test_phase_a7_council_red_tier.py.
    g._handle_red_tier = AsyncMock(return_value="defer")
    return g


@pytest.mark.unit
class TestActionClassification:

    @pytest.mark.parametrize("action_type", GREEN_ACTIONS)
    async def test_green_classified(self, gateway, action_type):
        result = await gateway.execute(make_action(action_type))
        assert result.level == "GREEN"
        assert result.approved is True
        assert result.executed is True

    @pytest.mark.parametrize("action_type", YELLOW_ACTIONS)
    async def test_yellow_classified(self, gateway, action_type):
        result = await gateway.execute(make_action(action_type))
        assert result.level == "YELLOW"
        assert result.approved is True

    @pytest.mark.parametrize("action_type", RED_ACTIONS)
    async def test_red_classified_with_confirmation(self, gateway, action_type):
        result = await gateway.execute(make_action(action_type, {"to": "a@b.com"}))
        assert result.level == "RED"
        assert result.approved is False

    @pytest.mark.parametrize("action_type", FORBIDDEN_ACTIONS)
    async def test_forbidden_classified(self, gateway, action_type):
        result = await gateway.execute(make_action(action_type))
        assert result.level == "FORBIDDEN"
        assert result.approved is False

    @pytest.mark.parametrize("action_type", ["unknown_action_xyz", "nonsense_op"])
    async def test_unknown_classified(self, gateway, action_type):
        result = await gateway.execute(make_action(action_type))
        assert result.level == "UNKNOWN"
        assert result.approved is False

    def test_classify_method(self, gateway):
        assert gateway._classify("search_web") == "GREEN"
        assert gateway._classify("commit_code") == "YELLOW"
        assert gateway._classify("send_email") == "RED"
        assert gateway._classify("format_drive") == "FORBIDDEN"
        assert gateway._classify("nonexistent_op_9999") == "UNKNOWN"


@pytest.mark.unit
class TestGreenActions:

    async def test_green_auto_executes_and_returns_ok(self, gateway):
        result = await gateway.execute(make_action("search_web", {"query": "test"}))
        assert result.approved is True
        assert result.level == "GREEN"
        assert result.executed is True

    async def test_green_writes_audit(self, gateway):
        await gateway.execute(make_action("search_web", {"query": "audit test"}))
        log = gateway.get_audit_log()
        assert len(log) == 1
        assert log[0]["action_type"] == "search_web"
        assert log[0]["level"] == "GREEN"
        assert log[0]["approved"] is True

    async def test_green_calls_execute_action(self, gateway):
        await gateway.execute(make_action("play_music", {"track": "jazz"}))
        gateway._execute_action.assert_awaited_once()


@pytest.mark.unit
class TestYellowActions:

    async def test_yellow_executes_with_notification(self, gateway):
        result = await gateway.execute(make_action("commit_code", {"msg": "fix"}))
        assert result.level == "YELLOW"
        assert result.executed is True
        assert result.approved is True

    async def test_yellow_triggers_notify(self, gateway):
        await gateway.execute(make_action("set_reminder", {"text": "meeting"}))
        gateway._notify.assert_awaited_once()


@pytest.mark.unit
class TestRedActions:

    async def test_red_blocks_without_confirmation(self, gateway):
        result = await gateway.execute(make_action("send_email", {"to": "t@t.com"}))
        assert result.level == "RED"
        assert result.approved is False
        assert result.executed is False

    async def test_red_allows_with_manual_confirmation(self):
        # 2026-09-24 (external review, Phase 2): CouncilBrain's deliberation
        # timeout was raised from a hardcoded 5.0s (which happened to fail
        # fast enough for this test's own 5s polling window by accident) to
        # a configurable, realistic ~30s (data/council_log.jsonl showed the
        # old 5s value caused a 58% real-world timeout rate). This test's
        # actual purpose -- the manual Pushover confirmation flow -- has
        # nothing to do with council timing, so mock it out directly rather
        # than depend on incidental real-Ollama-timeout races.
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._execute_action = AsyncMock(return_value={"status": "ok"})
        gw._check_capability = MagicMock(return_value=(True, ""))
        gw._handle_red_tier = AsyncMock(return_value="defer")

        task = asyncio.create_task(gw.execute(make_action("send_email", {"to": "t@t.com"})))
        loop = asyncio.get_running_loop()
        # 2026-09-24 (external review, Phase 2): the pending id is a random,
        # unguessable string (2026-09-23 fix), never the bare literal
        # "send_email" -- this condition never actually matched, so the loop
        # always just burned its full 5s budget regardless of real state.
        # It happened to "work" only because the OLD council flow's own ~5s
        # Ollama timeout meant _wait_for_confirmation's real (1s in test
        # mode, per `_red_timeout = 1 if "pytest" in sys.modules else 300`)
        # window opened at roughly the same moment this loop's deadline hit
        # -- a timing coincidence, not a real check. With council mocked to
        # resolve instantly, that 1s window now opens near t=0 and is long
        # gone by the time this loop's old condition would finally exit at
        # t=5s. Poll the real state instead.
        deadline = loop.time() + 5.0
        while not any(m.get("action_type") == "send_email" for m in gw._pending_actions.values()):
            await asyncio.sleep(0.01)
            if loop.time() > deadline:
                break
        gw.confirm_action("send_email")
        result = await asyncio.wait_for(task, timeout=5.0)
        assert result.level == "RED"
        assert result.approved is True

    async def test_red_no_notify_without_pushover(self, gateway):
        result = await gateway.execute(make_action("financial_transaction", {"amt": 100}))
        assert result.approved is False


@pytest.mark.unit
class TestForbiddenActions:

    async def test_forbidden_always_blocked(self, gateway):
        result = await gateway.execute(make_action("format_drive"))
        assert result.approved is False
        assert result.level == "FORBIDDEN"
        assert result.executed is False

    async def test_forbidden_error_message(self, gateway):
        result = await gateway.execute(make_action("mass_delete"))
        assert result.reason == "Action permanently forbidden"

    async def test_forbidden_skips_capability_check(self, gateway):
        result = await gateway.execute(make_action("share_private_data"))
        assert result.approved is False
        gateway._check_capability.assert_not_called()


@pytest.mark.unit
class TestUnknownActions:

    async def test_unknown_falls_to_red(self, gateway):
        result = await gateway.execute(make_action("unknown_action_xyz"))
        assert result.level == "UNKNOWN"
        assert result.approved is False

    async def test_unknown_error_message(self, gateway):
        result = await gateway.execute(make_action("bogus_op"))
        assert "Unknown action type" in result.reason

    async def test_unknown_tracked_after_three_hits(self, gateway):
        for _ in range(3):
            await gateway.execute(make_action("new_action_type"))
        unknown = gateway.get_unknown_actions()
        assert unknown.get("new_action_type", 0) == 3


@pytest.mark.unit
class TestAuditLog:

    async def test_audit_log_created_on_each_check(self, gateway):
        for typ in ["search_web", "commit_code", "send_email"]:
            await gateway.execute(make_action(typ, {"q": "t"}))
        assert len(gateway.get_audit_log()) == 3

    async def test_audit_log_contains_all_fields(self, gateway):
        await gateway.execute(make_action("search_web", {"q": "x"}, proposed_by="agent_a"))
        entry = gateway.get_audit_log()[0]
        for key in ("timestamp", "action_type", "level", "approved", "executed", "proposed_by", "reason"):
            assert key in entry
        assert entry["action_type"] == "search_web"
        assert entry["level"] == "GREEN"
        assert entry["proposed_by"] == "agent_a"

    async def test_audit_log_capped_at_500(self, gateway):
        for i in range(510):
            gateway._write_audit(
                make_action("search_web", {"q": str(i)}),
                GatewayResult(True, "GREEN", True, {}, ""),
            )
        assert len(gateway.audit_log) == 500


@pytest.mark.unit
class TestCapabilityCheck:

    async def test_capability_denied_blocks_green(self, gateway):
        gateway._check_capability = MagicMock(return_value=(False, "no capability"))
        result = await gateway.execute(make_action("search_web"))
        assert result.approved is False
        assert "Capability denied" in result.reason

    async def test_capability_denied_blocks_yellow(self, gateway):
        gateway._check_capability = MagicMock(return_value=(False, "no capability"))
        result = await gateway.execute(make_action("commit_code"))
        assert result.approved is False

    async def test_capability_pass_allows_execution(self, gateway):
        gateway._check_capability = MagicMock(return_value=(True, "has capability"))
        result = await gateway.execute(make_action("search_web"))
        assert result.approved is True

    async def test_capability_error_fails_closed(self, gateway):
        gateway._check_capability = MagicMock(return_value=(False, "capability check failed (error)"))
        result = await gateway.execute(make_action("search_web"))
        assert result.approved is False


@pytest.mark.unit
class TestRateLimiting:

    async def test_burst_allowed(self):
        limiter = GCRARateLimiter(tokens_per_minute=500, burst=500)
        for _ in range(10):
            result = limiter.check("agent_a", "health")
            assert result.allowed

    async def test_empty_caller_starts_allowed(self):
        limiter = GCRARateLimiter(tokens_per_minute=100, burst=100)
        result = limiter.check("new_caller", "health")
        assert result.allowed

    async def test_exhaust_blocks(self):
        limiter = GCRARateLimiter(tokens_per_minute=60, burst=60)
        for _ in range(60):
            limiter.check("agent_b", "health")
        result = limiter.check("agent_b", "health")
        assert not result.allowed
        assert result.retry_after_secs > 0

    async def test_concurrent_callers_independent(self):
        limiter = GCRARateLimiter(tokens_per_minute=60, burst=60)
        for _ in range(60):
            limiter.check("caller_a", "health")
        assert not limiter.check("caller_a", "health").allowed
        assert limiter.check("caller_b", "health").allowed

    async def test_reset_clears_caller(self):
        limiter = GCRARateLimiter(tokens_per_minute=60, burst=60)
        for _ in range(60):
            limiter.check("caller_c", "health")
        limiter.reset("caller_c")
        assert limiter.check("caller_c", "health").allowed

    async def test_operation_cost_table(self):
        assert operation_cost("health") == 1
        assert operation_cost("llm_message") == 30
        assert operation_cost("agent_spawn") == 50
        assert operation_cost("nonexistent_op") == 10


@pytest.mark.unit
class TestConfigOverrideModes:

    async def test_strict_mode_blocks_yellow_when_capability_fails(self, gateway):
        gateway._check_capability = MagicMock(return_value=(False, "strict: denied"))
        result = await gateway.execute(make_action("commit_code", {"msg": "test"}))
        assert result.approved is False

    async def test_permissive_mode_allows_green(self, gateway):
        result = await gateway.execute(make_action("widget_open", {"id": "map"}))
        assert result.approved is True
        assert result.level == "GREEN"

    async def test_unknown_action_always_blocked_regardless(self, gateway):
        result = await gateway.execute(make_action("some_unknown_operation"))
        assert result.approved is False
        assert result.level == "UNKNOWN"


@pytest.mark.unit
class TestErrorMessages:

    async def test_forbidden_error_message_format(self, gateway):
        result = await gateway.execute(make_action("format_drive"))
        assert result.reason == "Action permanently forbidden"

    async def test_capability_denied_message(self, gateway):
        gateway._check_capability = MagicMock(return_value=(False, "no capability"))
        result = await gateway.execute(make_action("search_web"))
        assert "Capability denied" in result.reason

    async def test_unknown_action_message(self, gateway):
        result = await gateway.execute(make_action("some_random_op"))
        assert result.reason == "Unknown action type: some_random_op"

    async def test_red_timeout_message(self, gateway):
        result = await gateway.execute(make_action("send_email", {"to": "t@t.com"}))
        assert "Timed out" in result.reason or "forbidden" in result.reason.lower()


@pytest.mark.unit
class TestRequestApprovalOnly:
    """request_approval() — approval-only helper for callers (e.g. browser
    governance) that need to perform the REAL action themselves after owner
    sign-off, rather than delegating execution to the gateway's own
    _execute_action (which dispatches through the governor — not appropriate
    for replaying a paused mid-page Playwright action)."""

    async def test_request_approval_notifies_and_waits_for_red(self):
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._wait_for_confirmation = AsyncMock(return_value=True)

        approved = await gw.request_approval("hand_browser", "Click 'Buy Now' on amazon.com")
        assert approved is True
        gw._notify.assert_awaited()

    async def test_request_approval_times_out_rejects_for_safety(self):
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._wait_for_confirmation = AsyncMock(side_effect=asyncio.TimeoutError)

        approved = await gw.request_approval("hand_browser", "Click 'Buy Now'", timeout=0.01)
        assert approved is False

    async def test_request_approval_rejected_explicitly(self):
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._wait_for_confirmation = AsyncMock(return_value=False)

        approved = await gw.request_approval("hand_browser", "Submit payment form")
        assert approved is False

    async def test_request_approval_does_not_call_execute_action(self):
        """The whole point: it must NOT call _execute_action — the caller
        executes the real action itself after approval."""
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._wait_for_confirmation = AsyncMock(return_value=True)
        gw._execute_action = AsyncMock(return_value={"status": "should not be called"})

        await gw.request_approval("hand_browser", "test summary")
        gw._execute_action.assert_not_awaited()

    async def test_request_approval_writes_audit_log(self):
        gw = PermissionGateway()
        gw._notify = AsyncMock()
        gw._wait_for_confirmation = AsyncMock(return_value=True)

        before = len(gw.audit_log)
        await gw.request_approval("hand_browser", "test summary")
        assert len(gw.audit_log) == before + 1
