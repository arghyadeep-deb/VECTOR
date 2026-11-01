"""
VECTOR SocialSimAgent — District 7: intelligence
Swarm intelligence and social simulation engine.

Runs a full "rehearse the future" pipeline:
  Documents → Ontology → Zep Knowledge Graph → Agent Personas →
  OASIS Twitter/Reddit Simulation → ReACT Report

Governor routes:
  social_simulate, build_ontology, build_graph, generate_personas,
  simulation_report, agent_interview, run_simulation

Requires: LLM_API_KEY (or OPENAI_API_KEY) for LLM calls.
          ZEP_API_KEY for knowledge graph operations (optional for simulation-only).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# Activate districts/intelligence/vector_social_sim/ path so "from app.X" imports resolve.
# The vendored tree is a sibling of this wrapper, not a package under core/.
_MIRO_DIR = Path(__file__).parent / "vector_social_sim"
if str(_MIRO_DIR) not in sys.path:
    sys.path.insert(0, str(_MIRO_DIR))

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from loguru import logger

class SocialSimAgent(AgentBase):
    """
    VECTOR's social simulation and swarm intelligence agent.
    Wraps the document-to-ontology, Zep graph, OASIS simulation,
    and ReACT report generation pipeline.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SocialSimAgent",
            district="intelligence",
            generation=generation,
        )
        self.capabilities = ["agent_interview", "build_graph", "build_ontology", "generate_personas", "intelligence", "run_simulation", "simulation", "simulation_report", "social_sim", "social_simulate"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        logger.info("[VECTOR][vector_social_sim] ready gen={} hp={}", generation, self.health_points)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cfg(self) -> dict:
        return CONFIG.get("vector_social_sim", {}) if isinstance(CONFIG, dict) else {}

    def _llm_client(self):
        from app.utils.llm_client import LLMClient
        cfg = self._cfg()
        return LLMClient(
            api_key=cfg.get("llm_api_key") or None,
            base_url=cfg.get("llm_base_url") or None,
            model=cfg.get("llm_model_name") or "gpt-4.1",
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    async def build_ontology(
        self,
        document_texts: list[str],
        simulation_requirement: str,
    ) -> dict:
        """
        Extract entity types and relationship schemas from documents.
        First step of the social simulation pipeline.

        document_texts: list of extracted text chunks from PDF/MD/TXT
        simulation_requirement: plain-English description of what to predict
          e.g. "Predict public reaction to a new AI regulation policy"
        """
        logger.info("[VECTOR][vector_social_sim] build_ontology for: {}", simulation_requirement[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from app.services.ontology_generator import OntologyGenerator
                gen = OntologyGenerator(llm_client=self._llm_client())
                ontology = gen.generate(
                    document_texts=document_texts,
                    simulation_requirement=simulation_requirement,
                )
                return {"status": "ok", "ontology": ontology,
                        "entity_count": len(ontology.get("entity_types", [])),
                        "edge_count": len(ontology.get("edge_types", []))}
            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] build_ontology error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(15, "ontology generated")
        return result

    async def build_graph(
        self,
        text: str,
        ontology: dict,
        graph_name: str = "VECTOR Simulation Graph",
    ) -> dict:
        """
        Construct a Zep knowledge graph from text + ontology.
        Returns a task_id to track the background build process.
        Requires ZEP_API_KEY.
        """
        logger.info("[VECTOR][vector_social_sim] build_graph: {} chars", len(text))
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = self._cfg()
                zep_key = cfg.get("zep_api_key", "")
                if not zep_key:
                    return {"status": "error",
                            "error": "ZEP_API_KEY not set. Add it to .env to use knowledge graphs."}
                from app.services.graph_builder import GraphBuilderService
                svc = GraphBuilderService(api_key=zep_key)
                task_id = svc.build_graph_async(
                    text=text,
                    ontology=ontology,
                    graph_name=graph_name,
                )
                return {"status": "ok", "task_id": task_id,
                        "note": "Graph building started in background. Check task_id for completion."}
            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] build_graph error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(20, "graph build started")
        return result

    async def generate_personas(
        self,
        graph_id: str,
        entity_type: str | None = None,
        max_profiles: int = 50,
    ) -> dict:
        """
        Generate OASIS agent personas from Zep knowledge graph entities.
        Creates full psychological profiles (MBTI, profession, sentiment bias, etc.)
        for Twitter and Reddit simulations.
        Requires ZEP_API_KEY.
        """
        logger.info("[VECTOR][vector_social_sim] generate_personas from graph={}", graph_id[:20])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = self._cfg()
                zep_key = cfg.get("zep_api_key", "")
                if not zep_key:
                    return {"status": "error",
                            "error": "ZEP_API_KEY not set."}
                from app.services.zep_entity_reader import ZepEntityReader
                from app.services.oasis_profile_generator import OasisProfileGenerator

                reader = ZepEntityReader(api_key=zep_key)
                entities = reader.get_entities(graph_id=graph_id, entity_type=entity_type)
                if len(entities) > max_profiles:
                    entities = entities[:max_profiles]

                gen = OasisProfileGenerator(
                    llm_client=self._llm_client(),
                    zep_api_key=zep_key,
                )
                gen.set_graph_id(graph_id)
                profiles = gen.generate_profiles_from_entities(entities)
                return {
                    "status": "ok",
                    "profile_count": len(profiles),
                    "profiles": [p.to_dict() for p in profiles],
                }
            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] generate_personas error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(25, f"personas: {result.get('profile_count', 0)} agents")
        return result

    async def simulation_report(
        self,
        simulation_id: str,
        graph_id: str,
        requirement: str,
    ) -> dict:
        """
        Generate a ReACT analysis report from simulation results.
        Uses InsightForge, PanoramaSearch, QuickSearch tools against the Zep graph.
        Requires ZEP_API_KEY.
        """
        logger.info("[VECTOR][vector_social_sim] simulation_report: sim={}", simulation_id[:20])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = self._cfg()
                zep_key = cfg.get("zep_api_key", "")
                reports_dir = Path(cfg.get("reports_dir",
                    Path.home() / ".vector" / "vector_social_sim" / "reports"))
                reports_dir.mkdir(parents=True, exist_ok=True)

                from app.services.report_agent import ReportAgent
                agent = ReportAgent(
                    llm_client=self._llm_client(),
                    zep_api_key=zep_key,
                    reports_dir=str(reports_dir),
                )
                report = agent.generate_report(
                    simulation_id=simulation_id,
                    graph_id=graph_id,
                    simulation_requirement=requirement,
                )
                return {
                    "status": "ok",
                    "report_id": report.report_id if hasattr(report, "report_id") else str(report),
                    "report": report.to_dict() if hasattr(report, "to_dict") else str(report),
                }
            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] simulation_report error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(40, "simulation report generated")
        self._memory.store(
            event_type="simulation_report",
            content=f"SocialSimAgent report: sim={simulation_id[:30]} -> {result.get('status')}",
            tags=["intelligence", "simulation", "report"],
            source="social_sim_agent",
        )
        return result

    async def agent_interview(
        self,
        report_id: str,
        message: str,
        graph_id: str | None = None,
    ) -> dict:
        """
        Chat with the ReACT Report Agent or interview a specific simulated agent.
        Use this to ask follow-up questions about the simulation results.
        Requires ZEP_API_KEY.
        """
        logger.info("[VECTOR][vector_social_sim] agent_interview: {}", message[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = self._cfg()
                zep_key = cfg.get("zep_api_key", "")
                reports_dir = str(Path(cfg.get("reports_dir",
                    Path.home() / ".vector" / "vector_social_sim" / "reports")))

                from app.services.report_agent import ReportAgent, ReportManager
                # Load existing report if available
                existing = ReportManager.get_report(report_id)
                agent = ReportAgent(
                    llm_client=self._llm_client(),
                    zep_api_key=zep_key,
                    reports_dir=reports_dir,
                )
                response = agent.chat(
                    message=message,
                    report_id=report_id,
                    graph_id=graph_id,
                )
                return {"status": "ok", "response": str(response)}
            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] agent_interview error: {}", e)
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def social_simulate(
        self,
        document_texts: list[str],
        simulation_requirement: str,
        rounds: int = 10,
        graph_name: str = "VECTOR Social Sim",
    ) -> dict:
        """
        Run the full pipeline: Ontology → Graph → Personas (returns IDs for async steps).
        Full pipeline is long-running; this returns the ontology and kicks off graph build.

        document_texts: text content from uploaded documents
        simulation_requirement: what scenario to predict
        rounds: simulation rounds (10 = ~1h, 40 = ~4h)
        """
        logger.info("[VECTOR][vector_social_sim] social_simulate: {}", simulation_requirement[:60])

        # Step 1: Ontology (synchronous, fast)
        onto_result = await self.build_ontology(document_texts, simulation_requirement)
        if onto_result.get("status") != "ok":
            return onto_result

        ontology = onto_result["ontology"]

        # Step 2: Graph build (async, returns task_id)
        combined_text = "\n\n".join(document_texts)
        graph_result = await self.build_graph(combined_text, ontology, graph_name)
        if graph_result.get("status") != "ok":
            return graph_result

        self.award_points(20, "social simulation pipeline started")
        return {
            "status": "ok",
            "pipeline": "started",
            "ontology": ontology,
            "graph_task_id": graph_result.get("task_id"),
            "simulation_requirement": simulation_requirement,
            "rounds": rounds,
            "next_steps": [
                "1. Wait for graph_task_id to complete (poll via build_graph status)",
                "2. Call generate_personas with the graph_id once graph is ready",
                "3. Run OASIS simulation via scripts/run_twitter_simulation.py",
                "4. Call simulation_report with simulation_id + graph_id",
            ],
        }

    async def run_simulation(
        self,
        profiles_path: str,
        simulation_config: dict | None = None,
        platform: str = "twitter",
        total_rounds: int = 10,
        max_concurrent: int = 5,
    ) -> dict:
        """
        Run a full social simulation using VECTOR's own engine (no camel-oasis needed).
        Agents make LLM-driven decisions each round; all actions logged to SQLite.

        profiles_path: path to twitter_profiles.csv or reddit_profiles.json
        simulation_config: dict matching simulation_config.json schema (optional)
        platform: "twitter" or "reddit"
        total_rounds: number of simulation rounds (10 = ~5h simulated)
        max_concurrent: max simultaneous LLM calls

        After this, call simulation_report with the returned db_path.
        """
        logger.info("[VECTOR][vector_social_sim] run_simulation: {} {} rounds on {}",
                    profiles_path[:50], total_rounds, platform)
        loop = asyncio.get_event_loop()

        async def _run():
            try:
                import os
                from app.services.vector_simulation_engine import VectorSocialSimEngine

                cfg = self._cfg()
                sim_dir = Path(cfg.get("simulations_dir",
                    Path.home() / ".vector" / "vector_social_sim" / "simulations"))
                sim_id = str(uuid.uuid4())[:8]
                run_dir = sim_dir / f"{platform}_{sim_id}"
                run_dir.mkdir(parents=True, exist_ok=True)

                db_path = str(run_dir / f"{platform}_simulation.db")
                config  = simulation_config or {
                    "simulation_id": sim_id,
                    "time_config": {
                        "total_simulation_hours": 72,
                        "minutes_per_round": 30,
                        "agents_per_hour_min": 3,
                        "agents_per_hour_max": min(8, total_rounds),
                        "peak_hours": [9, 10, 11, 14, 15, 20, 21, 22],
                        "off_peak_hours": [0, 1, 2, 3, 4, 5],
                        "peak_activity_multiplier": 1.5,
                        "off_peak_activity_multiplier": 0.3,
                    },
                    "event_config": {"initial_posts": []},
                    "agent_configs": [],
                }

                engine = VectorSocialSimEngine(
                    config=config,
                    db_path=db_path,
                    llm_client=self._llm_client(),
                    platform=platform,
                )

                if platform == "twitter":
                    n = engine.load_twitter_profiles(profiles_path)
                else:
                    n = engine.load_reddit_profiles(profiles_path)

                if n == 0:
                    return {"status": "error", "error": "No profiles loaded from path"}

                def _progress(rnd, total, summary):
                    logger.info("[VECTOR][vector_social_sim] round {}/{} hour={} active={}",
                                rnd, total, summary.get("simulated_hour"),
                                summary.get("active_agents"))

                result = await engine.run_simulation(
                    total_rounds=total_rounds,
                    max_concurrent=max_concurrent,
                    progress_callback=_progress,
                )
                result["simulation_id"] = sim_id
                result["run_dir"] = str(run_dir)
                return result

            except Exception as e:
                logger.warning("[VECTOR][vector_social_sim] run_simulation error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await _run()
        if result.get("status") == "completed":
            self.award_points(50, f"simulation completed: {total_rounds} rounds")
            self._memory.store(
                event_type="social_simulation",
                content=f"SocialSimAgent {platform} sim: {total_rounds} rounds "
                        f"-> {result.get('action_counts', {})}",
                tags=["intelligence", "simulation", platform],
                source="social_sim_agent",
            )
        return result

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # 2026-09-24 (external review, Phase 1): core/api/routers/simulation.py
        # sets the real intended action on task["type"] (e.g. "run_simulation",
        # "interview_agent") but this method only ever read params["action"],
        # which the router never sets -- every /simulation/* endpoint except
        # /ontology silently ran build_ontology() instead of what was
        # actually requested. task["type"] now wins when present.
        action = task.get("type") or p.get("action", "build_ontology")

        if action == "social_simulate":
            return await self.social_simulate(
                document_texts=p.get("document_texts", [p.get("text", "")]),
                simulation_requirement=p.get("requirement", p.get("query", "")),
                rounds=p.get("rounds", 10),
                graph_name=p.get("graph_name", "VECTOR Social Sim"),
            )
        elif action == "build_ontology":
            return await self.build_ontology(
                document_texts=p.get("document_texts", [p.get("text", "")]),
                simulation_requirement=p.get("requirement", ""),
            )
        elif action == "build_graph":
            return await self.build_graph(
                text=p.get("text", ""),
                ontology=p.get("ontology", {}),
                graph_name=p.get("graph_name", "VECTOR Sim Graph"),
            )
        elif action == "generate_personas":
            return await self.generate_personas(
                graph_id=p.get("graph_id", ""),
                entity_type=p.get("entity_type"),
                max_profiles=p.get("max_profiles", 50),
            )
        elif action == "simulation_report":
            return await self.simulation_report(
                simulation_id=p.get("simulation_id", ""),
                graph_id=p.get("graph_id", ""),
                requirement=p.get("requirement", ""),
            )
        elif action == "agent_interview":
            return await self.agent_interview(
                report_id=p.get("report_id", ""),
                message=p.get("message", p.get("query", "")),
                graph_id=p.get("graph_id"),
            )
        elif action == "run_simulation":
            return await self.run_simulation(
                profiles_path=p.get("profiles_path", ""),
                simulation_config=p.get("simulation_config"),
                platform=p.get("platform", "twitter"),
                total_rounds=p.get("total_rounds", 10),
                max_concurrent=p.get("max_concurrent", 5),
            )
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][vector_social_sim] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][vector_social_sim] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SocialSimAgent()
        assert agent.health_points == 500
        assert agent.name == "SocialSimAgent"
        assert agent.district == "intelligence"

        tools_ok = True
        try:
            from app.services.ontology_generator import OntologyGenerator
            from app.services.graph_builder import GraphBuilderService
            from app.services.oasis_profile_generator import OasisProfileGenerator
            from app.services.report_agent import ReportAgent
            from app.services.zep_tools import ZepTools
            from app.utils.llm_client import LLMClient
            from app.utils.file_parser import extract_text
            from app.utils.text_processor import split_text
        except ImportError as e:
            tools_ok = False
            print(f"  Import error: {e}")

        print(f"OK social_sim_agent.py HP={agent.health_points}")
        print(f"  district: {agent.district}")
        print(f"  core imports OK: {tools_ok}")
        print(f"  actions: social_simulate, build_ontology, build_graph,")
        print(f"           generate_personas, simulation_report, agent_interview")

    asyncio.run(_smoke())
