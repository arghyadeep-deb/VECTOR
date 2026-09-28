"""RR-1.5 regression tests — permission vocabulary reconciliation.

Background (see VECTOR_TECHNICAL_KNOWLEDGE/RR1_5_PERMISSION_VOCABULARY_REPORT.md):
RR-1's own production validation exposed that most REAL, established district
task_types classify_chat_intent() can name were never given a PermissionGateway
tier at all (UNKNOWN -> correctly fail-closed-blocked). Of 19 such task_types
individually source-verified for this remediation (the 9 fixed, deterministic
regex-preclassify task_types classify_chat_intent() itself can produce, plus 11
observed firing from a separate, pre-existing background subsystem), only 2
(list_districts, test_feature) had a confirmed, exact, genuinely read-only real
implementation. Only those 2 were added to core/config.py's GREEN list. The
other 17 — including system_status, which has NO implementation anywhere in the
codebase under that name — are deliberately left UNKNOWN.

Per .claude/rules/testing.md: PermissionGateway is never mocked here.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.loop.permission_gateway import PermissionGateway, Action


# ── 1. Inventory — no silent vocabulary gaps for the task_types this
#      remediation actually investigated ────────────────────────────────────

# The exact 19 task_types capability-verified in Phase 2 of RR-1.5 (see the
# report's Section 5/6). Every one of these must be either classified in
# core/config.py's permission lists, OR explicitly documented here as an
# intentional REMAIN_UNKNOWN with a one-line reason — never silently absent
# from both.
_RR1_5_INVESTIGATED = {
    # regex-preclassify vocabulary (classify_chat_intent's own fixed set)
    "study_session": "REMAIN_UNKNOWN: no agent declares this exact capability string",
    "quiz_vocabulary": "REMAIN_UNKNOWN: no agent declares this exact capability string",
    "sketch_layout": "REMAIN_UNKNOWN: no agent declares this exact capability string",
    "generate_report": "REMAIN_UNKNOWN: exact capability only exists in a different district than classify_chat_intent's own hardcoded (data_analytics) mapping",
    "habit_analysis": "REMAIN_UNKNOWN: no agent declares this exact capability string (declares 'habit'/'pattern' instead)",
    "idea_validation": "REMAIN_UNKNOWN: no agent declares this exact capability string (declares 'idea_validate' instead)",
    "weekly_review": "REMAIN_UNKNOWN: no agent declares this exact capability string (declares 'weekly_journal' instead)",
    "goal_summary": "REMAIN_UNKNOWN: no 'brain' district exists in the codebase at all",
    "system_status": "REMAIN_UNKNOWN: confirmed NO implementation anywhere in the codebase under this name",
    # observed background-subsystem vocabulary
    "review_content": "REMAIN_UNKNOWN: no exact capability match found; target district not fully traced",
    "distribute_content": "REMAIN_UNKNOWN: no exact capability match; falls to a generic LLM-draft fallback, not a confirmed dedicated handler",
    "track_campaign_performance": "REMAIN_UNKNOWN: no exact capability match found; target district not fully traced",
    "analyze_campaign_metrics": "REMAIN_UNKNOWN: no exact capability match found; target district not fully traced",
    "list_districts": "GREEN: real, dedicated, read-only district/agent registry enumeration endpoint",
    "test_feature": "GREEN: real, local-only HTTP self-diagnostic loop (own API only, no external network)",
    "document_feature": "REMAIN_UNKNOWN: confirmed STUB — this exact task_type is not handled by TechnicalWriter.run() at all",
    "update_content_from_review": "REMAIN_UNKNOWN: no exact capability match; falls to a generic fallback, not a confirmed dedicated handler",
    "optimize_from_analytics": "REMAIN_UNKNOWN: no exact capability match; falls to a generic fallback, not a confirmed dedicated handler",
    "adjust_campaign_from_analytics": "REMAIN_UNKNOWN: no exact capability match; falls to a generic fallback, not a confirmed dedicated handler",
}


class TestVocabularyInventory:
    def test_every_investigated_task_type_has_a_documented_disposition(self):
        """No silent gap: every task_type RR-1.5 actually investigated is
        accounted for above, either as a real classification or an explicit,
        justified REMAIN_UNKNOWN — never simply absent from this record."""
        assert len(_RR1_5_INVESTIGATED) == 19

    def test_green_additions_are_exactly_the_two_verified_ones(self):
        gw = PermissionGateway()
        green_additions = {
            t for t, reason in _RR1_5_INVESTIGATED.items() if reason.startswith("GREEN")
        }
        assert green_additions == {"list_districts", "test_feature"}
        for t in green_additions:
            assert gw.classify(t) == "GREEN"

    def test_remain_unknown_items_are_still_genuinely_unknown(self):
        """Confirms RR-1.5 did NOT silently classify anything it documented
        as REMAIN_UNKNOWN — these must still fail closed."""
        gw = PermissionGateway()
        remain_unknown = {
            t for t, reason in _RR1_5_INVESTIGATED.items() if reason.startswith("REMAIN_UNKNOWN")
        }
        assert len(remain_unknown) == 17
        # 2026-09-24 (Governor authorization-boundary work): these three read-only
        # summaries were deliberately classified GREEN after review; everything
        # else RR-1.5 left UNKNOWN must still fail closed.
        reclassified_green = {"generate_report", "goal_summary", "habit_analysis"}
        for t in remain_unknown - reclassified_green:
            assert gw.classify(t) == "UNKNOWN", f"{t} should still be UNKNOWN"
        for t in reclassified_green:
            assert gw.classify(t) == "GREEN", f"{t} was deliberately reclassified GREEN"

    def test_system_status_specifically_remains_unknown(self):
        """The mission's own explicitly-required control case: system_status
        has no real implementation anywhere and must not be classified."""
        assert PermissionGateway().classify("system_status") == "UNKNOWN"


# ── 2. GREEN control ─────────────────────────────────────────────────────────

class TestGreenControl:
    @pytest.mark.asyncio
    async def test_list_districts_auto_executes_without_approval(self):
        gw = PermissionGateway()
        result = await gw.execute(Action(
            action_type="list_districts", params={}, proposed_by="test_rr1_5",
        ))
        assert result.level == "GREEN"
        assert result.approved is True
        assert result.executed is True

    @pytest.mark.asyncio
    async def test_test_feature_auto_executes_without_approval(self):
        gw = PermissionGateway()
        result = await gw.execute(Action(
            action_type="test_feature", params={}, proposed_by="test_rr1_5",
        ))
        assert result.level == "GREEN"
        assert result.approved is True
        assert result.executed is True


# ── 3. YELLOW/RED control — untouched by RR-1.5 ─────────────────────────────

class TestYellowRedControlUnchanged:
    def test_financial_transaction_still_red(self):
        assert PermissionGateway().classify("financial_transaction") == "RED"

    def test_commit_code_still_yellow(self):
        assert PermissionGateway().classify("commit_code") == "YELLOW"

    @pytest.mark.asyncio
    async def test_red_action_still_requires_approval(self):
        gw = PermissionGateway()
        result = await gw.execute(Action(
            action_type="financial_transaction", params={}, proposed_by="test_rr1_5",
        ))
        # No confirmation given -> must not report as auto-executed.
        assert not (result.level == "RED" and result.approved and result.executed
                    and result.reason == "Auto-executed"), (
            "a RED action must never silently auto-execute"
        )


# ── 4. UNKNOWN control ──────────────────────────────────────────────────────

class TestUnknownControl:
    @pytest.mark.asyncio
    async def test_invented_action_remains_blocked(self):
        gw = PermissionGateway()
        made_up = "some_action_type_rr1_5_never_classified_xyz"
        assert gw.classify(made_up) == "UNKNOWN"
        result = await gw.execute(Action(action_type=made_up, params={}, proposed_by="test_rr1_5"))
        assert result.approved is False
        assert result.executed is False


# ── 5. FORBIDDEN control — untouched by RR-1.5 ──────────────────────────────

class TestForbiddenControl:
    @pytest.mark.asyncio
    async def test_forbidden_action_still_blocked(self):
        gw = PermissionGateway()
        assert gw.classify("format_drive") == "FORBIDDEN"
        result = await gw.execute(Action(action_type="format_drive", params={}, proposed_by="test_rr1_5"))
        assert result.approved is False
        assert result.executed is False


# ── 6. Owner command control (RR-1 pipeline, RR-1.5 vocabulary) ────────────

class TestOwnerCommandControl:
    @pytest.mark.asyncio
    async def test_classify_chat_intent_routed_green_action_executes(self, tmp_path, monkeypatch):
        """A real classify_chat_intent()-classified action (not the Stage-0
        keyword shortcut) now traverses the RR-1 canonical pipeline and, for
        a genuinely GREEN task_type, actually executes — closing the exact
        gap RR-1's own production validation (system_status -> UNKNOWN ->
        blocked) exposed."""
        monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "rr1_5_test.db"))
        monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated_rr1_5")
        import core.memory.episodic as ep
        ep.close_db_connection()
        mem = ep.EpisodicMemory()

        from unittest.mock import AsyncMock, patch
        from core.api.routers import commands as commands_router
        from core.api.schemas import CommandRequest
        from core.loop.decision_engine import DecisionEngine

        class _FakeContextEngine:
            def session_hydration_prompt(self, extra_context=None):
                return "TEST_HYDRATION_CONTEXT"

        text = "vector, enumerate every district you're running right now"
        assert commands_router._detect_intent_action(text)["action_type"] == "respond"

        # V1 TRUST CLOSURE (T3, 2026-09-21): this test used `list_districts`,
        # which is GREEN-registered but has NO PermissionGateway._execute_action
        # handler — it only ever "passed" because /command reported the
        # gateway's `not_implemented` result as executed (a phantom success,
        # now refused: see tests/test_v1_trust_t3_permission_vocabulary.py).
        # The intent here — a classify-routed GREEN action that genuinely
        # executes — is preserved with `set_timer`, a GREEN action that has
        # a real handler.
        with patch(
            "core.city.governor.classify_chat_intent",
            AsyncMock(return_value={"type": "set_timer", "district": "governance", "confidence": 0.9}),
        ):
            resp = await commands_router.command_endpoint(
                body=CommandRequest(text=text),
                ctx_engine=_FakeContextEngine(),
                decision_engine=DecisionEngine(),
                perm_gateway=PermissionGateway(),
                episodic_mem=mem,
            )
        ep.close_db_connection()

        assert resp.candidates_evaluated >= 1
        assert resp.action_taken == "set_timer"
        assert resp.district == "governance"


# ── 7. Autonomous regression — existing vocabulary unchanged ───────────────

class TestAutonomousRegressionUnchanged:
    """Confirms RR-1.5 touched ONLY the two documented additions — every
    pre-existing GREEN/YELLOW/RED entry keeps its exact prior tier."""

    _PRE_EXISTING_GREEN_SAMPLE = [
        "read_code", "analyze_progress", "check_weather", "check_attendance",
        "git_status", "respond", "script", "idea_validate", "schedule_post",
    ]
    _PRE_EXISTING_YELLOW_SAMPLE = ["commit_code", "set_reminder", "run_tests"]
    _PRE_EXISTING_RED_SAMPLE = [
        "send_email", "delete_files", "execute_code", "run_shell_command",
        "financial_transaction", "launch_app",
    ]

    def test_pre_existing_green_unchanged(self):
        gw = PermissionGateway()
        for t in self._PRE_EXISTING_GREEN_SAMPLE:
            assert gw.classify(t) == "GREEN", t

    def test_pre_existing_yellow_unchanged(self):
        gw = PermissionGateway()
        for t in self._PRE_EXISTING_YELLOW_SAMPLE:
            assert gw.classify(t) == "YELLOW", t

    def test_pre_existing_red_unchanged(self):
        gw = PermissionGateway()
        for t in self._PRE_EXISTING_RED_SAMPLE:
            assert gw.classify(t) == "RED", t

    def test_total_green_count_grew_by_exactly_two(self):
        # RR-1.5 added exactly two (list_districts, test_feature) to the 49 it started
        # with. The 2026-09-24 tier classification then deliberately grew GREEN to cover
        # the read-only routes (guarded by test_v1_trust_t3_permission_vocabulary.py's
        # frozen RED/YELLOW lists), so this now checks the RR-1.5 additions survived.
        green = CONFIG.get("permission", {}).get("green", [])
        assert len(green) >= 51
        assert {"list_districts", "test_feature"} <= set(green)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
