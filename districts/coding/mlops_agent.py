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

import sys

import asyncio
import contextlib
import threading
import uuid
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.permission_gateway import PermissionGateway, Action
from loguru import logger

# hf_hub()'s upload action confinement: local_path is caller-supplied and
# reaches HfApi.upload_file() directly (same bar as architect_bot.py's
# explain_module() fix this cycle -- confine before any file I/O on an
# externally-controlled path).
_ROOT = Path(__file__).resolve().parents[2]

# 2026-07-30 audit fix (Phase 6 — vendored integration reachability):
# districts/coding/vector_mlops/agent/ is this district's vendored HF-agent
# toolkit. Its own files do bare `from agent.core import X` / `from
# agent.tools.Y import Z` imports, expecting 'agent' to resolve to ITS
# package — which requires putting districts/coding/vector_mlops/ on
# sys.path. Until this fix, nothing ever did that (confirmed: every one of
# this class's 6 actions caught a swallowed ModuleNotFoundError and
# returned a soft {"status": "error"} on every single call).
#
# A naive `sys.path.insert(0, .../vector_mlops)` at import time would trade
# that guaranteed failure for a WORSE, non-deterministic one: this repo's
# vectorcode/src/ is already on sys.path for nearly every module (every
# district calls ensure_paths(), including this file two lines up), and
# vectorcode/src/run_agent.py ALSO does bare `from agent.X import Y`
# imports against its own, completely different 'agent' package (confirmed
# via inspection — agent.memory_manager, agent.retry_utils, etc. are real
# vectorcode modules, not vector_mlops ones). Python caches whichever
# 'agent' package is imported first in sys.modules for the rest of the
# process; the other would silently break for the process's entire
# remaining lifetime with a confusing error (ModuleNotFoundError for a
# submodule that "should" exist), depending purely on which subsystem
# happened to run first. That's not a fix, it's relocating the same class
# of bug onto vectorcode's currently-working agent tooling.
#
# _vector_mlops_agent_namespace() scopes the fix to exactly the moment
# this district's own code needs bare 'agent' to mean ITS package: save
# whatever's currently on sys.path / cached under 'agent'*, swap in
# vector_mlops's, let the caller's import (and anything it transitively
# imports) run, then restore everything exactly as found. A module-level
# lock serializes this against concurrent use, since hf_train/hf_dataset/
# github_ml/ml_plan run their blocking work via loop.run_in_executor
# (a thread pool) and this manipulates process-global sys.path/sys.modules
# state that isn't safe to touch from two threads at once.
_MLOPS_AGENT_NS_LOCK = threading.Lock()
_MLOPS_VENDOR_DIR = str(Path(__file__).parent / "vector_mlops")


@contextlib.contextmanager
def _vector_mlops_agent_namespace():
    with _MLOPS_AGENT_NS_LOCK:
        saved_path = list(sys.path)
        saved_agent_modules = {
            k: v for k, v in sys.modules.items()
            if k == "agent" or k.startswith("agent.")
        }
        for k in saved_agent_modules:
            del sys.modules[k]
        sys.path.insert(0, _MLOPS_VENDOR_DIR)
        try:
            yield
        finally:
            sys.path[:] = saved_path
            for k in [m for m in sys.modules if m == "agent" or m.startswith("agent.")]:
                del sys.modules[k]
            sys.modules.update(saved_agent_modules)


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
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["ml_research", "hf_train", "hf_dataset", "hf_hub", "github_ml", "ml_plan"]
        self._memory = EpisodicMemory()
        self._gateway = PermissionGateway()
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

        # 2026-08-04 fix: the vendored call this used to make
        # (`agent.tools.research_tool.run_research_agent(topic=...)`) never
        # actually existed — the real, only exported entry point is
        # `research_handler(arguments, session, tool_call_id)`, and it's not
        # a standalone function: `if not session: return "No session
        # available for research agent.", False`. `session` there means a
        # live `agent.core.session.Session` from vector_mlops's own
        # AgentLoop (litellm client config, tool router, message history,
        # HF token, etc.) — not something safe to fake from outside that
        # loop. This was unreachable before tonight (Phase 6) because the
        # `agent` namespace collision made every import here fail first,
        # masking the wrong-name bug underneath; fixing the namespace issue
        # exposed it. Rather than reimplement vector_mlops's session
        # machinery, this calls the reasoning LLM directly (same pattern as
        # _answer_query below) — a real, working capability, just without
        # the vendored tool's live citation-graph/paper-mining tool calls.
        # A full fix (constructing a real Session + AgentLoop) is future
        # work if that deeper capability is actually wanted.
        try:
            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine
            sys_prompt = (
                "You are an ML research assistant. Given a research topic, "
                "summarize the current state of the art: relevant papers/"
                "techniques, methodology, and known training recipes or "
                "pitfalls. Be concrete and technical. If you are not certain "
                "of a specific citation, say so rather than inventing one."
            )
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": topic})
            answer = chat(
                model=CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
                messages=[{"role": "system", "content": hydration},
                          {"role": "system", "content": sys_prompt},
                          {"role": "user", "content": topic}],
                timeout=60.0,
            )
            result = {"status": "ok" if answer else "error", "topic": topic, "result": answer or ""}
        except Exception as e:
            logger.warning("[VECTOR][vector_mlops] ml_research error: {}", e)
            result = {"status": "error", "error": str(e), "topic": topic}
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
                with _vector_mlops_agent_namespace():
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
                with _vector_mlops_agent_namespace():
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
                    resolved = Path(local_path).resolve()
                    if not resolved.is_relative_to(_ROOT):
                        return {"status": "error",
                                "error": f"local_path outside repo root: {local_path}"}
                    api.upload_file(
                        path_or_fileobj=str(resolved),
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

        RED-gated (58C remediation — VECTOR_TECHNICAL_KNOWLEDGE/58C_MLOPS_
        HF_TRAIN_PERMISSION_REMEDIATION.md): this submits caller-supplied
        Python for REAL remote execution on HuggingFace Jobs, under the
        owner's HF credentials, at real billing cost. All consequential,
        caller-controlled parameters (script, hardware, timeout, repo_id,
        requirements) are included in the gated Action so the approver sees
        exactly what would run, where, and on what hardware/duration — never
        an unqualified "run training". The real remote submission
        (hf_jobs_handler) may only be reached after gate_result.approved.
        """
        logger.info("[VECTOR][vector_mlops] hf_train: {} on {}", repo_id, hardware)

        try:
            gate_result = await self._gateway.execute(Action(
                action_type="hf_train",
                params={
                    "script": script,
                    "repo_id": repo_id,
                    "hardware": hardware,
                    "timeout": timeout,
                    "requirements": requirements or [],
                    "summary": (
                        f"Submit HF Jobs training run: repo_id={repo_id!r}, "
                        f"hardware={hardware!r}, timeout={timeout}s, "
                        f"script={len(script)} chars, "
                        f"requirements={requirements or []}"
                    ),
                },
                proposed_by=self.name,
            ))
        except Exception as e:
            # Fail closed — never let a gateway-unreachable condition fall
            # through to a real remote job submission (mirrors
            # hedgebot_agent.py's solana_swap_execute pattern).
            logger.error("[VECTOR][vector_mlops] gateway unavailable — refusing hf_train: {}", e)
            return {"status": "blocked", "reason": f"gateway unavailable: {e}"}

        if not gate_result.approved:
            logger.warning("[VECTOR][vector_mlops] hf_train blocked by gateway: {}", gate_result.reason)
            return {"status": "blocked", "reason": gate_result.reason}

        loop = asyncio.get_event_loop()

        def _run():
            try:
                with _vector_mlops_agent_namespace():
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

        # 2026-08-04 fix: same class of bug as ml_research above, plus a
        # second one layered on top. The real vendored function is
        # `plan_tool_handler`, not `plan_handler` (name typo/drift). But
        # even with the right name, `PlanTool.execute()` is NOT a plan
        # *generator* — it's an in-memory todo-list state tracker (the
        # vendored agent-loop's equivalent of a TodoWrite tool): it expects
        # `{"todos": [{"id", "content", "status"}, ...]}` and just records/
        # formats whatever list it's given. It does not accept, and cannot
        # do anything useful with, `{"title": ..., "description": goal}` —
        # there was never a code path here that could have produced a real
        # plan. Fixed the same way as ml_research: ask the reasoning LLM
        # directly for a concrete multi-step plan, grounded by first running
        # ml_research() on the goal (matches this method's own docstring
        # promise "uses the research sub-agent to ground the plan").
        try:
            research = await self.ml_research(goal)
            grounding = research.get("result", "") if research.get("status") == "ok" else ""

            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine
            user_content = f"Goal: {goal}"
            if grounding:
                user_content += f"\n\nResearch grounding:\n{grounding}"
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": user_content})
            sys_prompt = (
                "You are an ML engineering planner. Given a goal and optional "
                "research grounding, produce a concrete, numbered, multi-step "
                "engineering plan (data, model, training, evaluation, "
                "deployment as relevant). Be specific and actionable."
            )
            plan_text = chat(
                model=CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
                messages=[{"role": "system", "content": hydration},
                          {"role": "system", "content": sys_prompt},
                          {"role": "user", "content": user_content}],
                timeout=60.0,
            )
            result = {"status": "ok" if plan_text else "error", "goal": goal, "plan": plan_text or ""}
        except Exception as e:
            logger.warning("[VECTOR][vector_mlops] ml_plan error: {}", e)
            result = {"status": "error", "error": str(e), "goal": goal}
        if result.get("status") == "ok":
            self.award_points(15, "ml plan created")
        return result

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def _answer_query(self, query: str) -> dict:
        """Answer a free-text question directly, without invoking the (paid,
        API-key-backed) ml_research sub-agent or any HF Hub/Jobs action."""
        try:
            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine
            sys_prompt = (
                "You are MLOpsAgent, VECTOR's autonomous ML engineering agent. "
                "You do HF Papers research, submit HF Jobs training runs, inspect "
                "HF datasets, manage HF Hub files, search GitHub for ML code, and "
                "create multi-step ML engineering plans. Answer the user's "
                "question directly and concisely."
            )
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": query})
            answer = chat(
                model=CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
                messages=[{"role": "system", "content": hydration},
                          {"role": "system", "content": sys_prompt},
                          {"role": "user", "content": query}],
                timeout=30.0,
            )
            return {"status": "ok", "response": answer or "", "agent": self.name}
        except Exception as e:
            logger.warning("[VECTOR][vector_mlops] _answer_query error: {}", e)
            return {"status": "error", "error": str(e)}

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # 2026-09-24 (independent review finding -- HIGH): reading
        # p.get("action") unconditionally let a caller dispatch a
        # GREEN-classified outer task_type (e.g. "ml_research"/"hf_hub")
        # while setting params.action to a completely different, RED-tier
        # real action (e.g. "hf_train" -- real remote GPU billing --  or
        # "hf_hub" with hub_action="delete"/"upload" -- a real Hub write)
        # -- Governor's authorization check only inspects the OUTER type
        # it classified, never this inner field, so the real, executed
        # action was never actually gated at all, even bypassing
        # hf_train's own pre-existing RED tier (Task 58C remediation).
        # Fixed to prefer the real, authorized outer type (set by
        # Governor.dispatch() on every real dispatch), matching how
        # hedgebot_agent.py/trading_conductor_agent.py/finagent_agent.py/
        # media_studio_agent.py already correctly do this -- params.action
        # remains the fallback for internal/smoke-test callers that never
        # go through Governor at all (no "type" key present).
        action = task.get("type") or p.get("action")

        # 2026-07-29: `action` used to default to "ml_research" whenever no
        # explicit action was given, and ml_research() ran unconditionally —
        # including with an empty topic. ml_research invokes a real,
        # API-key-backed research sub-agent (ANTHROPIC_API_KEY/OPENAI_API_KEY
        # per this module's own docstring), so a stray free-text chat message
        # reaching this agent via generic district routing used to silently
        # burn a real paid API call on a nonsensical "topic". hf_train/hf_hub
        # were already correctly gated behind an exact action match (real
        # GPU jobs / Hub writes never fired on a default) — this closes the
        # same gap for the research action. Now: ml_research only fires on an
        # explicit action match; everything else gets a safe grounded answer.
        if action == "ml_research":
            topic = p.get("topic", p.get("query", ""))
            if not topic.strip():
                return {"status": "error", "error": "Missing 'topic' parameter"}
            return await self.ml_research(topic=topic)
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

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or ""
        )
        if query.strip():
            return await self._answer_query(query)
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

        # Verify core imports resolve to vector_mlops's own 'agent' package
        # (2026-07-30 audit fix — see _vector_mlops_agent_namespace() above)
        tools_ok = True
        try:
            with _vector_mlops_agent_namespace():
                from agent.tools.dataset_tools import inspect_dataset
                from agent.tools.github_find_examples import find_examples
                from agent.tools.jobs_tool import hf_jobs_handler
                from agent.tools.papers_tool import _s2_get_paper
                # 2026-08-04 fix: these three names/paths were wrong (didn't
                # match the real vendored files at all) — `build_litellm_
                # kwargs` doesn't exist in llm_params.py, `get_hf_token`
                # doesn't exist in hf_tokens.py, and context_manager/ lives
                # directly under vector_mlops's agent/, not agent/core/.
                # Corrected to real, existing names/paths.
                from agent.core.llm_params import _resolve_llm_params
                from agent.core.hf_tokens import get_cached_hf_token
                from agent.context_manager.manager import ContextManager
        except ImportError as e:
            tools_ok = False
            print(f"  Import error: {e}")

        # Regression test for the actual bug this fixes: simulate a DIFFERENT
        # 'agent' package (standing in for vectorcode's real one) already
        # cached in sys.modules before vector_mlops needs its own — confirm
        # the namespace swap doesn't clobber it permanently, and that
        # vector_mlops's own tools ARE reachable inside the context.
        import types
        _fake_agent = types.ModuleType("agent")
        _fake_agent.__marker__ = "not-vector-mlops"
        sys.modules["agent"] = _fake_agent
        with _vector_mlops_agent_namespace():
            from agent.tools.plan_tool import plan_tool_handler  # noqa: F401 -- proves vector_mlops's agent resolves here
            assert not hasattr(sys.modules["agent"], "__marker__"), \
                "namespace swap did not actually switch to vector_mlops's agent package"
        assert sys.modules["agent"] is _fake_agent, \
            "namespace swap failed to restore the pre-existing 'agent' module after exiting the context"
        del sys.modules["agent"]
        print("  namespace isolation OK: vector_mlops's agent package doesn't clobber vectorcode's")

        print(f"OK mlops_agent.py HP={agent.health_points}")
        print(f"  district: {agent.district}")
        print(f"  core imports OK: {tools_ok}")
        print(f"  actions: ml_research, hf_train, hf_dataset, hf_hub, github_ml, ml_plan")

    asyncio.run(_smoke())
