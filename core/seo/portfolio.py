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

__all__ = [
    "SEOPortfolio",
    "SEVERITY_WEIGHTS",
]


import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from core.memory.db_utils import configured_db_path

_PORTFOLIO_DIR = configured_db_path().parent / "seo_portfolio"

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


def _safe_site_id(site_id: str, root: Path) -> Path:
    """Confine site_id to root/sites/<site_id>, rejecting any traversal.

    record_audit()/add_goal()/get_audit_history()/record_followup_metrics()
    all build a file path directly from a caller-supplied site_id with no
    confinement check -- legitimate site_ids only ever come from
    _normalize_site_id() (which already strips to [a-zA-Z0-9_]), but these
    methods trusted that invariant rather than enforcing it. Both current
    real callers happen to validate site_id via get_site() first (which
    only matches an already-registered, already-normalized id), so this
    isn't reachable today -- hardened anyway at the primitive level, same
    bar as this cycle's other narrow/no-current-exploit-path confinement
    fixes (worktree.py, direct_executor.py).
    """
    site_dir = (root / "sites" / site_id).resolve()
    if not site_dir.is_relative_to((root / "sites").resolve()):
        raise ValueError(f"invalid site_id: {site_id!r}")
    return site_dir


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
        site_dir = _safe_site_id(site_id, self._root)
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
        try:
            audit_dir = _safe_site_id(site_id, self._root) / "audits"
        except ValueError:
            return []
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
        site_dir  = _safe_site_id(site_id, self._root)
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

    # ── Follow-up system (score_feedback + hydrate + record + followups_due) ────

    def schedule_followup(
        self,
        site_id: str,
        action_id: str,
        due_at: str,
        primary_metric: str = "organic_clicks_28d",
        primary_direction: str = "higher_better",
        success_threshold_pct: float = 0.1,
        notes: str = "",
    ) -> str:
        """Schedule a follow-up check for an action. Returns item_id."""
        import uuid
        item_id = str(uuid.uuid4())[:12]
        item = {
            "item_id": item_id,
            "site_id": site_id,
            "action_id": action_id,
            "due_at": due_at,
            "primary_metric": primary_metric,
            "primary_direction": primary_direction,
            "success_threshold_pct": success_threshold_pct,
            "notes": notes,
            "status": "pending",
            "created_at": _now(),
            "baseline_metrics": {},
            "observed_metrics": {},
        }
        schedule = _load(self._schedule_path, {"upcoming": []})
        schedule.setdefault("upcoming", []).append(item)
        _save(self._schedule_path, schedule)

        # Also write to site queue
        site_dir = _safe_site_id(site_id, self._root) / "queue"
        site_dir.mkdir(parents=True, exist_ok=True)
        _save(site_dir / f"{item_id}.json", item)

        logger.info("[VECTOR][seo_portfolio] followup scheduled: {} due={}", item_id, due_at)
        return item_id

    def get_due_followups(self, as_of: str | None = None) -> list[dict]:
        """Return all follow-up items that are due now (or by as_of timestamp)."""
        from datetime import datetime, timezone
        cutoff_str = as_of or _now()
        cutoff = datetime.fromisoformat(cutoff_str.replace("Z", "+00:00"))

        schedule = _load(self._schedule_path, {"upcoming": []})
        due = []
        for item in schedule.get("upcoming", []):
            if item.get("status") in ("done", "processed"):
                continue
            due_at_str = item.get("due_at", "")
            if not due_at_str:
                continue
            try:
                due_at = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
                if due_at <= cutoff:
                    due.append(item)
            except ValueError:
                pass
        return due

    def record_followup_metrics(
        self,
        item_id: str,
        site_id: str,
        observed_metrics: dict[str, float],
        baseline_metrics: dict[str, float] | None = None,
    ) -> None:
        """Record observed metrics for a follow-up item."""
        try:
            site_queue = _safe_site_id(site_id, self._root) / "queue"
        except ValueError:
            logger.warning("[VECTOR][seo_portfolio] invalid site_id: {}", site_id)
            return
        item_path = (site_queue / f"{item_id}.json").resolve()
        if not item_path.is_relative_to(site_queue.resolve()):
            logger.warning("[VECTOR][seo_portfolio] invalid item_id: {}", item_id)
            return
        if not item_path.exists():
            logger.warning("[VECTOR][seo_portfolio] followup not found: {}", item_id)
            return
        item = _load(item_path, {})
        item["observed_metrics"] = {**item.get("observed_metrics", {}), **observed_metrics}
        if baseline_metrics:
            item["baseline_metrics"] = {**item.get("baseline_metrics", {}), **baseline_metrics}
        item["updated_at"] = _now()
        _save(item_path, item)

        # Update schedule entry
        schedule = _load(self._schedule_path, {"upcoming": []})
        for entry in schedule.get("upcoming", []):
            if entry.get("item_id") == item_id:
                entry.update(item)
                break
        _save(self._schedule_path, schedule)

    def score_followup(self, item: dict) -> dict:
        """
        Score a follow-up outcome from before/after metrics.
        Returns {outcome: 'success'|'regression'|'inconclusive', primary_change, details}.
        """
        baseline = item.get("baseline_metrics") or {}
        observed = item.get("observed_metrics") or {}
        primary_metric = item.get("primary_metric")
        primary_direction = item.get("primary_direction", "higher_better")
        threshold = float(item.get("success_threshold_pct", 0.1))

        if not primary_metric or primary_metric not in baseline or primary_metric not in observed:
            return {"outcome": "inconclusive", "reason": f"missing data for {primary_metric}"}

        before = float(baseline[primary_metric])
        after  = float(observed[primary_metric])

        if before == 0:
            raw_change = 1.0 if after > 0 else 0.0
        else:
            raw_change = (after - before) / abs(before)

        # For "lower_better" metrics (e.g. CPC, bounce rate), invert direction
        primary_change = -raw_change if primary_direction == "lower_better" else raw_change

        if primary_change >= threshold:
            outcome = "success"
        elif primary_change <= -threshold:
            outcome = "regression"
        else:
            outcome = "inconclusive"

        return {
            "outcome": outcome,
            "primary_metric": primary_metric,
            "before": before,
            "after": after,
            "primary_change_pct": round(primary_change * 100, 1),
            "threshold_pct": round(threshold * 100, 1),
        }

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
