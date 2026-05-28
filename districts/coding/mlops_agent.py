"""
VECTOR MLOpsAgent — District 3: coding
Autonomous ML engineering with deep HuggingFace ecosystem integration.

Capabilities:
  - HF Papers research sub-agent (citation graphs, training recipe extraction)
  - HF Jobs GPU/CPU training submission
  - HF dataset inspection (schema, samples, column validation)
  - HF Hub file management (upload, git ops, PRs)
  - GitHub ML code search (semantic + keyword)
  - Multi-step ML engineering planning

Governor routes:
  ml_research, hf_train, hf_dataset, hf_hub, github_ml, ml_plan

Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY for research agent.
          HF_TOKEN for HF Jobs, dataset, and hub operations.
          GITHUB_TOKEN for GitHub code search.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path


# Activate districts/coding/vector_mlops/ path so "from agent.X" imports resolve
_ML_DIR = Path(__file__).parent.parent.parent.parent / "core" / "vector_mlops"
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from loguru import logger


class MLOpsAgent(AgentBase):
    """
    VECTOR's autonomous ML engineering agent.
    Wraps HF Papers research, HF Jobs submission, dataset inspection,
    Hub file management, and GitHub ML code search.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MLOpsAgent",
            district="coding",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        logger.info("[VECTOR][vector_mlops] ready gen={} hp={}", generation, self.health_points)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cfg(self) -> dict:
        return CONFIG.get("vector_mlops", {}) if isinstance(CONFIG, dict) else {}

    # ── Actions ───────────────────────────────────────────────────────────────

    async def ml_research(self, topic: str) -> dict:
        """
        Run the HF Papers + Semantic Scholar research sub-agent.
        Mines citation graphs, extracts methodology sections, identifies
        training recipes from published ML papers.

        topic examples:
          "GRPO training recipe for language models"
          "LoRA fine-tuning for vision transformers on small datasets"
          "State space models vs transformers for time series"
        """
        logger.info("[VECTOR][vector_mlops] ml_research: {}", topic[:70])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from agent.tools.research_tool import run_research_agent
                result = run_research_agent(topic=topic)
                return {"status": "ok", "topic": topic, "result": result}
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] ml_research error: {}", e)
                return {"status": "error", "error": str(e), "topic": topic}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="ml_research",
            content=f"MLOpsAgent research: {topic[:80]} -> {result.get('status')}",
            tags=["coding", "ml", "research", "papers"],
            source="mlops_agent",
        )
        if result.get("status") == "ok":
            self.award_points(30, f"ml research: {topic[:40]}")
        return result

    async def hf_dataset(
        self,
        dataset: str,
        config: str | None = None,
        split: str | None = None,
        sample_rows: int = 3,
    ) -> dict:
        """
        Inspect a HuggingFace dataset: schema, column types, sample rows,
        split sizes, parquet files. Validates formats for training compatibility.
        """
        logger.info("[VECTOR][vector_mlops] hf_dataset: {}", dataset)
        loop = asyncio.get_event_loop()

        async def _run():
            try:
                from agent.tools.dataset_tools import inspect_dataset
                cfg = self._cfg()
                result = await inspect_dataset(
                    dataset=dataset,
                    config=config,
                    split=split,
                    sample_rows=sample_rows,
                    hf_token=cfg.get("hf_token") or None,
                )
                formatted = result.get("formatted", str(result)) if isinstance(result, dict) else str(result)
                return {"status": "ok", "dataset": dataset, "result": formatted}
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] hf_dataset error: {}", e)
                return {"status": "error", "error": str(e), "dataset": dataset}

        result = await _run()
        if result.get("status") == "ok":
            self.award_points(10, f"dataset inspect: {dataset}")
        return result

    async def github_ml(
        self,
        keyword: str,
        repo: str = "trl",
        org: str = "huggingface",
        max_results: int = 10,
    ) -> dict:
        """
        Search GitHub for ML training examples using fuzzy matching.
        Defaults to searching huggingface/trl for training scripts.

        examples:
          keyword="grpo", repo="trl"
          keyword="lora", repo="diffusers"
          keyword="sft", repo="transformers"
        """
        logger.info("[VECTOR][vector_mlops] github_ml: {} in {}/{}", keyword, org, repo)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from agent.tools.github_find_examples import find_examples
                result = find_examples(
                    keyword=keyword,
                    repo=repo,
                    org=org,
                    max_results=max_results,
                )
                formatted = result.get("formatted", str(result)) if isinstance(result, dict) else str(result)
                is_error = result.get("isError", False) if isinstance(result, dict) else False
                return {
                    "status": "error" if is_error else "ok",
                    "keyword": keyword, "repo": f"{org}/{repo}",
                    "result": formatted,
                }
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] github_ml error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(10, f"github search: {keyword}")
        return result

    async def hf_hub(
        self,
        action: str,
        repo_id: str,
        path_in_repo: str | None = None,
        local_path: str | None = None,
        content: str | None = None,
    ) -> dict:
        """
        Manage files on HuggingFace Hub.
        actions: upload, delete, list
        """
        logger.info("[VECTOR][vector_mlops] hf_hub: {} {}", action, repo_id)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from huggingface_hub import HfApi
                cfg = self._cfg()
                token = cfg.get("hf_token") or None
                api = HfApi(token=token)

                if action == "list":
                    files = api.list_repo_files(repo_id=repo_id)
                    return {"status": "ok", "action": "list", "repo_id": repo_id,
                            "files": list(files)}
                elif action == "upload" and local_path and path_in_repo:
                    api.upload_file(
                        path_or_fileobj=local_path,
                        path_in_repo=path_in_repo,
                        repo_id=repo_id,
                    )
                    return {"status": "ok", "action": "upload", "repo_id": repo_id,
                            "path": path_in_repo}
                elif action == "delete" and path_in_repo:
                    api.delete_file(path_in_repo=path_in_repo, repo_id=repo_id)
                    return {"status": "ok", "action": "delete", "repo_id": repo_id,
                            "path": path_in_repo}
                else:
                    return {"status": "error",
                            "error": f"Invalid action '{action}' or missing required params"}
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] hf_hub error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(15, f"hf hub: {action}/{repo_id}")
        return result

    async def hf_train(
        self,
        script: str,
        repo_id: str,
        hardware: str = "cpu-basic",
        timeout: int = 3600,
        requirements: list[str] | None = None,
    ) -> dict:
        """
        Submit a training job to HuggingFace Jobs.
        hardware: cpu-basic, cpu-upgrade, nvidia-t4-small, nvidia-t4-medium,
                  nvidia-a10g-small, nvidia-a100-large
        script: Python training script content (will be uploaded then executed)
        """
        logger.info("[VECTOR][vector_mlops] hf_train: {} on {}", repo_id, hardware)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from agent.tools.jobs_tool import hf_jobs_handler
                args = {
                    "runtime": "python",
                    "script": script,
                    "repo_id": repo_id,
                    "hardware": hardware,
                    "timeout": timeout,
                    "requirements": requirements or [],
                }
                result, success = asyncio.run(hf_jobs_handler(args))
                return {
                    "status": "ok" if success else "error",
                    "repo_id": repo_id, "hardware": hardware,
                    "result": result,
                }
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] hf_train error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(40, f"hf job submitted: {hardware}")
        return result

    async def ml_plan(self, goal: str) -> dict:
        """
        Create a multi-step ML engineering plan for a given goal.
        Uses the research sub-agent to ground the plan in published work.
        """
        logger.info("[VECTOR][vector_mlops] ml_plan: {}", goal[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from agent.tools.plan_tool import plan_handler
                args = {"title": f"ML Plan: {goal[:60]}", "description": goal}
                result, success = asyncio.run(plan_handler(args))
                return {"status": "ok" if success else "error", "goal": goal, "plan": result}
            except Exception as e:
                logger.warning("[VECTOR][vector_mlops] ml_plan error: {}", e)
                return {"status": "error", "error": str(e), "goal": goal}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(15, "ml plan created")
        return result

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "ml_research")

        if action == "ml_research":
            return await self.ml_research(topic=p.get("topic", p.get("query", "")))
        elif action == "hf_train":
            return await self.hf_train(
                script=p.get("script", ""),
                repo_id=p.get("repo_id", ""),
                hardware=p.get("hardware", "cpu-basic"),
                timeout=p.get("timeout", 3600),
                requirements=p.get("requirements"),
            )
        elif action == "hf_dataset":
            return await self.hf_dataset(
                dataset=p.get("dataset", ""),
                config=p.get("config"),
                split=p.get("split"),
                sample_rows=p.get("sample_rows", 3),
            )
        elif action == "hf_hub":
            return await self.hf_hub(
                action=p.get("hub_action", "list"),
                repo_id=p.get("repo_id", ""),
                path_in_repo=p.get("path_in_repo"),
                local_path=p.get("local_path"),
                content=p.get("content"),
            )
        elif action == "github_ml":
            return await self.github_ml(
                keyword=p.get("keyword", ""),
                repo=p.get("repo", "trl"),
                org=p.get("org", "huggingface"),
                max_results=p.get("max_results", 10),
            )
        elif action == "ml_plan":
            return await self.ml_plan(goal=p.get("goal", p.get("task", "")))
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][vector_mlops] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][vector_mlops] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = MLOpsAgent()
        assert agent.health_points == 500
        assert agent.name == "MLOpsAgent"
        assert agent.district == "coding"

        # Verify core imports
        tools_ok = True
        try:
            from agent.tools.dataset_tools import inspect_dataset
            from agent.tools.github_find_examples import find_examples
            from agent.tools.jobs_tool import hf_jobs_handler
            from agent.tools.papers_tool import _s2_get_paper
            from agent.core.llm_params import build_litellm_kwargs
            from agent.core.hf_tokens import get_hf_token
            from agent.core.context_manager.manager import ContextManager
        except ImportError as e:
            tools_ok = False
            print(f"  Import error: {e}")

        print(f"OK mlops_agent.py HP={agent.health_points}")
        print(f"  district: {agent.district}")
        print(f"  core imports OK: {tools_ok}")
        print(f"  actions: ml_research, hf_train, hf_dataset, hf_hub, github_ml, ml_plan")

    asyncio.run(_smoke())
