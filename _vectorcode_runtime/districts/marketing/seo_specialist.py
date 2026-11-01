"""
SEO Specialist — technical SEO audits, keyword research, content optimization.

Focused on VECTOR project's own presence and any client sites managed via
the agency district. Covers keyword clustering, on-page optimization, and
cannibalization detection.
"""

import asyncio
import re
import math
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from districts.marketing._skill_loader import load_skill, SkillMixin

_OWNER_CONTEXT = {
    "project": "VECTOR",
    "github": "arghyadeep-deb",
    "target_keywords": [
        "autonomous AI Python", "personal AI system", "VECTOR AI agent",
        "AI for students Python", "self-improving AI system",
        "multi-agent autonomous AI", "darwinian AI agents",
    ],
}

class SEOSpecialist(AgentBase, SkillMixin):
    """
    Technical SEO + content optimization specialist.
    Audits pages, researches keywords, optimizes content, detects cannibalization.
    Augmented with: seo-audit, ai-seo, content-strategy skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="seo_specialist_001", name="SEOSpecialist", district="marketing")
        self.capabilities = ["audit", "cannibalization", "critical", "keywords", "marketing", "optimize", "report", "seo"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        self._skill_prompt = load_skill("seo-audit", "ai-seo", "content-strategy")
        logger.info("[VECTOR][seo] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def audit_technical_seo(self, html_content: str) -> dict:
        """Check title length, meta description, h1, internal links, basic issues."""
        issues = []
        score = 100

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        if not title_match:
            issues.append({"severity": "critical", "element": "title", "wcag": "N/A",
                           "fix": "Add <title> tag — missing entirely"})
            score -= 20
        else:
            tlen = len(title_match.group(1).strip())
            if tlen < 30:
                issues.append({"severity": "warning", "element": "title",
                                "fix": f"Title too short ({tlen} chars) — aim for 30-60"})
                score -= 10
            elif tlen > 60:
                issues.append({"severity": "warning", "element": "title",
                                "fix": f"Title too long ({tlen} chars) — trim to 60"})
                score -= 5

        meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                              html_content, re.IGNORECASE)
        if not meta_desc:
            issues.append({"severity": "high", "element": "meta-description",
                           "fix": "Add meta description (120-160 chars)"})
            score -= 15
        else:
            mlen = len(meta_desc.group(1))
            if mlen < 120 or mlen > 160:
                issues.append({"severity": "warning", "element": "meta-description",
                               "fix": f"Meta description is {mlen} chars — aim for 120-160"})
                score -= 5

        h1_count = len(re.findall(r"<h1[^>]*>", html_content, re.IGNORECASE))
        if h1_count == 0:
            issues.append({"severity": "critical", "element": "h1", "fix": "No H1 found — add exactly one"})
            score -= 15
        elif h1_count > 1:
            issues.append({"severity": "high", "element": "h1",
                           "fix": f"{h1_count} H1 tags found — use exactly one"})
            score -= 10

        imgs_missing_alt = len(re.findall(r"<img(?![^>]*alt=)[^>]*>", html_content, re.IGNORECASE))
        if imgs_missing_alt:
            issues.append({"severity": "high", "element": "img[alt]",
                           "fix": f"{imgs_missing_alt} image(s) missing alt attributes"})
            score -= min(imgs_missing_alt * 3, 15)

        internal_links = len(re.findall(r'<a\s+[^>]*href=["\'](?!http)[^"\']+["\']', html_content, re.IGNORECASE))
        if internal_links < 3:
            issues.append({"severity": "info", "element": "internal-links",
                           "fix": f"Only {internal_links} internal links — aim for 3+"})
            score -= 5

        return {
            "issues": issues,
            "score": max(0, score),
            "recommendations": [i["fix"] for i in issues if i["severity"] in ("critical", "high")],
        }

    def research_keywords(self, seed_keyword: str, context: str = "") -> dict:
        """Generate keyword clusters via LLM."""
        try:
            prompt = (
                f"Generate SEO keyword research for: '{seed_keyword}'\n"
                f"Context: {context or 'general tech/AI audience'}\n\n"
                f"Return JSON only:\n"
                f'{{"primary": ["3 exact-match keywords"], '
                f'"secondary": ["5 related keywords"], '
                f'"long_tail": ["5 specific long-tail phrases"], '
                f'"questions": ["5 question keywords (how/what/why/best)"], '
                f'"intent": {{"informational": [], "commercial": [], "navigational": []}}}}'
            )
            response = self._chat(prompt, timeout=25.0)
            import json as _json
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return _json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][seo] keyword research LLM failed: {}", e)

        return {
            "primary": [seed_keyword, f"{seed_keyword} guide", f"best {seed_keyword}"],
            "secondary": [f"{seed_keyword} tutorial", f"{seed_keyword} examples",
                          f"{seed_keyword} Python", f"{seed_keyword} 2026", f"learn {seed_keyword}"],
            "long_tail": [f"how to use {seed_keyword}", f"{seed_keyword} step by step",
                          f"{seed_keyword} for beginners", f"what is {seed_keyword}", f"{seed_keyword} vs alternatives"],
            "questions": [f"what is {seed_keyword}?", f"how does {seed_keyword} work?",
                          f"why use {seed_keyword}?", f"best {seed_keyword} tools?", f"how to learn {seed_keyword}?"],
            "intent": {"informational": [f"what is {seed_keyword}"], "commercial": [f"best {seed_keyword}"],
                       "navigational": [seed_keyword]},
        }

    def optimize_content(self, content: str, target_keyword: str) -> dict:
        """Check keyword density, suggest meta/title/H1 improvements."""
        words = content.lower().split()
        kw_lower = target_keyword.lower()
        kw_count = content.lower().count(kw_lower)
        density = round(kw_count / max(len(words), 1) * 100, 2)

        suggestions = []
        if density < 0.5:
            suggestions.append(f"Keyword density too low ({density}%) — use '{target_keyword}' more naturally")
        elif density > 2.0:
            suggestions.append(f"Keyword stuffing risk ({density}%) — reduce usage of '{target_keyword}'")

        if kw_lower not in content[:200].lower():
            suggestions.append("Include keyword in first 200 characters for relevance signal")

        word_count = len(words)
        if word_count < 300:
            suggestions.append(f"Content too thin ({word_count} words) — aim for 800+ for ranking")

        return {
            "keyword_density_pct": density,
            "keyword_count": kw_count,
            "word_count": word_count,
            "suggestions": suggestions,
            "optimized_meta": {
                "title": f"{target_keyword.title()} — Complete Guide | VECTOR",
                "description": f"Learn everything about {target_keyword}. "
                               f"Comprehensive guide with examples and best practices. "
                               f"Updated {datetime.datetime.now().year}.",
            },
        }

    def check_cannibalization(self, pages: list[dict]) -> list[dict]:
        """Find pages competing for the same keyword. pages = [{url, keyword, title}]."""
        from collections import defaultdict
        kw_map: dict[str, list[dict]] = defaultdict(list)
        for page in pages:
            kw = page.get("keyword", "").lower().strip()
            if kw:
                kw_map[kw].append(page)
        conflicts = []
        for kw, competing in kw_map.items():
            if len(competing) > 1:
                conflicts.append({
                    "keyword": kw,
                    "competing_pages": [p.get("url", "") for p in competing],
                    "fix": f"Consolidate or differentiate these {len(competing)} pages targeting '{kw}'",
                })
        return conflicts

    async def generate_seo_report(self, content: str, keyword: str) -> str:
        """Full markdown SEO report for content + keyword."""
        audit = self.optimize_content(content, keyword)
        kw_research = self.research_keywords(keyword)
        ts = datetime.datetime.now().strftime("%Y-%m-%d")
        report = (
            f"# SEO Report — '{keyword}' — {ts}\n\n"
            f"## Content Score\n"
            f"- Keyword density: **{audit['keyword_density_pct']}%** (target: 0.5-2%)\n"
            f"- Word count: **{audit['word_count']}** words\n"
            f"- Keyword occurrences: {audit['keyword_count']}\n\n"
            f"## Issues\n"
            + ("\n".join(f"- {s}" for s in audit["suggestions"]) or "No major issues found.")
            + f"\n\n## Recommended Meta\n"
            f"- **Title:** {audit['optimized_meta']['title']}\n"
            f"- **Description:** {audit['optimized_meta']['description']}\n\n"
            f"## Related Keywords\n"
            f"- Secondary: {', '.join(kw_research.get('secondary', []))}\n"
            f"- Long-tail: {', '.join(kw_research.get('long_tail', []))}\n"
            f"- Questions: {', '.join(kw_research.get('questions', []))}\n"
        )
        return report

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "report")
        try:
            if task_type == "audit":
                html = task.get("html", "<html><head></head><body><h1>Test</h1></body></html>")
                result = self.audit_technical_seo(html)
                self.award_points(20, "seo_audit_done")
                return {"status": "ok", "audit": result}

            elif task_type == "keywords":
                kws = self.research_keywords(task.get("keyword", "VECTOR AI"), task.get("context", ""))
                self.award_points(20, "keywords_researched")
                return {"status": "ok", "keywords": kws}

            elif task_type == "optimize":
                result = self.optimize_content(
                    task.get("content", ""), task.get("keyword", "VECTOR AI")
                )
                self.award_points(25, "content_optimized")
                return {"status": "ok", "optimization": result}

            elif task_type == "cannibalization":
                conflicts = self.check_cannibalization(task.get("pages", []))
                self.award_points(15, "cannibalization_checked")
                return {"status": "ok", "conflicts": conflicts, "count": len(conflicts)}

            elif task_type not in ("report",) and (task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")):
                # 2026-07-28: unmatched/free-text task_type always fell
                # through to "report" for a hardcoded content/keyword
                # ("autonomous AI Python"), ignoring what was actually
                # asked — same bug class as design district's #33.
                query = task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")
                return {"status": "ok", "response": await self.answer_marketing_question(query)}

            else:  # report
                content = task.get("content", f"VECTOR is an autonomous AI system built by Arghyadeep Deb.")
                keyword = task.get("keyword", "autonomous AI Python")
                report = await self.generate_seo_report(content, keyword)
                self._get_memory().store(
                    event_type="seo_report",
                    content=f"SEO report for keyword: {keyword}",
                    tags=["marketing", "seo"],
                    source="seo_specialist",
                )
                self.award_points(30, "seo_report_generated")
                return {"status": "ok", "report": report}

        except Exception as e:
            logger.error("[VECTOR][seo] {}", e)
            self.deduct_points(30, "seo_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SEOSpecialist()
        html = """<html><head><title>VECTOR AI System</title>
        <meta name="description" content="VECTOR is an autonomous AI personal assistant built with Python and local LLMs. Darwinian multi-agent system."></head>
        <body><h1>VECTOR AI</h1><p>An autonomous AI system.</p><img src="vector.png"></body></html>"""
        audit = agent.audit_technical_seo(html)
        print(f"[OK] audit: score={audit['score']} issues={len(audit['issues'])}")
        kws = agent.research_keywords("autonomous AI system")
        print(f"[OK] keywords: {len(kws.get('secondary', []))} secondary found")
        opt = agent.optimize_content("VECTOR is an autonomous AI system. " * 10, "autonomous AI")
        print(f"[OK] optimize: density={opt['keyword_density_pct']}% words={opt['word_count']}")
        result = await agent.run({"type": "report", "keyword": "autonomous AI Python"})
        print(f"[OK] run: status={result['status']}")
        print("seo_specialist.py OK")

    asyncio.run(_smoke())
