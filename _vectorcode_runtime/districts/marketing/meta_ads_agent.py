"""
VECTOR MetaAdsAgent — District 19: marketing
AI-powered Meta Ads (Facebook + Instagram) analysis, creative strategy,
audience optimization, ROAS diagnosis, and learning phase management.

Policy rules embedded from toprank's meta-ads/shared/policy-registry.json.

Governor routes: meta_ads_audit, meta_ads, meta_ads_performance,
                 meta_ads_creative, meta_ads_audience, ads_meta
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger
from districts.marketing._skill_loader import load_skill, SkillMixin


# ── Policy rules (absorbed from meta-ads/shared/policy-registry.json) ─────────

META_ADS_POLICIES = {
    "object-hierarchy": "Ad Account > Campaign > Ad Set > Ad. Budget at Ad Set or Campaign level (CBO).",
    "metric-definitions": "CPM = (Spend/Impressions)×1000. CTR(link) = Link Clicks/Impressions. ROAS = Revenue/Spend. Frequency = Impressions/Reach.",
    "graph-api-stability": "Meta Marketing API via Graph API. Marketing API versions deprecate quarterly — always use v18.0+.",
    "learning-phase": "Ad set enters Learning Phase on: creation, restart, significant edit (budget >20%, audience, bid, creative). Needs 50 optimization events to exit. Avoid editing during learning.",
    "creative-fatigue": "Frequency > 3.0 for cold audiences signals fatigue. CTR drop >25% week-over-week = refresh creative.",
    "audience-overlap": "Overlapping ad sets compete in the same auction → CPM inflation. Use Audience Overlap Tool; consolidate or exclude.",
    "campaign-budget-optimization": "CBO: Meta allocates budget across ad sets automatically. Use for 3+ ad sets with similar audiences.",
    "attribution-window": "Default: 7-day click, 1-day view. Compare to GA4 for cross-platform reconciliation.",
    "ios14-impact": "ATT prompt reduced pixel signal. Use Aggregated Event Measurement (AEM), Conversions API (CAPI), and broad targeting.",
    "broad-targeting": "Broad (no detailed targeting) + Advantage+ often outperforms narrow targeting post-iOS14.",
    "creative-hierarchy": "Creative is the main targeting signal in broad audiences. Static > Carousel for ROAS. Video for top-funnel.",
    "roas-seasonality": "ROAS spikes Q4 (Oct-Dec). Baseline off-peak ROAS before scaling. Avoid major changes 2 weeks before peak.",
    "bid-caps": "Bid Cap: strict cost control, may limit volume. Cost Cap: targets average cost, more volume. Lowest Cost: max volume, no cap.",
}

# ROAS benchmarks by industry for Meta Ads
META_BENCHMARKS = {
    "ecommerce":   {"target_roas": 3.0, "avg_cpm_usd": 14.0, "avg_ctr_pct": 1.5, "target_frequency": 2.5},
    "lead_gen":    {"target_roas": 2.0, "avg_cpm_usd": 12.0, "avg_ctr_pct": 1.2, "target_frequency": 2.0},
    "saas":        {"target_roas": 2.5, "avg_cpm_usd": 18.0, "avg_ctr_pct": 1.0, "target_frequency": 2.0},
    "retail":      {"target_roas": 4.0, "avg_cpm_usd": 10.0, "avg_ctr_pct": 2.0, "target_frequency": 3.0},
    "app_install": {"target_roas": 1.5, "avg_cpm_usd": 8.0,  "avg_ctr_pct": 3.0, "target_frequency": 2.0},
    "general":     {"target_roas": 2.5, "avg_cpm_usd": 12.0, "avg_ctr_pct": 1.5, "target_frequency": 2.5},
}


class MetaAdsAgent(AgentBase, SkillMixin):
    """
    VECTOR's Meta Ads specialist.
    Diagnoses ROAS, creative fatigue, audience overlap, learning phase issues.
    Generates ad copy and audience strategy recommendations.
    Augmented with: ads, ad-creative, analytics skill prompts.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MetaAdsAgent",
            district="marketing",
            generation=generation,
        )
        self.capabilities = ["ads", "audit", "creative", "fatigue", "marketing", "meta_ads", "roas"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._skill_prompt = load_skill("ads", "ad-creative", "analytics")
        logger.info("[VECTOR][meta_ads_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Account audit ─────────────────────────────────────────────────────────

    async def audit_account(
        self,
        account_id: str = "",
        industry: str = "general",
        business_context: str = "",
    ) -> dict:
        """Full Meta Ads account health audit."""
        hydration = self._context.session_hydration_prompt()
        benchmarks = META_BENCHMARKS.get(industry, META_BENCHMARKS["general"])
        policies_text = "\n".join(f"- {k}: {v}" for k, v in META_ADS_POLICIES.items())

        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Audit this Meta Ads account for a {industry} business.\n"
                f"Account ID: {account_id or 'not provided'}\n"
                f"Business context: {business_context or 'not provided'}\n\n"
                f"Industry benchmarks:\n"
                f"  Target ROAS: {benchmarks['target_roas']}x\n"
                f"  Avg CPM: ${benchmarks['avg_cpm_usd']}\n"
                f"  Avg CTR: {benchmarks['avg_ctr_pct']}%\n"
                f"  Target Frequency: {benchmarks['target_frequency']}\n\n"
                f"Meta Ads policy rules:\n{policies_text}\n\n"
                "Audit across 6 dimensions:\n"
                "1. Campaign structure and CBO setup\n"
                "2. Audience strategy (broad vs narrow, overlap)\n"
                "3. Creative health and fatigue signals\n"
                "4. Learning phase status\n"
                "5. Attribution window and CAPI setup\n"
                "6. ROAS and CPM vs benchmarks\n\n"
                "Output JSON: {dimension_scores, critical_issues, action_plan}"
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
            result = str(e)

        self._memory.store(
            event_type="meta_ads_audit",
            content=f"Meta Ads audit: account={account_id} industry={industry}",
            tags=["meta_ads", "audit", "marketing"],
            source="meta_ads_agent",
        )
        self.award_points(40, f"meta ads audit: {account_id}")
        return {"status": "ok", "account_id": account_id, "industry": industry,
                "benchmarks": benchmarks, "audit": result}

    # ── Creative fatigue diagnosis ─────────────────────────────────────────────

    async def diagnose_creative_fatigue(
        self,
        metrics: dict,
        industry: str = "general",
    ) -> dict:
        """
        Diagnose creative fatigue from Meta Ads metrics.
        Key signals: frequency > 3.0, CTR week-over-week drop > 25%.
        """
        benchmarks = META_BENCHMARKS.get(industry, META_BENCHMARKS["general"])
        issues = []
        recommendations = []

        frequency = metrics.get("frequency", 0)
        ctr = metrics.get("ctr_pct", 0)
        ctr_prev = metrics.get("ctr_pct_prev_week", ctr)
        roas = metrics.get("roas", 0)

        if frequency > benchmarks["target_frequency"]:
            issues.append({
                "type": "high_frequency",
                "value": frequency,
                "threshold": benchmarks["target_frequency"],
                "severity": "critical" if frequency > 4.0 else "warning",
            })
            recommendations.append("Refresh creatives — introduce 3+ new variants immediately.")

        if ctr_prev > 0 and ctr < ctr_prev * 0.75:
            ctr_drop = (1 - ctr / ctr_prev) * 100
            issues.append({
                "type": "ctr_drop",
                "value": round(ctr_drop, 1),
                "threshold": 25.0,
                "severity": "warning",
            })
            recommendations.append(f"CTR dropped {ctr_drop:.1f}% WoW — test new hooks and formats.")

        if roas and roas < benchmarks["target_roas"] * 0.7:
            issues.append({
                "type": "low_roas",
                "value": roas,
                "benchmark": benchmarks["target_roas"],
                "severity": "critical",
            })
            recommendations.append("ROAS below target — pause underperformers, scale winners.")

        fatigue_score = min(100, len(issues) * 30 + (20 if frequency > 3.5 else 0))

        return {
            "status": "ok",
            "fatigue_score": fatigue_score,
            "is_fatigued": fatigue_score >= 50,
            "issues": issues,
            "recommendations": recommendations,
            "metrics_checked": list(metrics.keys()),
        }

    # ── ROAS analysis ─────────────────────────────────────────────────────────

    async def analyze_roas(
        self,
        campaign_data: list[dict],
        industry: str = "general",
    ) -> dict:
        """Analyze ROAS across campaigns and identify winners/losers."""
        benchmarks = META_BENCHMARKS.get(industry, META_BENCHMARKS["general"])
        target = benchmarks["target_roas"]

        winners = [c for c in campaign_data if c.get("roas", 0) >= target]
        losers  = [c for c in campaign_data if c.get("roas", 0) < target * 0.7]

        self.award_points(15, "meta ads roas analysis")
        return {
            "status": "ok",
            "target_roas": target,
            "winners": sorted(winners, key=lambda x: x.get("roas", 0), reverse=True)[:5],
            "losers":  sorted(losers,  key=lambda x: x.get("spend_usd", 0), reverse=True)[:5],
            "recommendation": (
                f"Scale {len(winners)} campaigns above {target}x ROAS. "
                f"Pause or restructure {len(losers)} underperformers."
            ),
        }

    # ── Ad copy generation ────────────────────────────────────────────────────

    async def generate_creative_brief(
        self,
        product: str,
        target_audience: str,
        objective: str = "conversions",
        num_variants: int = 3,
    ) -> dict:
        """Generate Meta ad creative brief (copy + hook + format recommendation)."""
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Generate {num_variants} Meta ad creative briefs for:\n"
                f"Product: {product}\n"
                f"Target audience: {target_audience}\n"
                f"Objective: {objective}\n\n"
                "For each variant provide:\n"
                "1. Hook (first 3 seconds / first line — pattern interrupt)\n"
                "2. Primary text (125 chars for mobile feed)\n"
                "3. Headline (40 chars)\n"
                "4. Format: Static image | Single video | Carousel | Collection\n"
                "5. Call to action button\n"
                "6. Estimated CTR range\n\n"
                "Apply: attention → interest → desire → action structure.\n"
                "Output JSON array."
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

        self.award_points(20, f"meta creative brief: {product}")
        return {"status": "ok", "product": product, "audience": target_audience, "briefs": result}

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        action = task.get("type") or p.get("action", "audit")

        if action in ("audit", "meta_ads_audit"):
            return await self.audit_account(
                account_id=p.get("account_id", ""),
                industry=p.get("industry", "general"),
                business_context=p.get("business_context", ""),
            )
        elif action in ("fatigue", "meta_ads_creative"):
            return await self.diagnose_creative_fatigue(
                metrics=p.get("metrics", {}),
                industry=p.get("industry", "general"),
            )
        elif action in ("roas", "meta_ads_performance"):
            return await self.analyze_roas(
                campaign_data=p.get("campaigns", []),
                industry=p.get("industry", "general"),
            )
        elif action in ("creative", "meta_ads"):
            return await self.generate_creative_brief(
                product=p.get("product", ""),
                target_audience=p.get("audience", ""),
                objective=p.get("objective", "conversions"),
            )

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branches above,
        # carrying a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). Route by keyword to whichever real capability the query
        # actually asks for and has the args for; never guess a required
        # field (product/campaigns) that wasn't supplied.
        query = (p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            q = query.lower()
            if "fatigu" in q and p.get("metrics"):
                return await self.diagnose_creative_fatigue(metrics=p.get("metrics", {}), industry=p.get("industry", "general"))
            if "roas" in q and p.get("campaigns"):
                return await self.analyze_roas(campaign_data=p.get("campaigns", []), industry=p.get("industry", "general"))
            if ("creative" in q or "brief" in q) and p.get("product"):
                return await self.generate_creative_brief(
                    product=p.get("product", ""), target_audience=p.get("audience", ""),
                    objective=p.get("objective", "conversions"),
                )
            return await self.audit_account(
                account_id=p.get("account_id", ""),
                industry=p.get("industry", "general"),
                business_context=p.get("business_context", "") or query,
            )

        return {
            "status": "error",
            "error": f"unhandled type: {action}",
            "supported": [
                "audit",
                "meta_ads_audit",
                "fatigue",
                "meta_ads_creative",
                "roas",
                "meta_ads_performance",
                "creative",
                "meta_ads",
            ],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][meta_ads_agent] ready")
        while self.is_alive:
            await asyncio.sleep(60)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = MetaAdsAgent()
        assert agent.health_points == 500
        assert agent.name == "MetaAdsAgent"
        assert agent.district == "marketing"

        # Test creative fatigue diagnosis
        result = await agent.diagnose_creative_fatigue(
            metrics={"frequency": 4.2, "ctr_pct": 0.8, "ctr_pct_prev_week": 1.5, "roas": 1.8},
            industry="ecommerce",
        )
        assert result["is_fatigued"] is True
        assert len(result["issues"]) >= 2
        print(f"Creative fatigue: score={result['fatigue_score']} issues={len(result['issues'])}")

        # Test policy lookup
        assert "Learning Phase" in META_ADS_POLICIES["learning-phase"]

        print(f"OK meta_ads_agent.py HP={agent.health_points} policies={len(META_ADS_POLICIES)}")

    asyncio.run(_smoke())
