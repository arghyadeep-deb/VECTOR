"""
Ads Orchestrator — multi-platform paid advertising audit, creative, and optimization.

Covers Google Ads (80 checks), Meta (50 checks), LinkedIn, TikTok, Microsoft,
YouTube, Apple Ads. Provides landing page analysis, AI creative generation,
PPC financial modeling, A/B test design, and PDF report building.

Routes all ads_* task types from the governor to the appropriate sub-workflow.
"""

import sys
import asyncio
import subprocess
import json
from pathlib import Path

# Ensure codebase root is first in sys.path so CONFIG resolves to the real dict,
# not vectorcode/src/core/config.py (VectorConfig).

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from districts.marketing._skill_loader import load_skill, SkillMixin

# Real location is districts/marketing/ads/{scripts,references,templates}/ --
# this previously chained 4 .parent hops to a nonexistent core/ads/ one level
# ABOVE the repo root, so _run_script()/_load_reference()/_load_template()
# silently found nothing (every script call returned "Script not found", every
# reference/template load returned "") for every ads_* task type. Phantom
# failure: callers still returned {"status": "ok"} around the empty/error
# results (see the status-check fix below).
_ADS_SCRIPTS = Path(__file__).parent / "ads" / "scripts"
_ADS_REFERENCES = Path(__file__).parent / "ads" / "references"
_ADS_TEMPLATES = Path(__file__).parent / "ads" / "templates"

class AdsOrchestratorAgent(AgentBase, SkillMixin):
    """
    Multi-platform ads intelligence agent.
    Handles audits, creative generation, landing page analysis, PPC math, and reporting.
    Augmented with: ads, ad-creative, cro skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="ads_orchestrator_001", name="AdsOrchestratorAgent", district="marketing")
        self.capabilities = ["ads", "ads_audit", "ads_budget", "ads_competitor", "ads_create", "ads_creative", "ads_dna", "ads_generate", "ads_google_audit", "ads_landing", "ads_math", "ads_photoshoot", "ads_plan", "ads_report", "ads_test", "marketing", "orchestrate"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._skill_prompt = load_skill("ads", "ad-creative", "cro")
        logger.info("[VECTOR][ads] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _run_script(self, script_name: str, args: list[str]) -> dict:
        """Run a core/ads/scripts/ utility and return parsed JSON output."""
        script = _ADS_SCRIPTS / script_name
        if not script.exists():
            return {"error": f"Script not found: {script_name}"}
        try:
            result = subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "script failed"}
            return json.loads(result.stdout) if result.stdout.strip().startswith("{") else {"output": result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {"error": "script timed out after 60s"}
        except Exception as e:
            return {"error": str(e)}

    def _load_reference(self, name: str) -> str:
        """Load a knowledge reference doc for LLM context."""
        path = _ADS_REFERENCES / f"{name}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _load_template(self, industry: str) -> str:
        """Load an industry strategy template."""
        path = _ADS_TEMPLATES / f"{industry}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    async def _llm_audit(self, platform: str, account_data: str) -> dict:
        """Run an LLM-based audit against the weighted scoring reference."""
        ref = self._load_reference(f"{platform}-audit")
        scoring = self._load_reference("scoring-system")
        benchmarks = self._load_reference("benchmarks")
        prompt = (
            f"You are a VECTOR Ads audit specialist.\n\n"
            f"## {platform.upper()} AUDIT CHECKS\n{ref}\n\n"
            f"## SCORING SYSTEM\n{scoring}\n\n"
            f"## INDUSTRY BENCHMARKS\n{benchmarks}\n\n"
            f"## ACCOUNT DATA\n{account_data}\n\n"
            f"Run the full {platform} audit. Return a JSON object with:\n"
            f"health_score (0-100), grade (A-F), checks (list of check results), "
            f"critical_issues (list), quick_wins (list), recommendations (list)."
        )
        response = await chat(prompt, model=self._model)
        if not response or not response.strip():
            raise RuntimeError(f"LLM returned empty response for {platform} audit — Ollama may be offline")
        return {"platform": platform, "audit": response}

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "ads_audit")
        params = task.get("params", {})

        try:
            # ── Full multi-platform audit ──────────────────────────────────────
            if task_type in ("ads_audit", "ads_full_audit", "ads_multi_audit"):
                platforms = params.get("platforms", ["google", "meta"])
                account_data = params.get("account_data", "No data provided — perform gap analysis.")
                audit_results = await asyncio.gather(
                    *[self._llm_audit(platform, account_data) for platform in platforms],
                    return_exceptions=True,
                )
                results = {}
                for platform, result in zip(platforms, audit_results):
                    if isinstance(result, Exception):
                        logger.warning("[VECTOR][ads] {} audit failed: {}", platform, result)
                        results[platform] = {"platform": platform, "error": str(result)}
                    else:
                        results[platform] = result
                self.award_points(30, "multi_platform_audit_done")
                self._get_memory().store(
                    event_type="ads_audit",
                    content=f"Ads audit completed: {platforms}",
                    tags=["marketing", "ads", "audit"],
                    context={"platforms": platforms},
                    source="ads_orchestrator_agent",
                )
                return {"status": "ok", "type": task_type, "results": results}

            # ── Landing page analysis ─────────────────────────────────────────
            elif task_type in ("ads_landing", "ads_landing_analysis"):
                url = params.get("url", "")
                if not url:
                    return {"status": "error", "error": "url required"}
                result = self._run_script("analyze_landing.py", [url])
                if "error" in result:
                    self.deduct_points(15, "landing_analysis_failed")
                    return {"status": "error", "type": task_type, "error": result["error"]}
                self.award_points(20, "landing_analysis_done")
                self._get_memory().store(
                    event_type="ads_landing_analysis",
                    content=f"Landing page analyzed: {url}",
                    tags=["marketing", "ads", "landing"],
                    context={"url": url},
                    source="ads_orchestrator_agent",
                )
                return {"status": "ok", "type": task_type, "analysis": result}

            # ── Platform-specific audits ──────────────────────────────────────
            elif task_type in ("ads_google_audit", "ads_linkedin_audit", "ads_tiktok_audit",
                               "ads_microsoft_audit", "ads_apple_audit", "ads_youtube_audit"):
                platform = task_type.replace("ads_", "").replace("_audit", "")
                account_data = params.get("account_data", "No data — perform gap analysis.")
                result = await self._llm_audit(platform, account_data)
                self.award_points(25, f"{platform}_audit_done")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Creative audit ────────────────────────────────────────────────
            elif task_type in ("ads_creative", "ads_creative_audit"):
                creative_data = params.get("creative_data", "No creatives provided.")
                ref = self._load_reference("platform-specs")
                copy_ref = self._load_reference("copy-frameworks")
                prompt = (
                    f"You are a VECTOR Ads creative specialist.\n\n"
                    f"## PLATFORM SPECS\n{ref}\n\n## COPY FRAMEWORKS\n{copy_ref}\n\n"
                    f"## CREATIVES TO REVIEW\n{creative_data}\n\n"
                    f"Audit these ad creatives. Return critical_issues, improvements, "
                    f"platform_compliance (pass/fail per spec), copy_score (0-100)."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "creative_audit_done")
                return {"status": "ok", "type": task_type, "audit": response}

            # ── Budget & bidding ──────────────────────────────────────────────
            elif task_type in ("ads_budget", "ads_budget_alloc", "ads_bidding"):
                budget_data = params.get("budget_data", "")
                ref = self._load_reference("budget-allocation")
                bidding_ref = self._load_reference("bidding-strategies")
                prompt = (
                    f"You are a VECTOR Ads budget strategist.\n\n"
                    f"## BUDGET ALLOCATION GUIDE\n{ref}\n\n"
                    f"## BIDDING STRATEGIES\n{bidding_ref}\n\n"
                    f"## CURRENT BUDGET\n{budget_data or 'No data — provide general guidance.'}\n\n"
                    f"Recommend optimal budget split across platforms, bidding strategies, "
                    f"and expected ROAS/CPA targets."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "budget_strategy_done")
                return {"status": "ok", "type": task_type, "strategy": response}

            # ── Strategic plan ────────────────────────────────────────────────
            elif task_type in ("ads_plan", "ads_strategy"):
                industry = params.get("industry", "generic")
                business_data = params.get("business_data", "")
                template = self._load_template(industry)
                prompt = (
                    f"You are a VECTOR Ads strategist.\n\n"
                    f"## {industry.upper()} INDUSTRY TEMPLATE\n{template}\n\n"
                    f"## BUSINESS CONTEXT\n{business_data or 'Use template defaults.'}\n\n"
                    f"Create a complete paid advertising strategy: platform selection, "
                    f"budget allocation, KPIs, campaign structure, 90-day roadmap."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(25, "ads_plan_done")
                return {"status": "ok", "type": task_type, "plan": response}

            # ── Competitor research ───────────────────────────────────────────
            elif task_type in ("ads_competitor", "ads_competitor_research"):
                competitor = params.get("competitor", "")
                prompt = (
                    f"Research competitor ad strategy for: {competitor or 'the specified brand'}.\n"
                    f"Cover: estimated spend, platforms used, ad angles, creative themes, "
                    f"targeting signals, gaps to exploit. Use public signals only."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "competitor_research_done")
                return {"status": "ok", "type": task_type, "research": response}

            # ── PPC financial calculator ──────────────────────────────────────
            elif task_type in ("ads_math", "ppc_calculator"):
                metrics = params.get("metrics", {})
                budget = metrics.get("budget", 0)
                clicks = metrics.get("clicks", 0)
                conversions = metrics.get("conversions", 0)
                revenue = metrics.get("revenue", 0)

                cpc = budget / clicks if clicks else 0
                cvr = conversions / clicks * 100 if clicks else 0
                cpa = budget / conversions if conversions else 0
                roas = revenue / budget if budget else 0
                breakeven_roas = 1 / metrics.get("margin", 0.3) if metrics.get("margin") else 0

                ref = self._load_reference("benchmarks")
                result = {
                    "cpc": round(cpc, 2),
                    "cvr_pct": round(cvr, 2),
                    "cpa": round(cpa, 2),
                    "roas": round(roas, 2),
                    "breakeven_roas": round(breakeven_roas, 2),
                    "profitable": roas > breakeven_roas if breakeven_roas else None,
                    "benchmarks_reference": "see core/ads/references/benchmarks.md"
                }
                self.award_points(15, "ppc_math_done")
                return {"status": "ok", "type": task_type, "calculations": result}

            # ── A/B test design ───────────────────────────────────────────────
            elif task_type in ("ads_test", "ab_test_design"):
                test_data = params.get("test_data", "")
                prompt = (
                    f"Design an A/B test for this paid advertising scenario:\n{test_data or 'General ad test design.'}\n\n"
                    f"Provide: hypothesis, control vs variant, KPI to measure, "
                    f"minimum sample size (80% power, 95% confidence), test duration, "
                    f"statistical significance threshold, and decision framework."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "ab_test_design_done")
                return {"status": "ok", "type": task_type, "test_design": response}

            # ── Brand DNA extraction ──────────────────────────────────────────
            elif task_type in ("ads_dna", "brand_dna"):
                url = params.get("url", "")
                if url:
                    page = self._run_script("fetch_page.py", [url])
                    # capture_screenshot.py takes a positional url + --viewport
                    # (desktop/tablet/mobile), not --url/--device -- the old argv
                    # shape always failed with "unrecognized arguments".
                    screenshot = self._run_script("capture_screenshot.py", [url, "--viewport", "desktop"])
                else:
                    page = {"html": params.get("html", "")}
                    screenshot = {}
                ref = self._load_reference("brand-dna-template")
                prompt = (
                    f"Extract brand DNA from this website.\n\n"
                    f"## BRAND DNA TEMPLATE\n{ref}\n\n"
                    f"## PAGE CONTENT\n{str(page)[:3000]}\n\n"
                    f"Return: brand_name, mission, target_audience, brand_voice, "
                    f"visual_palette, key_differentiators, ad_angle_ideas."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "brand_dna_done")
                return {"status": "ok", "type": task_type, "brand_dna": response}

            # ── Campaign brief generation ─────────────────────────────────────
            elif task_type in ("ads_create", "campaign_brief"):
                brand_data = params.get("brand_data", "")
                ref = self._load_reference("copy-frameworks")
                voice_ref = self._load_reference("voice-to-style")
                prompt = (
                    f"Create a campaign brief for:\n{brand_data or 'Generic campaign'}\n\n"
                    f"## COPY FRAMEWORKS\n{ref}\n\n## VOICE TO STYLE\n{voice_ref}\n\n"
                    f"Return: campaign_name, objective, target_audience, value_proposition, "
                    f"headline_variations (5+), ad_copy_variants (3+), visual_direction, "
                    f"platform_adaptations per channel."
                )
                response = await chat(prompt, model=self._model)
                if not response or not response.strip():
                    raise RuntimeError(f"LLM returned empty response for {task_type} — Ollama may be offline")
                self.award_points(20, "campaign_brief_done")
                return {"status": "ok", "type": task_type, "brief": response}

            # ── AI image generation ───────────────────────────────────────────
            elif task_type in ("ads_generate", "ad_image_generate"):
                prompt_text = params.get("prompt", "")
                aspect = params.get("aspect_ratio", "1:1")
                output_dir = params.get("output_dir", "output/ads_screenshots")
                # generate_image.py takes a positional prompt + --ratio
                # (not --prompt/--aspect-ratio, which don't exist on its
                # argparse at all -- always "unrecognized arguments").
                result = self._run_script(
                    "generate_image.py",
                    [prompt_text, "--ratio", aspect, "--output-dir", output_dir]
                )
                if "error" in result:
                    self.deduct_points(15, "ad_image_generation_failed")
                    return {"status": "error", "type": task_type, "error": result["error"]}
                self.award_points(25, "ad_image_generated")
                return {"status": "ok", "type": task_type, "result": result}

            # ── Product photoshoot ────────────────────────────────────────────
            elif task_type == "ads_photoshoot":
                product = params.get("product", "")
                style = params.get("style", "studio")
                output_dir = params.get("output_dir", "output/ads_screenshots")
                styles = {
                    "studio": f"Professional studio photography of {product}, white background, perfect lighting, product hero shot",
                    "floating": f"Floating product photography of {product}, levitating, dramatic shadows, commercial style",
                    "ingredient": f"Ingredient-story photography of {product} surrounded by raw ingredients, flat lay, overhead",
                    "in_use": f"Lifestyle action shot, {product} being used by person, natural lighting, authentic",
                    "lifestyle": f"Aspirational lifestyle photography featuring {product}, beautiful setting, editorial quality",
                }
                prompt_text = styles.get(style, styles["studio"])
                result = self._run_script(
                    "generate_image.py",
                    [prompt_text, "--ratio", "1:1", "--output-dir", output_dir]
                )
                if "error" in result:
                    self.deduct_points(15, "photoshoot_failed")
                    return {"status": "error", "type": task_type, "error": result["error"]}
                self.award_points(20, "photoshoot_done")
                return {"status": "ok", "type": task_type, "style": style, "result": result}

            # ── PDF report ────────────────────────────────────────────────────
            elif task_type in ("ads_report", "ads_pdf_report"):
                audit_markdown = params.get("audit_markdown", "")
                output_path = params.get("output_path", "output/ads_reports/audit_report.pdf")
                # generate_report.py takes a positional input + --output
                # (not --input, which doesn't exist on its argparse).
                result = self._run_script(
                    "generate_report.py",
                    [audit_markdown, "--output", output_path]
                )
                if "error" in result:
                    self.deduct_points(15, "pdf_report_failed")
                    return {"status": "error", "type": task_type, "error": result["error"]}
                self.award_points(25, "pdf_report_done")
                return {"status": "ok", "type": task_type, "report": result}

            else:
                return {"status": "error", "error": f"Unknown ads task type: {task_type}"}

        except Exception as e:
            logger.error(f"[VECTOR][ads] {task_type} failed: {e}")
            self.deduct_points(30, f"ads_{task_type}_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    async def _test():
        agent = AdsOrchestratorAgent()
        result = await agent.run({"type": "ads_math", "params": {
            "metrics": {"budget": 5000, "clicks": 2500, "conversions": 75, "revenue": 22500, "margin": 0.35}
        }})
        print("OK: AdsOrchestratorAgent" if result["status"] == "ok" else f"FAILED: {result}")
        print(result.get("calculations", result))

    asyncio.run(_test())
