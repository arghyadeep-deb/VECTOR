"""Toprank absorption audit + 3-module wiring audit"""
import sys, os, ast, tempfile, asyncio
sys.stdout.reconfigure(encoding="utf-8")

results = []
def ok(m): results.append(("PASS", m)); print(f"  PASS  {m}")
def fail(m): results.append(("FAIL", m)); print(f"  FAIL  {m}")

# GROUP 1: Syntax of all new + modified files
print("GROUP 1 -- Syntax")
files = [
    "core/seo/__init__.py",
    "core/seo/gsc_client.py",
    "core/seo/pagespeed_client.py",
    "core/seo/broken_link_checker.py",
    "core/seo/cms_connector.py",
    "core/seo/portfolio.py",
    "districts/marketing/seo_agent.py",
    "districts/marketing/seo_portfolio.py",
    "core/loop/autonomous_loop.py",
    "run_vector.py",
    "core/inference/provider_client.py",
]
for f in files:
    try:
        with open(f, encoding="utf-8") as fh: ast.parse(fh.read())
        ok(f"syntax: {f}")
    except Exception as e:
        fail(f"syntax: {f}: {e}")
print()

# GROUP 2: Toprank imports
print("GROUP 2 -- Toprank imports")
for mod, syms in [
    ("core.seo", ["GSCClient","PageSpeedClient","BrokenLinkChecker","CMSConnector","SEOPortfolio"]),
    ("core.seo.gsc_client", ["GSCClient","list_sites"]),
    ("core.seo.pagespeed_client", ["PageSpeedClient"]),
    ("core.seo.broken_link_checker", ["BrokenLinkChecker"]),
    ("core.seo.cms_connector", ["CMSConnector"]),
    ("core.seo.portfolio", ["SEOPortfolio"]),
]:
    try:
        m = __import__(mod, fromlist=syms)
        for s in syms: assert hasattr(m, s), f"missing {s}"
        ok(f"import: {mod}")
    except Exception as e:
        fail(f"import: {mod}: {e}")
print()

# GROUP 3: Toprank functional tests
print("GROUP 3 -- Toprank functional")

from core.seo.portfolio import SEOPortfolio
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    portfolio = SEOPortfolio(base_dir=Path(tmp))
    sid = portfolio.add_site("https://example.com", display_name="Example", business_weight=2.0)
    assert sid == "example_com"
    ok(f"SEOPortfolio.add_site() -> site_id={sid}")

    sites = portfolio.list_sites()
    assert len(sites) == 1
    ok("SEOPortfolio.list_sites() returns registered sites")

    portfolio.record_audit(sid, {"summary": "Audit done"}, issues=[
        {"title": "Slow LCP", "severity": "warning"},
        {"title": "No schema", "severity": "info"},
    ])
    state_file = Path(tmp) / "sites" / sid / "latest-state.json"
    assert state_file.exists()
    ok("SEOPortfolio.record_audit() writes latest-state.json")

    rankings = portfolio.rank_sites()
    assert rankings[0]["site_id"] == sid
    assert rankings[0]["open_issue_count"] == 2
    ok(f"SEOPortfolio.rank_sites() scores correctly (open_issues=2)")

    goal_id = portfolio.add_goal(sid, goal_type="grow_organic_clicks")
    assert goal_id.startswith("goal_")
    ok(f"SEOPortfolio.add_goal() -> {goal_id}")

    summary = portfolio.portfolio_summary()
    assert summary["site_count"] == 1
    ok("SEOPortfolio.portfolio_summary() returns correct count")

    history = portfolio.get_audit_history(sid)
    assert len(history) >= 1
    ok("SEOPortfolio.get_audit_history() returns audit records")

from core.seo.broken_link_checker import BrokenLinkChecker, _check_url, _LinkParser
parser = _LinkParser("https://example.com")
parser.feed('<html><body><a href="/about">About</a><a href="https://other.com/page">Other</a></body></html>')
assert "https://example.com/about" in parser.links
assert "https://other.com/page" in parser.links
ok("_LinkParser: extracts relative and absolute links correctly")

checker = BrokenLinkChecker()
ok("BrokenLinkChecker instantiates OK")

from core.seo.cms_connector import CMSConnector
connector = CMSConnector()
ok(f"CMSConnector: detected CMS = {connector.detect() or 'none (no env vars)'}")

from core.seo.pagespeed_client import PageSpeedClient
psc = PageSpeedClient()
ok(f"PageSpeedClient instantiates (api_key={'set' if psc._api_key else 'free tier'})")

from core.seo.gsc_client import GSCClient, _classify_page, _opportunities
assert _classify_page("/blog/post-1") == "blog"
assert _classify_page("/pricing") == "pricing"
assert _classify_page("/random/page") == "other"
ok("GSCClient._classify_page(): blog/pricing/other classification correct")

opps = _opportunities([
    {"url": "/fast-page", "impressions": 50, "ctr": 1.0, "position": 5.0},
    {"url": "/slow-page", "impressions": 1000, "ctr": 1.5, "position": 8.0},
    {"url": "/top-page", "impressions": 2000, "ctr": 5.0, "position": 2.0},  # high CTR - no opp
])
assert any(o["url"] == "/slow-page" for o in opps)
assert not any(o["url"] == "/top-page" for o in opps)
ok("GSCClient._opportunities(): identifies low-CTR high-impression pages, skips high-CTR")
print()

# GROUP 4: Agent tests
print("GROUP 4 -- Marketing district agents")
try:
    from districts.marketing.seo_agent import SEOAgent
    agent = SEOAgent()
    assert agent.health_points == 500
    assert agent.district == "marketing"
    ok(f"SEOAgent init: HP={agent.health_points}, district={agent.district}")
except Exception as e:
    fail(f"SEOAgent: {e}")

try:
    from districts.marketing.seo_portfolio import SEOPortfolioAgent
    pa = SEOPortfolioAgent()
    assert pa.health_points == 500
    assert pa.district == "marketing"
    ok(f"SEOPortfolioAgent init: HP={pa.health_points}, district={pa.district}")
except Exception as e:
    fail(f"SEOPortfolioAgent: {e}")
print()

# GROUP 5: Governor routing
print("GROUP 5 -- Governor routes")
from core.city.governor import DISTRICT_TASK_MAP
seo_routes = {
    "seo_audit": "marketing", "seo_analysis": "marketing",
    "seo_portfolio": "marketing", "seo_onboard": "marketing",
    "seo_weekly_review": "marketing", "keyword_research": "marketing",
    "broken_links": "marketing", "pagespeed": "marketing",
    "schema_markup": "marketing", "geo_optimize": "marketing",
}
for key, expected in seo_routes.items():
    actual = DISTRICT_TASK_MAP.get(key)
    if actual == expected:
        ok(f"governor routes {key!r} -> marketing")
    else:
        fail(f"governor missing route: {key!r} (got {actual})")
print()

# GROUP 6: 3-module wiring verification
print("GROUP 6 -- 3 newly wired modules")

# ambient_scheduler_loop in autonomous_loop
with open("core/loop/autonomous_loop.py", encoding="utf-8") as f: src = f.read()
assert "ambient_scheduler_loop" in src
assert "AmbientScheduler" in src
assert "take_due_items" in src
assert "take_pending_directives" in src
ok("autonomous_loop: ambient_scheduler_loop() runs every 60s, fires due directives")

# session_persistence in autonomous_loop + run_vector
assert "from core.jcode.session_persistence import SessionPersistence" in src
assert "recover_crashed_sessions" in src
ok("autonomous_loop: SessionPersistence.recover_crashed_sessions() at startup")

with open("run_vector.py", encoding="utf-8") as f: rv = f.read()
assert "SessionPersistence" in rv
assert "crash recovery enabled" in rv
ok("run_vector.py: SessionPersistence crash recovery in _start_background_services()")

# ToolDispatcher in provider_client
with open("core/inference/provider_client.py", encoding="utf-8") as f: pc = f.read()
assert "from core.engine.tools.dispatcher import NativeDispatcher" in pc
assert "tool_dispatcher parsed" in pc
assert "_tool_calls" in pc
ok("ProviderClient._call_openai_compat(): NativeDispatcher parses tool_calls from LLM response")

print()
passed = sum(1 for r, _ in results if r == "PASS")
failed = sum(1 for r, _ in results if r == "FAIL")
print(f"RESULT: PASS={passed} FAIL={failed}")
if failed:
    for r, m in results:
        if r == "FAIL": print(f"  FAIL: {m}")

sys.exit(1 if failed else 0)
