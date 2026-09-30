"""
VECTOR SEOAgent — District 19: marketing
Full-site SEO audit pipeline using real data from Google Search Console,
PageSpeed Insights, and broken link detection.

Governor routes: seo_audit, seo_analysis, keyword_research, broken_links,
                 pagespeed, seo_meta, schema_markup, geo_optimize

Usage:
    agent = SEOAgent()
    result = asyncio.run(agent.full_audit("https://example.com", days=28))
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger
from districts.marketing._skill_loader import load_skill, SkillMixin


class SEOAgent(AgentBase, SkillMixin):
    """
    VECTOR's SEO specialist — data-driven audits, not guesswork.
    Uses real GSC data, PageSpeed scores, and link checking.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SEOAgent",
            district="marketing",
            generation=generation,
        )
        self.capabilities = ["broken_links", "full_audit", "geo_optimize", "keyword_research", "marketing", "pagespeed", "schema_markup", "seo"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._skill_prompt = load_skill("seo-audit", "analytics")
        logger.info("[VECTOR][seo_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Full audit pipeline ───────────────────────────────────────────────────

    async def full_audit(
        self,
        site_url: str,
        days: int = 28,
        gsc_site: str | None = None,
    ) -> dict:
        """
        Run a full SEO audit:
          1. GSC performance data (clicks, impressions, CTR, position)
          2. PageSpeed scores (mobile + desktop Core Web Vitals)
          3. Broken link detection
          4. LLM summary of findings + recommendations
        """
        logger.info("[VECTOR][seo_agent] full audit starting: {}", site_url)
        results: dict = {"site": site_url, "status": "ok", "sections": {}}

        # Stage 1: GSC performance
        gsc_data = await self.fetch_gsc(gsc_site or site_url, days=days)
        results["sections"]["gsc"] = gsc_data

        # Stage 2: PageSpeed
        ps_data = await self.fetch_pagespeed(site_url)
        results["sections"]["pagespeed"] = ps_data

        # Stage 3: Broken links (limit to 30 pages for speed)
        link_data = await self.check_broken_links(site_url, max_pages=30)
        results["sections"]["broken_links"] = link_data

        # Stage 4: LLM synthesis
        summary = await self._synthesize_audit(site_url, results["sections"])
        results["summary"] = summary

        # Score and memory
        issues = self._extract_issues(results)
        results["issue_count"] = len(issues)
        results["issues"] = issues

        self._memory.store(
            event_type="seo_audit",
            content=f"SEOAgent audit: {site_url} — {len(issues)} issues found",
            tags=["seo", "audit", "marketing"],
            source="seo_agent",
        )
        self.award_points(50, f"seo audit: {site_url}")
        return results

    # ── Individual tools ──────────────────────────────────────────────────────

    async def fetch_gsc(self, site: str, days: int = 28) -> dict:
        """Fetch Google Search Console data for a site."""
        try:
            from core.seo.gsc_client import GSCClient
            client = GSCClient()
            return await client.fetch_and_analyze(site, days=days)
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] GSC fetch failed: {}", e)
            return {"error": str(e), "note": "Set up gcloud auth to enable GSC data"}

    async def fetch_pagespeed(self, url: str) -> dict:
        """Get PageSpeed Insights scores for a URL."""
        try:
            from core.seo.pagespeed_client import PageSpeedClient
            client = PageSpeedClient()
            return await client.analyze(url)
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] PageSpeed failed: {}", e)
            return {"error": str(e)}

    async def check_broken_links(self, url: str, max_pages: int = 50) -> dict:
        """Crawl site and find broken links."""
        try:
            from core.seo.broken_link_checker import BrokenLinkChecker
            checker = BrokenLinkChecker()
            return await checker.check_async(url, max_pages=max_pages)
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] broken link check failed: {}", e)
            return {"error": str(e)}

    async def analyze_keywords(self, topic: str, site: str = "") -> dict:
        """Generate keyword research using LLM + GSC data."""
        if os.environ.get("VECTOR_SEO_LLM") != "1":
            base = topic.strip() or "seo"
            return {
                "topic": topic,
                "analysis": {
                    "mode": "deterministic",
                    "primary_keywords": [base, f"{base} strategy", f"{base} tools"],
                    "long_tail_keywords": [f"best {base} workflow", f"how to improve {base}"],
                    "question_keywords": [f"what is {base}", f"how does {base} work"],
                    "content_gaps": ["Add comparison pages", "Add FAQ coverage", "Refresh outdated examples"],
                },
            }
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Perform keyword research for: '{topic}'\n"
                f"Site context: {site or 'general'}\n\n"
                "Provide:\n"
                "1. Primary keywords (high volume, relevant)\n"
                "2. Long-tail keywords (easier to rank)\n"
                "3. Question keywords (for featured snippets)\n"
                "4. Content gaps and opportunities\n"
                "Format as structured JSON."
            )
            response = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=30.0,
            )
            return {"topic": topic, "analysis": response}
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] keyword analysis failed: {}", e)
            return {"topic": topic, "error": str(e)}

    async def generate_schema_markup(self, page_type: str, data: dict) -> str:
        """Generate JSON-LD schema markup for a page type."""
        if os.environ.get("VECTOR_SEO_LLM") != "1":
            import json

            return json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": page_type or "WebPage",
                    **{k: v for k, v in data.items() if isinstance(k, str)},
                },
                ensure_ascii=False,
            )
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Generate JSON-LD schema markup for a '{page_type}' page.\n"
                f"Page data: {str(data)[:500]}\n\n"
                "Return only valid JSON-LD, no markdown fences."
            )
            return chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=20.0,
            )
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] schema gen failed: {}", e)
            return ""

    async def optimize_for_ai_search(self, url: str, content: str) -> dict:
        """
        GEO (Generative Engine Optimization) — optimize content so ChatGPT,
        Claude, Perplexity, and Gemini cite this page in their answers.
        """
        if os.environ.get("VECTOR_SEO_LLM") != "1":
            return {
                "url": url,
                "geo_analysis": {
                    "mode": "deterministic",
                    "score": 50 if content else 0,
                    "recommendations": [
                        "Add explicit author and source information",
                        "Answer high-intent questions directly",
                        "Use concise definitions and structured headings",
                    ],
                },
            }
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            prompt = (
                f"Analyze this content for AI search engine optimization (GEO).\n"
                f"URL: {url}\n"
                f"Content preview: {content[:1000]}\n\n"
                "Provide:\n"
                "1. GEO Score (0-100) — how likely AI models cite this page\n"
                "2. Missing authoritative signals\n"
                "3. Specific rewrites to improve citation probability\n"
                "4. E-E-A-T improvements (Experience, Expertise, Authority, Trust)\n"
            )
            analysis = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=30.0,
            )
            return {"url": url, "geo_analysis": analysis}
        except Exception as e:
            logger.warning("[VECTOR][seo_agent] GEO analysis failed: {}", e)
            return {"url": url, "error": str(e)}

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _synthesize_audit(self, site: str, sections: dict) -> str:
        if os.environ.get("VECTOR_SEO_LLM") != "1":
            return f"Audit complete for {site}. Review GSC, PageSpeed, and broken-link sections for prioritized fixes."
        hydration = self._context.session_hydration_prompt()
        try:
            from core.inference.vectorcode_llm import chat
            gsc   = sections.get("gsc", {})
            ps    = sections.get("pagespeed", {})
            links = sections.get("broken_links", {})

            # Position bucket insight (from show_gsc.py absorption)
            buckets = gsc.get("position_buckets", {})
            bucket_insight = buckets.get("insight", "") if buckets else ""
            bucket_counts  = buckets.get("counts", {}) if buckets else {}

            # CrUX real-user data (from show_pagespeed.py absorption)
            crux = ps.get("crux", {})
            crux_overall = crux.get("overall", "unknown") if crux else "unknown"
            crux_lcp     = crux.get("lcp", {}).get("rating", "unknown") if crux else "unknown"

            summary_data = {
                "gsc_summary":       gsc.get("summary", gsc.get("error", "no data")),
                "mobile_score":      ps.get("scores", {}).get("mobile", "unknown"),
                "mobile_label":      ps.get("scores", {}).get("mobile_label", ""),
                "desktop_score":     ps.get("scores", {}).get("desktop", "unknown"),
                "crux_overall":      crux_overall,   # FAST/AVERAGE/SLOW from real users
                "crux_lcp":          crux_lcp,       # LCP rating from real users
                "broken_links":      links.get("broken_count", 0),
                "top_opportunity":   (gsc.get("opportunities") or [{}])[0] if gsc.get("opportunities") else {},
                "position_buckets":  bucket_counts,  # {1-3, 4-10, 11-20, 21+}
                "ranking_insight":   bucket_insight,
            }

            prompt = (
                f"SEO audit summary for: {site}\n\n"
                f"Data: {str(summary_data)[:1200]}\n\n"
                "Write a concise 3-bullet executive summary with:\n"
                "1. Current performance state (include CrUX real-user rating if available)\n"
                "2. Top issue to fix this week (consider position bucket distribution)\n"
                "3. Biggest growth opportunity (CTR opportunities, page-2 keyword wins)\n"
            )
            return chat(
                model=CONFIG["models"]["focus"],
                messages=[
                    {"role": "system", "content": self._with_skill_system(hydration)},
                    {"role": "user", "content": prompt},
                ],
                timeout=20.0,
            )
        except Exception:
            return f"Audit complete for {site}. Review sections for details."

    def _extract_issues(self, results: dict) -> list[dict]:
        issues = []
        sections = results.get("sections", {})

        # PageSpeed issues
        ps = sections.get("pagespeed", {})
        mobile_score = ps.get("scores", {}).get("mobile", 100)
        if isinstance(mobile_score, int) and mobile_score < 50:
            issues.append({"title": f"Poor mobile performance ({mobile_score}/100)",
                           "severity": "critical", "source": "pagespeed"})
        elif isinstance(mobile_score, int) and mobile_score < 75:
            issues.append({"title": f"Mobile performance needs improvement ({mobile_score}/100)",
                           "severity": "warning", "source": "pagespeed"})

        # Broken links
        bl = sections.get("broken_links", {})
        broken = bl.get("broken_count", 0)
        if broken > 10:
            issues.append({"title": f"{broken} broken links detected",
                           "severity": "critical", "source": "broken_links"})
        elif broken > 0:
            issues.append({"title": f"{broken} broken links detected",
                           "severity": "warning", "source": "broken_links"})

        # GSC opportunities
        gsc = sections.get("gsc", {})
        opps = gsc.get("opportunities", [])
        for opp in opps[:3]:
            issues.append({
                "title": f"CTR opportunity: {opp.get('url', '')[:60]} (pos {opp.get('position')})",
                "severity": "info",
                "source": "gsc",
            })

        return issues

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        action = task.get("type") or p.get("action", "full_audit")

        if action in ("full_audit", "seo_audit", "seo_analysis"):
            return await self.full_audit(
                site_url=p.get("url", p.get("site", "")),
                days=int(p.get("days", 28)),
                gsc_site=p.get("gsc_site"),
            )
        elif action == "keyword_research":
            return await self.analyze_keywords(
                topic=p.get("topic", ""),
                site=p.get("site", ""),
            )
        elif action == "broken_links":
            return await self.check_broken_links(
                url=p.get("url", ""),
                max_pages=int(p.get("max_pages", 50)),
            )
        elif action == "pagespeed":
            return await self.fetch_pagespeed(p.get("url", ""))
        elif action == "schema_markup":
            return {"schema": await self.generate_schema_markup(
                page_type=p.get("page_type", "WebPage"),
                data=p.get("data", {}),
            )}
        elif action == "geo_optimize":
            return await self.optimize_for_ai_search(
                url=p.get("url", ""),
                content=p.get("content", ""),
            )

        # 2026-09-30 (Phase 3 codebase audit finding): real chat dispatch sends
        # an LLM-invented task_type that won't match the branches above,
        # carrying a real free-text question in params (see
        # tests/test_marketing_district_run_wiring.py's module docstring for
        # the bug class — same as districts/languages/hindi_coach.py's fixed
        # pattern). Route by keyword to whichever real capability the query
        # actually asks for and has the args for; default to full_audit (it
        # takes no required args — url/site/gsc_site all default) since a
        # generic "how's our SEO doing" ask maps most closely to that.
        query = (p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or "").strip()
        if query:
            q = query.lower()
            if "keyword" in q and p.get("topic"):
                return await self.analyze_keywords(topic=p.get("topic", ""), site=p.get("site", ""))
            if ("pagespeed" in q or "page speed" in q or "core web vitals" in q) and p.get("url"):
                return await self.fetch_pagespeed(p.get("url", ""))
            if "schema" in q and p.get("data"):
                return {"schema": await self.generate_schema_markup(page_type=p.get("page_type", "WebPage"), data=p.get("data", {}))}
            if ("ai search" in q or "geo" in q or "llm" in q) and p.get("url") and p.get("content"):
                return await self.optimize_for_ai_search(url=p.get("url", ""), content=p.get("content", ""))
            if "broken link" in q and p.get("url"):
                return await self.check_broken_links(url=p.get("url", ""), max_pages=int(p.get("max_pages", 50)))
            return await self.full_audit(
                site_url=p.get("url", p.get("site", "")),
                days=int(p.get("days", 28)),
                gsc_site=p.get("gsc_site"),
            )

        return {
            "status": "error",
            "error": f"unhandled type: {action}",
            "supported": [
                "full_audit",
                "seo_audit",
                "seo_analysis",
                "keyword_research",
                "broken_links",
                "pagespeed",
                "schema_markup",
                "geo_optimize",
            ],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][seo_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][seo_agent] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SEOAgent()
        assert agent.health_points == 500
        assert agent.name == "SEOAgent"
        assert agent.district == "marketing"

        # Test keyword research (uses LLM — may fail if Ollama down)
        result = await agent.run({
            "params": {"action": "keyword_research", "topic": "AI automation", "site": ""}
        })
        assert "topic" in result

        # Test schema markup
        schema_result = await agent.run({
            "params": {"action": "schema_markup", "page_type": "Article",
                       "data": {"title": "VECTOR AI", "author": "Arghyadeep"}}
        })
        assert "schema" in schema_result

        print(f"OK seo_agent.py HP={agent.health_points}")

    asyncio.run(_smoke())
