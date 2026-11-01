"""
Module: agents/news_trends/venture_pipeline.py
District: news_trends | Focus: End-to-end side-hustle discovery pipeline (orchestrator)

Chains the whole loop the owner asked for:

  1. MINE     SocialMiner        — real problems from Reddit + HN (30 days)
  2. CLUSTER  ProblemClusterer   — group, rank by demand, flag software-solvable
  3. VALIDATE startups district  — IdeaValidator (market/competition) on top ideas
  4. MODEL    startups district  — RevenueModeler (subscription viability)
  5. DRAFT    content district   — ScriptGenerator marketing scripts (voice/video-ready)
  6. REPORT   data/venture/venture_report_*.md + Obsidian Brain (when available)
  7. NOTIFY   nudge_engine.push(priority 0.85) — spoken aloud by the realtime
              voice layer (Phase 5) when the owner is present

DELIBERATE GATES (nothing publishes or builds without the owner):
  • Content scripts are DRAFTS on disk — posting via content_scheduler/uploader
    only happens after the owner approves.
  • Software build is a RECOMMENDATION — the report names the top idea and the
    exact voice/API command to kick off a code_task through the Governor
    (PermissionGateway classification applies as always).

Scheduled weekly (Mon 07:00) via core/loop/cron_jobs.py::job_venture_pipeline.
On-demand: governor task type "venture_pipeline", or run this file directly.
"""

import sys

__all__ = ["VenturePipeline"]

import datetime
import json
import os
import tempfile
from pathlib import Path

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG


def _atomic_write_text(path: Path, content: str) -> None:
    """Durably replace a report without exposing a partial shared file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


class VenturePipeline(AgentBase):
    """Orchestrates mine -> cluster -> validate -> model -> draft -> report -> notify."""

    def __init__(self):
        super().__init__(
            agent_id="venture_pipeline",
            name="VenturePipeline",
            district="news_trends",
        )
        self.capabilities = ["cluster_problems", "mine_social", "news_trends", "venture_pipeline"]
        vcfg = CONFIG.get("venture", {})
        self.max_ideas = int(vcfg.get("max_validated_ideas", 3))
        self.data_dir = Path(vcfg.get("data_dir", "data/venture"))

    # ── stages 3-4: startups district ─────────────────────────────────────────

    async def _validate_idea(self, cluster: dict) -> dict:
        """IdeaValidator + RevenueModeler on one problem cluster. Never raises."""
        idea = cluster.get("product_idea") or cluster.get("problem", "")
        out: dict = {"idea": idea, "problem": cluster.get("problem", ""),
                     "demand_score": cluster.get("demand_score", 0),
                     "post_count": cluster.get("size", 0)}
        try:
            from districts.startups.idea_validator import IdeaValidator
            v = await IdeaValidator().run({"type": "validate_idea",
                                           "params": {"idea": idea,
                                                      "description": cluster.get("problem", "")}})
            out["validation"] = {k: v[k] for k in v if k != "status"}
            # IdeaValidator signals LLM failure as status "error" / verdict UNVERIFIED;
            # stripping "status" above used to make that look like a real validation.
            out["verified"] = (v.get("status") != "error"
                               and v.get("verdict") not in (None, "", "UNVERIFIED"))
        except Exception as e:
            logger.warning("[VECTOR][venture] IdeaValidator failed: {}", e)
            out["validation"] = {"error": str(e)}
            out["verified"] = False
        try:
            from districts.startups.revenue_modeler import RevenueModeler
            m = await RevenueModeler().run({"type": "model_revenue",
                                            "params": {"idea": idea,
                                                       "model": "subscription"}})
            out["revenue"] = ({"error": m.get("error", "revenue model failed")}
                              if m.get("status") == "error"
                              else {k: m[k] for k in m if k != "status"})
        except Exception as e:
            logger.warning("[VECTOR][venture] RevenueModeler failed: {}", e)
            out["revenue"] = {"error": str(e)}
        return out

    # ── stage 5: marketing drafts ─────────────────────────────────────────────

    async def _draft_content(self, idea: dict) -> dict:
        """Short-form marketing script draft for the top idea. Never raises."""
        try:
            from districts.content.script_generator import ScriptGenerator
            r = await ScriptGenerator().run({
                "type": "generate_script",
                "params": {
                    "topic": idea.get("idea") or idea.get("problem", ""),
                    "format": "short_video",
                    "tone": "problem-solution",
                    "duration_seconds": 45,
                },
            })
            if r.get("status") == "error":
                raise RuntimeError(r.get("error", "script generation failed"))
            return {k: r[k] for k in r if k != "status"}
        except Exception as e:
            logger.warning("[VECTOR][venture] ScriptGenerator failed: {}", e)
            # LLM fallback so the report always has a usable draft
            try:
                fb_prompt = (
                    "Write a 45-second short-video marketing script (hook, problem, "
                    "solution tease, call to action) for this software idea: "
                    f"{idea.get('idea') or idea.get('problem', '')}. Plain text."
                )
                script = self.vchat(fb_prompt)
                # vchat() echoes the prompt back when the LLM is unreachable
                if not (script or "").strip() or script.strip() == fb_prompt.strip():
                    return {"error": f"{e} / LLM fallback returned nothing"}
                return {"script": script, "generator": "vchat_fallback"}
            except Exception as e2:
                return {"error": f"{e} / {e2}"}

    # ── stages 6-7: report + notify ───────────────────────────────────────────

    def _write_report(self, mined: dict, clustered: dict, ideas: list[dict],
                      drafts: list[dict]) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        path = self.data_dir / f"venture_report_{stamp}.md"
        lines = [
            f"# Venture Pipeline Report — {stamp}",
            "",
            f"Mined **{mined.get('count', 0)}** problem posts (30 days, Reddit + HN); "
            f"**{clustered.get('cluster_count', 0)}** clusters, "
            f"**{clustered.get('software_solvable', 0)}** software-solvable.",
            "",
            "## Top validated ideas",
            "",
        ]
        if not any(i.get("verified") for i in ideas):
            lines += ["_No idea could be validated this run (validator unavailable or "
                      "returned nothing usable) — nothing below is recommended._", ""]
        for i, idea in enumerate(ideas, 1):
            if not idea.get("verified"):
                lines += [f"### {i}. [UNVERIFIED] {idea.get('idea') or idea.get('problem', '?')}",
                          "", "- Validation failed — not scored, not recommended.", ""]
                continue
            lines += [
                f"### {i}. {idea.get('idea') or idea.get('problem', '?')}",
                "",
                f"- Problem: {idea.get('problem', '')}",
                f"- Demand: {idea.get('demand_score', 0)} engagement across "
                f"{idea.get('post_count', 0)} posts",
                f"- Validation: `{json.dumps(idea.get('validation', {}), default=str)[:400]}`",
                f"- Revenue model: `{json.dumps(idea.get('revenue', {}), default=str)[:400]}`",
                "",
            ]
        lines += ["## Marketing script drafts (NOT posted — awaiting your approval)", ""]
        if not drafts:
            lines += ["_No draft generated (no verified idea)._", ""]
        for i, d in enumerate(drafts, 1):
            script = str(d.get("script", d))[:1200]
            lines += [f"### Draft {i}", "", "```", script, "```", ""]
        lines += [
            "## Next actions (each requires your explicit go-ahead)",
            "",
            '- Build it: say "fix the bug…"-style code task, e.g. '
            '"VECTOR, start a code task: build an MVP of <idea>".',
            "- Record/publish content: approve a draft and the content district "
            "(voice clone -> video pipeline -> scheduler) takes it from there.",
            "- Deeper validation: ask the intelligence district to run a "
            "social simulation of the target audience.",
            "",
        ]
        report_text = "\n".join(lines)
        _atomic_write_text(path, report_text)
        # Mirror into the Obsidian Brain when the vault is reachable
        try:
            # CONFIG has no "brain" section: the old lookup yielded Path("") and wrote
            # a stray "02 Projects/" into the CWD instead of the vault.
            vault = CONFIG.get("vault_path") or CONFIG.get("obsidian", {}).get("vault_path") or ""
            brain = Path(vault) / "02 Projects"
            if vault and brain.parent.exists():
                brain.mkdir(parents=True, exist_ok=True)
                _atomic_write_text(brain / path.name, report_text)
        except Exception as e:
            logger.warning("[VECTOR][venture] brain mirror failed: {}", e)
        return path

    def _notify(self, ideas: list[dict], report: Path) -> None:
        try:
            from core.loop.nudge_engine import nudge_engine
            top = next((i for i in ideas if i.get("verified")), {})
            nudge_engine.push(
                f"Venture pipeline finished. Top opportunity: "
                f"{(top.get('idea') or top.get('problem', 'none found'))[:120]}. "
                f"Report: {report.name}",
                source="venture_pipeline",
                need="review_venture_report",
                priority=0.85,   # above the 0.7 threshold -> spoken when you're present
            )
        except Exception as e:
            logger.warning("[VECTOR][venture] owner nudge failed: {}", e)

    # ── full pipeline ─────────────────────────────────────────────────────────

    async def execute(self) -> dict:
        from districts.news_trends.social_miner import SocialMiner
        from districts.news_trends.problem_clusterer import ProblemClusterer

        mined = SocialMiner().mine_all()
        if mined.get("status") == "error":
            logger.error("[VECTOR][venture] mining failed: {}", mined.get("error"))
            return {"status": "error", "stage": "mine", "error": mined.get("error", "mining failed"),
                    "mined_posts": 0, "clusters": 0, "validated_ideas": 0, "report": "", "top_idea": ""}
        clustered = ProblemClusterer().analyze(mined.get("posts", []))
        if clustered.get("status") == "error":
            return {"status": "error", "stage": "cluster", "error": clustered.get("error", "clustering failed"),
                    "mined_posts": mined.get("count", 0), "clusters": 0, "validated_ideas": 0,
                    "report": "", "top_idea": ""}

        candidates = [c for c in clustered.get("top_clusters", [])
                      if c.get("software_solvable")][:self.max_ideas]
        ideas = [await self._validate_idea(c) for c in candidates]
        verified = [i for i in ideas if i.get("verified")]
        # draft the top VERIFIED idea only
        drafts = [await self._draft_content(i) for i in verified[:1]]

        report = self._write_report(mined, clustered, ideas, drafts)
        self._notify(ideas, report)
        self.award_points(25, "venture_pipeline_complete")
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="venture_pipeline",
                content=f"Pipeline run: {mined.get('count', 0)} posts -> "
                        f"{len(verified)} validated ideas. Report {report.name}",
                tags=["venture", "side_hustle", "pipeline"],
                source="venture_pipeline",
            )
        except Exception as e:
            logger.warning("[VECTOR][venture] episodic store failed: {}", e)
        status = "partial" if len(verified) < len(ideas) or mined.get("status") == "partial" else "ok"
        return {"status": status, "mined_posts": mined.get("count", 0),
                "clusters": clustered.get("cluster_count", 0),
                "validated_ideas": len(verified),
                "unverified_ideas": len(ideas) - len(verified),
                "report": str(report),
                "top_idea": (verified[0].get("idea") or verified[0].get("problem", ""))
                            if verified else ""}

    async def run(self, task: dict) -> dict:
        return await self.execute()


if __name__ == "__main__":
    import asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    vp = VenturePipeline()
    assert vp.district == "news_trends"
    print("OK venture_pipeline.py (agent init; full run requires network)")
    if "--live" in sys.argv:
        print(asyncio.run(vp.execute()))
