"""
VECTOR SEO Portfolio — multi-site SEO portfolio management.

Manages a portfolio of websites for VECTOR's autonomous SEO operations:
  - Site registration and profiling
  - Priority scoring (urgency × business weight × opportunity)
  - Scheduled audit queue
  - State persistence (~/.vector/seo_portfolio/)

Absorbed from OpenClaw: runtime.py + portfolio_review.py + onboard_site.py
+ weekly_review.py + improve_page.py + bootstrap_site.py + site_id.py

Usage:
    portfolio = SEOPortfolio()
    portfolio.add_site("https://example.com", display_name="My Site")
    next_site = portfolio.next_to_audit()
    portfolio.record_audit(site_id, {"summary": "...", "open_issues": [...]})
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

_PORTFOLIO_DIR = Path.home() / ".vector" / "seo_portfolio"

SEVERITY_WEIGHTS = {
    "critical": 3.0,
    "warning":  1.5,
    "info":     0.5,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalize_site_id(site: str) -> str:
    """Convert 'https://example.com/' → 'example_com'."""
    site = site.strip().rstrip("/")
    if "://" in site:
        site = site.split("://", 1)[1]
    site = re.sub(r"^www\.", "", site)
    site = re.sub(r"[^a-zA-Z0-9]", "_", site).strip("_")
    return site[:60].lower()


# ── Site data model ───────────────────────────────────────────────────────────

def _make_site_record(
    site_url: str,
    display_name: str = "",
    business_weight: float = 1.0,
    cadence: str = "weekly",
    cms: Optional[str] = None,
) -> dict:
    site_id = _normalize_site_id(site_url)
    return {
        "schema_version": "1",
        "site_id": site_id,
        "canonical_url": site_url if "://" in site_url else f"https://{site_url}",
        "display_name": display_name or site_id,
        "business_weight": business_weight,
        "cadence": cadence,
        "cms": cms,
        "status": "active",
        "registered_at": _now(),
    }


def _site_priority(record: dict, latest_state: dict, goals: dict) -> tuple[float, dict]:
    open_issues = latest_state.get("open_issues", [])
    urgency = sum(
        SEVERITY_WEIGHTS.get(issue.get("severity", "warning"), 1.0)
        for issue in open_issues
    ) or 0.5
    active_goals = len(goals.get("active", [])) or 1
    business_weight = float(record.get("business_weight", 1.0))
    opportunity = 1.0 + (0.25 * min(active_goals, 4))
    score = round(business_weight * urgency * opportunity, 3)
    return score, {
        "site_id": record["site_id"],
        "display_name": record.get("display_name") or record["site_id"],
        "canonical_url": record.get("canonical_url", ""),
        "score": score,
        "open_issue_count": len(open_issues),
        "active_goal_count": len(goals.get("active", [])),
        "summary": latest_state.get("summary", "No state yet."),
        "top_issue": open_issues[0].get("title") if open_issues else None,
    }


# ── SEOPortfolio ──────────────────────────────────────────────────────────────

class SEOPortfolio:
    """
    VECTOR's multi-site SEO portfolio.
    Manages site registration, priority ranking, and audit history.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._root = base_dir or _PORTFOLIO_DIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._portfolio_path = self._root / "portfolio.json"
        self._schedule_path  = self._root / "schedule.json"
        self._bootstrap()

    def _bootstrap(self) -> None:
        if not self._portfolio_path.exists():
            _save(self._portfolio_path, {
                "schema_version": "1",
                "portfolio_id": "vector_seo",
                "sites": [],
                "created_at": _now(),
            })
        if not self._schedule_path.exists():
            _save(self._schedule_path, {"schema_version": "1", "upcoming": []})

    # ── Site management ───────────────────────────────────────────────────────

    def add_site(
        self,
        site_url: str,
        display_name: str = "",
        business_weight: float = 1.0,
        cadence: str = "weekly",
        cms: Optional[str] = None,
    ) -> str:
        record = _make_site_record(site_url, display_name, business_weight, cadence, cms)
        site_id = record["site_id"]

        # Ensure site directory
        site_dir = self._root / "sites" / site_id
        for subdir in ["audits", "issues", "goals"]:
            (site_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Update portfolio
        portfolio = _load(self._portfolio_path, {"sites": []})
        existing_ids = {s["site_id"] for s in portfolio.get("sites", [])}
        if site_id not in existing_ids:
            portfolio.setdefault("sites", []).append(record)
            _save(self._portfolio_path, portfolio)
            logger.info("[VECTOR][seo_portfolio] registered site: {} ({})", site_id, site_url)
        else:
            logger.info("[VECTOR][seo_portfolio] site already registered: {}", site_id)

        return site_id

    def list_sites(self) -> list[dict]:
        portfolio = _load(self._portfolio_path, {"sites": []})
        return portfolio.get("sites", [])

    def get_site(self, site_id: str) -> Optional[dict]:
        for site in self.list_sites():
            if site["site_id"] == site_id:
                return site
        return None

    def remove_site(self, site_id: str) -> bool:
        portfolio = _load(self._portfolio_path, {"sites": []})
        sites = portfolio.get("sites", [])
        new_sites = [s for s in sites if s["site_id"] != site_id]
        if len(new_sites) < len(sites):
            portfolio["sites"] = new_sites
            _save(self._portfolio_path, portfolio)
            logger.info("[VECTOR][seo_portfolio] removed site: {}", site_id)
            return True
        return False

    # ── Priority ranking ──────────────────────────────────────────────────────

    def rank_sites(self) -> list[dict]:
        """Rank all active sites by priority score (urgency × weight × opportunity)."""
        portfolio = _load(self._portfolio_path, {"sites": []})
        active = [s for s in portfolio.get("sites", []) if s.get("status", "active") == "active"]

        rankings = []
        for record in active:
            site_dir  = self._root / "sites" / record["site_id"]
            state     = _load(site_dir / "latest-state.json", {"summary": "No state.", "open_issues": []})
            goals     = _load(site_dir / "goals.json", {"active": [], "archived": []})
            score, summary = _site_priority(record, state, goals)
            rankings.append(summary)

        rankings.sort(key=lambda x: x["score"], reverse=True)
        return rankings

    def next_to_audit(self) -> Optional[dict]:
        """Return the highest-priority site that needs auditing."""
        rankings = self.rank_sites()
        return rankings[0] if rankings else None

    # ── Audit records ─────────────────────────────────────────────────────────

    def record_audit(
        self,
        site_id: str,
        audit_data: dict,
        issues: Optional[list[dict]] = None,
    ) -> str:
        """Save an audit result and update the site's latest state."""
        site_dir = self._root / "sites" / site_id
        site_dir.mkdir(parents=True, exist_ok=True)

        audit_ts = _now().replace(":", "-").replace("+", "")[:19]
        audit_id = f"audit_{audit_ts}"
        audit_path = site_dir / "audits" / f"{audit_id}.json"

        full_audit = {
            "id": audit_id,
            "site_id": site_id,
            "run_at": _now(),
            "data": audit_data,
            "issues": issues or [],
        }
        _save(audit_path, full_audit)

        # Update latest state
        state = {
            "schema_version": "1",
            "site_id": site_id,
            "updated_at": _now(),
            "summary": audit_data.get("summary", ""),
            "open_issues": issues or [],
            "last_audit_id": audit_id,
        }
        _save(site_dir / "latest-state.json", state)

        logger.info("[VECTOR][seo_portfolio] audit recorded for {}: {} issues", site_id, len(issues or []))
        return audit_id

    def get_audit_history(self, site_id: str, limit: int = 5) -> list[dict]:
        audit_dir = self._root / "sites" / site_id / "audits"
        if not audit_dir.exists():
            return []
        files = sorted(audit_dir.glob("*.json"), reverse=True)[:limit]
        return [_load(f, {}) for f in files]

    # ── Goals ─────────────────────────────────────────────────────────────────

    def add_goal(
        self,
        site_id: str,
        goal_type: str = "grow_organic_clicks",
        metric: str = "clicks_28d",
        target_delta: float = 0.2,
    ) -> str:
        site_dir  = self._root / "sites" / site_id
        site_dir.mkdir(parents=True, exist_ok=True)
        goals = _load(site_dir / "goals.json", {"active": [], "archived": []})
        goal_id = f"goal_{site_id}_{len(goals['active'])+1:03d}"
        goals["active"].append({
            "id": goal_id,
            "type": goal_type,
            "metric": metric,
            "target_delta": target_delta,
            "created_at": _now(),
            "status": "active",
        })
        _save(site_dir / "goals.json", goals)
        logger.info("[VECTOR][seo_portfolio] goal added: {} for {}", goal_id, site_id)
        return goal_id

    def portfolio_summary(self) -> dict:
        rankings = self.rank_sites()
        return {
            "site_count": len(rankings),
            "generated_at": _now(),
            "rankings": rankings,
            "top_priority": rankings[0] if rankings else None,
        }


if __name__ == "__main__":
    import tempfile, os
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        portfolio = SEOPortfolio(base_dir=Path(tmp))

        sid = portfolio.add_site("https://example.com", display_name="Example", business_weight=2.0)
        assert sid == "example_com"

        sites = portfolio.list_sites()
        assert len(sites) == 1
        assert sites[0]["display_name"] == "Example"

        portfolio.record_audit(sid, {"summary": "Good site"}, issues=[
            {"title": "Slow LCP", "severity": "warning"}
        ])

        rankings = portfolio.rank_sites()
        assert rankings[0]["site_id"] == "example_com"

        goal_id = portfolio.add_goal(sid, goal_type="grow_organic_clicks")
        assert goal_id.startswith("goal_")

    print("OK portfolio.py — SEOPortfolio works (register, rank, audit, goals)")
