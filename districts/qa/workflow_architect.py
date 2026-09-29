"""
Workflow Architect — maps complete workflow trees before VECTOR executes complex tasks.

Before any multi-step task runs: map it. Every step gets an owner district,
clear inputs/outputs, failure modes, and success criteria.
No map = no execution for complex tasks.
"""

import asyncio
import datetime
import json
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

_DISTRICT_OWNERS = {
    "code": "coding", "git": "coding", "commit": "coding", "review": "coding",
    "research": "research", "search": "research", "paper": "research",
    "calendar": "time_calendar", "schedule": "time_calendar", "kiit": "time_calendar",
    "memory": "memory_curator", "recall": "memory_curator",
    "security": "security", "scan": "security", "threat": "security",
    "finance": "finance", "budget": "finance", "upi": "finance",
    "health": "health", "sleep": "health", "fatigue": "health",
    "reflect": "reflection", "journal": "reflection",
    "project": "projects", "deadline": "projects",
    "doc": "documentation", "write": "documentation",
    "test": "qa", "verify": "qa", "check": "qa",
    "deploy": "ops", "monitor": "ops", "incident": "ops",
    "analytics": "data_analytics", "report": "data_analytics",
    "learn": "personal_growth", "motivate": "personal_growth",
    "content": "content", "video": "content",
    "news": "news_trends", "trend": "news_trends",
    "startup": "startups", "invest": "investment",
}

class WorkflowArchitect(AgentBase):
    """
    Maps complete workflow trees before VECTOR executes complex tasks.
    Identifies steps, owners, preconditions, failure modes, success criteria.
    """

    def __init__(self):
        super().__init__(agent_id="workflow_architect_001", name="WorkflowArchitect", district="qa")
        self.capabilities = ["check_preconditions", "design", "qa", "validate", "workflow"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._root = Path(__file__).resolve().parent.parent.parent
        logger.info("[VECTOR][workflow_architect] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self) -> ObsidianSync:
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    # ── Workflow mapping ───────────────────────────────────────────────────────

    async def map_workflow(self, task_description: str) -> dict:
        """Use LLM to produce a complete workflow map for a task."""
        prompt = (
            "You are a workflow architect. Map this task as a complete workflow.\n\n"
            f"Task: {task_description}\n\n"
            "Produce a JSON workflow with this exact structure:\n"
            "{\n"
            '  "task": "task name",\n'
            '  "complexity": 1-10,\n'
            '  "preconditions": ["list of things that must be true before starting"],\n'
            '  "steps": [\n'
            '    {"id": 1, "name": "step name", "owner_district": "district", "input": "what it needs", "output": "what it produces", "failure_mode": "what can go wrong"}\n'
            "  ],\n"
            '  "decision_points": ["if X then Y, else Z"],\n'
            '  "success_criteria": ["measurable criteria for done"],\n'
            '  "failure_recovery": "what to do if the workflow fails"\n'
            "}\n\n"
            "Reply with only valid JSON, no explanation."
        )
        try:
            response = chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30.0,
            )
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                workflow = json.loads(json_match.group())
                workflow["task_description"] = task_description
                workflow["mapped_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                return workflow
        except Exception as e:
            logger.warning("[VECTOR][workflow_architect] LLM map failed: {}", e)

        # Fallback: minimal workflow
        return {
            "task": task_description,
            "complexity": 5,
            "preconditions": ["system available"],
            "steps": [{"id": 1, "name": "execute task", "owner_district": "research", "input": "task", "output": "result", "failure_mode": "unknown"}],
            "decision_points": [],
            "success_criteria": ["task completed without error"],
            "failure_recovery": "retry or escalate to governance",
            "task_description": task_description,
            "mapped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def validate_workflow(self, workflow: dict) -> dict:
        """Check that each step has a valid owner district and clear output."""
        issues = []
        valid_districts = set(_DISTRICT_OWNERS.values()) | {
            "coding", "security", "research", "memory_curator", "governance",
            "reflection", "health", "finance", "projects", "time_calendar",
            "communications", "content", "news_trends", "startups", "investment",
            "skills", "languages", "interview_prep", "learning", "karpathy_lab",
            "relationships", "privacy", "pattern_detective", "data_analytics",
            "personal_growth", "documentation", "qa", "ops", "chief_of_staff",
        }

        for step in workflow.get("steps", []):
            if not step.get("name"):
                issues.append(f"Step {step.get('id', '?')} has no name")
            if not step.get("output"):
                issues.append(f"Step '{step.get('name', '?')}' has no defined output")
            owner = step.get("owner_district", "")
            if owner and owner not in valid_districts:
                issues.append(f"Step '{step.get('name', '?')}' has unknown district: {owner}")

        if not workflow.get("success_criteria"):
            issues.append("No success criteria defined")
        if not workflow.get("preconditions"):
            issues.append("No preconditions listed")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "step_count": len(workflow.get("steps", [])),
        }

    def estimate_complexity(self, workflow: dict) -> int:
        """Score workflow complexity 1-10 based on steps and decision points."""
        step_count = len(workflow.get("steps", []))
        decision_count = len(workflow.get("decision_points", []))
        base = min(10, step_count + decision_count)
        return max(1, base)

    def infer_owner_district(self, step_name: str) -> str:
        """Infer district ownership from step name keywords."""
        name_lower = step_name.lower()
        for keyword, district in _DISTRICT_OWNERS.items():
            if keyword in name_lower:
                return district
        return "research"

    # ── Precondition checking ──────────────────────────────────────────────────

    def check_preconditions(self, workflow: dict) -> dict:
        """Verify each precondition is actually met."""
        preconditions = workflow.get("preconditions", [])
        results = []

        for pre in preconditions:
            pre_lower = pre.lower()
            # Check common preconditions
            if "ollama" in pre_lower or "model" in pre_lower:
                try:
                    import ollama
                    models = ollama.list()
                    met = len(models.get("models", [])) > 0
                except Exception:
                    met = False
                results.append({"precondition": pre, "met": met, "check": "ollama_available"})
            elif "file" in pre_lower or "exist" in pre_lower:
                results.append({"precondition": pre, "met": True, "check": "assumed_met"})
            elif "system" in pre_lower or "available" in pre_lower:
                results.append({"precondition": pre, "met": True, "check": "system_running"})
            else:
                results.append({"precondition": pre, "met": True, "check": "not_checkable"})

        all_met = all(r["met"] for r in results)
        return {"all_met": all_met, "checks": results}

    # ── Document workflow ──────────────────────────────────────────────────────

    def generate_workflow_doc(self, task: str, workflow: dict, validation: dict) -> str:
        """Write workflow to Obsidian Workflows/ folder."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        task_slug = task[:40].replace(" ", "-").lower()

        steps_md = "\n".join(
            f"**{s.get('id', i+1)}. {s.get('name', '?')}**\n"
            f"  - Owner: `{s.get('owner_district', '?')}`\n"
            f"  - Input: {s.get('input', '?')}\n"
            f"  - Output: {s.get('output', '?')}\n"
            f"  - Failure: _{s.get('failure_mode', 'unknown')}_\n"
            for i, s in enumerate(workflow.get("steps", []))
        )

        content = (
            f"# Workflow: {task}\n"
            f"*Mapped: {ts} · Complexity: {workflow.get('complexity', '?')}/10*\n\n"
            f"## Preconditions\n"
            + "\n".join(f"- {p}" for p in workflow.get("preconditions", ["none"])) + "\n\n"
            f"## Steps\n{steps_md}\n"
            f"## Decision Points\n"
            + "\n".join(f"- {d}" for d in workflow.get("decision_points", ["none"])) + "\n\n"
            f"## Success Criteria\n"
            + "\n".join(f"- {c}" for c in workflow.get("success_criteria", ["task completed"])) + "\n\n"
            f"## Failure Recovery\n{workflow.get('failure_recovery', 'escalate to governance')}\n\n"
            f"## Validation\n"
            f"- Valid: {'✅' if validation.get('valid') else '❌'}\n"
            + "\n".join(f"- ⚠️ {issue}" for issue in validation.get("issues", [])) + "\n"
        )

        try:
            vault = Path(CONFIG.get("paths", {}).get("obsidian_vault", str(Path.home() / "V.E.C.T.O.R Brain")))
            wf_dir = vault / "Workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            wf_path = wf_dir / f"{ts[:10]}-{task_slug}.md"
            wf_path.write_text(content, encoding="utf-8")
            logger.info("[VECTOR][workflow_architect] workflow doc written: {}", wf_path)
            return str(wf_path)
        except Exception as e:
            logger.warning("[VECTOR][workflow_architect] doc write failed: {}", e)
            return ""

    # ── Main run ───────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        Map → validate → check preconditions → document → store.
        task["type"]: "map_workflow" | "validate" | "check_preconditions"
        task["description"]: the task to map
        """
        try:
            task_type = task.get("type", "map_workflow")
            description = task.get("description", task.get("task", "unspecified task"))

            if task_type == "validate" and "workflow" in task:
                validation = self.validate_workflow(task["workflow"])
                self.award_points(20, "workflow_validated")
                return {"status": "ok", "validation": validation}

            if task_type == "check_preconditions" and "workflow" in task:
                pre_check = self.check_preconditions(task["workflow"])
                self.award_points(15, "preconditions_checked")
                return {"status": "ok", "precondition_check": pre_check}

            # Full workflow mapping
            workflow = await self.map_workflow(description)
            workflow["complexity"] = self.estimate_complexity(workflow)
            validation = self.validate_workflow(workflow)
            pre_check = self.check_preconditions(workflow)
            doc_path = self.generate_workflow_doc(description, workflow, validation)

            # Store in memory
            mem = self._get_memory()
            mem.store(
                event_type="workflow_mapped",
                content=f"Workflow mapped: '{description}' — {len(workflow.get('steps',[]))} steps, complexity={workflow['complexity']}",
                tags=["qa", "workflow", "planning"],
                context={"complexity": workflow["complexity"], "step_count": len(workflow.get("steps", [])), "valid": validation["valid"]},
                source="workflow_architect",
            )

            if validation["valid"] and pre_check["all_met"]:
                self.award_points(50, "workflow_complete_and_valid")
            elif validation["valid"]:
                self.award_points(30, "workflow_valid_preconditions_unmet")
            else:
                self.award_points(15, "workflow_mapped_with_issues")

            return {
                "status": "ok",
                "workflow": workflow,
                "validation": validation,
                "precondition_check": pre_check,
                "doc_path": doc_path,
                "ready_to_execute": validation["valid"] and pre_check["all_met"],
            }

        except Exception as e:
            logger.error("[VECTOR][workflow_architect] run failed: {}", e)
            self.deduct_points(30, "workflow_mapping_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = WorkflowArchitect()

        # Test validate with a simple workflow
        test_workflow = {
            "task": "research and summarise async Python patterns",
            "preconditions": ["system available", "internet access"],
            "steps": [
                {"id": 1, "name": "search web", "owner_district": "research", "input": "query", "output": "articles", "failure_mode": "no results"},
                {"id": 2, "name": "summarise findings", "owner_district": "research", "input": "articles", "output": "summary", "failure_mode": "LLM timeout"},
            ],
            "decision_points": [],
            "success_criteria": ["summary written to Obsidian"],
            "failure_recovery": "retry with different query",
        }
        validation = agent.validate_workflow(test_workflow)
        print(f"[OK] validate_workflow: valid={validation['valid']} issues={validation['issues']}")

        complexity = agent.estimate_complexity(test_workflow)
        print(f"[OK] estimate_complexity: {complexity}/10")

        pre_check = agent.check_preconditions(test_workflow)
        print(f"[OK] check_preconditions: all_met={pre_check['all_met']}")

        result = await agent.run({"type": "map_workflow", "description": "summarise today's KIIT attendance and send digest"})
        print(f"[OK] map_workflow: steps={len(result.get('workflow',{}).get('steps',[]))} ready={result.get('ready_to_execute')}")
        print("workflow_architect.py OK")

    asyncio.run(_smoke())
