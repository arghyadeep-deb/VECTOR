"""Phase 3 audit regressions for districts/agency."""
import asyncio
import json

import pytest

from districts.agency import content_strategist as cs_mod
from districts.agency import proposal_strategist as ps_mod
from districts.agency import sales_strategist as ss_mod
from districts.agency.client_manager import ClientManager
from districts.agency.performance_tracker import PerformanceTracker


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_TEST_DATA_DIR", str(tmp_path / "data"))


def _run(coro):
    return asyncio.run(coro)


# ---- client_manager -------------------------------------------------------
def test_bad_payment_amount_rejected_without_partial_mutation():
    cm = ClientManager()
    cm.add_client("Acme", "a@acme.test")
    res = cm.track_engagement("Acme", "payment_received", {"amount": "lots"})
    assert res["status"] == "error"
    c = cm.get_client("Acme")
    assert c["total_engagements"] == 0 and c["lifetime_value"] == 0.0
    assert cm.get_engagement_history("Acme") == []
    ok = cm.track_engagement("Acme", "payment_received", {"amount": "150.5"})
    assert ok["status"] == "success" and cm.get_client("Acme")["lifetime_value"] == 150.5


def test_update_client_rejects_non_numeric_lifetime_value():
    cm = ClientManager()
    cm.add_client("Acme", "a@acme.test")
    assert cm.update_client("Acme", {"lifetime_value": "abc"})["status"] == "error"
    assert cm.get_client_summary()["total_lifetime_value"] == 0.0  # summary still works


def test_corrupt_client_file_is_backed_up_not_destroyed(tmp_path):
    cm = ClientManager()
    cm._client_file.parent.mkdir(parents=True, exist_ok=True)
    cm._client_file.write_text('{"clients": {"Keep": ', encoding="utf-8")  # truncated
    cm2 = ClientManager()
    assert cm2.list_clients() == []
    cm2.add_client("New", "n@x.test")  # overwrites the live file
    backup = cm2._client_file.with_name(cm2._client_file.name + ".corrupt")
    assert backup.exists() and "Keep" in backup.read_text(encoding="utf-8")


def test_client_save_is_atomic(monkeypatch):
    cm = ClientManager()
    cm.add_client("Acme", "a@acme.test")

    def boom(*a, **k):
        raise RuntimeError("disk full mid-write")

    monkeypatch.setattr(json, "dump", boom)
    assert cm._save_clients() is False
    monkeypatch.undo()
    assert "Acme" in json.loads(cm._client_file.read_text(encoding="utf-8"))["clients"]


# ---- performance_tracker --------------------------------------------------
def test_unknown_metric_not_reported_ok():
    pt = PerformanceTracker()
    res = _run(pt.run({"type": "get_trend", "params": {"metric": "nope_metric"}}))
    assert res["status"] == "error"
    res = _run(pt.run({"type": "get_comparison", "params": {"metric_a": "x1", "metric_b": "x2"}}))
    assert res["status"] == "error"


def test_known_metric_trend_still_ok():
    pt = PerformanceTracker()
    pt.track_metric("latency", 5.0)
    res = _run(pt.run({"type": "get_trend", "params": {"metric": "latency"}}))
    assert res["status"] == "ok" and res["data_points"] == 1


def test_corrupt_metrics_file_backed_up():
    pt = PerformanceTracker()
    pt._data_file.parent.mkdir(parents=True, exist_ok=True)
    pt._data_file.write_text("{not json", encoding="utf-8")
    pt2 = PerformanceTracker()
    pt2.track_metric("m", 1.0)
    assert pt2._data_file.with_name(pt2._data_file.name + ".corrupt").read_text(encoding="utf-8") == "{not json"


def test_metrics_save_is_atomic(monkeypatch):
    pt = PerformanceTracker()
    pt.track_metric("m", 1.0)
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert pt._save_data() is False
    monkeypatch.undo()
    assert "m" in json.loads(pt._data_file.read_text(encoding="utf-8"))["metrics"]


# ---- content_strategist ---------------------------------------------------
def test_content_plan_path_traversal_confined(tmp_path, monkeypatch):
    agent = cs_mod.ContentStrategist()
    vault = tmp_path / "vault"
    agent._obsidian._vault = vault
    plan = {"id": "abcdef12345", "topic": "../../../../escaped", "content": "c",
            "headlines": [], "outline": [], "platforms": [], "created_at": "t", "status": "draft"}
    assert agent._save_content_plan(plan) is True
    assert not (tmp_path / "escaped_abcdef12.md").exists()
    written = list((vault / "Research/ContentStrategy/Plans").glob("*.md"))
    assert len(written) == 1 and written[0].resolve().is_relative_to(vault.resolve())


def test_trend_path_traversal_confined(tmp_path):
    agent = cs_mod.ContentStrategist()
    vault = tmp_path / "vault"
    agent._obsidian._vault = vault
    topic = "../../../../etc/evil"
    agent._trends_cache[topic] = {"analysis": "a", "timestamp": "t"}
    assert agent.save_trends_to_vault(topic) is True
    files = list((vault / "Research/ContentStrategy/Trends").glob("*.md"))
    assert len(files) == 1 and files[0].resolve().is_relative_to(vault.resolve())


def test_content_run_llm_failure_is_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(cs_mod, "_llm", boom)
    agent = cs_mod.ContentStrategist()
    res = _run(agent.run({"type": "x", "params": None}))
    assert res["status"] == "error"


# ---- sales_strategist -----------------------------------------------------
def test_pipeline_unparseable_date_not_healthy():
    agent = ss_mod.SalesStrategist()
    r = agent.analyze_pipeline([{"name": "D", "stage": "proposal", "value": 10, "last_updated": "garbage"}])
    assert r["health"] != "healthy" and r["unparseable_dates"] == ["D"]


def test_pipeline_tz_aware_stale_date_flagged():
    agent = ss_mod.SalesStrategist()
    r = agent.analyze_pipeline([{"name": "Old", "stage": "proposal", "value": 10,
                                 "last_updated": "2020-01-01T00:00:00+00:00"}])
    assert r["at_risk_deals"] == ["Old"]


def test_sales_run_reads_params_and_empty_pipeline_is_error():
    agent = ss_mod.SalesStrategist()
    agent._memory = type("M", (), {"store": lambda self, **k: None})()
    res = _run(agent.run({"type": "pipeline", "params": {"deals": [
        {"name": "A", "stage": "qualified", "value": 100}]}}))
    assert res["status"] == "ok" and res["pipeline"]["total_deals"] == 1
    assert _run(agent.run({"type": "pipeline", "params": {"deals": []}}))["status"] == "error"


# ---- proposal_strategist --------------------------------------------------
def test_proposal_roi_reads_params():
    agent = ps_mod.ProposalStrategist()
    res = _run(agent.run({"type": "roi", "params": {"solution_cost": 1000, "time_saved_hours_monthly": 1,
                                                    "hourly_rate": 1000.0}}))
    assert res["roi"]["solution_investment"] == 1000
    assert res["roi"]["monthly_savings_inr"] == 1000.0


def test_proposal_question_llm_failure_not_fabricated_proposal(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(ps_mod, "chat", boom)
    agent = ps_mod.ProposalStrategist()
    res = _run(agent.run({"type": "proposal_question", "params": {"query": "How do I price a chatbot?"}}))
    assert res["status"] == "error" and "proposal" not in res
