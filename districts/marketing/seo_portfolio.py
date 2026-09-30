"""
VECTOR SEOPortfolioAgent — District 19: marketing
Multi-site SEO portfolio management: onboard sites, run scheduled audits,
surface the highest-priority site for weekly review, track goals.

Absorbed from OpenClaw: portfolio_review, weekly_review, improve_page,
investigate_drop, onboard_site, persist_run, score_feedback.

Governor routes: seo_portfolio, seo_onboard, seo_weekly_review,
                 seo_improve_page, seo_portfolio_review, seo_investigate_drop

Usage:
    agent = SEOPortfolioAgent()
    asyncio.run(agent.onboard_site("https://mysite.com"))
    asyncio.run(agent.run_portfolio_review())
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger
from districts.marketing._skill_loader import load_skill, SkillMixin


class SEOPortfolioAgent(AgentBase, SkillMixin):
    """
    VECTOR's SEO portfolio manager.
    Orchestrates multi-site SEO operations using the SEOPortfolio and SEOAgent.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SEOPortfolioAgent",
            district="marketing",
            generation=generation,
        )
        self.capabilities = ["improve_page", "investigate_drop", "marketing", "onboard", "portfolio", "portfolio_review", "seo", "weekly_review"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._skill_prompt = load_skill("seo-audit", "ai-seo")
        logger.info("[VECTOR][seo_portfolio] ready gen={} hp={}", generation, self.health_points)

    def _get_portfolio(self):
        from core.seo.portfolio import SEOPortfolio
        return SEOPortfolio()

    # ── Site management ───────────────────────────────────────────────────────

    async def onboard_site(
        self,
        site_url: str,
        display_name: str = "",
        business_weight: float = 1.0,
        cadence: str = "weekly",
        cms: str | None = None,
    ) -> dict:
        """Register a new site in the SEO portfolio."""
        portfolio = self._get_portfolio()
        site_id = portfolio.add_site(
            site_url=site_url,
            display_name=display_name or site_url,
            business_weight=business_weight,
            cadence=cadence,
            cms=cms,
        )
        portfolio.add_goal(site_id, goal_type="grow_organic_clicks")

        self._memory.store(
            event_type="seo_site_onboarded",
            content=f"SEO portfolio: onboarded {site_url} (id={site_id})",
            tags=["seo", "portfolio", "onboard"],
            source="seo_portfolio_agent",
        )
        self.award_points(20, f"onboarded: {site_url}")
        logger.info("[VECTOR][seo_portfolio] onboarded: {} → {}", site_url, site_id)
        return {"status": "ok", "site_id": site_id, "site_url": site_url}

    # ── Portfolio review ──────────────────────────────────────────────────────

    async def run_portfolio_review(self) -> dict:
        """Rank all sites by priority and return the one that needs attention most."""
        portfolio = self._get_portfolio()
        summary = portfolio.portfolio_summary()
        top = summary.get("top_priority")

        if not top:
            return {"status": "ok", "message": "No sites in portfolio. Add sites with onboard_site()."}

        self._memory.store(
            event_type="seo_portfolio_review",
            content=f"Portfolio review: top={top.get('display_name')} score={top.get('score')}",
            tags=["seo", "portfolio", "review"],
            source="seo_portfolio_agent",
        )
        self.award_points(15, "portfolio review")
        return {
            "status": "ok",
            "site_count": summary["site_count"],
            "top_priority": top,
            "all_rankings": summary["rankings"],
            "recommendation": f"Run weekly review for: {top.get('display_name', top.get('site_id'))}",
        }

    # ── Weekly review ─────────────────────────────────────────────────────────

    async def run_weekly_review(self, site_id: str | None = None) -> dict:
        """
        Run a full SEO audit for the highest-priority site (or specified site).
        Records results and updates portfolio state.
        """
        portfolio = self._get_portfolio()

        if not site_id:
            rankings = portfolio.rank_sites()
            if not rankings:
                return {"status": "error", "error": "No sites in portfolio"}
            site_id = rankings[0]["site_id"]

        site = portfolio.get_site(site_id)
        if not site:
            return {"status": "error", "error": f"Site not found: {site_id}"}

        site_url = site.get("canonical_url", site_id)
        logger.info("[VECTOR][seo_portfolio] weekly review: {}", site_url)

        # Run full audit via SEOAgent
        from districts.marketing.seo_agent import SEOAgent
        seo = SEOAgent()
        audit = await seo.full_audit(site_url, days=28)

        # Record in portfolio
        issues = audit.get("issues", [])
        audit_id = portfolio.record_audit(site_id, audit, issues=issues)

        self._memory.store(
            event_type="seo_weekly_review",
            content=f"Weekly review {site_url}: {len(issues)} issues, audit={audit_id}",
            tags=["seo", "weekly", "audit"],
            source="seo_portfolio_agent",
        )
        self.award_points(40, f"weekly review: {site_url}")

        return {
            "status": "ok",
            "site_id": site_id,
            "site_url": site_url,
            "audit_id": audit_id,
            "issue_count": len(issues),
            "summary": audit.get("summary", ""),
            "top_issue": issues[0] if issues else None,
        }

    # ── Page improvement ──────────────────────────────────────────────────────

    async def improve_page(self, site_id: str, page_url: str) -> dict:
        """Deep-dive analysis on a single page to find improvement opportunities."""
        portfolio = self._get_portfolio()
        site = portfolio.get_site(site_id)
        if not site:
            return {"status": "error", "error": f"Site not found: {site_id}"}

        logger.info("[VECTOR][seo_portfolio] improving page: {}", page_url)

        # PageSpeed for this specific page
        from core.seo.pagespeed_client import PageSpeedClient
        ps = PageSpeedClient()
        ps_data = await ps.analyze(page_url)

        # Scrape and analyze content
        content = ""
        try:
            from core.scraper.vector_scraper import get_scraper
            scraper = get_scraper()
            result = await scraper.smart_fetch(page_url)
            content = result.markdown or result.content[:3000]
        except Exception as e:
            logger.debug("[VECTOR][seo_portfolio] scrape failed: {}", e)

        # LLM analysis
        from districts.marketing.seo_agent import SEOAgent
        seo = SEOAgent()
        geo_result = await seo.optimize_for_ai_search(page_url, content)

        return {
            "status": "ok",
            "page_url": page_url,
            "pagespeed": ps_data,
            "geo_optimization": geo_result,
            "content_preview": content[:500] if content else "",
        }

    # ── Drop investigation ────────────────────────────────────────────────────

    async def investigate_drop(self, site_id: str, days: int = 28) -> dict:
        """Investigate a traffic drop by comparing recent vs prior period GSC data."""
        portfolio = self._get_portfolio()
        site = portfolio.get_site(site_id)
        if not site:
            return {"status": "error", "error": f"Site not found: {site_id}"}

        site_url = site.get("canonical_url", site_id)
        logger.info("[VECTOR][seo_portfolio] investigating drop: {}", site_url)

        # Fetch two periods
        from core.seo.gsc_client import GSCClient
        client = GSCClient()

        try:
            recent = await client.fetch_and_analyze(site_url, days=days)
            prior  = await client.fetch_and_analyze(site_url, days=days * 2)
        except Exception as e:
            return {"status": "error", "error": f"GSC fetch failed: {e}"}

        # Compare totals
        recent_clicks = recent.get("summary", {}).get("total_clicks", 0)
        prior_clicks  = prior.get("summary", {}).get("total_clicks", 0) / 2  # normalize to same period

        delta_pct = ((recent_clicks - prior_clicks) / max(prior_clicks, 1)) * 100

        # LLM diagnosis
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Investigate this organic traffic drop for {site_url}:\n"
                f"Recent period ({days}d): {recent_clicks} clicks\n"
                f"Prior period ({days}d avg): {prior_clicks:.0f} clicks\n"
                f"Delta: {delta_pct:+.1f}%\n\n"
                f"Top pages losing traffic: {str(recent.get('top_pages', [])[:5])[:300]}\n\n"
                "Diagnose: algorithm update, technical issues, content decay, "
                "seasonality, or competition? Provide 3 specific investigation steps."
            )
            diagnosis = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=30.0,
            )
        except Exception:
            diagnosis = f"Traffic delta: {delta_pct:+.1f}%. Manual investigation needed."

        self.award_points(30, f"drop investigation: {site_url}")
        return {
            "status": "ok",
            "site_url": site_url,
            "recent_clicks": recent_clicks,
            "prior_avg_clicks": round(prior_clicks),
            "delta_pct": round(delta_pct, 1),
            "diagnosis": diagnosis,
        }

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        action = task.get("type") or p.get("action", "portfolio_review")

        if action in ("portfolio_review", "seo_portfolio_review"):
            return await self.run_portfolio_review()
        elif action in ("onboard", "seo_onboard"):
            return await self.onboard_site(
                site_url=p.get("url", p.get("site", "")),
                display_name=p.get("display_name", ""),
                business_weight=float(p.get("business_weight", 1.0)),
                cadence=p.get("cadence", "weekly"),
                cms=p.get("cms"),
            )
        elif action in ("weekly_review", "seo_weekly_review"):
            return await self.run_weekly_review(site_id=p.get("site_id"))
        elif action in ("improve_page", "seo_improve_page"):
            return await self.improve_page(
                site_id=p.get("site_id", ""),
                page_url=p.get("url", ""),
            )
        elif action in ("investigate_drop", "seo_investigate_drop"):
            return await self.investigate_drop(
                site_id=p.get("site_id", ""),
                days=int(p.get("days", 28)),
            )

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branches above,
        # carrying a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). Route by keyword to whichever real capability the query
        # actually asks for and has the args for; default to
        # run_portfolio_review (takes no args) for a generic "how's our SEO
        # doing across sites" ask.
        query = (p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            q = query.lower()
            if ("onboard" in q or "add" in q and "site" in q) and p.get("url"):
                return await self.onboard_site(
                    site_url=p.get("url", p.get("site", "")), display_name=p.get("display_name", ""),
                    business_weight=float(p.get("business_weight", 1.0)), cadence=p.get("cadence", "weekly"),
                    cms=p.get("cms"),
                )
            if ("drop" in q or "decline" in q or "fell" in q) and p.get("site_id"):
                return await self.investigate_drop(site_id=p.get("site_id", ""), days=int(p.get("days", 28)))
            if ("improve" in q or "fix" in q) and p.get("site_id") and p.get("url"):
                return await self.improve_page(site_id=p.get("site_id", ""), page_url=p.get("url", ""))
            if "weekly" in q or "this week" in q:
                return await self.run_weekly_review(site_id=p.get("site_id"))
            return await self.run_portfolio_review()

        return {
            "status": "error",
            "error": f"unhandled type: {action}",
            "supported": [
                "portfolio_review",
                "seo_portfolio_review",
                "onboard",
                "seo_onboard",
                "weekly_review",
                "seo_weekly_review",
                "improve_page",
                "seo_improve_page",
                "investigate_drop",
                "seo_investigate_drop",
            ],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][seo_portfolio] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][seo_portfolio] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        import tempfile
        from pathlib import Path
        from core.seo.portfolio import SEOPortfolio

        agent = SEOPortfolioAgent()
        assert agent.health_points == 500
        assert agent.name == "SEOPortfolioAgent"
        assert agent.district == "marketing"

        # Test onboard via portfolio directly (no network needed)
        with tempfile.TemporaryDirectory() as tmp:
            portfolio = SEOPortfolio(base_dir=Path(tmp))
            sid = portfolio.add_site("https://vector.ai", display_name="VECTOR", business_weight=3.0)
            portfolio.add_goal(sid)
            summary = portfolio.portfolio_summary()
            assert summary["site_count"] == 1
            assert summary["top_priority"]["site_id"] == sid

        print(f"OK seo_portfolio.py HP={agent.health_points}")

    asyncio.run(_smoke())
