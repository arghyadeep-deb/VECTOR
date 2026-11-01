
import asyncio
import datetime
import json
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

class WorkflowOptimizer(AgentBase):
    """
    Process improvement agent — applies Lean/Six Sigma thinking to analyze
    workflows for bottlenecks, generate optimized SOPs, recommend automation
    opportunities, and calculate ROI of optimizations.
    RULE 11: local models only — never Claude API at runtime.
    """

    DEFAULT_HOURLY_RATE = 500.0  # INR per hour — configurable

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="WorkflowOptimizer",
            district="qa",
            generation=generation,
        )
        self.capabilities = ["analyze", "automate", "low", "optimize", "qa", "roi", "sop", "workflow"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info(f"[VECTOR][workflow_optimizer] initialized gen={generation}")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float = 30.0) -> str:
        from core.prompt_library import get_library as _gl
        _sys = _gl().get_for_agent("workflow_optimizer") or ""
        messages = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
        return chat(self._model, messages, timeout=timeout)

    # ── Core workflow methods ─────────────────────────────────────────────────

    def analyze_workflow(
        self,
        steps: list[str],
        times_minutes: list[float] | None = None,
    ) -> dict:
        """
        Lean analysis: identifies bottlenecks, waste, and automation candidates.
        Returns {bottleneck_step, waste_pct, efficiency_score, opportunities}.
        """
        if not steps:
            return {
                "bottleneck_step": None,
                "waste_pct": 0.0,
                "efficiency_score": 0,
                "opportunities": [],
                "note": "No steps provided",
            }

        n = len(steps)

        # If times provided, find bottleneck by longest duration
        if times_minutes and len(times_minutes) == n:
            max_time = max(times_minutes)
            bottleneck_idx = times_minutes.index(max_time)
            bottleneck_step = steps[bottleneck_idx]
            total_time = sum(times_minutes)
            avg_time = total_time / n if n > 0 else 0
            # Waste = steps that take < 10% of average (idle/handoff time heuristic)
            waste_steps = [s for s, t in zip(steps, times_minutes) if t < avg_time * 0.1]
            waste_pct = round(len(waste_steps) / n * 100, 1) if n > 0 else 0.0
            # Efficiency: how far the slowest step is from average
            balance_ratio = avg_time / max_time if max_time > 0 else 1.0
            efficiency_score = int(balance_ratio * 100)
        else:
            # No times — heuristic analysis only
            bottleneck_step = steps[-1] if steps else None  # last step often blocks
            waste_pct = 0.0
            efficiency_score = 60  # unknown without timing data

        # LLM: identify automation candidates
        steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
        prompt = (
            f"Analyze this workflow for automation and waste using Lean thinking:\n{steps_text}\n\n"
            "List up to 5 automation opportunities. For each provide:\n"
            "- step_number (1-indexed integer)\n"
            "- opportunity (short description)\n"
            "- impact: 'high', 'medium', or 'low'\n\n"
            "Respond ONLY with valid JSON array:\n"
            '[{"step_number": 1, "opportunity": "", "impact": "medium"}]'
        )
        raw = self._llm(prompt)
        opportunities: list[dict] = []
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                for item in parsed:
                    step_num = item.get("step_number", 0)
                    step_name = steps[step_num - 1] if 0 < step_num <= n else f"Step {step_num}"
                    opportunities.append({
                        "step": step_name,
                        "opportunity": item.get("opportunity", ""),
                        "impact": item.get("impact", "medium"),
                    })
        except Exception as e:
            logger.warning(f"[VECTOR][workflow_optimizer] automation parse failed: {e}")

        logger.info(
            f"[VECTOR][workflow_optimizer] analyzed {n} steps, "
            f"bottleneck='{bottleneck_step}', efficiency={efficiency_score}%"
        )
        return {
            "total_steps": n,
            "bottleneck_step": bottleneck_step,
            "waste_pct": waste_pct,
            "efficiency_score": efficiency_score,
            "opportunities": opportunities,
            "has_timing_data": times_minutes is not None and len(times_minutes) == n,
        }

    def generate_sop(self, process_name: str, steps: list[str]) -> str:
        """
        Generates a structured Standard Operating Procedure document.
        Returns a markdown string.
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        n = len(steps)

        lines = [
            f"# Standard Operating Procedure: {process_name}",
            "",
            "## Purpose",
            f"This SOP defines the standardized procedure for '{process_name}' "
            "to ensure consistent, repeatable execution with measurable quality.",
            "",
            "## Scope",
            f"Applies to all executions of '{process_name}' within the VECTOR system. "
            "All {n} steps must be completed in sequence unless otherwise noted.",
            "",
            f"**Version:** 1.0  ",
            f"**Created:** {now}  ",
            f"**Author:** VECTOR WorkflowOptimizer  ",
            "",
            "## Prerequisites",
            "- All required inputs are available before starting",
            "- Relevant tools and access permissions are confirmed",
            "- Previous step outputs are verified before proceeding",
            "",
            "## Step-by-Step Procedure",
            "",
        ]

        for i, step in enumerate(steps, 1):
            lines.append(f"### Step {i}: {step}")
            lines.append("")
            lines.append(f"**Action:** Execute '{step}'")
            lines.append("**Owner:** Assigned team member / VECTOR agent")
            lines.append("**Expected Output:** Step completion confirmed")
            lines.append("**Quality Gate:** Verify output before proceeding to next step")
            lines.append("")

        lines += [
            "## Success Metrics",
            "- All steps completed without skipping",
            "- Each quality gate passed",
            "- Total elapsed time within target window",
            "",
            "## Error Handling",
            "- If any step fails: stop, log the failure, notify supervisor",
            "- Do not proceed to the next step until the current step is resolved",
            "- Document all deviations from this SOP",
            "",
            "## Review Cycle",
            "This SOP should be reviewed quarterly or after any process failure.",
            "",
            f"*Generated by VECTOR WorkflowOptimizer | {now}*",
        ]

        logger.info(f"[VECTOR][workflow_optimizer] SOP generated for '{process_name}' ({n} steps)")
        return "\n".join(lines)

    def recommend_automations(self, workflow_description: str) -> list[dict]:
        """
        LLM identifies automation opportunities from a free-text workflow description.
        Returns [{step, tool, estimated_time_saved_pct, complexity}].
        """
        prompt = (
            f"You are a Lean Six Sigma expert. Analyze this workflow description:\n\n"
            f"{workflow_description}\n\n"
            "Identify up to 6 automation opportunities. For each provide:\n"
            "- step: the specific step or activity to automate\n"
            "- tool: best tool/technology to automate it (be specific: e.g. 'Python script', 'GitHub Actions', 'Playwright')\n"
            "- estimated_time_saved_pct: integer 1-90 (% of time saved for that step)\n"
            "- complexity: 'low', 'medium', or 'high'\n\n"
            "Respond ONLY with a valid JSON array:\n"
            '[{"step": "", "tool": "", "estimated_time_saved_pct": 50, "complexity": "medium"}]'
        )

        raw = self._llm(prompt, timeout=40.0)
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                automations = json.loads(raw[start:end])
                # Validate and clip values
                for a in automations:
                    pct = a.get("estimated_time_saved_pct", 0)
                    a["estimated_time_saved_pct"] = max(1, min(90, int(pct)))
                    if a.get("complexity") not in ("low", "medium", "high"):
                        a["complexity"] = "medium"
                logger.info(f"[VECTOR][workflow_optimizer] {len(automations)} automation recommendations")
                return automations
        except Exception as e:
            logger.warning(f"[VECTOR][workflow_optimizer] automation LLM parse failed: {e}")

        # Fallback
        return [{
            "step": "Manual data processing",
            "tool": "Python script",
            "estimated_time_saved_pct": 50,
            "complexity": "medium",
        }]

    def calculate_roi(
        self,
        current_time_hours: float,
        optimized_time_hours: float,
        hourly_rate: float = DEFAULT_HOURLY_RATE,
    ) -> dict:
        """
        ROI of optimization: time saved, money saved monthly, payback period.
        Returns {time_saved_hours, time_saved_pct, money_saved_monthly, payback_period_days}.
        """
        if current_time_hours <= 0:
            return {"error": "current_time_hours must be > 0"}

        time_saved_hours = max(0.0, current_time_hours - optimized_time_hours)
        time_saved_pct = round(time_saved_hours / current_time_hours * 100, 1)

        # Assume this process runs once daily on workdays (22 working days/month)
        workdays_per_month = 22
        money_saved_monthly = round(time_saved_hours * hourly_rate * workdays_per_month, 2)

        # Payback period: assume 8 hours of engineering time at same rate to implement
        implementation_cost = 8 * hourly_rate
        if money_saved_monthly > 0:
            payback_days = round(implementation_cost / (money_saved_monthly / workdays_per_month), 1)
        else:
            payback_days = float("inf")

        roi_label = "Excellent" if time_saved_pct >= 50 else ("Good" if time_saved_pct >= 25 else "Marginal")

        logger.info(
            f"[VECTOR][workflow_optimizer] ROI: saved {time_saved_hours:.1f}h "
            f"({time_saved_pct}%), INR {money_saved_monthly}/month"
        )
        return {
            "current_time_hours": current_time_hours,
            "optimized_time_hours": optimized_time_hours,
            "time_saved_hours": round(time_saved_hours, 2),
            "time_saved_pct": time_saved_pct,
            "hourly_rate_inr": hourly_rate,
            "money_saved_monthly_inr": money_saved_monthly,
            "implementation_cost_inr": implementation_cost,
            "payback_period_days": payback_days,
            "roi_label": roi_label,
        }

    # ── run dispatch ──────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "analyze")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "analyze":
                steps = task.get("steps", [])
                times = task.get("times_minutes")
                result = self.analyze_workflow(steps, times)
                self._get_memory().store(
                    event_type="workflow_analysis",
                    content=f"Analyzed {result['total_steps']}-step workflow, efficiency={result['efficiency_score']}%",
                    tags=["qa", "workflow", "lean"],
                    source="workflow_optimizer",
                )
                self.award_points(30, "analysis_done")
                return {"status": "ok", "result": result}

            elif task_type == "sop":
                process_name = task.get("process_name", "Process")
                steps = task.get("steps", [])
                sop = self.generate_sop(process_name, steps)
                self.award_points(35, "sop_generated")
                return {"status": "ok", "sop": sop}

            elif task_type == "automate":
                description = task.get("workflow_description", task.get("description", ""))
                if not description:
                    return {"status": "error", "error": "task.workflow_description is required"}
                automations = self.recommend_automations(description)
                self.award_points(30, "automation_recommendations_done")
                return {"status": "ok", "automations": automations}

            elif task_type == "roi":
                current = float(task.get("current_time_hours", 0))
                optimized = float(task.get("optimized_time_hours", 0))
                rate = float(task.get("hourly_rate", self.DEFAULT_HOURLY_RATE))
                if current <= 0:
                    return {"status": "error", "error": "task.current_time_hours must be > 0"}
                result = self.calculate_roi(current, optimized, rate)
                self.award_points(20, "roi_calculated")
                return {"status": "ok", "result": result}

            else:
                steps = task.get("steps", [])
                result = self.analyze_workflow(steps)
                self.award_points(30, "analysis_done")
                return {"status": "ok", "result": result}

        except Exception as e:
            logger.error("[VECTOR][workflow_optimizer] {}", e)
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = WorkflowOptimizer()
        assert agent.health_points == 500

        # Test analyze_workflow with timing data
        steps = ["Gather requirements", "Write code", "Code review", "QA testing", "Deploy"]
        times = [30.0, 120.0, 45.0, 60.0, 15.0]
        analysis = agent.analyze_workflow(steps, times)
        assert "bottleneck_step" in analysis and "efficiency_score" in analysis
        assert analysis["bottleneck_step"] == "Write code"  # longest step
        print(f"  analyze_workflow: bottleneck='{analysis['bottleneck_step']}', efficiency={analysis['efficiency_score']}%")

        # Test analyze_workflow without timing
        analysis_no_time = agent.analyze_workflow(steps)
        assert "bottleneck_step" in analysis_no_time
        print(f"  analyze_workflow (no times): efficiency={analysis_no_time['efficiency_score']}%")

        # Test generate_sop
        sop = agent.generate_sop("Code Release Process", steps)
        assert "Standard Operating Procedure" in sop
        assert "Step 1:" in sop
        assert "Step 5:" in sop
        print(f"  generate_sop: {len(sop)} chars")

        # Test calculate_roi
        roi = agent.calculate_roi(4.0, 1.5, 500.0)
        assert roi["time_saved_hours"] == 2.5
        assert roi["time_saved_pct"] == 62.5
        assert roi["money_saved_monthly_inr"] > 0
        print(f"  calculate_roi: saved={roi['time_saved_hours']}h, INR {roi['money_saved_monthly_inr']}/month")

        # Test run dispatch
        result = await agent.run({"type": "analyze", "steps": steps, "times_minutes": times})
        assert result["status"] == "ok"
        print(f"[OK] status={result['status']}")
        print("workflow_optimizer.py OK")

    asyncio.run(_smoke())
