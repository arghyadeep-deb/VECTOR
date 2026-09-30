"""
Performance Optimizer — profiling, bottleneck detection, optimization recommendations.
Loaded from: vectorcode/agents/vector-performance-optimizer.md
District: data_analytics
"""
import asyncio
import time
import cProfile
import pstats
import io

from loguru import logger
from core.city.prompt_agent import PromptAgent


class PerformanceOptimizer(PromptAgent):
    """
    Performance analysis and optimization. Profiles code, identifies bottlenecks,
    suggests algorithm improvements. More focused than performance_benchmarker
    (which measures latency) — this optimizes the code itself.
    Powered by vector-performance-optimizer.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-performance-optimizer.md", "performance_optimizer_001", "data_analytics")
        self.capabilities = ["analyze", "data_analytics", "optimize", "performance"]

    def profile_callable(self, func, *args, runs: int = 3, **kwargs) -> dict:
        """Profile a callable and return top hotspots."""
        profiler = cProfile.Profile()
        timings = []
        for _ in range(runs):
            t0 = time.perf_counter()
            profiler.enable()
            try:
                func(*args, **kwargs)
            except Exception as e:
                return {"error": str(e)}
            finally:
                profiler.disable()
            timings.append(time.perf_counter() - t0)

        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(10)
        profile_output = stream.getvalue()

        avg_ms = round(sum(timings) / len(timings) * 1000, 2)
        return {
            "avg_ms": avg_ms,
            "min_ms": round(min(timings) * 1000, 2),
            "max_ms": round(max(timings) * 1000, 2),
            "runs": runs,
            "top_hotspots": profile_output[:2000],
        }

    async def analyze_code_for_performance(self, code: str, language: str = "python") -> dict:
        """LLM-assisted performance analysis of code snippet."""
        query = (
            f"Analyze this {language} code for performance issues.\n"
            f"Identify: O(n²) or worse algorithms, unnecessary re-computation, "
            f"missing caching, blocking I/O in async paths, memory leaks.\n\n"
            f"```{language}\n{code[:3000]}\n```\n\n"
            f"Format: ISSUE | SEVERITY | OPTIMIZED VERSION | EXPECTED SPEEDUP"
        )
        response = await self.ask(query, timeout=40.0)
        return {"status": "ok", "analysis": response, "code_length": len(code)}

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        task = {**task, **(task.get("params") or {})}
        task_type = task.get("type", "ask")
        try:
            if task_type == "analyze":
                result = await self.analyze_code_for_performance(
                    task.get("code", ""), task.get("language", "python")
                )
                self.award_points(25, "performance_analyzed")
                return result
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][perf_opt] {}", e)
            self.deduct_points(30, "optimization_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = PerformanceOptimizer()
        print(f"[OK] loaded: {agent.name} prompt={len(agent._system_prompt)}chars")
        # Profile a simple callable
        result = agent.profile_callable(sorted, list(range(1000, 0, -1)), runs=3)
        print(f"[OK] profile: avg={result.get('avg_ms','?')}ms runs={result.get('runs','?')}")
        print("performance_optimizer.py OK")
    asyncio.run(_smoke())
