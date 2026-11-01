"""
RapidPrototyper — Ultra-fast proof-of-concept development.

Selects fastest viable tech, generates boilerplate, focuses on validating
the core assumption in minimum time.
"""

import asyncio
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

# Stack selection heuristics: keyword → recommended stack
# Each entry: keyword_signals → {stack, why, estimated_time_hours, tools}
_STACK_RULES: list[tuple[list[str], dict]] = [
    (
        ["api", "rest", "backend", "fastapi", "endpoint", "server"],
        {
            "stack": "FastAPI + SQLite + httpx",
            "why": "Fastest Python API: auto-docs, async, minimal setup, no ORM needed for POC",
            "estimated_time_hours": 2,
            "tools": ["fastapi", "uvicorn", "httpx", "sqlite3"],
        },
    ),
    (
        ["scrape", "crawl", "playwright", "browser", "selenium"],
        {
            "stack": "Playwright + httpx",
            "why": "Playwright handles JS-heavy sites; httpx for lightweight scraping",
            "estimated_time_hours": 1,
            "tools": ["playwright", "httpx", "asyncio"],
        },
    ),
    (
        ["ml", "model", "train", "predict", "classify", "nlp", "embedding"],
        {
            "stack": "Ollama (local) + FastAPI",
            "why": "No cloud cost; Ollama gives instant inference for POC; FastAPI for serving",
            "estimated_time_hours": 3,
            "tools": ["ollama", "fastapi", "pydantic"],
        },
    ),
    (
        ["dashboard", "ui", "frontend", "streamlit", "visualization", "chart"],
        {
            "stack": "Streamlit + pandas + plotly",
            "why": "Streamlit is the fastest Python dashboard — zero HTML/JS needed for POC",
            "estimated_time_hours": 2,
            "tools": ["streamlit", "pandas", "plotly"],
        },
    ),
    (
        ["bot", "discord", "telegram", "whatsapp", "message", "chat"],
        {
            "stack": "FastAPI webhook + httpx",
            "why": "Webhook receiver is simpler than polling for POC; FastAPI handles it in <50 lines",
            "estimated_time_hours": 1,
            "tools": ["fastapi", "httpx", "pydantic"],
        },
    ),
    (
        ["cli", "command", "terminal", "argparse", "script"],
        {
            "stack": "Python click + typer",
            "why": "Typer wraps Click with type annotations — fastest CLI POC in Python",
            "estimated_time_hours": 1,
            "tools": ["typer", "rich"],
        },
    ),
    (
        ["agent", "llm", "langchain", "langgraph", "autonomous"],
        {
            "stack": "LangGraph + Ollama (local)",
            "why": "LangGraph for state machines; Ollama for zero-cost local inference",
            "estimated_time_hours": 3,
            "tools": ["langgraph", "langchain", "ollama"],
        },
    ),
    (
        ["database", "sql", "postgres", "sqlite", "store", "persist"],
        {
            "stack": "SQLite + Python stdlib",
            "why": "SQLite needs zero setup, ships with Python — fastest data POC",
            "estimated_time_hours": 1,
            "tools": ["sqlite3", "pathlib"],
        },
    ),
    (
        ["worker", "queue", "background", "task", "job", "schedule"],
        {
            "stack": "APScheduler + asyncio",
            "why": "APScheduler handles cron + interval jobs; asyncio for concurrent workers",
            "estimated_time_hours": 2,
            "tools": ["apscheduler", "asyncio"],
        },
    ),
]

# Default stack when no heuristic matches
_DEFAULT_STACK = {
    "stack": "FastAPI + SQLite",
    "why": "Safe default: async, typed, auto-docs, zero-setup storage",
    "estimated_time_hours": 2,
    "tools": ["fastapi", "uvicorn", "sqlite3", "pydantic"],
}

def _match_stack(requirements: str) -> dict:
    """Match requirements text against stack rules, return best match."""
    req_lower = requirements.lower()
    best: dict | None = None
    best_score = 0
    for signals, stack_info in _STACK_RULES:
        score = sum(1 for sig in signals if sig in req_lower)
        if score > best_score:
            best_score = score
            best = stack_info
    return dict(best) if best and best_score > 0 else dict(_DEFAULT_STACK)

class RapidPrototyper(AgentBase):
    """Ultra-fast POC development — validates core assumption in minimum time."""

    def __init__(self):
        super().__init__(
            agent_id="rapid_proto_001",
            name="RapidPrototyper",
            district="coding",
        )
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["stack_select", "plan", "analyze", "status"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][rapid_prototyper] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def select_stack(self, requirements: str) -> dict:
        """Given requirements text, return fastest viable tech stack.

        Returns:
            {
                stack: str,
                why: str,
                estimated_time_hours: int,
                tools: list[str],
                matched_signals: list[str],
            }
        Never raises.
        """
        try:
            stack_info = _match_stack(requirements)
            req_lower = requirements.lower()

            # Collect matched signals for transparency
            matched_signals: list[str] = []
            for signals, _ in _STACK_RULES:
                matched_signals.extend([s for s in signals if s in req_lower])
            matched_signals = list(set(matched_signals))

            result = {**stack_info, "matched_signals": matched_signals}

            self._get_memory().store(
                event_type="select_stack",
                content=f"stack={stack_info['stack']} signals={matched_signals}",
                tags=["prototype", "stack_select"],
                source="rapid_prototyper",
            )

            self.award_points(15, "stack_selected")
            logger.info(
                f"[VECTOR][rapid_prototyper] select_stack: "
                f"stack={stack_info['stack']} hours={stack_info['estimated_time_hours']}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][rapid_prototyper] select_stack error: {e}")
            self.deduct_points(10, "select_stack_failed")
            return {
                "stack": "Python stdlib",
                "why": f"Error during selection: {e}",
                "estimated_time_hours": 1,
                "tools": [],
                "matched_signals": [],
            }

    def generate_prototype_plan(self, idea: str, time_budget_hours: int = 2) -> dict:
        """Break POC into must-have/nice-to-have, generate file structure + steps.

        Returns:
            {
                idea: str,
                time_budget_hours: int,
                stack: dict,
                must_have: list[str],
                nice_to_have: list[str],
                file_structure: list[str],
                implementation_steps: list[str],
                core_hypothesis: str,
                timestamp: str,
            }
        Never raises.
        """
        try:
            stack = self.select_stack(idea)
            tools_str = ", ".join(stack.get("tools", []))

            # Simple heuristic-based plan (no LLM required for instant response)
            idea_lower = idea.lower()

            # Core hypothesis: the one thing this POC must prove
            core_hypothesis = f"Verify that {idea.strip()} is technically feasible in {time_budget_hours}h"

            # Must-haves: the minimal feature set
            must_have = [
                "Working entry point that runs end-to-end",
                "Core business logic (no error handling edge cases)",
                "One happy-path test / smoke script",
                f"Uses {stack['stack']} — no deviations",
            ]

            # Nice-to-haves: polish that doesn't validate the hypothesis
            nice_to_have = [
                "Error handling beyond happy path",
                "Documentation / README",
                "Tests beyond smoke test",
                "UI polish / logging verbosity",
                "Deployment / containerization",
            ]

            # File structure: minimal scaffold
            if "fastapi" in idea_lower or "api" in idea_lower:
                file_structure = [
                    "proto/",
                    "proto/main.py      # FastAPI app + routes",
                    "proto/schema.py    # Pydantic models",
                    "proto/db.py        # SQLite setup",
                    "proto/smoke.py     # end-to-end test script",
                ]
            elif "streamlit" in idea_lower or "dashboard" in idea_lower:
                file_structure = [
                    "proto/",
                    "proto/app.py       # Streamlit dashboard",
                    "proto/data.py      # data loading / transforms",
                    "proto/smoke.py     # headless smoke check",
                ]
            elif "cli" in idea_lower or "script" in idea_lower:
                file_structure = [
                    "proto/",
                    "proto/cli.py       # Typer CLI entry point",
                    "proto/core.py      # business logic",
                    "proto/smoke.py     # arg smoke test",
                ]
            else:
                file_structure = [
                    "proto/",
                    "proto/main.py      # entry point",
                    "proto/core.py      # core logic",
                    "proto/smoke.py     # smoke test",
                ]

            # Implementation steps: time-boxed
            minutes_each = max(15, (time_budget_hours * 60) // 5)
            implementation_steps = [
                f"[{minutes_each}m] Set up {stack['stack']} — install {tools_str}",
                f"[{minutes_each}m] Implement core_logic.py — only the happy path",
                f"[{minutes_each}m] Wire entry point — run the thing end-to-end",
                f"[{minutes_each}m] Write smoke test — assert it works",
                f"[{minutes_each}m] Demo / record output — validate hypothesis",
            ]

            result = {
                "idea": idea,
                "time_budget_hours": time_budget_hours,
                "stack": stack,
                "core_hypothesis": core_hypothesis,
                "must_have": must_have,
                "nice_to_have": nice_to_have,
                "file_structure": file_structure,
                "implementation_steps": implementation_steps,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            self._get_memory().store(
                event_type="generate_prototype_plan",
                content=f"idea={idea[:80]} hours={time_budget_hours} stack={stack['stack']}",
                tags=["prototype", "plan"],
                source="rapid_prototyper",
            )

            self.award_points(30, "prototype_plan_generated")
            logger.info(
                f"[VECTOR][rapid_prototyper] generate_prototype_plan: "
                f"hours={time_budget_hours} stack={stack['stack']}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][rapid_prototyper] generate_prototype_plan error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "idea": idea,
                "time_budget_hours": time_budget_hours,
                "error": str(e),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

    async def analyze_requirements(self, requirements: str) -> dict:
        """LLM call to identify core hypothesis, riskiest assumption, minimum viable proof.

        Returns:
            {
                core_hypothesis: str,
                riskiest_assumption: str,
                minimum_viable_proof: str,
                recommended_time_hours: int,
            }
        Never raises.
        """
        try:
            # RULE 1 — hydrate before LLM call
            try:
                from core.loop.context_engine import ContextEngine
                ctx = ContextEngine()
                hydration = ctx.session_hydration_prompt({"task": "analyze_requirements"})
            except Exception:
                hydration = "You are VECTOR, an autonomous personal AI assistant."

            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("rapid_prototyper") or ""
            _rp_sys = (hydration + "\n\n" + _lib).strip() if _lib else hydration
            messages = [
                {"role": "system", "content": _rp_sys},
                {
                    "role": "user",
                    "content": (
                        "You are RapidPrototyper. Analyze this project requirement and respond with "
                        "a JSON object with exactly these keys:\n"
                        "- core_hypothesis: the one thing the POC must prove (1 sentence)\n"
                        "- riskiest_assumption: the biggest technical unknown (1 sentence)\n"
                        "- minimum_viable_proof: the simplest output that proves the hypothesis (1 sentence)\n"
                        "- recommended_time_hours: integer hours for a focused POC (1-8)\n\n"
                        f"REQUIREMENT: {requirements}\n\n"
                        "Respond with ONLY the JSON object, no explanation."
                    ),
                },
            ]

            raw = chat(model=self._model, messages=messages, timeout=30.0)

            # Parse JSON from response
            import json
            import re
            result: dict = {}
            json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError as e:
                    logger.debug("[VECTOR][rapid_prototyper] failed to parse JSON block: {}", e)

            # Fallback if LLM or parse failed
            if not result:
                logger.warning("[VECTOR][rapid_prototyper] LLM analyze_requirements fallback")
                result = {
                    "core_hypothesis": f"Can we implement '{requirements[:60]}' in minimal code?",
                    "riskiest_assumption": "The core algorithm works as expected without edge cases",
                    "minimum_viable_proof": "A script that runs end-to-end on one example input",
                    "recommended_time_hours": 2,
                }

            self._get_memory().store(
                event_type="analyze_requirements",
                content=f"req={requirements[:80]} hypothesis={str(result.get('core_hypothesis',''))[:80]}",
                tags=["prototype", "requirements_analysis"],
                source="rapid_prototyper",
            )

            self.award_points(30, "requirements_analyzed")
            logger.info(
                f"[VECTOR][rapid_prototyper] analyze_requirements: "
                f"hours={result.get('recommended_time_hours')}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][rapid_prototyper] analyze_requirements error: {e}")
            self.deduct_points(30, "task_failed")
            return {
                "core_hypothesis": "Unknown",
                "riskiest_assumption": "Unknown",
                "minimum_viable_proof": "Unknown",
                "recommended_time_hours": 2,
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # run() — multi-task dispatcher
    # ------------------------------------------------------------------

    async def answer_question(self, query: str) -> str:
        """Answer a free-text question directly, grounded in
        RapidPrototyper's role. Used by run() when a real chat query is
        present but no stack_select/plan/analyze was explicitly requested."""
        try:
            sys_prompt = (
                "You are RapidPrototyper, VECTOR's ultra-fast POC development "
                "agent. You select the fastest viable tech stack for a given "
                "idea, generate prototype plans (must-haves, file structure, "
                "time-boxed steps), and analyze requirements for core hypothesis "
                "and riskiest assumptions. Answer the user's question directly "
                "and concisely."
            )
            answer = chat(
                model=self._model,
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": query}],
                timeout=30.0,
            )
            self.award_points(10, "rapid_prototyper_qa_answered")
            return answer or "I don't have enough information to answer that right now."
        except Exception as e:
            logger.error(f"[VECTOR][rapid_prototyper] answer_question error: {e}")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        """Dispatch task types: stack_select | plan | analyze | status."""
        try:
            task_type = task.get("type", "")
            p = task.get("params", {}) if isinstance(task.get("params"), dict) else {}
            # 2026-07-29: real chat dispatch puts the user's actual text at
            # task["params"]["query"] — none of the branches below looked
            # there, so a real free-text idea/question landing here with no
            # "type" (default was "plan") or with "type":"plan" but no
            # top-level "idea"/"requirements" key always hit the
            # "Missing 'idea' parameter" error. Use the real query text as a
            # fallback idea/requirements value everywhere it's read below —
            # RapidPrototyper's whole job is "given free text, propose a
            # plan", so this is the correct grounded behavior, not just a
            # patch to avoid a stub.
            query = (
                p.get("query") or p.get("content") or task.get("query")
                or task.get("prompt") or ""
            )

            if not task_type:
                task_type = "plan" if query.strip() else "status"

            if task_type == "stack_select":
                requirements = task.get("requirements", task.get("req", "")) or query
                if not requirements:
                    return {"status": "error", "error": "Missing 'requirements' parameter"}
                result = self.select_stack(requirements)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "plan":
                idea = task.get("idea", task.get("requirements", "")) or query
                if not idea:
                    return {"status": "error", "error": "Missing 'idea' parameter"}
                hours = int(task.get("time_budget_hours", task.get("hours", 2)))
                result = self.generate_prototype_plan(idea, hours)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "analyze":
                requirements = task.get("requirements", task.get("req", "")) or query
                if not requirements:
                    return {"status": "error", "error": "Missing 'requirements' parameter"}
                result = await self.analyze_requirements(requirements)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif query.strip():
                # Unmatched task_type (e.g. "status") but a real free-text
                # question is present — answer it instead of returning the
                # content-free capabilities stub.
                answer = await self.answer_question(query)
                return {"status": "ok", "response": answer, "agent": self.name}

            else:
                # Default: status
                return {
                    "status": "ok",
                    "agent": self.name,
                    "district": self.district,
                    "hp": self.health_points,
                    "model": self._model,
                    "capabilities": ["stack_select", "plan", "analyze"],
                }

        except Exception as e:
            logger.error(f"[VECTOR][rapid_prototyper] run error: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = RapidPrototyper()

        # 1. stack_select
        result = await agent.run({
            "type": "stack_select",
            "requirements": "build a REST API for tracking student attendance",
        })
        assert result["status"] == "ok", f"stack_select failed: {result}"
        assert "stack" in result
        assert "estimated_time_hours" in result
        print(f"[OK] stack_select: stack={result['stack']} hours={result['estimated_time_hours']}")

        # 2. plan
        result2 = await agent.run({
            "type": "plan",
            "idea": "build a CLI tool that summarizes PDF papers using local Ollama",
            "time_budget_hours": 3,
        })
        assert result2["status"] == "ok", f"plan failed: {result2}"
        assert "must_have" in result2
        assert "implementation_steps" in result2
        assert "core_hypothesis" in result2
        print(
            f"[OK] plan: stack={result2['stack']['stack']} "
            f"must_have={len(result2['must_have'])} steps={len(result2['implementation_steps'])}"
        )

        # 3. status
        result3 = await agent.run({"type": "status"})
        assert result3["status"] == "ok"
        print(f"[OK] run: status={result3['status']}")
        print("rapid_prototyper.py OK")

    asyncio.run(_smoke())
