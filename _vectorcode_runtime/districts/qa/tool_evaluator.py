
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

class ToolEvaluator(AgentBase):
    """
    Technology assessment and tool selection for VECTOR's stack.
    Evaluates tools/libraries/frameworks with TCO, adoption cost, stability
    scoring, and a comprehensive comparison matrix.
    RULE 11: local models only — never Claude API at runtime.
    """

    EVALUATION_DIMENSIONS = [
        "functionality",
        "performance",
        "maintainability",
        "community",
        "security",
        "cost",
        "integration_ease",
        "documentation",
    ]

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ToolEvaluator",
            district="qa",
            generation=generation,
        )
        self.capabilities = ["adoption_cost", "compare", "evaluate", "qa", "report", "tool_eval"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info(f"[VECTOR][tool_evaluator] initialized gen={generation}")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float = 30.0) -> str:
        """Single-shot LLM call with fallback to empty string."""
        from core.prompt_library import get_library as _gl
        _sys = _gl().get_for_agent("tool_evaluator") or ""
        messages = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
        return chat(self._model, messages, timeout=timeout)

    # ── Core evaluation methods ───────────────────────────────────────────────

    def evaluate_tool(
        self,
        tool_name: str,
        use_case: str,
        alternatives: list[str] | None = None,
    ) -> dict:
        """
        LLM-driven evaluation of a single tool.
        Returns {scores: {dimension: 0-10}, total_score, verdict, risks, recommendation}.
        """
        alts_text = (
            f"Known alternatives: {', '.join(alternatives)}" if alternatives else "No alternatives specified."
        )
        prompt = (
            f"Evaluate the tool/library '{tool_name}' for the use case: '{use_case}'.\n"
            f"{alts_text}\n\n"
            f"Score it on each dimension from 0 to 10 (integer only):\n"
            + "\n".join(f"- {dim}" for dim in self.EVALUATION_DIMENSIONS)
            + "\n\n"
            "Then provide:\n"
            "- verdict: one of 'Recommended', 'Conditional', 'Not Recommended'\n"
            "- risks: top 3 risks as a semicolon-separated list\n"
            "- recommendation: one concise paragraph\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            '{"scores": {"functionality": 0, "performance": 0, "maintainability": 0, '
            '"community": 0, "security": 0, "cost": 0, "integration_ease": 0, "documentation": 0}, '
            '"verdict": "", "risks": "", "recommendation": ""}'
        )

        raw = self._llm(prompt)
        try:
            # Extract JSON block
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            scores = {dim: int(data.get("scores", {}).get(dim, 5)) for dim in self.EVALUATION_DIMENSIONS}
            total_score = round(sum(scores.values()) / len(scores), 2)
            return {
                "tool": tool_name,
                "use_case": use_case,
                "scores": scores,
                "total_score": total_score,
                "verdict": data.get("verdict", "Conditional"),
                "risks": data.get("risks", "Unknown"),
                "recommendation": data.get("recommendation", "Consult documentation before adopting."),
            }
        except Exception as e:
            logger.warning(f"[VECTOR][tool_evaluator] LLM parse failed for '{tool_name}': {e}")
            # Fallback: default mid scores
            scores = {dim: 5 for dim in self.EVALUATION_DIMENSIONS}
            return {
                "tool": tool_name,
                "use_case": use_case,
                "scores": scores,
                "total_score": 5.0,
                "verdict": "Conditional",
                "risks": "LLM evaluation unavailable — manual review required",
                "recommendation": f"Evaluate '{tool_name}' manually against VECTOR's stack requirements.",
            }

    def compare_tools(self, tools: list[str], use_case: str) -> dict:
        """
        Side-by-side comparison matrix of multiple tools.
        Returns {matrix: {tool: scores}, winner, scores_table, rationale}.
        """
        if not tools:
            return {"error": "No tools provided for comparison", "matrix": {}, "winner": None}

        matrix: dict[str, dict] = {}
        for tool in tools:
            result = self.evaluate_tool(tool, use_case)
            matrix[tool] = {
                "scores": result["scores"],
                "total_score": result["total_score"],
                "verdict": result["verdict"],
            }

        winner = max(matrix.keys(), key=lambda t: matrix[t]["total_score"])

        scores_table = []
        for dim in self.EVALUATION_DIMENSIONS:
            row = {"dimension": dim}
            for tool in tools:
                row[tool] = matrix[tool]["scores"].get(dim, 0)
            scores_table.append(row)

        rationale = (
            f"'{winner}' scored highest with {matrix[winner]['total_score']}/10 across "
            f"{len(self.EVALUATION_DIMENSIONS)} dimensions for use case: '{use_case}'."
        )

        logger.info(f"[VECTOR][tool_evaluator] compare: winner={winner} from {tools}")
        return {
            "tools": tools,
            "use_case": use_case,
            "matrix": matrix,
            "scores_table": scores_table,
            "winner": winner,
            "rationale": rationale,
        }

    def assess_adoption_cost(self, current_stack: list[str], new_tool: str) -> dict:
        """
        Migration effort, learning curve, and integration complexity analysis.
        Returns {migration_effort, learning_curve, integration_complexity, overall_cost, recommendation}.
        """
        stack_str = ", ".join(current_stack) if current_stack else "empty stack"
        prompt = (
            f"Assess the adoption cost of adding '{new_tool}' to an existing stack: [{stack_str}].\n\n"
            "Score each dimension 1-10 (1=trivial, 10=very high cost):\n"
            "- migration_effort: effort to migrate existing code/data\n"
            "- learning_curve: time/effort for the team to learn this tool\n"
            "- integration_complexity: difficulty wiring it into the existing stack\n\n"
            "Provide a one-sentence recommendation.\n\n"
            "Respond ONLY with valid JSON:\n"
            '{"migration_effort": 5, "learning_curve": 5, "integration_complexity": 5, '
            '"recommendation": ""}'
        )

        raw = self._llm(prompt)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            migration = int(data.get("migration_effort", 5))
            learning = int(data.get("learning_curve", 5))
            integration = int(data.get("integration_complexity", 5))
            overall = round((migration + learning + integration) / 3, 1)
            return {
                "new_tool": new_tool,
                "current_stack": current_stack,
                "migration_effort": migration,
                "learning_curve": learning,
                "integration_complexity": integration,
                "overall_cost": overall,
                "cost_label": "High" if overall >= 7 else ("Medium" if overall >= 4 else "Low"),
                "recommendation": data.get("recommendation", f"Evaluate '{new_tool}' adoption carefully."),
            }
        except Exception as e:
            logger.warning(f"[VECTOR][tool_evaluator] adoption cost parse failed: {e}")
            return {
                "new_tool": new_tool,
                "current_stack": current_stack,
                "migration_effort": 5,
                "learning_curve": 5,
                "integration_complexity": 5,
                "overall_cost": 5.0,
                "cost_label": "Medium",
                "recommendation": f"Manual assessment required for '{new_tool}'.",
            }

    def generate_evaluation_report(self, tool: str, use_case: str) -> str:
        """
        Markdown report with executive summary, scoring breakdown, recommendation.
        """
        eval_result = self.evaluate_tool(tool, use_case)
        scores = eval_result["scores"]
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"# Tool Evaluation Report: {tool}",
            f"**Generated:** {now}  ",
            f"**Use Case:** {use_case}  ",
            f"**Verdict:** {eval_result['verdict']}  ",
            f"**Overall Score:** {eval_result['total_score']}/10",
            "",
            "## Executive Summary",
            eval_result["recommendation"],
            "",
            "## Scoring Breakdown",
            "| Dimension | Score | Bar |",
            "|-----------|-------|-----|",
        ]

        for dim in self.EVALUATION_DIMENSIONS:
            score = scores.get(dim, 0)
            bar = "#" * score + "-" * (10 - score)
            lines.append(f"| {dim.replace('_', ' ').title()} | {score}/10 | [{bar}] |")

        lines += [
            "",
            "## Risk Assessment",
            "",
        ]
        risks = eval_result.get("risks", "")
        if risks and risks != "Unknown":
            for i, risk in enumerate(risks.split(";"), 1):
                lines.append(f"{i}. {risk.strip()}")
        else:
            lines.append("No specific risks identified — manual review recommended.")

        lines += [
            "",
            "## Recommendation",
            eval_result["recommendation"],
            "",
            f"*Report generated by VECTOR ToolEvaluator | {now}*",
        ]

        return "\n".join(lines)

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
        task_type = task.get("type", "evaluate")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "evaluate":
                tool = task.get("tool", "")
                use_case = task.get("use_case", "general")
                alts = task.get("alternatives")
                if not tool:
                    return {"status": "error", "error": "task.tool is required for evaluate"}
                result = self.evaluate_tool(tool, use_case, alts)
                self._get_memory().store(
                    event_type="tool_evaluation",
                    content=f"Evaluated '{tool}' for '{use_case}': score={result['total_score']}",
                    tags=["qa", "tool_evaluation"],
                    source="tool_evaluator",
                )
                self.award_points(30, "evaluation_done")
                return {"status": "ok", "result": result}

            elif task_type == "compare":
                tools = task.get("tools", [])
                use_case = task.get("use_case", "general")
                if not tools:
                    return {"status": "error", "error": "task.tools list is required for compare"}
                result = self.compare_tools(tools, use_case)
                self.award_points(40, "comparison_done")
                return {"status": "ok", "result": result}

            elif task_type == "adoption_cost":
                current_stack = task.get("current_stack", [])
                new_tool = task.get("new_tool", task.get("tool", ""))
                if not new_tool:
                    return {"status": "error", "error": "task.new_tool is required for adoption_cost"}
                result = self.assess_adoption_cost(current_stack, new_tool)
                self.award_points(25, "adoption_cost_done")
                return {"status": "ok", "result": result}

            elif task_type == "report":
                tool = task.get("tool", "")
                use_case = task.get("use_case", "general")
                if not tool:
                    return {"status": "error", "error": "task.tool is required for report"}
                report = self.generate_evaluation_report(tool, use_case)
                self.award_points(35, "report_generated")
                return {"status": "ok", "report": report}

            else:
                # default: evaluate
                tool = task.get("tool", "")
                use_case = task.get("use_case", "general")
                result = self.evaluate_tool(tool, use_case)
                self.award_points(30, "evaluation_done")
                return {"status": "ok", "result": result}

        except Exception as e:
            logger.error("[VECTOR][tool_evaluator] {}", e)
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ToolEvaluator()
        assert agent.health_points == 500

        # Test evaluate_tool (LLM may be offline — fallback must still work)
        eval_result = agent.evaluate_tool("fastapi", "REST API backend")
        assert "scores" in eval_result and "total_score" in eval_result
        assert set(eval_result["scores"].keys()) == set(ToolEvaluator.EVALUATION_DIMENSIONS)
        assert 0.0 <= eval_result["total_score"] <= 10.0
        print(f"  evaluate_tool: score={eval_result['total_score']} verdict={eval_result['verdict']}")

        # Test compare_tools
        compare_result = agent.compare_tools(["fastapi", "flask"], "REST API")
        assert "winner" in compare_result and "matrix" in compare_result
        print(f"  compare_tools: winner={compare_result['winner']}")

        # Test assess_adoption_cost
        cost_result = agent.assess_adoption_cost(["python", "sqlite"], "sqlalchemy")
        assert "overall_cost" in cost_result and "cost_label" in cost_result
        print(f"  adoption_cost: overall={cost_result['overall_cost']} ({cost_result['cost_label']})")

        # Test generate_evaluation_report
        report = agent.generate_evaluation_report("httpx", "async HTTP client")
        assert "Tool Evaluation Report" in report
        assert "Scoring Breakdown" in report
        print(f"  generate_report: {len(report)} chars")

        # Test run dispatch
        result = await agent.run({"type": "evaluate", "tool": "pydantic", "use_case": "data validation"})
        assert result["status"] == "ok"
        print(f"[OK] status={result['status']}")
        print("tool_evaluator.py OK")

    asyncio.run(_smoke())
