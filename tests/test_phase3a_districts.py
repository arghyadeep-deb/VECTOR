"""
Tests for Phase 3a districts:
- relationships: ContactManager, CommunicationAnalyst
- privacy:       DataFlowAuditor, PrivacyEnforcer
- pattern_detective: BehaviorAnalyst, HabitFinder

All LLM calls, Ollama, EpisodicMemory.store, EpisodicMemory.recall,
ObsidianSync, and ContextEngine are mocked so tests run offline.
"""

import datetime
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────

def _noop_store(*args, **kwargs):
    return None


def _make_mock_memory(recall_return=None):
    """Return a pre-configured MagicMock for EpisodicMemory."""
    mem = MagicMock()
    mem.recall.return_value = recall_return or []
    mem.store.side_effect = _noop_store
    mem.close.return_value = None
    return mem


# ─── patch targets ────────────────────────────────────────────────────────────
# Agents call `from core.inference.vectorcode_llm import chat` locally inside their
# _call_ollama() methods — that's the function that must be patched, not ollama_safe.chat
# (which these agents never call). Patching the wrong target silently no-ops: most tests
# here use loose assertions (membership/type checks) that happen to pass on real LLM
# output too, which is how this went undetected.
_CHAT    = "core.inference.vectorcode_llm.chat"
_HYDRATE = "core.loop.context_engine.ContextEngine.session_hydration_prompt"
_OBSIDIAN_WRITE = "core.memory.obsidian_sync.ObsidianSync.write"
_OBSIDIAN_READ  = "core.memory.obsidian_sync.ObsidianSync.read"


def _patch_all(extra_patches=()):
    """Return a list of patchers that cover LLM + Obsidian + ContextEngine."""
    patchers = [
        patch(_CHAT, return_value='{"result": "mocked"}'),
        patch(_HYDRATE, return_value="[mock hydration]"),
        patch(_OBSIDIAN_WRITE, return_value=True),
        patch(_OBSIDIAN_READ, return_value=""),
    ]
    for p in extra_patches:
        patchers.append(p)
    return patchers


# ══════════════════════════════════════════════════════════════════════════════
# DISTRICT 1 — relationships
# ══════════════════════════════════════════════════════════════════════════════

class TestContactManager:
    """5 tests for ContactManager covering its 4 public methods."""

    def _make_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "contacts.db"
            with patch("districts.relationships.contact_manager.EpisodicMemory", return_value=_make_mock_memory()), \
                 patch("districts.relationships.contact_manager.ObsidianSync"):
                from districts.relationships.contact_manager import ContactManager
                agent = ContactManager()
                # redirect DB to temp path so it's isolated
                agent.db_path = db_path
                agent._init_db()
                return agent, tmpdir

    def test_contact_manager_district_and_name(self):
        """Agent must identify itself as 'relationships' district."""
        with patch("districts.relationships.contact_manager.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.relationships.contact_manager.ObsidianSync"):
            from districts.relationships.contact_manager import ContactManager
            agent = ContactManager()
        assert agent.district == "relationships"
        assert agent.name == "ContactManager"
        assert agent.health_points == 500

    def test_add_contact_returns_expected_keys(self):
        """add_contact must return a dict with name/phone/email/notes/added_at."""
        mock_mem = _make_mock_memory()
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("districts.relationships.contact_manager.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.contact_manager.ObsidianSync"):
            from districts.relationships.contact_manager import ContactManager
            agent = ContactManager()
            agent.db_path = Path(tmpdir) / "contacts.db"
            agent._init_db()
            result = agent.add_contact("Charlie", "+919000000001", "charlie@test.com", "Test note")

        assert result["name"] == "Charlie"
        assert result["phone"] == "+919000000001"
        assert result["email"] == "charlie@test.com"
        assert "added_at" in result
        # EpisodicMemory.store must have been called at least once
        mock_mem.store.assert_called()

    def test_get_contact_not_found_returns_error(self):
        """get_contact on a non-existent name must return {'error': ...}."""
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("districts.relationships.contact_manager.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.relationships.contact_manager.ObsidianSync"):
            from districts.relationships.contact_manager import ContactManager
            agent = ContactManager()
            agent.db_path = Path(tmpdir) / "contacts.db"
            agent._init_db()
            result = agent.get_contact("NoSuchPerson")

        assert "error" in result

    def test_list_contacts_empty_db(self):
        """list_contacts on an empty DB must return total_contacts=0."""
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("districts.relationships.contact_manager.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.relationships.contact_manager.ObsidianSync"):
            from districts.relationships.contact_manager import ContactManager
            agent = ContactManager()
            agent.db_path = Path(tmpdir) / "contacts.db"
            agent._init_db()
            result = agent.list_contacts()

        assert result["total_contacts"] == 0
        assert isinstance(result["contacts"], list)

    @pytest.mark.parametrize("interaction_type", ["meeting", "call", "email", "casual"])
    def test_track_interaction_records_type(self, interaction_type):
        """track_interaction must record the type and return expected keys."""
        mock_mem = _make_mock_memory()
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("districts.relationships.contact_manager.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.contact_manager.ObsidianSync"):
            from districts.relationships.contact_manager import ContactManager
            agent = ContactManager()
            agent.db_path = Path(tmpdir) / "contacts.db"
            agent._init_db()
            # Must add the contact first so UPDATE does not fail silently
            agent.add_contact("Dave", "", "", "")
            result = agent.track_interaction("Dave", "Talked about project", interaction_type)

        assert result["contact_name"] == "Dave"
        assert result["type"] == interaction_type
        assert "timestamp" in result
        mock_mem.store.assert_called()


class TestCommunicationAnalyst:
    """5 tests for CommunicationAnalyst covering its 3 public methods."""

    def _make_agent(self):
        with patch("districts.relationships.communication_analyst.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.relationships.communication_analyst.ObsidianSync"):
            from districts.relationships.communication_analyst import CommunicationAnalyst
            return CommunicationAnalyst()

    def test_communication_analyst_district(self):
        agent = self._make_agent()
        assert agent.district == "relationships"
        assert agent.name == "CommunicationAnalyst"

    def test_analyze_communication_style_keys(self):
        """analyze_communication_style must return contact_name and style_data."""
        mock_mem = _make_mock_memory(recall_return=[
            {"event_type": "message", "content": "hey yeah cool", "timestamp": "2026-05-01T10:00:00Z", "source": "gmail"},
        ])
        llm_response = '{"style": "casual", "formality_score": 0.3, "responsiveness": "fast", "tone": "friendly", "key_characteristics": [], "recommendations": []}'
        with patch("districts.relationships.communication_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.communication_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=llm_response):
            from districts.relationships.communication_analyst import CommunicationAnalyst
            agent = CommunicationAnalyst()
            result = agent.analyze_communication_style("Eve")

        assert result["contact_name"] == "Eve"
        assert "style_data" in result
        assert "analyzed_at" in result
        assert result["style_data"].get("style") == "casual"

    def test_suggest_reconnect_keys(self):
        """suggest_reconnect must return reconnection_suggestion and recommended_method."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.relationships.communication_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.communication_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value="Send a message saying hello"):
            from districts.relationships.communication_analyst import CommunicationAnalyst
            agent = CommunicationAnalyst()
            result = agent.suggest_reconnect("Frank")

        assert result["contact_name"] == "Frank"
        assert "reconnection_suggestion" in result
        assert result["recommended_method"] in ("message", "call")

    def test_generate_relationship_insights_keys(self):
        """generate_relationship_insights must include interaction_count and relationship_insights."""
        mock_mem = _make_mock_memory(recall_return=[
            {"event_type": "call", "content": "Discussed project plans", "timestamp": "2026-05-01T10:00:00Z"},
        ])
        with patch("districts.relationships.communication_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.communication_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value="Relationship is strong with score 8/10"):
            from districts.relationships.communication_analyst import CommunicationAnalyst
            agent = CommunicationAnalyst()
            result = agent.generate_relationship_insights("Grace")

        assert result["contact_name"] == "Grace"
        assert "relationship_insights" in result
        assert isinstance(result["interaction_count"], int)

    def test_analyze_style_stores_in_memory(self):
        """After analyze_communication_style, EpisodicMemory.store should be called."""
        mock_mem = _make_mock_memory(recall_return=[
            {"event_type": "email", "content": "Please find regards", "timestamp": "2026-05-01T10:00:00Z", "source": "gmail"},
        ])
        with patch("districts.relationships.communication_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.relationships.communication_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value='{"style": "formal", "formality_score": 0.8}'):
            from districts.relationships.communication_analyst import CommunicationAnalyst
            agent = CommunicationAnalyst()
            agent.analyze_communication_style("Henry")

        mock_mem.store.assert_called()


# ══════════════════════════════════════════════════════════════════════════════
# DISTRICT 2 — privacy
# ══════════════════════════════════════════════════════════════════════════════

class TestDataFlowAuditor:
    """5 tests for DataFlowAuditor covering audit_data_flows, find_leaks, generate_audit_report."""

    def _make_agent(self):
        with patch("districts.privacy.data_flow_auditor.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.privacy.data_flow_auditor.ObsidianSync"):
            from districts.privacy.data_flow_auditor import DataFlowAuditor
            return DataFlowAuditor()

    def test_data_flow_auditor_district(self):
        agent = self._make_agent()
        assert agent.district == "privacy"
        assert agent.name == "DataFlowAuditor"

    def test_audit_data_flows_empty_memory(self):
        """audit_data_flows must return required keys even with empty episodic memory."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.data_flow_auditor.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.data_flow_auditor.ObsidianSync"):
            from districts.privacy.data_flow_auditor import DataFlowAuditor
            agent = DataFlowAuditor()
            result = agent.audit_data_flows()

        required = {"total_events_audited", "data_flows_detected", "suspicious_flows", "audited_at"}
        assert required.issubset(result.keys())
        assert result["total_events_audited"] == 0

    def test_find_leaks_risk_level_present(self):
        """find_leaks must always return a risk_level key with a valid value."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.data_flow_auditor.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.data_flow_auditor.ObsidianSync"):
            from districts.privacy.data_flow_auditor import DataFlowAuditor
            agent = DataFlowAuditor()
            result = agent.find_leaks()

        assert "leaks_found" in result
        assert result["risk_level"] in ("LOW", "HIGH", "CRITICAL")
        assert isinstance(result["leaks_found"], int)

    def test_find_leaks_high_risk_with_suspicious_event(self):
        """When episodic memory contains PII + storage leak keywords, risk must be elevated."""
        evil_event = {
            "id": "evt-001",
            "event_type": "upload",
            "content": "user email and password token exposed publicly unauthenticated api_key",
            "tags": "[]",
            "timestamp": "2026-05-10T12:00:00Z",
        }
        mock_mem = _make_mock_memory(recall_return=[evil_event] * 5)
        mock_mem_class = MagicMock(return_value=mock_mem)
        # Patch both the module-level import AND the local `from core.memory.episodic import` path
        with patch("districts.privacy.data_flow_auditor.EpisodicMemory", mock_mem_class), \
             patch("core.memory.episodic.EpisodicMemory", mock_mem_class), \
             patch("districts.privacy.data_flow_auditor.ObsidianSync"):
            from districts.privacy.data_flow_auditor import DataFlowAuditor
            agent = DataFlowAuditor()
            # Patch the local import inside find_leaks directly
            import districts.privacy.data_flow_auditor as _dfa_mod
            original_ep = None
            try:
                import core.memory.episodic as _ep_mod
                original_ep = _ep_mod.EpisodicMemory
                _ep_mod.EpisodicMemory = mock_mem_class
                result = agent.find_leaks()
            finally:
                if original_ep is not None:
                    _ep_mod.EpisodicMemory = original_ep

        assert result["leaks_found"] > 0
        assert result["risk_level"] in ("HIGH", "CRITICAL")

    def test_generate_audit_report_calls_llm(self):
        """generate_audit_report must call the LLM and return a 'report' key."""
        mock_mem = _make_mock_memory(recall_return=[])
        llm_response = "Executive summary: no critical leaks found. Data flows are compliant."
        with patch("districts.privacy.data_flow_auditor.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.data_flow_auditor.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=llm_response):
            from districts.privacy.data_flow_auditor import DataFlowAuditor
            agent = DataFlowAuditor()
            result = agent.generate_audit_report()

        assert "report" in result
        assert result["report"] == llm_response
        assert "generated_at" in result


class TestPrivacyEnforcer:
    """5 tests for PrivacyEnforcer covering scan_data_sharing, enforce_gdpr, redact_pii."""

    def _make_agent(self):
        with patch("districts.privacy.privacy_enforcer.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.privacy.privacy_enforcer.ObsidianSync"):
            from districts.privacy.privacy_enforcer import PrivacyEnforcer
            return PrivacyEnforcer()

    def test_privacy_enforcer_district(self):
        agent = self._make_agent()
        assert agent.district == "privacy"
        assert agent.name == "PrivacyEnforcer"

    def test_scan_data_sharing_keys(self):
        """scan_data_sharing must return scanned_events, pii_violations and risk_level."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.privacy_enforcer.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.privacy_enforcer.ObsidianSync"):
            from districts.privacy.privacy_enforcer import PrivacyEnforcer
            agent = PrivacyEnforcer()
            result = agent.scan_data_sharing()

        assert "scanned_events" in result
        assert "risk_level" in result
        assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_redact_pii_removes_email(self):
        """redact_pii must strip a clearly formatted email address from text."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.privacy_enforcer.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.privacy_enforcer.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value='{"additional_finds": []}'):
            from districts.privacy.privacy_enforcer import PrivacyEnforcer
            agent = PrivacyEnforcer()
            text = "Please contact john.doe@example.com for details."
            result = agent.redact_pii(text)

        assert "redacted_text" in result
        assert "john.doe@example.com" not in result["redacted_text"]
        assert result["total_redactions"] >= 1

    def test_redact_pii_removes_phone(self):
        """redact_pii must strip an Indian mobile number from text."""
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.privacy_enforcer.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.privacy_enforcer.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value='{"additional_finds": []}'):
            from districts.privacy.privacy_enforcer import PrivacyEnforcer
            agent = PrivacyEnforcer()
            text = "Call me at 9876543210 anytime."
            result = agent.redact_pii(text)

        assert "9876543210" not in result["redacted_text"]
        assert result["total_redactions"] >= 1

    def test_enforce_gdpr_structure(self):
        """enforce_gdpr must return overall_score, compliance_level, and 7 requirement checks."""
        compliant_json = '{"compliant": true, "score": 85, "issues": [], "recommendations": ["Keep it up"]}'
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.privacy.privacy_enforcer.EpisodicMemory", return_value=mock_mem), \
             patch("districts.privacy.privacy_enforcer.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=compliant_json):
            from districts.privacy.privacy_enforcer import PrivacyEnforcer
            agent = PrivacyEnforcer()
            result = agent.enforce_gdpr({"data_type": "profile", "retention_days": 90})

        assert "overall_score" in result
        assert "compliance_level" in result
        assert result["compliance_level"] in ("COMPLIANT", "PARTIAL", "NON_COMPLIANT")
        # All 7 GDPR principles must appear in checks
        assert len(result["checks"]) == 7


# ══════════════════════════════════════════════════════════════════════════════
# DISTRICT 3 — pattern_detective
# ══════════════════════════════════════════════════════════════════════════════

_ACTIVITY_LOG = [
    {"type": "coding",   "timestamp": "2026-05-01T10:00:00Z", "duration": 120},
    {"type": "coding",   "timestamp": "2026-05-01T14:00:00Z", "duration": 90},
    {"type": "reading",  "timestamp": "2026-05-01T20:00:00Z", "duration": 30},
    {"type": "coding",   "timestamp": "2026-05-02T09:00:00Z", "duration": 150},
    {"type": "exercise", "timestamp": "2026-05-02T07:00:00Z", "duration": 45},
]

_EPISODIC_EVENTS = [
    {"event_type": "coding", "timestamp": "2026-05-01T14:00:00Z", "content": "Started coding session"},
    {"event_type": "coding", "timestamp": "2026-05-02T14:30:00Z", "content": "Continued coding"},
    {"event_type": "coding", "timestamp": "2026-05-03T14:15:00Z", "content": "More coding"},
    {"event_type": "reading", "timestamp": "2026-05-01T20:00:00Z", "content": "Read book"},
]


class TestBehaviorAnalyst:
    """5 tests for BehaviorAnalyst covering analyze_behavior, predict_next_action, suggest_improvements."""

    def _make_agent(self):
        with patch("districts.pattern_detective.behavior_analyst.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.pattern_detective.behavior_analyst.ObsidianSync"):
            from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
            return BehaviorAnalyst()

    def test_behavior_analyst_district(self):
        agent = self._make_agent()
        assert agent.district == "pattern_detective"
        assert agent.name == "BehaviorAnalyst"

    def test_analyze_behavior_profile_keys(self):
        """analyze_behavior must build a profile for each activity type present."""
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.behavior_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.behavior_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value="Coding is the dominant activity. Consistency score: 8/10."):
            from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
            agent = BehaviorAnalyst()
            result = agent.analyze_behavior(_ACTIVITY_LOG)

        assert result["total_activities"] == len(_ACTIVITY_LOG)
        assert "behavior_profile" in result
        assert "coding" in result["behavior_profile"]
        assert result["behavior_profile"]["coding"]["frequency"] == 3

    @pytest.mark.parametrize("activity_type,expected_freq", [
        ("coding", 3),
        ("reading", 1),
        ("exercise", 1),
    ])
    def test_analyze_behavior_frequencies(self, activity_type, expected_freq):
        """Activity frequency counts must be accurate per type."""
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.behavior_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.behavior_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value="Analysis complete."):
            from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
            agent = BehaviorAnalyst()
            result = agent.analyze_behavior(_ACTIVITY_LOG)

        profile = result["behavior_profile"]
        assert activity_type in profile
        assert profile[activity_type]["frequency"] == expected_freq

    def test_predict_next_action_structure(self):
        """predict_next_action must return prediction dict and predicted_at timestamp."""
        pred_json = '{"predicted_action": "coding", "confidence": 0.85, "reasoning": "Pattern shows morning coding", "alternative_actions": ["reading"]}'
        mock_mem = _make_mock_memory(recall_return=[])
        with patch("districts.pattern_detective.behavior_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.behavior_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=pred_json):
            from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
            agent = BehaviorAnalyst()
            # Pre-populate profile so predict does not re-analyze
            agent.behavior_profiles["default"] = {"coding": {"frequency": 3, "avg_duration": 120, "time_distribution": {"morning": 2}, "total_duration": 360}}
            result = agent.predict_next_action({"time": "2026-05-03T09:00:00Z", "day": "Sunday"})

        assert "prediction" in result
        assert "predicted_at" in result
        assert "current_context" in result

    def test_suggest_improvements_structure(self):
        """suggest_improvements must return an 'improvements' key in the result."""
        improvements_json = '{"improvements": [{"action": "Take more breaks", "priority": "high", "expected_impact": "reduce fatigue"}]}'
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.behavior_analyst.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.behavior_analyst.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=improvements_json):
            from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
            agent = BehaviorAnalyst()
            sample_profile = {"coding": {"frequency": 3, "avg_duration": 120}}
            result = agent.suggest_improvements(sample_profile)

        assert "improvements" in result
        assert "behavior_summary" in result
        assert "generated_at" in result


class TestHabitFinder:
    """5 tests for HabitFinder covering analyze_screen_time, find_habits, generate_habit_report."""

    _SCREEN_DATA = [
        {"date": "2026-05-01", "app": "Chrome",  "duration_minutes": 120, "hour": 14},
        {"date": "2026-05-01", "app": "VSCode",  "duration_minutes": 180, "hour": 15},
        {"date": "2026-05-02", "app": "Chrome",  "duration_minutes": 90,  "hour": 14},
        {"date": "2026-05-02", "app": "Slack",   "duration_minutes": 30,  "hour": 10},
    ]

    def _make_agent(self):
        with patch("districts.pattern_detective.habit_finder.EpisodicMemory", return_value=_make_mock_memory()), \
             patch("districts.pattern_detective.habit_finder.ObsidianSync"):
            from districts.pattern_detective.habit_finder import HabitFinder
            return HabitFinder()

    def test_habit_finder_district(self):
        agent = self._make_agent()
        assert agent.district == "pattern_detective"
        assert agent.name == "HabitFinder"

    def test_analyze_screen_time_totals(self):
        """analyze_screen_time must compute correct average and list top apps."""
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.habit_finder.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.habit_finder.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value="Chrome dominates. Recommend reducing usage after 21:00."):
            from districts.pattern_detective.habit_finder import HabitFinder
            agent = HabitFinder()
            result = agent.analyze_screen_time(self._SCREEN_DATA)

        # total_minutes = 120+180+90+30 = 420; avg over 2 days = 210
        assert result["total_minutes"] == 420
        assert result["average_daily_minutes"] == pytest.approx(210.0, abs=0.1)
        assert result["days_tracked"] == 2
        top_apps = [a["app"] for a in result["top_apps"]]
        assert "Chrome" in top_apps

    def test_find_habits_recurring_patterns(self):
        """find_habits must detect recurring time-slot patterns when events repeat >= 3 times."""
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.habit_finder.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.habit_finder.ObsidianSync"):
            from districts.pattern_detective.habit_finder import HabitFinder
            agent = HabitFinder()
            result = agent.find_habits(_EPISODIC_EVENTS)

        assert "recurring_patterns" in result
        assert "frequent_actions" in result
        assert result["total_events"] == len(_EPISODIC_EVENTS)
        # coding at 14:xx appears 3 times → should be detected
        assert result["patterns_found"] >= 1

    def test_find_habits_frequent_actions_ordering(self):
        """frequent_actions must be sorted descending by count."""
        mock_mem = _make_mock_memory()
        with patch("districts.pattern_detective.habit_finder.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.habit_finder.ObsidianSync"):
            from districts.pattern_detective.habit_finder import HabitFinder
            agent = HabitFinder()
            result = agent.find_habits(_EPISODIC_EVENTS)

        actions = result["frequent_actions"]
        assert actions[0]["action"] == "coding"   # coding appears 3×, reading 1×
        counts = [a["count"] for a in actions]
        assert counts == sorted(counts, reverse=True)

    def test_generate_habit_report_keys(self):
        """generate_habit_report must return habit_report text and patterns_analyzed count."""
        mock_mem = _make_mock_memory(recall_return=[])
        report_text = "Key habits: evening reading, morning exercise. Consistency: good."
        with patch("districts.pattern_detective.habit_finder.EpisodicMemory", return_value=mock_mem), \
             patch("districts.pattern_detective.habit_finder.ObsidianSync"), \
             patch(_HYDRATE, return_value="[mock]"), \
             patch(_CHAT, return_value=report_text):
            from districts.pattern_detective.habit_finder import HabitFinder
            agent = HabitFinder()
            # Pre-populate patterns to skip recall path
            agent.habit_patterns = {
                "hourly_14:00": {"count": 3, "percentage": 75.0, "examples": ["coding"]},
            }
            result = agent.generate_habit_report()

        assert "habit_report" in result
        assert result["habit_report"] == report_text
        assert result["patterns_analyzed"] == 1
        assert "generated_at" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
