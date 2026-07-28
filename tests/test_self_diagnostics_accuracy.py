"""Regression tests for two self-diagnostics that lied about VECTOR's own state.
Both were found on 2026-07-17 by dogfooding the HUD in a real browser and
reading VECTOR's own episodic-memory feed, where it was reporting nonsense
ABOUT ITSELF:

  1. api_health_check: "grade=F 2/8 endpoints OK" for a perfectly healthy API
     — the QA agent's api_tester called its own auth-gated endpoints with NO
     Authorization header (6x 401), plus two wrong paths (/goals, /districts
     404'd even WITH auth — real routes are /brain/goals, /city/districts),
     plus a POST body missing the required `text` field.

  2. analytics: "success_rate=0.0%" across 49k events forever — it counted the
     event TYPES 'task_completed'/'task_failed', of which the DB has exactly
     ZERO. The real outcome signal is `status=ok` inside governor_dispatch
     event content (~87% ok in practice).

These are cheap structural checks (no running server needed).
Run: python tests/test_self_diagnostics_accuracy.py   (or via pytest)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

ROOT = Path(__file__).parent.parent
API_TESTER = ROOT / "districts" / "qa" / "api_tester.py"
ANALYTICS = ROOT / "districts" / "data_analytics" / "analytics_reporter.py"


# ── api_tester ────────────────────────────────────────────────────────────────

def test_api_tester_sends_auth():
    src = API_TESTER.read_text(encoding="utf-8")
    assert "VECTOR_API_KEY" in src, "api_tester must read the API key"
    assert "_auth_headers" in src, "api_tester must build auth headers"
    # every httpx call in test_endpoint must pass headers
    fn = re.search(r"def test_endpoint\(.*?\n(?=    def )", src, re.S)
    assert fn, "could not find test_endpoint()"
    body = fn.group(0)
    # each httpx.<verb>(...) call line must carry headers= (match to end of the
    # logical line, not the first ')' — method.upper() has an inner paren).
    for line in body.splitlines():
        m = re.search(r"\br\s*=\s*httpx\.\w+\(", line)
        if m:
            assert "headers" in line, f"httpx call without auth headers: {line.strip()}"


def test_api_tester_uses_real_paths():
    src = API_TESTER.read_text(encoding="utf-8")
    suite = re.search(r"tests = \[(.*?)\]", src, re.S)
    assert suite, "could not find the endpoint suite"
    s = suite.group(1)
    # the bogus paths must be gone, the real ones present
    assert '"/goals"' not in s, "/goals is a 404 — must be /brain/goals"
    assert '"/districts"' not in s, "/districts is a 404 — must be /city/districts"
    assert "/brain/goals" in s and "/city/districts" in s
    # /command must carry a `text` field, not the old {"type":...}
    assert '"text"' in s, "/command test body must include the required `text` field"


# ── analytics_reporter ────────────────────────────────────────────────────────

def test_analytics_computes_success_from_status_not_phantom_event_types():
    src = ANALYTICS.read_text(encoding="utf-8")
    # must parse the status= field
    assert "_STATUS_RE" in src or "status=" in src, "analytics must read the status field"
    # must not compute success SOLELY from the never-emitted event types.
    # (back-compat additions of by_type.get(...) are fine, but the governor_dispatch
    # status parsing must be present.)
    assert "governor_dispatch" in src, (
        "success must be derived from governor_dispatch status, the real signal")


def test_analytics_success_rate_logic():
    """Exercise the real computation against synthetic events shaped like the
    live DB: governor_dispatch with status=ok/None/no_agents."""
    from districts.data_analytics.analytics_reporter import AnalyticsReporter
    events = (
        [{"event_type": "governor_dispatch", "source": "governor",
          "timestamp": "2026-07-17T10:00:00", "content": "type=x district=y status=ok"}] * 7
        + [{"event_type": "governor_dispatch", "source": "governor",
            "timestamp": "2026-07-17T10:00:00", "content": "type=x district=y status=no_agents"}] * 3
        + [{"event_type": "vault_write", "source": "reflection",
            "timestamp": "2026-07-17T10:00:00", "content": "wrote note"}] * 5
    )
    r = AnalyticsReporter.__new__(AnalyticsReporter)   # skip heavy __init__
    m = AnalyticsReporter.compute_activity_metrics(r, events)
    assert m["task_success_rate"] == 0.7, f"expected 0.7, got {m['task_success_rate']}"
    assert m["tasks_completed"] == 7
    # vault_write events must NOT be counted as task attempts
    assert m["total_events"] == 15


def main() -> bool:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"ok   {t.__name__}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} pass")
    return not failed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = main()
    print("✅ self-diagnostics accuracy OK" if ok else "❌ FAILED")
    raise SystemExit(0 if ok else 1)
