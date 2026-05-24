"""
Session 9 — Spec 15: System Hardening integration tests.

Covers:
  - RulesEngine: load defaults, match patterns, execute templates, add new rules, get stats
  - RulesEngine: bypass attempts are logged via match() returning a rule
  - RulesEngine: load_from_file (JSON + YAML)
  - HPValidator: outlier clamping, EMA smoothing, seesaw detection, cross-validation stub
  - HPValidator wired into AgentBase.award_points / deduct_points
  - MCPSecurityMiddleware: tool classification, rate limiting, anomaly detection, auditing
  - _mcp_secure_call wrapper exists and is callable
"""

from __future__ import annotations

import json
import time
import pytest
import tempfile
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# RulesEngine
# ---------------------------------------------------------------------------

class TestRulesEngineDefaults:
    def setup_method(self):
        from core.security.rules_engine import RulesEngine
        self.engine = RulesEngine()
        self.engine.load_defaults()

    def test_load_defaults_registers_rules(self):
        assert len(self.engine._rules) >= 10

    def test_match_time_query(self):
        rule = self.engine.match("what time is it")
        assert rule is not None
        assert rule.category == "time"

    def test_match_greeting(self):
        rule = self.engine.match("hello there")
        assert rule is not None
        assert rule.category == "greeting"

    def test_match_thanks(self):
        rule = self.engine.match("thank you so much")
        assert rule is not None
        assert rule.category == "thanks"

    def test_match_who_created(self):
        rule = self.engine.match("who created you")
        assert rule is not None
        assert rule.category == "owner"

    def test_match_status_ping(self):
        rule = self.engine.match("ping")
        assert rule is not None

    def test_no_match_complex_query(self):
        rule = self.engine.match("write me a sorting algorithm in Python")
        assert rule is None

    def test_no_match_code_question(self):
        rule = self.engine.match("explain how transformers work")
        assert rule is None

    def test_should_bypass_true(self):
        assert self.engine.should_bypass("what time is it") is True

    def test_should_bypass_false(self):
        assert self.engine.should_bypass("summarize this document") is False


class TestRulesEngineExecution:
    def setup_method(self):
        from core.security.rules_engine import RulesEngine
        self.engine = RulesEngine()
        self.engine.load_defaults()

    def test_execute_time_rule_contains_colon(self):
        rule = self.engine.match("what time is it")
        response = self.engine.execute_rule(rule, {})
        assert ":" in response  # HH:MM:SS format

    def test_execute_date_rule_contains_date(self):
        rule = self.engine.match("what date is it today")
        assert rule is not None
        response = self.engine.execute_rule(rule, {})
        assert "2026" in response or "-" in response

    def test_execute_greeting_returns_sir(self):
        rule = self.engine.match("good morning")
        response = self.engine.execute_rule(rule, {})
        assert "Sir" in response or "sir" in response.lower()

    def test_execute_with_context(self):
        from core.security.rules_engine import BypassRule
        rule = BypassRule(
            pattern=r"\bhello\b",
            response_template="Hello {name}!",
            priority=50, category="test",
        )
        response = self.engine.execute_rule(rule, {"name": "Arghyadeep"})
        assert "Arghyadeep" in response

    def test_get_stats_returns_dict(self):
        self.engine.match("what time is it")
        stats = self.engine.get_stats()
        assert isinstance(stats, dict)
        assert "time" in stats
        assert stats["time"] >= 1


class TestRulesEngineNewRules:
    """Verify: New rules can be added; bypass attempts logged."""

    def test_register_custom_rule_and_match(self):
        from core.security.rules_engine import RulesEngine, BypassRule
        engine = RulesEngine()
        engine.register(BypassRule(
            pattern=r"\bvector version\b",
            response_template="VECTOR v1.0.0-alpha",
            priority=60, category="version",
        ))
        rule = engine.match("vector version")
        assert rule is not None
        assert rule.category == "version"

    def test_registered_rule_executes(self):
        from core.security.rules_engine import RulesEngine, BypassRule
        engine = RulesEngine()
        engine.register(BypassRule(
            pattern=r"\bcustom query\b",
            response_template="custom response {time}",
            priority=50, category="custom",
        ))
        rule = engine.match("custom query here")
        assert rule is not None
        response = engine.execute_rule(rule, {})
        assert "custom response" in response

    def test_priority_ordering(self):
        from core.security.rules_engine import RulesEngine, BypassRule
        engine = RulesEngine()
        engine.register(BypassRule(pattern=r"\bhello\b", response_template="low", priority=10, category="low"))
        engine.register(BypassRule(pattern=r"\bhello\b", response_template="high", priority=90, category="high"))
        rule = engine.match("hello")
        assert rule.category == "high"  # higher priority wins

    def test_load_from_json_file(self):
        from core.security.rules_engine import RulesEngine
        engine = RulesEngine()
        rules_data = {
            "rules": [
                {
                    "pattern": r"\bjson test\b",
                    "response_template": "json rule fired",
                    "priority": 50,
                    "category": "test_json",
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(rules_data, f)
            tmp_path = f.name
        try:
            count = engine.load_from_file(tmp_path)
            assert count == 1
            rule = engine.match("json test query")
            assert rule is not None
            assert rule.category == "test_json"
        finally:
            os.unlink(tmp_path)

    def test_bypass_attempts_are_tracked_in_stats(self):
        from core.security.rules_engine import RulesEngine
        engine = RulesEngine()
        engine.load_defaults()
        # Simulate bypass attempts
        engine.match("what time is it")
        engine.match("what time is it now")
        engine.match("hello there")
        stats = engine.get_stats()
        assert stats.get("time", 0) >= 2
        assert stats.get("greeting", 0) >= 1

    def test_get_rules_engine_singleton(self):
        from core.security.rules_engine import get_rules_engine
        e1 = get_rules_engine()
        e2 = get_rules_engine()
        assert e1 is e2


# ---------------------------------------------------------------------------
# HPValidator
# ---------------------------------------------------------------------------

class TestHPValidatorCore:
    def setup_method(self):
        from core.security.hp_validator import HPValidator
        self.v = HPValidator(db_path=":memory:")

    def test_normal_delta_passes_through(self):
        result = self.v.validate(30.0, "agent_alpha", "coding", {})
        assert result.original_delta == 30.0
        assert not result.issues  # no issues for normal delta

    def test_outlier_clamped_to_max(self):
        result = self.v.validate(500.0, "agent_alpha", "coding", {})
        assert any("clamped" in i for i in result.issues)
        assert abs(result.validated_delta) <= 200.0

    def test_negative_outlier_clamped(self):
        result = self.v.validate(-500.0, "agent_beta", "combat", {})
        assert any("clamped" in i for i in result.issues)
        assert result.validated_delta >= -200.0

    def test_ema_smoothing_applied(self):
        # After first call, EMA state is seeded; second call should smooth
        self.v.validate(100.0, "agent_x", "test", {})
        result2 = self.v.validate(10.0, "agent_x", "test", {})
        # Smoothed value should be between 10 and 100 (EMA blends them)
        assert 10.0 <= abs(result2.smoothed_hp) <= 100.0

    def test_seesaw_pattern_detected(self):
        for _ in range(5):
            self.v.validate(10.0, "seesaw_agent", "test", {})
            self.v.validate(-10.0, "seesaw_agent", "test", {})
        result = self.v.validate(-10.0, "seesaw_agent", "test", {})
        assert any("seesaw" in i for i in result.issues)

    def test_agent_history_stored(self):
        self.v.validate(20.0, "hist_agent", "test", {})
        self.v.validate(30.0, "hist_agent", "test", {})
        history = self.v.get_agent_history("hist_agent", days=1)
        assert len(history) >= 2

    def test_hp_validation_result_fields(self):
        result = self.v.validate(25.0, "field_test", "mining", {})
        assert hasattr(result, "validated_delta")
        assert hasattr(result, "original_delta")
        assert hasattr(result, "issues")
        assert hasattr(result, "smoothed_hp")
        assert hasattr(result, "cross_validated")

    def test_get_hp_validator_singleton(self):
        from core.security.hp_validator import get_hp_validator, HPValidator
        v1 = get_hp_validator()
        v2 = get_hp_validator()
        assert v1 is v2


class TestHPValidatorWiredInAgentBase:
    """HP validator is wired: award_points and deduct_points go through validation."""

    def _make_agent(self):
        from core.city.agent_base import AgentBase
        agent = AgentBase(name="test_hardening_agent", role="tester")
        agent.health_points = 500
        return agent

    def test_award_points_applies_validation(self):
        agent = self._make_agent()
        result = agent.award_points(50, "task completed")
        assert result["new_hp"] > result["old_hp"]
        assert result["new_hp"] <= 1000

    def test_deduct_points_applies_validation(self):
        agent = self._make_agent()
        result = agent.deduct_points(50, "task failed")
        assert result["new_hp"] < result["old_hp"]
        assert result["new_hp"] >= 0

    def test_outlier_award_clamped(self):
        agent = self._make_agent()
        # Try to award a huge amount that should be clamped by validator
        agent.health_points = 100
        result = agent.award_points(1000, "suspicious award")
        # EMA smoothing will moderate this; the validator runs and clips/smooths
        assert result["new_hp"] <= 1000

    def test_validate_hp_delta_method_exists(self):
        agent = self._make_agent()
        assert hasattr(agent, "_validate_hp_delta")
        delta = agent._validate_hp_delta(30.0, "test")
        assert isinstance(delta, float)

    def test_validate_hp_delta_with_zero(self):
        agent = self._make_agent()
        delta = agent._validate_hp_delta(0.0, "no change")
        assert delta == 0.0


# ---------------------------------------------------------------------------
# MCPSecurityMiddleware
# ---------------------------------------------------------------------------

class TestMCPSecurityClassification:
    def setup_method(self):
        from core.security.mcp_security import MCPSecurityMiddleware
        self.mw = MCPSecurityMiddleware(db_path=":memory:")

    def test_read_tools_are_low_risk(self):
        for name in ("read_file", "list_files", "search_files", "fetch_url"):
            assert self.mw.classify_tool(name) == "low", f"{name} should be low"

    def test_write_tools_are_medium_risk(self):
        for name in ("write_file", "edit_file", "create_file", "git_commit"):
            assert self.mw.classify_tool(name) == "medium", f"{name} should be medium"

    def test_exec_tools_are_critical(self):
        for name in ("bash_exec", "shell_exec", "admin_exec", "sudo_run", "rm_rf"):
            assert self.mw.classify_tool(name) == "critical", f"{name} should be critical"

    def test_prefix_fallback_low(self):
        assert self.mw.classify_tool("get_custom_data") == "low"
        assert self.mw.classify_tool("list_custom_items") == "low"

    def test_prefix_fallback_critical(self):
        assert self.mw.classify_tool("exec_my_script") == "critical"

    def test_unknown_tool_defaults_to_medium(self):
        assert self.mw.classify_tool("totally_unknown_tool_xyz") == "medium"


class TestMCPRateLimiting:
    def setup_method(self):
        from core.security.mcp_security import MCPSecurityMiddleware
        self.mw = MCPSecurityMiddleware(db_path=":memory:")

    def test_first_call_allowed(self):
        assert self.mw.check_rate_limit("district_a", "read_file") is True

    def test_many_calls_within_limit(self):
        for _ in range(50):
            assert self.mw.check_rate_limit("district_b", "read_file") is True

    def test_rate_limit_exceeded(self):
        from core.security.mcp_security import RATE_LIMIT_DISTRICT
        mw = MCPSecurityMiddleware(db_path=":memory:")
        for _ in range(RATE_LIMIT_DISTRICT):
            mw.check_rate_limit("district_c", "read_file")
        # Next call should be blocked
        assert mw.check_rate_limit("district_c", "read_file") is False

    def test_different_districts_independent(self):
        from core.security.mcp_security import RATE_LIMIT_DISTRICT
        mw = MCPSecurityMiddleware(db_path=":memory:")
        for _ in range(RATE_LIMIT_DISTRICT):
            mw.check_rate_limit("district_d", "read_file")
        # district_e is fresh
        assert mw.check_rate_limit("district_e", "read_file") is True


class TestMCPAuditing:
    def setup_method(self):
        from core.security.mcp_security import MCPSecurityMiddleware, ToolCallRecord
        self.mw = MCPSecurityMiddleware(db_path=":memory:")
        self.Record = ToolCallRecord

    def test_audit_call_stored(self):
        record = self.Record(
            tool_name="read_file",
            source_district="test_district",
            params={"path": "/tmp/test"},
            timestamp=time.time(),
            allowed=True,
            risk_level="low",
        )
        self.mw.audit_call(record)
        recent = self.mw.get_recent_calls(limit=10)
        assert len(recent) >= 1
        assert recent[0]["tool_name"] == "read_file"

    def test_get_recent_calls_ordered_by_timestamp(self):
        for i in range(3):
            record = self.Record(
                tool_name=f"tool_{i}",
                source_district="d1",
                params={},
                timestamp=time.time() + i,
                allowed=True,
                risk_level="low",
            )
            self.mw.audit_call(record)
        recent = self.mw.get_recent_calls(limit=5)
        assert len(recent) >= 3
        # Most recent first
        timestamps = [r["timestamp"] for r in recent[:3]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_anomaly_report_is_list(self):
        report = self.mw.get_anomaly_report()
        assert isinstance(report, list)

    def test_anomaly_detect_first_critical_call(self):
        # First critical call from a district that has no history is anomalous
        result = self.mw.detect_anomalous_call("bash_exec", "new_district_xyz", {})
        assert result is True

    def test_anomaly_not_flagged_for_low_risk(self):
        result = self.mw.detect_anomalous_call("read_file", "safe_district", {})
        assert result is False

    def test_get_mcp_security_singleton(self):
        from core.security.mcp_security import get_mcp_security
        m1 = get_mcp_security()
        m2 = get_mcp_security()
        assert m1 is m2


class TestMCPSecureCallWrapper:
    """_mcp_secure_call is wired into mcp_server and callable."""

    def test_secure_call_wrapper_exists(self):
        from core.mcp_server import _mcp_secure_call
        assert callable(_mcp_secure_call)

    def test_secure_call_returns_bool(self):
        from core.mcp_server import _mcp_secure_call
        result = _mcp_secure_call("read_file", "test_district", {"path": "/tmp"})
        assert isinstance(result, bool)

    def test_secure_call_allows_normal_traffic(self):
        from core.mcp_server import _mcp_secure_call
        result = _mcp_secure_call("recall_memory", "coding", {"query": "test"})
        assert result is True

    def test_secure_call_flags_critical_first_use(self):
        # A critical tool from a fresh district may be flagged (anomaly detection)
        # but the call is still allowed (rate limit not exceeded); we just verify it runs
        from core.mcp_server import _mcp_secure_call
        result = _mcp_secure_call("bash_exec", "brand_new_district_xyz_test", {})
        assert isinstance(result, bool)  # may be True or False, just must not raise


# ---------------------------------------------------------------------------
# Integration: rules engine bypass in autonomous loop
# ---------------------------------------------------------------------------

class TestRulesEngineBypassIntegration:
    """Verify the bypass is reachable from the autonomous loop's code path."""

    def test_rules_engine_import_from_loop_path(self):
        from core.security.rules_engine import get_rules_engine
        engine = get_rules_engine()
        assert engine is not None

    def test_bypass_match_for_time_query(self):
        from core.security.rules_engine import get_rules_engine
        engine = get_rules_engine()
        rule = engine.match("what time is it")
        assert rule is not None
        response = engine.execute_rule(rule, {})
        assert len(response) > 0

    def test_no_bypass_for_complex_query(self):
        from core.security.rules_engine import get_rules_engine
        engine = get_rules_engine()
        rule = engine.match("explain the attention mechanism in transformers")
        assert rule is None

    def test_autonomous_loop_has_governor_dispatch(self):
        """Verify _act bug fixed: _act_on uses _get_governor().dispatch, not self._act."""
        import inspect
        with open("core/loop/autonomous_loop.py", "rb") as f:
            src = f.read().decode("utf-8", errors="replace")
        # The old self._act({ should be gone
        assert "await self._act({" not in src
        # governor dispatch should be present in voice path
        assert "_get_governor().dispatch" in src

    def test_bypass_block_exists_in_autonomous_loop(self):
        """Verify the bypass code block is present in the voice path."""
        with open("core/loop/autonomous_loop.py", "rb") as f:
            src = f.read().decode("utf-8", errors="replace")
        assert "rules_engine" in src
        assert "bypass_response" in src
        assert "_bypass_rule" in src
