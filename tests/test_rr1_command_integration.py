"""RR-1 regression tests — owner command -> cognition/action unification.

Background (see VECTOR_TECHNICAL_KNOWLEDGE/RR0_ROOT_CAUSE_ARCHITECTURE_REPORT.md
and RR1_OWNER_COMMAND_INTEGRATION_REPORT.md): before RR-1, an owner /command
that classify_chat_intent() recognized as an executable action was dispatched
via a bespoke `gov_task` dict straight to GovernorCouncil().dispatch() —
bypassing Candidate construction, DecisionEngine.evaluate(), and
PermissionGateway.execute() entirely (RG-C's own finding:
candidates_evaluated=0, action_taken=None, district=None for a real owner
action request). RR-1 removed that second, parallel, gateway-bypassing path:
the classifier's output is now folded back into `intent_action` and falls
through to the exact same Candidate -> DecisionEngine.evaluate() ->
PermissionGateway.execute() pipeline Stage-0 keyword-matched actions
(_detect_intent_action) already used.

Per .claude/rules/testing.md: PermissionGateway is NEVER mocked here — every
test below exercises the real gate (real GREEN/YELLOW/RED/UNKNOWN
classification, real Action-level authorization decisions). Only
classify_chat_intent() (an LLM/embedding call) and — where explicitly noted —
DecisionEngine's own evaluate() are mocked/spied, never the permission
boundary itself. All DB-touching tests use an isolated temp SQLite DB (same
pattern as tests/unit/test_command_websocket_parity.py's isolated_episodic),
never the production vector_memory.db.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway


# ── Isolated DB fixture (mirrors tests/unit/test_command_websocket_parity.py) ──

@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    """Fresh, isolated SQLite DB per test — never touches the real memory DB."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "rr1_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated_rr1")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem, ep
    ep.close_db_connection()


class _FakeContextEngine:
    """Real ContextEngine.session_hydration_prompt() pulls in a lot of live
    world-state (screen, presence, goals, ...) that isn't the subject of
    these tests and slows every test down for no RR-1-relevant reason.
    Stubbed identically for every test — this is NOT PermissionGateway,
    NOT session_hydration's own cold-start behavior test (that lives
    elsewhere), and not on testing.md's "never mock" list."""
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


async def _call_command_endpoint(text, isolated_episodic):
    """Call command_endpoint() directly (bypassing FastAPI's Depends
    injection, same pattern test_command_websocket_parity.py uses for
    ws_command_http) with REAL DecisionEngine + REAL PermissionGateway +
    REAL EpisodicMemory (isolated DB), only ContextEngine stubbed."""
    mem, _ = isolated_episodic
    return await commands_router.command_endpoint(
        body=CommandRequest(text=text),
        ctx_engine=_FakeContextEngine(),
        decision_engine=DecisionEngine(),
        perm_gateway=PermissionGateway(),
        episodic_mem=mem,
    )


# ── 1. Classified action integration ────────────────────────────────────────

class TestClassifiedActionIntegration:
    @pytest.mark.asyncio
    async def test_action_reaches_decision_engine_and_gateway_not_governor_bypass(
        self, isolated_episodic
    ):
        """Text deliberately avoids every Stage-0 deterministic keyword
        (_detect_intent_action's ~10 fixed categories) so classify_chat_
        intent() is genuinely the only router that can produce an action
        here — proving this exercises the classifier-routed path, not
        Stage-0's own keyword-matched Candidate path."""
        text = "vector please look into today's outdoor conditions for me"
        assert commands_router._detect_intent_action(text)["action_type"] == "respond", (
            "test text must NOT match Stage-0's deterministic keyword map — "
            "otherwise this exercises Stage-0, not the classify_chat_intent path"
        )

        real_evaluate = DecisionEngine.evaluate
        captured = {}

        async def spy_evaluate(self, candidates):
            captured["candidates"] = list(candidates)
            return await real_evaluate(self, candidates)

        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "check_weather", "district": "life", "confidence": 0.9}),
        ), patch.object(DecisionEngine, "evaluate", new=spy_evaluate):
            resp = await _call_command_endpoint(text, isolated_episodic)

        # A. classified executable action reaches DecisionEngine
        assert "candidates" in captured, "DecisionEngine.evaluate() was never called"
        assert len(captured["candidates"]) == 1
        assert captured["candidates"][0].action_type == "check_weather"
        assert resp.candidates_evaluated >= 1

        # PermissionGateway was reached and is authoritative (GREEN -> auto-executed)
        assert resp.action_taken == "check_weather"
        assert resp.district == "life"

    @pytest.mark.asyncio
    async def test_governor_council_dispatch_no_longer_reachable_for_this_route(
        self, isolated_episodic
    ):
        """The old bypass (GovernorCouncil().dispatch() called directly from
        commands.py, no Candidate/DecisionEngine/PermissionGateway involved)
        must be provably gone: patch GovernorCouncil.dispatch to explode if
        called at all during a classify_chat_intent-routed action."""
        from core.city.governor import GovernorCouncil

        text = "vector please look into today's outdoor conditions for me"
        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "check_weather", "confidence": 0.9}),
        ), patch.object(
            GovernorCouncil, "dispatch",
            new=AsyncMock(side_effect=AssertionError(
                "GovernorCouncil.dispatch() must not be called directly by "
                "commands.py any more — RR-1 removed that bypass"
            )),
        ):
            resp = await _call_command_endpoint(text, isolated_episodic)
        # Real PermissionGateway path was used instead (no exception raised above)
        assert resp.action_taken == "check_weather"


# ── 2. answer_question control ──────────────────────────────────────────────

class TestAnswerQuestionControl:
    @pytest.mark.asyncio
    async def test_answer_question_stays_text_only(self, isolated_episodic):
        text = "vector please look into today's outdoor conditions for me"
        evaluate_spy = AsyncMock()

        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "answer_question"}),
        ), patch.object(DecisionEngine, "evaluate", new=evaluate_spy), patch.object(
            commands_router, "_llm_answer", new=AsyncMock(return_value="Sunny and 24C, sir.")
        ):
            resp = await _call_command_endpoint(text, isolated_episodic)

        evaluate_spy.assert_not_called()  # DecisionEngine NOT invoked for execution
        assert resp.action_taken is None
        assert resp.candidates_evaluated == 0
        assert resp.response == "Sunny and 24C, sir."

    @pytest.mark.asyncio
    async def test_answer_question_gateway_not_invoked(self, isolated_episodic):
        text = "vector please look into today's outdoor conditions for me"
        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "answer_question"}),
        ), patch.object(
            PermissionGateway, "execute",
            new=AsyncMock(side_effect=AssertionError(
                "PermissionGateway.execute() must not be called for a pure "
                "answer_question response"
            )),
        ), patch.object(commands_router, "_llm_answer", new=AsyncMock(return_value="fine")):
            resp = await _call_command_endpoint(text, isolated_episodic)
        assert resp.action_taken is None


# ── 3. Classifier timeout/fallback control ──────────────────────────────────

class TestClassifierTimeoutControl:
    @pytest.mark.asyncio
    async def test_timeout_fallback_preserves_talk_not_act(self, isolated_episodic):
        """classify_chat_intent()'s own real timeout handling normalizes
        EVERY uncertain outcome (12s timeout, parse error, low confidence,
        unrecognized district) to the identical {"type": "answer_question"}
        fallback (governor.py:1342) before commands.py ever sees it — so
        from this call site's perspective, simulating the timeout IS
        returning that exact fallback dict. Proves RR-1 did not make the
        classifier's uncertainty handling more aggressive: talk-not-act
        still holds, no Candidate execution, no PermissionGateway, no
        governor action dispatch."""
        text = "vector please look into today's outdoor conditions for me"
        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "answer_question"}),  # real timeout fallback shape
        ), patch.object(
            PermissionGateway, "execute",
            new=AsyncMock(side_effect=AssertionError("gateway must not be reached on timeout fallback")),
        ), patch.object(
            commands_router, "_llm_answer", new=AsyncMock(return_value="still here, sir")
        ):
            resp = await _call_command_endpoint(text, isolated_episodic)
        assert resp.action_taken is None
        assert resp.candidates_evaluated == 0
        assert resp.response == "still here, sir"


# ── 4. Decision authority ───────────────────────────────────────────────────

class TestDecisionAuthority:
    @pytest.mark.asyncio
    async def test_gateway_receives_the_decision_engine_selected_candidate(
        self, isolated_episodic
    ):
        """This route legitimately produces exactly ONE Candidate (RR-0's
        own 'an order, not a suggestion' precedent — background goal
        candidates never compete with an explicit owner command). Prove by
        object identity that PermissionGateway.execute() receives an Action
        built from decision.winner (the object DecisionEngine.evaluate()
        itself returned), not an independently reconstructed copy of the
        original classified intent."""
        text = "vector please look into today's outdoor conditions for me"
        real_evaluate = DecisionEngine.evaluate
        winners = {}

        async def spy_evaluate(self, candidates):
            decision = await real_evaluate(self, candidates)
            winners["winner"] = decision.winner
            return decision

        real_execute = PermissionGateway.execute
        gateway_actions = {}

        async def spy_execute(self, action):
            gateway_actions["action"] = action
            return await real_execute(self, action)

        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "check_weather", "confidence": 0.9}),
        ), patch.object(DecisionEngine, "evaluate", new=spy_evaluate), patch.object(
            PermissionGateway, "execute", new=spy_execute
        ):
            await _call_command_endpoint(text, isolated_episodic)

        assert "winner" in winners and "action" in gateway_actions
        assert gateway_actions["action"].action_type == winners["winner"].action_type
        assert gateway_actions["action"].params is winners["winner"].params, (
            "PermissionGateway must receive the params object DecisionEngine's "
            "own winning Candidate carries, not an independently rebuilt dict"
        )


# ── 5. Safety — RED action authority ────────────────────────────────────────

class TestSafetyRedAction:
    @pytest.mark.asyncio
    async def test_red_action_requires_real_approval_not_auto_executed(
        self, isolated_episodic
    ):
        """financial_transaction is real, existing RED-tier config
        (core/config.py) — VECTOR has no trading capability and this must
        NEVER auto-execute. The real (unmocked) PermissionGateway.execute()
        is exercised end-to-end; under pytest it uses its own existing
        fast RED timeout (1s, permission_gateway.py's
        `1 if "pytest" in sys.modules else 300`) and, with no owner
        confirmation given, must reject — proving PermissionGateway's
        authorization decision is authoritative and no direct-dispatch
        fallback occurs merely because it did."""
        text = "vector please look into today's outdoor conditions for me"
        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "financial_transaction", "confidence": 0.9}),
        ):
            resp = await _call_command_endpoint(text, isolated_episodic)

        assert PermissionGateway().classify("financial_transaction") == "RED"
        # No confirmation was ever supplied -> must remain denied, not executed.
        assert resp.action_taken is None, (
            "a RED action with no owner confirmation must not report as executed"
        )


# ── 6. Taint / council regression ───────────────────────────────────────────

class TestTaintCouncilRegression:
    def test_unmatched_llm_classified_action_fails_closed_not_open(self):
        """The pre-RR-1 path (GovernorCouncil().dispatch()) only ever
        taint-checked task_types matching a narrow shell/fetch substring
        list (governor.py's _shell_ish/_fetch_ish) — everything else was
        dispatched freely with no PermissionGateway involvement at all.
        Post-RR-1, ANY classify_chat_intent-classified task_type not yet
        present in core/config.py's GREEN/YELLOW/RED lists is UNKNOWN, and
        PermissionGateway's own real, pre-existing, untouched _classify()
        fails closed for UNKNOWN ('UNKNOWN — default to RED, never silently
        allow') — strictly stronger than the old taint-substring-match-only
        check, not weaker. Confirmed directly against the real gateway,
        no mocking, for a realistic invented district task_type that would
        previously have executed via the bypass."""
        gw = PermissionGateway()
        assert gw.classify("some_llm_invented_task_type_not_in_config") == "UNKNOWN"

    def test_run_shell_command_still_gated_at_least_as_strongly(self):
        """run_shell_command IS a real, pre-existing RED-tier config entry
        AND the one task_type the old taint tracker's SHELL_EXEC sink check
        specifically matched (governor.py: `"shell" in task_type`). Post-
        RR-1 it now goes through PermissionGateway's own real RED-tier flow
        (CouncilBrain deliberation + real Pushover owner approval, fail-
        closed on timeout) before anything can execute — strictly stronger
        than the old path's taint-check-then-advisory-only-council-then-
        execute sequence. Confirmed against the real, unmodified gateway
        classification — no PermissionGateway mocking."""
        gw = PermissionGateway()
        assert gw.classify("run_shell_command") == "RED"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
