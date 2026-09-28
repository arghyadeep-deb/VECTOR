"""V1 handoff "workflow C": a safe, persistent, multi-step, read-only browser task -- proven end to end.

    open index -> discover detail URL -> persist URL/progress -> INTERRUPT AND RESTART -> follow the persisted URL ->
    extract fields -> return page evidence -> verify against independently known fixture contents -> record outcome

Runs the REAL chain: AutonomousLoop._think_tick -> DecisionEngine -> PlanRunner -> AutonomousExecutor -> PermissionGateway ->
Governor -> WebScout.web_extract -> page_extract -> a real local HTTP server. Nothing below the loop is stubbed. The
"restart" is a brand-new AutonomousLoop + PlanStore loaded from the plan's JSON file, with the s1 output only available
because it was persisted. No accounts, forms, purchases, publication or writes: every action is a GET.
"""
from __future__ import annotations

import http.server
import sys
import threading
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.autonomous_loop import AutonomousLoop
from core.runtime.plans import Plan, PlanStep, PlanStore, _now
from tests.test_r13_production_learning_validation import build_isolated_engine

# ── independently known fixture truth ──────────────────────────────────────────
GROUND_TRUTH = {"customer": "Acme Corp", "total": "INR 11,800.00", "detail_path": "/invoice/42"}
INDEX_HTML = f"""<html><head><title>Ledger</title></head><body><h1>Ledger</h1>
<a class="detail" href="{GROUND_TRUTH['detail_path']}">Invoice 42</a></body></html>""".encode()


def _detail_html(customer: str) -> bytes:
    return f"""<html><head><title>Invoice 42</title></head><body><h2 id="customer">{customer}</h2>
<span class="total">{GROUND_TRUTH['total']}</span></body></html>""".encode()


class _Site(http.server.ThreadingHTTPServer):
    customer = GROUND_TRUTH["customer"]
    hits: list[str] = []


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.server.hits.append(self.path)
        if self.path == "/":
            body, code = INDEX_HTML, 200
        elif self.path == GROUND_TRUTH["detail_path"]:
            body, code = _detail_html(self.server.customer), 200
        else:
            body, code = b"nope", 404
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("VECTOR_WEB_EXTRACT_ALLOW_PRIVATE", "1")  # the fixture is on localhost
    srv = _Site(("127.0.0.1", 0), _H)
    srv.hits = []
    srv.customer = GROUND_TRUTH["customer"]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.base = f"http://127.0.0.1:{srv.server_port}"
    yield srv
    srv.shutdown()


@pytest.fixture
def web_registry():
    """Two-agent-free registry: just the real WebScout, swapped in for the process-wide singleton."""
    import core.city.agent_registry as registry_mod
    from core.city.agent_registry import AgentRegistry
    from districts.research.web_scout import WebScout

    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    fresh.register(WebScout())
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


def _plan(base: str) -> Plan:
    return Plan(
        id="plan-workflow-c", goal_id="", objective="Find the invoice detail page and read its customer and total",
        status="active", created_at=_now(), updated_at=_now(),
        steps=[
            PlanStep(
                id="s1", action_type="web_extract",
                params={"url": base + "/", "fields": {"detail_url": "a.detail@href"}, "links": False},
                verification={"type": "all_of", "criteria": {"checks": [
                    {"type": "status_check"},
                    {"type": "result_field", "criteria": {"field": "fields.detail_url", "regex": r"/invoice/\d+$"}},
                ]}},
            ),
            PlanStep(
                id="s2", action_type="web_extract", depends_on=["s1"],
                params={"fields": {"customer": "#customer", "total": ".total"}, "links": False},
                param_bindings={"url": "s1.fields.detail_url"},   # only resolvable from s1's PERSISTED output
                verification={"type": "all_of", "criteria": {"checks": [
                    {"type": "status_check"},
                    {"type": "result_field", "criteria": {"field": "fields.customer", "equals": GROUND_TRUTH["customer"]}},
                    {"type": "result_field", "criteria": {"field": "fields.total", "contains": "11,800"}},
                ]}},
            ),
        ],
    )


def _loop(tmp_path, monkeypatch, plans_file):
    monkeypatch.setattr("core.sensing.stuck_detector.get_active_session", lambda: None, raising=False)
    loop = AutonomousLoop()
    loop._decision_engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
    loop._plan_store = PlanStore(path=plans_file)
    ctx = MagicMock()
    ctx.get_world_state.return_value = {}
    goals = MagicMock()
    goals.generate_immediate_actions.return_value = []
    monkeypatch.setattr(loop, "_get_context", lambda: ctx)
    monkeypatch.setattr(loop, "_get_goals", lambda: goals)
    return loop


async def _tick_until(loop, plan_id, predicate, budget=12):
    for n in range(1, budget + 1):
        loop._tick_count = n
        await loop._think_tick()
        if predicate(loop._plan_store.get(plan_id)):
            return n
    return None


@pytest.mark.asyncio
async def test_persistent_browser_plan_survives_a_restart_and_is_verified_against_the_fixture(
    isolated_vector_db, web_registry, site, tmp_path, monkeypatch,
):
    plans_file = tmp_path / "plans.json"
    loop1 = _loop(tmp_path, monkeypatch, plans_file)
    loop1._plan_store.add(_plan(site.base))

    # phase 1: only s1 (open index, discover detail URL) -- stop as soon as it is completed
    n = await _tick_until(loop1, "plan-workflow-c", lambda p: p.get_step("s1").status == "completed")
    assert n is not None, "s1 never completed"
    p1 = loop1._plan_store.get("plan-workflow-c")
    assert p1.get_step("s2").status == "planned" and p1.status == "active"
    assert p1.get_step("s1").actual_outcome["result"]["fields"]["detail_url"] == site.base + GROUND_TRUTH["detail_path"]
    assert site.hits == ["/"], "only the index may have been fetched before the interruption"

    # interruption: throw the whole loop away; nothing but the plan file survives
    del loop1
    loop2 = _loop(tmp_path, monkeypatch, plans_file)
    reloaded = loop2._plan_store.get("plan-workflow-c")
    assert reloaded.get_step("s1").status == "completed" and reloaded.get_step("s2").status == "planned"

    # phase 2: follow the persisted URL, extract, verify
    n2 = await _tick_until(loop2, "plan-workflow-c", lambda p: p.status == "completed")
    assert n2 is not None, "plan did not complete after the restart"
    final = loop2._plan_store.get("plan-workflow-c")
    assert all(s.status == "completed" for s in final.steps)
    assert site.hits == ["/", GROUND_TRUTH["detail_path"]]

    evidence = final.get_step("s2").actual_outcome["result"]
    assert evidence["fields"] == {"customer": GROUND_TRUTH["customer"], "total": GROUND_TRUTH["total"]}
    assert evidence["url"] == site.base + GROUND_TRUTH["detail_path"] and evidence["http_status"] == 200
    assert final.get_step("s2").actual_outcome["verification_passed"] is True

    # independent check: read the page ourselves (not through VECTOR) and confirm the evidence is really on it
    raw = urllib.request.urlopen(evidence["url"], timeout=10).read().decode()
    assert GROUND_TRUTH["customer"] in raw and GROUND_TRUTH["total"] in raw
    import hashlib
    assert hashlib.sha256(raw.encode()).hexdigest() == evidence["content_sha256"]


@pytest.mark.asyncio
async def test_wrong_page_content_fails_verification_instead_of_completing(
    isolated_vector_db, web_registry, site, tmp_path, monkeypatch,
):
    """The page is fetched fine (status ok) but the customer is not the one the plan expects: the step must FAIL, the plan
    must not complete, and the run must not count it as success."""
    site.customer = "Someone Else Ltd"
    loop = _loop(tmp_path, monkeypatch, tmp_path / "plans.json")
    loop._plan_store.add(_plan(site.base))
    await _tick_until(loop, "plan-workflow-c", lambda p: p.status != "active")
    final = loop._plan_store.get("plan-workflow-c")
    s2 = final.get_step("s2")
    assert s2.status != "completed", "a step whose evidence does not match must never complete"
    assert s2.actual_outcome["verification_passed"] is False and s2.actual_outcome["status"] == "executed"
    # ...and no LLM may restructure the plan around the failed check: it is abandoned with the failure on record
    assert final.status == "failed" and s2.status == "failed"
    assert [e.type for e in final.events][-1] == "abandoned" and "objective verification" in final.events[-1].message
    assert [s.id for s in final.steps] == ["s1", "s2"], "the failed step must not be replaced by invented steps"


@pytest.mark.asyncio
async def test_private_targets_are_refused_when_not_explicitly_allowed(
    isolated_vector_db, web_registry, site, tmp_path, monkeypatch,
):
    monkeypatch.delenv("VECTOR_WEB_EXTRACT_ALLOW_PRIVATE")
    loop = _loop(tmp_path, monkeypatch, tmp_path / "plans.json")
    loop._plan_store.add(_plan(site.base))
    await _tick_until(loop, "plan-workflow-c", lambda p: p.get_step("s1").status in ("failed", "completed"), budget=6)
    s1 = loop._plan_store.get("plan-workflow-c").get_step("s1")
    assert s1.status == "failed" and "SSRF" in (s1.reason or "") + str((s1.actual_outcome or {}).get("result", {}))
    assert site.hits == [], "the guard must stop the request before it reaches the private host"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
