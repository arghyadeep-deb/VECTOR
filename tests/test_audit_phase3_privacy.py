"""Audit phase 3 - districts/privacy regression tests (no real network, no real DB)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

from districts.privacy import data_flow_auditor as dfa
from districts.privacy import privacy_enforcer as pe

_CHAT = "core.inference.vectorcode_llm.chat"
_HYDRATE = "core.loop.context_engine.ContextEngine.session_hydration_prompt"


def _mk(cls, mod, events=None):
    with patch.object(mod, "EpisodicMemory"), patch.object(mod, "ObsidianSync"):
        agent = cls()
    agent.memory = MagicMock()
    agent.memory.recall.return_value = events or []
    return agent


def _stored_blob(agent) -> str:
    return json.dumps([c.kwargs for c in agent.memory.store.call_args_list], default=str)


def test_llm_calls_are_forced_local_only():
    for cls, mod in ((pe.PrivacyEnforcer, pe), (dfa.DataFlowAuditor, dfa)):
        agent = _mk(cls, mod)
        with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value="x") as chat:
            agent._call_ollama("hello")
        kw = chat.call_args.kwargs
        assert kw["allow_cloud"] is False and kw["sensitive"] is True and kw["district"] == "privacy"


def test_redact_pii_does_not_return_or_store_raw_values():
    agent = _mk(pe.PrivacyEnforcer, pe)
    text = "mail john.doe@example.com phone 9876543210"
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value='{"additional_finds": []}'):
        res = agent.redact_pii(text)
    assert "john.doe@example.com" not in json.dumps(res)
    assert "9876543210" not in json.dumps(res)
    blob = _stored_blob(agent)
    assert "john.doe@example.com" not in blob and "9876543210" not in blob
    assert res["total_redactions"] == 2


def test_find_leaks_does_not_copy_event_content_into_result_or_memory():
    secret = "password hunter2-SECRETVALUE exposed publicly via https://x"
    agent = _mk(dfa.DataFlowAuditor, dfa, [{"id": "e1", "content": secret, "timestamp": "t"}])
    res = agent.find_leaks()
    assert res["leaks_found"] == 1
    assert "hunter2" not in json.dumps(res).lower()
    assert "hunter2" not in _stored_blob(agent).lower()
    assert "hunter2" not in json.dumps(agent.leak_candidates).lower()


def test_scan_detects_uppercase_only_pan_pattern():
    ev = [{"id": "e1", "content": "Please share my PAN ABCDE1234F with the vendor"}]
    agent = _mk(pe.PrivacyEnforcer, pe, ev)
    with patch("core.memory.episodic.EpisodicMemory") as em:
        em.return_value.recall.return_value = ev
        res = agent.scan_data_sharing()
    assert any(v["type"] == "pan" for v in res["violations"])


def test_scan_with_no_events_is_flagged_no_data_not_plain_clean():
    agent = _mk(pe.PrivacyEnforcer, pe)
    with patch("core.memory.episodic.EpisodicMemory") as em:
        em.return_value.recall.return_value = []
        res = agent.scan_data_sharing()
    assert res["status"] == "no_data"
    leaks = _mk(dfa.DataFlowAuditor, dfa).find_leaks()
    assert leaks["status"] == "no_data"


def test_find_leaks_medium_severity_is_not_reported_low():
    # "email"(2) + "https://"(1) + "json"(1) = 4 -> MEDIUM severity
    ev = [{"id": "e1", "content": "email sent https:// json", "timestamp": "t"}]
    res = _mk(dfa.DataFlowAuditor, dfa, ev).find_leaks()
    assert res["medium_leaks"] == 1 and res["risk_level"] == "MEDIUM"


def test_find_leaks_tolerates_malformed_tags_and_null_content():
    ev = [{"id": "e1", "content": None, "tags": "not-json{"},
          {"id": "e2", "content": "x", "tags": "privacy"}]
    res = _mk(dfa.DataFlowAuditor, dfa, ev).find_leaks()
    assert res["leaks_found"] == 0


def test_audit_report_llm_failure_is_error_not_ok():
    agent = _mk(dfa.DataFlowAuditor, dfa)
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        out = asyncio.run(agent.run({}))
    assert out["status"] == "error"
    assert not any(c.kwargs.get("event_type") == "audit_report_generated"
                   for c in agent.memory.store.call_args_list)


def test_gdpr_all_llm_calls_failed_is_error_status():
    agent = _mk(pe.PrivacyEnforcer, pe)
    with patch(_HYDRATE, return_value="h"), patch(_CHAT, return_value=""):
        res = agent.enforce_gdpr({"a": 1})
    assert res["status"] == "error" and res["compliance_level"] == "NON_COMPLIANT"


def test_gdpr_non_numeric_score_does_not_crash():
    agent = _mk(pe.PrivacyEnforcer, pe)
    with patch(_HYDRATE, return_value="h"), \
         patch(_CHAT, return_value='{"compliant": true, "score": "high", "issues": []}'):
        res = agent.enforce_gdpr({"a": 1})
    assert res["overall_score"] == 0 and res["status"] == "ok"


def test_redact_pii_survives_malformed_llm_finds():
    agent = _mk(pe.PrivacyEnforcer, pe)
    with patch(_HYDRATE, return_value="h"), \
         patch(_CHAT, return_value='{"additional_finds": ["not-a-dict"]}'):
        res = agent.redact_pii("call 9876543210")
    assert "9876543210" not in res["redacted_text"]
