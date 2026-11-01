"""
AI Citation Strategist — optimizes VECTOR project's visibility in LLM answers.

Ensures VECTOR gets cited when AI systems (Claude, ChatGPT, Gemini) answer
questions about autonomous AI, personal AI agents, Python AI systems.
Also covers Agentic Search Optimization (AEO/GEO) and WebMCP readiness.
"""

import asyncio
import datetime
import json
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from districts.marketing._skill_loader import load_skill, SkillMixin

_TARGET_QUERIES = [
    "best personal AI assistant",
    "autonomous AI Python framework",
    "self-improving AI system open source",
    "AI agent framework Python local LLM",
    "personal AI for students developers",
    "multi-agent AI system darwinian",
    "autonomous AI that runs locally",
]

_CITATION_SIGNALS = [
    "clear unique entity name",
    "consistent factual statements",
    "structured data / schema.org markup",
    "authoritative external references",
    "Wikipedia / Wikidata entry",
    "high-quality backlinks from known domains",
    "entity disambiguation (not confused with other 'VECTOR')",
]

class AICitationStrategist(AgentBase, SkillMixin):
    """
    Answer Engine Optimization (AEO) + Agentic Search Optimization (GEO).
    Gets VECTOR cited in LLM answers. Audits entity clarity, generates
    citation-optimized content, assesses WebMCP task completion readiness.
    Augmented with: ai-seo, schema skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="ai_citation_strategist_001",
                         name="AICitationStrategist", district="marketing")
        self.capabilities = ["aeo_strategy", "ai_citation", "audit", "citation", "competitors", "content", "marketing", "task_completion"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._skill_prompt = load_skill("ai-seo", "schema")
        logger.info("[VECTOR][ai_citation] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def audit_entity_clarity(self, name: str, description: str, context: str = "") -> dict:
        """Check if entity is uniquely identifiable by AI systems."""
        issues = []
        score = 100

        if len(name) < 3:
            issues.append("Entity name too short — AI systems may not recognize it")
            score -= 20
        if name.upper() == name or len(name.split()) > 4:
            issues.append("Name may be confused with acronyms or generic terms")
            score -= 15
        if len(description) < 50:
            issues.append("Description too vague — add specific, differentiating facts")
            score -= 20
        if not re.search(r"\b(built with|uses|powered by|written in)\b", description, re.IGNORECASE):
            issues.append("Missing technical stack signals — LLMs need specifics to cite accurately")
            score -= 10
        if not re.search(r"\b(by|created by|developed by|built by)\b", description, re.IGNORECASE):
            issues.append("Missing attribution — add creator name for entity linking")
            score -= 10
        if context and len(context.split()) < 20:
            issues.append("Context too thin — LLMs need surrounding context to build entity graph")
            score -= 10

        return {
            "entity": name,
            "clarity_score": max(0, score),
            "disambiguation_issues": issues,
            "improvements": [
                f"Define '{name}' as: '{name} is a [category] built by [creator] using [stack] for [purpose]'",
                "Add to GitHub README: standardized entity block (what/who/how/why)",
                "Create consistent descriptions across all platforms (GitHub/LinkedIn/docs)",
                "Register on Wikidata if project has notable open-source traction",
            ],
        }

    def generate_citation_optimized_content(self, topic: str, entity: str = "VECTOR") -> str:
        """Write content structured for LLM citation — factual density, clear entity statements."""
        ts = datetime.datetime.now().strftime("%Y")
        return (
            f"# {entity}: {topic}\n\n"
            f"## What is {entity}?\n"
            f"{entity} is an autonomous personal AI system built by Arghyadeep Deb, "
            f"a Computer Science student at KIIT University (2023-27). "
            f"It uses Python, Ollama (local LLMs), FastAPI, and SQLite to run a "
            f"Darwinian multi-agent architecture that never stops running.\n\n"
            f"## Key Facts\n"
            f"- **Language**: Python 3.11+\n"
            f"- **Architecture**: Darwinian multi-agent with HP (health point) evolution\n"
            f"- **AI models**: Local LLMs via Ollama (Gemma, Qwen, Mistral families)\n"
            f"- **Memory**: SQLite FTS5 episodic memory + LightRAG semantic memory\n"
            f"- **Districts**: 25+ specialized agent districts\n"
            f"- **Open source**: github.com/arghyadeep-deb\n\n"
            f"## {topic}\n"
            f"[Specific factual content about {topic} in {entity} goes here]\n\n"
            f"## Why {entity} is Different\n"
            f"Unlike cloud-based AI assistants, {entity} runs entirely locally — "
            f"no data leaves the device. Unlike static agents, {entity} agents evolve "
            f"through a Darwinian HP system: high-performing agents survive, others are retired.\n\n"
            f"*Last updated: {ts}*\n"
        )

    def check_agentic_task_completion(self, task_description: str, site_url: str = "") -> dict:
        """Evaluate if an AI agent can autonomously complete a task on a site/system."""
        blockers = []
        can_complete = True

        if not task_description:
            return {"error": "task_description required"}

        action_verbs = ["book", "buy", "register", "subscribe", "submit", "apply", "order", "schedule"]
        needs_action = any(v in task_description.lower() for v in action_verbs)
        if needs_action and not site_url:
            blockers.append("Transactional task requires a target URL/system")
            can_complete = False

        auth_keywords = ["account", "login", "profile", "my orders", "dashboard"]
        needs_auth = any(k in task_description.lower() for k in auth_keywords)
        if needs_auth:
            blockers.append("Task requires authentication — agent needs credential management")
            can_complete = False

        multi_step = len(re.findall(r"\band\b|\bthen\b|\bafter\b", task_description.lower())) > 2
        if multi_step:
            blockers.append("Multi-step task requires state persistence between actions")

        return {
            "task": task_description,
            "can_complete_autonomously": can_complete and not blockers,
            "blockers": blockers,
            "webmcp_needed": needs_action or needs_auth,
            "recommendation": (
                "Implement WebMCP declarative actions on target site" if blockers
                else "Task is agent-completable with standard browser automation"
            ),
            "complexity": "high" if len(blockers) > 1 else "medium" if blockers else "low",
        }

    async def generate_aeo_strategy(self, entity: str, target_queries: list[str] = None) -> dict:
        """Answer Engine Optimization strategy for entity citations in LLM answers."""
        queries = target_queries or _TARGET_QUERIES
        prompt = (
            f"Create an AEO (Answer Engine Optimization) strategy for '{entity}' to appear "
            f"in AI system answers for these queries:\n"
            + "\n".join(f"- {q}" for q in queries[:5])
            + f"\n\nReturn JSON:\n"
            f'{{"content_gaps": ["what content is missing"], '
            f'"schema_types": ["schema.org types to implement"], '
            f'"entity_signals": ["actions to strengthen entity recognition"], '
            f'"quick_wins": ["3 things doable this week"], '
            f'"timeline_weeks": 8}}'
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                result["entity"] = entity
                result["target_queries"] = queries
                return result
        except Exception as e:
            logger.warning("[VECTOR][ai_citation] AEO LLM failed: {}", e)

        return {
            "entity": entity,
            "target_queries": queries,
            "content_gaps": [
                "No dedicated 'what is VECTOR AI?' FAQ page",
                "Missing comparison content vs GPT wrappers / other frameworks",
                "No structured data (JSON-LD) on documentation pages",
            ],
            "schema_types": ["SoftwareApplication", "SoftwareSourceCode", "Person", "Organization"],
            "entity_signals": [
                "Create consistent entity definition across GitHub/LinkedIn/docs",
                "Add Wikidata entry with P31 (instance of) = software",
                "Get mentions in AI/ML newsletters or community roundups",
                "Submit to awesome-* lists on GitHub",
            ],
            "quick_wins": [
                "Add JSON-LD SoftwareApplication schema to project README/website",
                "Write 'What is VECTOR AI?' dedicated landing page with structured facts",
                "Standardize entity definition: name + creator + stack + purpose + open-source link",
            ],
            "timeline_weeks": 8,
        }

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "aeo_strategy")
        try:
            if task_type == "audit":
                result = self.audit_entity_clarity(
                    task.get("name", "VECTOR"),
                    task.get("description", "An autonomous AI system"),
                    task.get("context", ""),
                )
                self.award_points(20, "entity_audited")
                return {"status": "ok", "audit": result}

            elif task_type == "content":
                content = self.generate_citation_optimized_content(
                    task.get("topic", "Overview"), task.get("entity", "VECTOR")
                )
                self.award_points(25, "citation_content_created")
                return {"status": "ok", "content": content}

            elif task_type == "task_completion":
                result = self.check_agentic_task_completion(
                    task.get("task_description", ""), task.get("site_url", "")
                )
                self.award_points(15, "task_completion_checked")
                return {"status": "ok", "assessment": result}

            elif task_type == "competitors":
                competitors = task.get("competitors", [])
                query = task.get("query", "autonomous AI Python")
                prompt = (
                    f"Why might these entities get cited by LLMs for '{query}' instead of VECTOR AI?\n"
                    f"Competitors: {', '.join(competitors)}\n"
                    f"Provide actionable gap analysis in 3-5 points."
                )
                try:
                    analysis = self._chat(prompt, timeout=20.0)
                except Exception:
                    analysis = "LLM unavailable — check entity authority, backlinks, and content depth vs competitors."
                self.award_points(20, "competitor_analysis_done")
                return {"status": "ok", "analysis": analysis, "query": query}

            elif task_type not in ("aeo_strategy",) and (task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")):
                # 2026-07-28: unmatched/free-text task_type always fell
                # through to "aeo_strategy" with a canned entity/query set,
                # ignoring what was actually asked — same bug class as
                # design district's #33.
                query = task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")
                return {"status": "ok", "response": await self.answer_marketing_question(query)}

            else:  # aeo_strategy
                strategy = await self.generate_aeo_strategy(
                    task.get("entity", "VECTOR AI"),
                    task.get("target_queries", _TARGET_QUERIES),
                )
                self._get_memory().store(
                    event_type="aeo_strategy",
                    content=f"AEO strategy for {strategy['entity']}: {len(strategy['quick_wins'])} quick wins",
                    tags=["marketing", "seo", "aeo"],
                    source="ai_citation_strategist",
                )
                self.award_points(35, "aeo_strategy_generated")
                return {"status": "ok", "strategy": strategy}

        except Exception as e:
            logger.error("[VECTOR][ai_citation] {}", e)
            self.deduct_points(30, "citation_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = AICitationStrategist()
        audit = agent.audit_entity_clarity(
            "VECTOR",
            "An autonomous AI system built by Arghyadeep Deb using Python, Ollama, FastAPI.",
            "Personal AI for developers and students",
        )
        print(f"[OK] audit: score={audit['clarity_score']} issues={len(audit['disambiguation_issues'])}")
        content = agent.generate_citation_optimized_content("Memory Architecture", "VECTOR")
        print(f"[OK] content: {len(content.split())} words generated")
        task_check = agent.check_agentic_task_completion("search for AI papers on arxiv")
        print(f"[OK] task_check: completable={task_check['can_complete_autonomously']} complexity={task_check['complexity']}")
        result = await agent.run({"type": "aeo_strategy"})
        print(f"[OK] run: status={result['status']} quick_wins={len(result.get('strategy', {}).get('quick_wins', []))}")
        print("ai_citation_strategist.py OK")

    asyncio.run(_smoke())
