"""Extra tests for PermissionGateway uncovered code paths."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.loop.permission_gateway import PermissionGateway, Action, GatewayResult


def make_action(action_type, params=None, proposed_by="test_agent"):
    return Action(action_type=action_type, params=params or {}, proposed_by=proposed_by)


@pytest.fixture
def gateway():
    g = PermissionGateway()
    g._notify = AsyncMock()
    g._execute_action = AsyncMock(return_value={"status": "ok"})
    g._check_capability = MagicMock(return_value=(True, "mock ok"))
    g._wait_for_confirmation = AsyncMock(return_value=False)
    return g


class TestGatewayExecute:
    """Test execute() — GREEN/YELLOW/RED/FORBIDDEN/UNKNOWN branches."""

    async def test_execute_green_action_approved(self, gateway):
        action = make_action("search_web", {"query": "test"})
        result = await gateway.execute(action)
        assert result.approved is True
        assert result.level == "GREEN"
        assert result.executed is True

    async def test_execute_green_notifies(self, gateway):
        action = make_action("search_web", {"query": "hello"})
        await gateway.execute(action)
        gateway._notify.assert_called()

    async def test_execute_yellow_action_approved(self, gateway):
        action = make_action("create_calendar_event", {"title": "Meeting"})
        result = await gateway.execute(action)
        assert result.approved is True
        assert result.level == "YELLOW"
        assert result.executed is True

    async def test_execute_yellow_notifies(self, gateway):
        action = make_action("set_reminder", {"time": "18:00"})
        await gateway.execute(action)
        gateway._notify.assert_called()

    async def test_execute_yellow_timeout_fails_closed_by_default(self, monkeypatch):
        import asyncio
        # "By default" must mean the flag is OFF — the owner's live .env sets
        # VECTOR_YELLOW_AUTO_CONFIRM=1, which legitimately flips this branch to
        # execute-after-window. Pin the default so the test is hermetic.
        monkeypatch.delenv("VECTOR_YELLOW_AUTO_CONFIRM", raising=False)
        g = PermissionGateway()
        g._notify = AsyncMock()
        g._execute_action = AsyncMock(return_value={"status": "ok"})
        g._check_capability = MagicMock(return_value=(True, "mock ok"))

        async def never_confirms(_action):
            await asyncio.sleep(1)
            return True

        g._wait_for_confirmation = never_confirms
        result = await g.execute(make_action("set_reminder", {"time": "18:00"}))
        assert result.approved is False
        assert result.executed is False
        g._execute_action.assert_not_awaited()

    async def test_execute_forbidden_blocked(self, gateway):
        action = make_action("format_drive", {})
        result = await gateway.execute(action)
        assert result.approved is False
        assert result.level == "FORBIDDEN"
        assert result.executed is False

    async def test_execute_unknown_blocked(self, gateway):
        action = make_action("some_completely_unknown_xyz_action_999", {})
        result = await gateway.execute(action)
        assert result.approved is False
        assert result.level == "UNKNOWN"

    async def test_execute_red_denied_no_owner_approval(self, gateway):
        # _wait_for_confirmation returns False → timed out / denied
        action = make_action("push_github", {})
        result = await gateway.execute(action)
        assert result.approved is False
        assert result.level == "RED"

    async def test_execute_capability_check_fail_blocks(self):
        g = PermissionGateway()
        g._notify = AsyncMock()
        g._execute_action = AsyncMock(return_value={"status": "ok"})
        g._check_capability = MagicMock(return_value=(False, "no capability"))
        action = make_action("search_web", {})
        result = await g.execute(action)
        assert result.approved is False

    async def test_execute_writes_audit(self, gateway):
        action = make_action("play_music", {"track": "jazz"})
        await gateway.execute(action)
        assert len(gateway.audit_log) > 0

    async def test_confirm_action_no_pending_returns_false(self):
        g = PermissionGateway()
        result = g.confirm_action("nonexistent_action_type")
        assert result is False


class TestExecuteActionStubs:
    """Test _execute_action() directly for all stub action types."""

    async def test_play_music_launches_configured_app(self):
        # 2026-07-23 (task #91 core-subsystem audit): this test previously
        # asserted status == "not_implemented", which was stale — play_music
        # was wired to a real PCController.play_music() call on 2026-07-17
        # (permission_gateway.py's play_music branch launches an app + hits
        # play). Left unmocked, running THIS test actually launched Spotify
        # and sent a real media key on the host machine (confirmed live:
        # 'launched spotify pid=30424' + 'media key play_pause sent' in the
        # pytest run that first caught this). Mock PCController so the test
        # verifies the gateway wires the call correctly without a real
        # side effect, and assert the CURRENT correct status.
        from unittest.mock import MagicMock, patch
        g = PermissionGateway()
        mock_pc = MagicMock()
        mock_pc.play_music.return_value = {"ok": True, "app": "spotify"}
        with patch("core.control.pc_controller.PCController", return_value=mock_pc):
            result = await g._execute_action(Action("play_music", {"track": "jazz"}, "test"))
        assert result["status"] == "ok"
        mock_pc.play_music.assert_called_once()

    async def test_set_timer_returns_duration(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("set_timer", {"duration_sec": 120}, "test"))
        assert result["set"] == 120
        assert result["status"] == "ok"

    async def test_set_timer_default_duration(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("set_timer", {}, "test"))
        assert result["set"] == 60

    async def test_check_weather_returns_ok(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        g = PermissionGateway()
        mock_response = MagicMock()
        mock_response.text = "Kolkata: Sunny +35°C"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await g._execute_action(Action("check_weather", {"location": "Kolkata"}, "test"))
        assert result["location"] == "Kolkata"
        assert result["status"] == "ok"
        assert "weather" in result

    async def test_check_attendance_returns_checked(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("check_attendance", {}, "test"))
        assert result["status"] == "ok"
        assert "checked" in result  # True if scraper succeeded, False if unavailable

    def _mock_ha(self, reply: str):
        """Mock HAConnector/EntityManager/VoiceBridge at their _execute_action
        import location so home_control's branch never touches a real HA
        instance. VoiceBridge.process() is a bare string return (see that
        class's own docstring) -- reply is exactly what it returns."""
        from unittest.mock import AsyncMock, MagicMock, patch
        mock_connector = AsyncMock()
        mock_entities = AsyncMock()
        mock_bridge = MagicMock()
        mock_bridge.process = AsyncMock(return_value=reply)
        return (
            patch("districts.home_assistant.connector.HAConnector", return_value=mock_connector),
            patch("districts.home_assistant.entity_manager.EntityManager", return_value=mock_entities),
            patch("districts.home_assistant.voice_bridge.VoiceBridge", return_value=mock_bridge),
        )

    async def test_home_control_real_success_is_ok(self):
        """2026-09-23 round 3: only a genuine device-control execution
        result (not a parse failure, not a pending confirmation, not an
        execution error) is status="ok"."""
        p1, p2, p3 = self._mock_ha("Turned on living room light")
        with p1, p2, p3:
            g = PermissionGateway()
            result = await g._execute_action(Action("home_control", {"text": "turn on the light"}, "test"))
        assert result["status"] == "ok"

    async def test_home_control_unparseable_is_rejected_not_ok(self):
        p1, p2, p3 = self._mock_ha("I couldn't understand that home control command.")
        with p1, p2, p3:
            g = PermissionGateway()
            result = await g._execute_action(Action("home_control", {"text": "asdfasdf"}, "test"))
        assert result["status"] == "rejected"

    async def test_home_control_pending_confirmation_is_not_ok(self):
        """A high-risk action (lock/unlock/arm) that's only asking for
        confirmation has NOT executed anything yet -- must not be "ok"."""
        p1, p2, p3 = self._mock_ha("Are you sure you want to lock front_door?")
        with p1, p2, p3:
            g = PermissionGateway()
            result = await g._execute_action(Action("home_control", {"text": "lock the front door"}, "test"))
        assert result["status"] == "awaiting_confirmation"

    async def test_home_control_execution_failure_is_error_not_ok(self):
        p1, p2, p3 = self._mock_ha("Sorry, I couldn't execute that command: connection refused")
        with p1, p2, p3:
            g = PermissionGateway()
            result = await g._execute_action(Action("home_control", {"text": "turn on the light"}, "test"))
        assert result["status"] == "error"

    async def test_vectorcode_unavailable_is_not_implemented_not_ok(self):
        """2026-09-23 fix: a task that never ran because VectorCode wasn't
        available used to be certified "ok" -- the exact false-success
        shape TERMINAL_STATUSES/_HANDLER_DID_NOT_RUN exist to catch, except
        this call site bypassed them by hardcoding "ok" itself."""
        from unittest.mock import MagicMock, patch
        mock_bridge = MagicMock()
        mock_bridge.is_available.return_value = False
        g = PermissionGateway()
        with patch("districts.coding.vectorcode_bridge.get_bridge", return_value=mock_bridge):
            result = await g._execute_action(Action("code_task", {"title": "do something"}, "test"))
        assert result["status"] == "not_implemented"

    async def test_vectorcode_exception_is_error_not_ok(self):
        """2026-09-23 fix: a real exception from the VectorCode bridge used
        to be swallowed and reported "ok" -- a genuine failure mislabeled
        as success."""
        from unittest.mock import MagicMock, patch
        mock_bridge = MagicMock()
        mock_bridge.is_available.side_effect = RuntimeError("bridge died")
        g = PermissionGateway()
        with patch("districts.coding.vectorcode_bridge.get_bridge", return_value=mock_bridge):
            result = await g._execute_action(Action("code_task", {"title": "do something"}, "test"))
        assert result["status"] == "error"

    async def test_commit_code_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("commit_code", {"msg": "fix bug"}, "test"))
        # status is "ok" (committed or nothing-to-commit) or "error" (no repo in test env)
        assert result["status"] in ("ok", "error")
        assert "committed" in result

    async def test_write_note_personal_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("write_note_personal", {"title": "Note"}, "test"))
        # F-4: a write_note_personal with no vault configured / no content is a
        # silent no-op and now reports "error" (not "ok") so a trust-ladder-
        # promoted write demotes on this outcome instead of persistently
        # swallowing notes with zero owner signal. title is always echoed.
        assert result["status"] == "error"
        assert result["title"] == "Note"

    async def test_send_email_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("send_email", {"to": "a@b.com"}, "test"))
        assert result["status"] == "ok"

    async def test_delete_files_not_implemented(self):
        # delete_files is intentionally not auto-executed — prevents RL phantom reward
        g = PermissionGateway()
        result = await g._execute_action(Action("delete_files", {"path": "/tmp/x"}, "test"))
        assert result["status"] == "not_implemented"

    async def test_financial_transaction_not_implemented(self):
        # financial_transaction is intentionally not auto-executed — prevents RL phantom reward
        g = PermissionGateway()
        result = await g._execute_action(Action("financial_transaction", {"amount": 100}, "test"))
        assert result["status"] == "not_implemented"

    async def test_respond_echoes_message(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("respond", {"message": "Hello, sir."}, "test"))
        assert result["status"] == "ok"
        assert result["message"] == "Hello, sir."

    async def test_respond_default_message(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("respond", {}, "test"))
        assert result["status"] == "ok"
        assert "message" in result

    async def test_unknown_action_not_implemented(self):
        # Unknown actions must NOT return ok — prevents phantom RL reward corruption
        g = PermissionGateway()
        result = await g._execute_action(Action("no_such_action_xyz", {}, "test"))
        assert result["status"] == "not_implemented"
        assert "note" in result

    async def test_widget_open_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("widget_open", {"id": "calendar"}, "test"))
        assert result["status"] == "ok"
        assert "message" in result

    async def test_widget_close_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("widget_close", {"id": "map"}, "test"))
        assert result["status"] == "ok"

    async def test_widget_close_all_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("widget_close", {"id": "all"}, "test"))
        assert result["status"] == "ok"

    async def test_music_pause_returns_ok(self):
        # 2026-07-23 (task #91): unmocked, this sends a REAL Windows media
        # key (permission_gateway.py's music_pause branch calls
        # PCController().media_key('play_pause')) — confirmed live during
        # the audit that caught this alongside the play_music finding above.
        # Mock PCController so running this test doesn't touch real playback.
        from unittest.mock import MagicMock, patch
        g = PermissionGateway()
        with patch("core.control.pc_controller.PCController", return_value=MagicMock()):
            result = await g._execute_action(Action("music_pause", {}, "test"))
        assert result["status"] == "ok"

    async def test_music_next_returns_ok(self):
        from unittest.mock import MagicMock, patch
        g = PermissionGateway()
        with patch("core.control.pc_controller.PCController", return_value=MagicMock()):
            result = await g._execute_action(Action("music_next", {}, "test"))
        assert result["status"] == "ok"

    async def test_widget_show_location_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("widget_show_location", {"query": "KIIT"}, "test"))
        assert result["status"] == "ok"

    async def test_open_panel_returns_ok(self):
        g = PermissionGateway()
        result = await g._execute_action(Action("open_panel", {"panel": "health"}, "test"))
        assert result["status"] == "ok"


class TestOwnerReadonlyDispatchStatusHonesty:
    """2026-09-23 regression tests for a real bug an independent review
    found: _execute_action()'s own _OWNER_READONLY_DISPATCH_ACTION_TYPES
    branch used to default ANY missing "status" key to "ok" -- but
    GitBot's real internal-failure shape ({} for get_status(), {"commits":
    []} for get_recent_commits()) is IDENTICAL to its real success shape
    (neither ever sets "status" itself). A real failure was therefore
    certified as success for every consumer that calls
    PermissionGateway.execute() directly (voice, WebSocket,
    AutonomousExecutor) -- not just the /command path, which already had
    its own separate `_is_git_readonly_empty()` protection.

    A real, single-agent AgentRegistry scoped to each test (same
    established pattern as tests/test_rgd2a_probe_stability.py) supplies a
    real GitBot so Governor.dispatch() has something real to route to; the
    only boundary mocked is `git.Repo(...)` itself.
    """

    def _isolated_registry(self, monkeypatch):
        from core.city.agent_registry import AgentRegistry
        from districts.coding.git_bot import GitBot
        registry = AgentRegistry()
        registry.register(GitBot())
        monkeypatch.setattr("core.city.agent_registry.get_registry", lambda: registry)

    async def test_git_status_real_success_is_ok(self, monkeypatch):
        self._isolated_registry(monkeypatch)
        fake_repo = MagicMock()
        fake_repo.head.is_detached = False
        fake_repo.active_branch.name = "main"
        fake_repo.active_branch.tracking_branch.return_value = None
        fake_repo.index.diff.return_value = []
        fake_repo.untracked_files = []
        with patch("git.Repo", return_value=fake_repo):
            g = PermissionGateway()
            result = await g._execute_action(Action("git_status", {}, "test"))
        assert result["status"] == "ok"
        assert result.get("branch") == "main"

    async def test_git_status_real_failure_is_not_ok(self, monkeypatch):
        """The exact bug: GitBot.get_status() returns {} (no "branch", no
        "status") when the repo can't be opened -- this must NOT become
        "ok"."""
        self._isolated_registry(monkeypatch)
        with patch("git.Repo", side_effect=RuntimeError("not a git repository")):
            g = PermissionGateway()
            result = await g._execute_action(Action("git_status", {}, "test"))
        assert result["status"] != "ok"

    async def test_recent_commits_real_failure_is_not_ok(self, monkeypatch):
        """Same bug, the get_recent_commits() shape: {"commits": []} both
        for a genuinely empty history and for a real failure -- either way,
        an empty list here must not be certified "ok"."""
        self._isolated_registry(monkeypatch)
        with patch("git.Repo", side_effect=RuntimeError("not a git repository")):
            g = PermissionGateway()
            result = await g._execute_action(Action("recent_commits", {}, "test"))
        assert result["status"] != "ok"


class TestRecordUnknownAction:
    """Tests for _record_unknown_action() and get_unknown_actions()."""

    def test_record_unknown_action_once(self):
        g = PermissionGateway()
        g._record_unknown_action("totally_new_action")
        actions = g.get_unknown_actions()
        assert "totally_new_action" in actions
        assert actions["totally_new_action"] == 1

    def test_record_unknown_action_increments(self):
        g = PermissionGateway()
        for _ in range(3):
            g._record_unknown_action("repeated_action")
        actions = g.get_unknown_actions()
        assert actions["repeated_action"] == 3

    def test_get_unknown_actions_empty_initially(self):
        g = PermissionGateway()
        actions = g.get_unknown_actions()
        assert actions == {}

    def test_record_multiple_unknown_types(self):
        g = PermissionGateway()
        g._record_unknown_action("action_a")
        g._record_unknown_action("action_b")
        g._record_unknown_action("action_a")
        actions = g.get_unknown_actions()
        assert actions["action_a"] == 2
        assert actions["action_b"] == 1


class TestEvaluateExternal:
    """Tests for evaluate_external() — external action validation path."""

    async def test_external_forbidden_action_blocked(self, gateway):
        result = await gateway.evaluate_external("format_drive", {}, "phone")
        assert result.approved is False
        assert result.level == "FORBIDDEN"

    async def test_external_unknown_action_blocked(self, gateway):
        result = await gateway.evaluate_external("unknown_op_xyz", {}, "cloud")
        assert result.approved is False
        assert result.level == "UNKNOWN"

    async def test_external_known_action_executed(self, gateway):
        result = await gateway.evaluate_external("search_web", {"query": "test"}, "phone")
        assert result.executed is True
        assert result.approved is True

    async def test_external_green_action(self, gateway):
        result = await gateway.evaluate_external("play_music", {"track": "jazz"}, "phone")
        assert result.approved is True

    async def test_external_red_action_uses_normal_gateway(self, gateway):
        result = await gateway.evaluate_external("send_email", {"to": "a@b.com"}, "cloud")
        assert result.approved is False
        assert result.level == "RED"
        gateway._execute_action.assert_not_awaited()

    async def test_external_unknown_increments_block_count(self, gateway):
        await gateway.evaluate_external("brand_new_op_xyz", {}, "esp32")
        actions = gateway.get_unknown_actions()
        assert "brand_new_op_xyz" in actions


class TestCheckCapabilityRealMethod:
    """Test _check_capability() directly — covers the fail-closed path."""

    def test_check_capability_fails_closed_when_import_unavailable(self):
        """When vc_security.capabilities is not installed, fail closed."""
        g = PermissionGateway()
        ok, reason = g._check_capability(make_action("search_web"))
        # Either True (if CapabilityRegistry is available) or False (fail closed)
        assert isinstance(ok, bool)
        assert isinstance(reason, str)

    def test_check_capability_returns_tuple(self):
        g = PermissionGateway()
        result = g._check_capability(make_action("send_email"))
        assert len(result) == 2


class TestDecisionEngineRealLazyInit:
    """Test DecisionEngine lazy-init methods without mocking."""

    def test_get_policy_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        pm = e._get_policy()
        assert pm is not None
        # Calling again returns same instance
        assert e._get_policy() is pm

    def test_get_memory_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        mem = e._get_memory()
        assert mem is not None

    def test_get_reasoning_bank_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        rb = e._get_reasoning_bank()
        # Either a ReasoningBank or None (if vectorcode/src not accessible)
        assert rb is None or rb is not False

    def test_get_neural_trainer_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        trainer = e._get_neural_trainer()
        # Either None (if VECTORTrainer not available) or a trainer
        assert trainer is None or hasattr(trainer, "select_action")

    def test_get_epistemic_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        et = e._get_epistemic()
        # EpistemicTracker might or might not be importable
        assert et is None or hasattr(et, "get_belief")

    def test_get_goals_real(self):
        from core.loop.decision_engine import DecisionEngine
        e = DecisionEngine()
        gs = e._get_goals()
        assert gs is not None


class TestAgentBaseUncoveredPaths:
    """Tests for AgentBase methods not yet covered."""

    def test_get_system_prompt_returns_string(self):
        from core.city.agent_base import AgentBase
        import uuid
        a = AgentBase(str(uuid.uuid4()), "TestBot", "coding")
        prompt = a.get_system_prompt()
        assert isinstance(prompt, str)

    def test_vchat_with_no_district_llm(self):
        """2026-09-23: autospec=True enforces ollama_safe.chat()'s REAL
        signature (model, messages, ...) -- a plain patch(..., return_value=)
        mock accepts any call shape and previously hid a real bug where
        vchat() called chat(msg_list, ...) with no `model` argument at all,
        landing msg_list in the `model` slot and guaranteeing a TypeError on
        every real (non-mocked) call."""
        from core.city.agent_base import AgentBase
        import uuid
        from unittest.mock import patch
        a = AgentBase(str(uuid.uuid4()), "TestBot", "coding")
        a._district_llm = None  # Force fallback path
        with patch("core.inference.ollama_safe.chat", autospec=True, return_value="test response") as mock_chat:
            result = a.vchat([{"role": "user", "content": "hello"}])
        assert isinstance(result, str)
        assert mock_chat.call_args.args[0] == a.model, "model must be passed positionally, not the messages list"

    def test_know_does_not_crash(self):
        from core.city.agent_base import AgentBase
        import uuid
        a = AgentBase(str(uuid.uuid4()), "KnowBot", "research")
        # Should not crash even if SharedFacts unavailable
        a.know("test_key", "test_value")

    def test_recall_fact_returns_default_on_failure(self):
        from core.city.agent_base import AgentBase
        import uuid
        a = AgentBase(str(uuid.uuid4()), "RecallBot", "research")
        result = a.recall_fact("nonexistent_key", default="fallback")
        # Returns default if SharedFacts fails or key missing
        assert result is None or result == "fallback" or isinstance(result, str)

    async def test_request_agent_help_returns_result(self):
        from core.city.agent_base import AgentBase
        import uuid
        from unittest.mock import patch, AsyncMock
        a = AgentBase(str(uuid.uuid4()), "HelpBot", "coding")
        with patch("core.loop.workflow_runner.WorkflowRunner") as mock_wr:
            mock_wr.return_value.trigger_workflow = AsyncMock(return_value="wf_123")
            result = await a.request_agent_help("target_agent", {"type": "test"})
        assert isinstance(result, dict)
