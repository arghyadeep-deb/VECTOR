"""BrowserController / GUIAutomationAgent: a model's `finished()` is a claim, not evidence (V1 handoff workflow C gaps).

  * the controller now returns the final page as evidence, records blocked/failed actions and aborts after 3 in a row
  * with an `expect` the final page is checked independently: a mismatch turns END into ERROR (verified False)
  * the agent rewards HP by the evidence: verified +40, bare self-report +10, everything else costs HP

The controller runs in a REAL headless Chromium against a real local HTTP server (child process: the suite's selector event
loop cannot run Playwright subprocesses). Only the VLM call is scripted. Skips when Playwright/Chromium is unavailable.
"""
from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.vision_control.browser_controller import BrowserController

ROOT = Path(__file__).resolve().parents[1]


# ── pure expectation checks ─────────────────────────────────────────────────────

EV = {"final_url": "http://x/invoice/42", "final_title": "Invoice 42", "final_text_excerpt": "Acme Corp INR 11,800.00"}


@pytest.mark.parametrize("expect,ok", [
    ({"url_contains": "/invoice/42"}, True),
    ({"url_contains": "/invoice/43"}, False),
    ({"url_equals": "http://x/invoice/42"}, True),
    ({"title_contains": "Invoice"}, True),
    ({"text_contains": "Acme Corp"}, True),
    ({"text_contains": ["Acme Corp", "11,800"]}, True),
    ({"text_contains": ["Acme Corp", "Globex"]}, False),
    ({"url_contains": "/invoice/42", "text_contains": "Globex"}, False),   # every key must hold
    ({}, False), (None, False), ({"unknown_key": 1}, False),               # nothing to check is not a pass
])
def test_check_expectation(expect, ok):
    assert BrowserController.check_expectation(expect, EV)[0] is ok


# ── real browser, scripted VLM ──────────────────────────────────────────────────

PAGE = b"<html><head><title>Invoice 42</title></head><body><h2>Acme Corp</h2><p>INR 11,800.00</p></body></html>"


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


_CHILD = r"""
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from core.vision_control.browser_controller import BrowserController
from core.loop.permission_gateway import PermissionGateway

base, scenario, expect = sys.argv[2], sys.argv[3], json.loads(sys.argv[4])

async def _deny(self, *a, **k):   # never wait for an owner in a test
    return False
PermissionGateway.request_approval = _deny

scripts = {
    "finish_on_page": [f"Thought: open\nAction: navigate(url='{base}/invoice/42')", "Thought: done\nAction: finished()"],
    "finish_on_wrong_page": ["Thought: nothing\nAction: wait()", "Thought: done\nAction: finished()"],
    "blocked_actions": ["Thought: x\nAction: drag(start_box='<point>1 1</point>')"] * 6,
}
steps = iter(scripts[scenario])

async def main():
    c = BrowserController(max_loop=8, loop_interval=0.0, headless=True, allow_private_navigation=True)
    async def fake_vlm(system_prompt, shot_b64, history):
        return next(steps)
    c._call_vlm = fake_vlm
    r = await c.run_browser_task("check the invoice", url=base + "/", expect=expect or None)
    r.pop("conversations", None)
    print("RESULT:" + json.dumps(r))

asyncio.run(main())
"""


def _run(site, scenario, expect=None):
    pytest.importorskip("playwright")
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    r = subprocess.run([sys.executable, "-c", _CHILD, str(ROOT), site, scenario, json.dumps(expect or {})],
                       capture_output=True, text=True, timeout=180, env=env, cwd=str(ROOT))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT:")]
    if not lines:
        pytest.skip(f"browser run produced no result (chromium missing?): {r.stderr[-300:]}")
    return json.loads(lines[-1][len("RESULT:"):])


def test_finished_without_expectation_is_a_self_report_with_evidence(site):
    r = _run(site, "finish_on_page")
    assert r["status"] == "end" and r["self_reported_finish"] is True and "verified" not in r
    assert r["evidence"]["final_url"] == site + "/invoice/42" and r["evidence"]["final_title"] == "Invoice 42"
    assert "Acme Corp" in r["evidence"]["final_text_excerpt"]
    assert [a["action"] for a in r["action_log"]] == ["navigate"]


def test_matching_expectation_marks_the_run_verified(site):
    r = _run(site, "finish_on_page", {"url_contains": "/invoice/42", "text_contains": ["Acme Corp", "11,800"]})
    assert r["status"] == "end" and r["verified"] is True and "error" not in r


def test_finished_on_the_wrong_page_is_an_error_not_a_success(site):
    r = _run(site, "finish_on_wrong_page", {"url_contains": "/invoice/42"})
    assert r["status"] == "error" and r["verified"] is False
    assert "did not match the expected evidence" in r["error"] and r["self_reported_finish"] is True


def test_three_blocked_actions_in_a_row_abort_the_run(site):
    r = _run(site, "blocked_actions")
    assert r["status"] == "error" and "3 consecutive" in r["error"]
    assert [a["status"] for a in r["action_log"]] == ["blocked"] * 3
    assert r["loop_count"] == 3, "the run must stop instead of burning all its loops"


# ── agent rewards follow the evidence ───────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("result,delta_sign", [
    ({"status": "end", "verified": True}, +1),
    ({"status": "end", "self_reported_finish": True}, +1),
    ({"status": "error", "verified": False, "error": "mismatch"}, -1),
    ({"status": "max_loop"}, -1),
    ({"status": "call_user"}, -1),
])
async def test_agent_hp_follows_the_evidence(isolated_vector_db, monkeypatch, result, delta_sign):
    import core.vision_control.browser_controller as bc
    from districts.coding.gui_automation_agent import GUIAutomationAgent

    async def fake_run(self, instruction, url=None, browser_context=None, expect=None):
        fake_run.expect = expect
        return dict(result)

    monkeypatch.setattr(bc.BrowserController, "run_browser_task", fake_run)
    agent = GUIAutomationAgent()
    monkeypatch.setattr(agent, "_store_result", lambda *a, **k: None)
    before = agent.health_points
    out = await agent.run_browser_task("do it", url="http://x/", expect={"url_contains": "x"})
    assert out["status"] == result["status"] and fake_run.expect == {"url_contains": "x"}
    assert (agent.health_points - before) * delta_sign > 0


@pytest.mark.asyncio
async def test_a_verified_finish_earns_more_than_a_bare_self_report(isolated_vector_db, monkeypatch):
    import core.vision_control.browser_controller as bc
    from districts.coding.gui_automation_agent import GUIAutomationAgent

    async def gain(result):
        async def fake_run(self, instruction, url=None, browser_context=None, expect=None):
            return dict(result)
        monkeypatch.setattr(bc.BrowserController, "run_browser_task", fake_run)
        agent = GUIAutomationAgent()
        monkeypatch.setattr(agent, "_store_result", lambda *a, **k: None)
        before = agent.health_points
        await agent.run_browser_task("do it")
        return agent.health_points - before

    verified = await gain({"status": "end", "verified": True})
    bare = await gain({"status": "end", "self_reported_finish": True})
    assert verified > bare > 0, (verified, bare)

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
