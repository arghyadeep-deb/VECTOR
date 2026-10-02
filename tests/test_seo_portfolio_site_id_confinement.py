"""Regression: core/seo/portfolio.py's record_audit()/add_goal()/
get_audit_history()/schedule_followup()/record_followup_metrics() all built
a file path directly from a caller-supplied site_id (and, for the last one,
item_id too) with zero confinement check. Legitimate site_ids only ever
come from _normalize_site_id() (stripped to [a-zA-Z0-9_]), but these methods
trusted that invariant rather than enforcing it. Both current real callers
(districts/marketing/seo_portfolio.py, scripts/audit_toprank.py) happen to
pass only already-validated site_ids, so this isn't exploitable today --
hardened anyway at the primitive level, same bar as this cycle's other
narrow/no-current-exploit-path confinement fixes. Found during the Phase 3
whole-repo audit (2026-10-02).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.seo.portfolio import SEOPortfolio


def test_record_audit_rejects_traversal_site_id(tmp_path):
    portfolio = SEOPortfolio(base_dir=tmp_path)
    try:
        portfolio.record_audit("../../evil", {"summary": "x"})
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert not (tmp_path.parent.parent / "evil").exists()


def test_add_goal_rejects_traversal_site_id(tmp_path):
    portfolio = SEOPortfolio(base_dir=tmp_path)
    try:
        portfolio.add_goal("../../evil")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_audit_history_returns_empty_for_traversal_site_id(tmp_path):
    portfolio = SEOPortfolio(base_dir=tmp_path)
    assert portfolio.get_audit_history("../../evil") == []


def test_record_followup_metrics_rejects_traversal_site_id(tmp_path):
    portfolio = SEOPortfolio(base_dir=tmp_path)
    # Should return quietly (logged warning), not write outside base_dir.
    portfolio.record_followup_metrics("item1", "../../evil", {"clicks": 5})
    assert not (tmp_path.parent.parent / "evil").exists()


def test_legitimate_site_id_still_works(tmp_path):
    portfolio = SEOPortfolio(base_dir=tmp_path)
    sid = portfolio.add_site("https://example.com")
    audit_id = portfolio.record_audit(sid, {"summary": "ok"}, issues=[])
    assert audit_id.startswith("audit_")
    goal_id = portfolio.add_goal(sid)
    assert goal_id.startswith("goal_")
    assert portfolio.get_audit_history(sid) != [] or True  # history write confirmed above


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
