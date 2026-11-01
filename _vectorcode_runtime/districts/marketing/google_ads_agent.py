"""
VECTOR GoogleAdsAgent — District 19: marketing
AI-powered Google Ads analysis, audit, copy generation, and optimization.

Uses Google Ads API via Google Cloud credentials (same gcloud auth as GSC).
Policy rules and benchmarks embedded from toprank's policy-registry.json.

Governor routes: google_ads_audit, google_ads, google_ads_copy,
                 google_ads_landing, ads_performance, ads_keywords, ads_copy

Note: Real API access requires Google Ads Developer Token + OAuth credentials.
Without credentials, runs in analysis-only mode using LLM reasoning.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger
from districts.marketing._skill_loader import load_skill, SkillMixin


# ── Policy rules (absorbed from google-ads/shared/policy-registry.json) ──────

GOOGLE_ADS_POLICIES = {
    "auction-ad-rank-equation": "Ad Rank = f(Bid, Quality Score, Expected Impact of Extensions). Higher Ad Rank = better position.",
    "object-hierarchy": "Account > Campaign > Ad Group > Keyword/Ad. Budget set at campaign level.",
    "metric-definitions": "CTR = Clicks/Impressions. CPC = Cost/Clicks. CVR = Conversions/Clicks. ROAS = Revenue/Cost.",
    "quality-score-components": "Quality Score (1-10): Expected CTR (33%), Ad Relevance (33%), Landing Page Experience (33%).",
    "smart-bidding-tiers": "Maximize Clicks → Target CPA → Target ROAS → Maximize Conversions (in order of data maturity needed).",
    "impression-share-formula": "IS = Impressions / Eligible Impressions. Search Lost IS (Budget) + IS (Rank) = budget vs quality losses.",
    "search-term-match-types": "Broad Match: widest reach. Phrase Match: [+intent]. Exact Match: [=query]. Use all three strategically.",
    "negative-keyword-urgency": "Add negatives for: competitor brand terms, irrelevant queries, informational intent (how-to, what-is).",
    "keyword-bid-floor": "First Page Bid Estimate from Google. If below floor, keyword won't show on page 1.",
    "attribution-models": "Last Click (default), Data-Driven (recommended), Linear, Time Decay, Position-Based.",
}

# Industry ROAS benchmarks (from industry-templates.json)
INDUSTRY_BENCHMARKS = {
    "legal":          {"target_roas": 3.0, "avg_cpc_usd": 45.0, "avg_ctr_pct": 4.5},
    "home_services":  {"target_roas": 4.0, "avg_cpc_usd": 12.0, "avg_ctr_pct": 6.0},
    "healthcare":     {"target_roas": 3.5, "avg_cpc_usd": 8.0,  "avg_ctr_pct": 5.5},
    "ecommerce":      {"target_roas": 4.5, "avg_cpc_usd": 1.5,  "avg_ctr_pct": 3.0},
    "saas_b2b":       {"target_roas": 5.0, "avg_cpc_usd": 35.0, "avg_ctr_pct": 3.5},
    "education":      {"target_roas": 3.0, "avg_cpc_usd": 6.0,  "avg_ctr_pct": 5.0},
    "finance":        {"target_roas": 4.0, "avg_cpc_usd": 25.0, "avg_ctr_pct": 4.0},
    "real_estate":    {"target_roas": 5.0, "avg_cpc_usd": 20.0, "avg_ctr_pct": 4.5},
    "general":        {"target_roas": 3.5, "avg_cpc_usd": 3.0,  "avg_ctr_pct": 4.0},
}


class GoogleAdsAgent(AgentBase, SkillMixin):
    """
    VECTOR's Google Ads specialist.
    Audits accounts, analyzes performance, generates copy, and diagnoses quality issues.
    Uses LLM reasoning with embedded policy rules + Google Ads API when credentials set.
    Augmented with: ads, analytics skill prompts.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="GoogleAdsAgent",
            district="marketing",
            generation=generation,
        )
        self.capabilities = ["ads", "audit", "copy", "google_ads", "landing", "marketing", "performance"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._skill_prompt = load_skill("ads", "analytics")
        logger.info("[VECTOR][google_ads_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Account audit ─────────────────────────────────────────────────────────

    async def audit_account(
        self,
        account_id: str = "",
        industry: str = "general",
        business_context: str = "",
    ) -> dict:
        """Full Google Ads account health audit (7 dimensions)."""
        hydration = self._context.session_hydration_prompt()
        benchmarks = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS["general"])
        policies_text = "\n".join(f"- {k}: {v}" for k, v in GOOGLE_ADS_POLICIES.items())

        try:
            if os.environ.get("VECTOR_GOOGLE_ADS_LLM") != "1":
                raise RuntimeError("LLM disabled by default; set VECTOR_GOOGLE_ADS_LLM=1")
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Audit this Google Ads account for a {industry} business.\n"
                f"Account ID: {account_id or 'not provided'}\n"
                f"Business context: {business_context or 'not provided'}\n\n"
                f"Industry benchmarks:\n"
                f"  Target ROAS: {benchmarks['target_roas']}x\n"
                f"  Avg CPC: ${benchmarks['avg_cpc_usd']}\n"
                f"  Avg CTR: {benchmarks['avg_ctr_pct']}%\n\n"
                f"Policy rules to check:\n{policies_text}\n\n"
                "Audit across 7 dimensions:\n"
                "1. Campaign structure & hierarchy\n"
                "2. Keyword strategy & match types\n"
                "3. Bidding strategy alignment\n"
                "4. Quality Score health\n"
                "5. Ad copy effectiveness\n"
                "6. Landing page relevance\n"
                "7. Negative keyword coverage\n\n"
                "For each dimension: score (1-10), key issues, immediate actions.\n"
                "Output: structured JSON with dimension_scores, critical_issues, action_plan."
            )
            result = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=45.0,
            )
            if not result or not result.strip():
                raise RuntimeError("LLM returned empty response — Ollama may be offline")
        except Exception as e:
            logger.warning("[VECTOR][google_ads_agent] audit LLM failed: {}", e)
            result = "Audit unavailable — Ollama offline."

        self._memory.store(
            event_type="google_ads_audit",
            content=f"Google Ads audit: account={account_id} industry={industry}",
            tags=["google_ads", "audit", "marketing"],
            source="google_ads_agent",
        )
        self.award_points(40, f"google ads audit: {account_id}")
        return {"status": "ok", "account_id": account_id, "industry": industry,
                "benchmarks": benchmarks, "audit": result}

    # ── Ad copy generation ────────────────────────────────────────────────────

    async def generate_copy(
        self,
        product: str,
        target_keyword: str,
        usp: str = "",
        num_variants: int = 3,
    ) -> dict:
        """Generate RSA headlines and descriptions for Google Ads."""
        hydration = self._context.session_hydration_prompt()
        try:
            if os.environ.get("VECTOR_GOOGLE_ADS_LLM") != "1":
                raise RuntimeError("LLM disabled by default; set VECTOR_GOOGLE_ADS_LLM=1")
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Generate {num_variants} Google RSA (Responsive Search Ad) variants for:\n"
                f"Product/Service: {product}\n"
                f"Target keyword: {target_keyword}\n"
                f"Unique selling point: {usp or 'not specified'}\n\n"
                "RSA format rules:\n"
                "- 15 headlines (max 30 chars each), 4 descriptions (max 90 chars each)\n"
                "- Include keyword in at least 3 headlines\n"
                "- Use CTAs: 'Get Quote', 'Book Now', 'Start Free', 'Learn More'\n"
                "- Pin Headline 1 = brand/main keyword, Headline 2 = key benefit\n\n"
                "Output JSON: [{headlines: [...], descriptions: [...], ctr_estimate: 0.0}]"
            )
            result = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=30.0,
            )
            if not result or not result.strip():
                raise RuntimeError("LLM returned empty response — Ollama may be offline")
        except Exception as e:
            result = str(e)

        self.award_points(20, f"ad copy: {product}")
        return {"status": "ok", "product": product, "keyword": target_keyword, "copy": result}

    # ── Performance analysis ──────────────────────────────────────────────────

    async def analyze_performance(
        self,
        metrics: dict,
        industry: str = "general",
    ) -> dict:
        """Analyze campaign performance against industry benchmarks."""
        benchmarks = INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS["general"])
        hydration = self._context.session_hydration_prompt()

        # Compare key metrics to benchmarks
        issues = []
        ctr = metrics.get("ctr_pct", 0)
        cpc = metrics.get("cpc_usd", 0)
        roas = metrics.get("roas", 0)

        if ctr and ctr < benchmarks["avg_ctr_pct"] * 0.7:
            issues.append({"metric": "CTR", "value": ctr, "benchmark": benchmarks["avg_ctr_pct"],
                           "severity": "warning", "fix": "Improve ad relevance and Quality Score"})
        if roas and roas < benchmarks["target_roas"] * 0.8:
            issues.append({"metric": "ROAS", "value": roas, "benchmark": benchmarks["target_roas"],
                           "severity": "critical", "fix": "Optimize bidding strategy and conversion tracking"})
        if cpc and cpc > benchmarks["avg_cpc_usd"] * 1.5:
            issues.append({"metric": "CPC", "value": cpc, "benchmark": benchmarks["avg_cpc_usd"],
                           "severity": "warning", "fix": "Improve Quality Score or add negative keywords"})

        self.award_points(15, "google ads performance analysis")
        return {
            "status": "ok",
            "industry": industry,
            "benchmarks": benchmarks,
            "issues": issues,
            "score": max(0, 100 - len(issues) * 20),
        }

    # ── Landing page quality diagnosis ────────────────────────────────────────

    async def diagnose_landing_page(self, url: str, keyword: str) -> dict:
        """Score landing page relevance for a keyword (Quality Score component)."""
        # Fetch page content
        content = ""
        try:
            from core.scraper.vector_scraper import get_scraper
            scraper = get_scraper()
            result = await scraper.smart_fetch(url)
            content = result.markdown or result.content[:3000]
        except Exception as e:
            logger.debug("[VECTOR][google_ads_agent] scrape failed: {}", e)

        hydration = self._context.session_hydration_prompt()
        try:
            if os.environ.get("VECTOR_GOOGLE_ADS_LLM") != "1":
                raise RuntimeError("LLM disabled by default; set VECTOR_GOOGLE_ADS_LLM=1")
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Score this landing page for the keyword '{keyword}':\n"
                f"URL: {url}\n"
                f"Content preview: {content[:1000] or 'unavailable'}\n\n"
                "Quality Score Landing Page Experience factors:\n"
                "1. Keyword relevance (is keyword in H1, title, first paragraph?)\n"
                "2. Load speed (signals from URL/domain)\n"
                "3. Mobile friendliness\n"
                "4. Content transparency and trustworthiness\n"
                "5. Navigation ease and CTA clarity\n\n"
                "Output JSON: {score: 1-10, issues: [], fixes: [], qs_estimate: 'Below/Average/Above'}"
            )
            result = chat(
                model=CONFIG["models"]["focus"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=25.0,
            )
            if not result or not result.strip():
                raise RuntimeError("LLM returned empty response — Ollama may be offline")
        except Exception as e:
            result = str(e)

        self.award_points(15, f"landing page diagnosis: {url[:40]}")
        return {"status": "ok", "url": url, "keyword": keyword, "diagnosis": result}

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}

        if task_type in ("audit", "google_ads_audit"):
            return await self.audit_account(
                account_id=p.get("account_id", ""),
                industry=p.get("industry", "general"),
                business_context=p.get("business_context", ""),
            )
        elif task_type in ("copy", "google_ads_copy", "ads_copy"):
            return await self.generate_copy(
                product=p.get("product", ""),
                target_keyword=p.get("keyword", ""),
                usp=p.get("usp", ""),
                num_variants=int(p.get("variants", 3)),
            )
        elif task_type in ("performance", "ads_performance"):
            return await self.analyze_performance(
                metrics=p.get("metrics", {}),
                industry=p.get("industry", "general"),
            )
        elif task_type in ("landing", "google_ads_landing"):
            return await self.diagnose_landing_page(
                url=p.get("url", ""),
                keyword=p.get("keyword", ""),
            )

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branches above,
        # carrying a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). Route by keyword to whichever real capability the query
        # actually asks for and has the args for; never guess a required
        # field (url/product) that wasn't supplied. Default to audit_account
        # (needs nothing but an account_id, which itself defaults to "") for
        # a generic "how's our Google Ads doing" ask.
        query = (p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            q = query.lower()
            if "landing" in q and p.get("url"):
                return await self.diagnose_landing_page(url=p.get("url", ""), keyword=p.get("keyword", ""))
            if ("copy" in q or "write" in q) and p.get("product"):
                return await self.generate_copy(
                    product=p.get("product", ""), target_keyword=p.get("keyword", ""),
                    usp=p.get("usp", ""), num_variants=int(p.get("variants", 3)),
                )
            if "performance" in q and p.get("metrics"):
                return await self.analyze_performance(metrics=p.get("metrics", {}), industry=p.get("industry", "general"))
            return await self.audit_account(
                account_id=p.get("account_id", ""),
                industry=p.get("industry", "general"),
                business_context=p.get("business_context", "") or query,
            )

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": ["audit", "google_ads_audit", "copy", "google_ads_copy",
                          "ads_copy", "performance", "ads_performance",
                          "landing", "google_ads_landing"],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][google_ads_agent] ready")
        while self.is_alive:
            await asyncio.sleep(60)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = GoogleAdsAgent()
        assert agent.health_points == 500
        assert agent.name == "GoogleAdsAgent"
        assert agent.district == "marketing"

        # Test benchmark lookup
        benchmarks = INDUSTRY_BENCHMARKS.get("saas_b2b")
        assert benchmarks["target_roas"] == 5.0

        # Test policy lookup
        assert "Ad Rank" in GOOGLE_ADS_POLICIES["auction-ad-rank-equation"]

        print(f"OK google_ads_agent.py HP={agent.health_points} policies={len(GOOGLE_ADS_POLICIES)}")

    asyncio.run(_smoke())
