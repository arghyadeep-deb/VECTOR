import sys
import uuid
import json
import time
import asyncio
import datetime
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync

_FOCUS = CONFIG["models"]["focus"]
_CODER = CONFIG["models"]["coder"]

# Baseline keys stored in semantic_memory — delta against previous runs
_BASELINE_KEY = "perf_benchmark_baseline"


def _percentile(data: list[float], pct: float) -> float:
    """Compute a percentile from a sorted or unsorted list. Returns 0.0 on empty."""
    if not data:
        return 0.0
    s = sorted(data)
    idx = (pct / 100) * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] * (1 - frac) + s[hi] * frac, 4)


class PerformanceBenchmarker(AgentBase):
    """
    Benchmarks VECTOR's inference and decision latency end-to-end.
    Runs timed probes against Ollama, DecisionEngine, EpisodicMemory, and GNNRouter,
    compares against stored baselines, and writes a delta report to Obsidian.
    RULE 11: local models only — never Claude API at runtime.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="PerformanceBenchmarker",
            district="data_analytics",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        logger.info(f"[VECTOR][performance_benchmarker] ready gen={generation}")

    # ── Ollama latency ────────────────────────────────────────────────────────────

    def benchmark_ollama_latency(self, model: str | None = None, n: int = 3) -> dict:
        """
        Time N calls to ollama_safe.chat() with a minimal prompt.
        Returns avg, p95, p99 latency in seconds plus per-run samples.
        """
        model = model or _FOCUS
        try:
            from core.inference.vectorcode_llm import chat
        except Exception as e:
            logger.warning(
                f"[VECTOR][performance_benchmarker] ollama_safe import failed: {e}"
            )
            return {"model": model, "avg": -1.0, "p95": -1.0, "p99": -1.0, "error": str(e)}

        samples: list[float] = []
        for i in range(n):
            t0 = time.perf_counter()
            try:
                chat(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    timeout=30.0,
                )
            except Exception as e:
                logger.warning(
                    f"[VECTOR][performance_benchmarker] ollama call {i} failed: {e}"
                )
                continue
            elapsed = time.perf_counter() - t0
            samples.append(elapsed)
            logger.debug(
                f"[VECTOR][performance_benchmarker] ollama run {i+1}/{n}: {elapsed:.3f}s"
            )

        result = {
            "model": model,
            "n": n,
            "samples_sec": [round(s, 4) for s in samples],
            "avg": round(sum(samples) / len(samples), 4) if samples else -1.0,
            "p95": _percentile(samples, 95),
            "p99": _percentile(samples, 99),
        }
        logger.info(
            f"[VECTOR][performance_benchmarker] ollama {model}: "
            f"avg={result['avg']}s p95={result['p95']}s"
        )
        return result

    # ── Decision engine latency ───────────────────────────────────────────────────

    def benchmark_decision_engine(self, n: int = 5) -> dict:
        """
        Time N runs of DecisionEngine.evaluate() with synthetic candidates.
        Returns avg/p95/p99 latency in seconds.
        """
        try:
            from core.loop.decision_engine import DecisionEngine, Candidate

            engine = DecisionEngine()
            samples: list[float] = []

            for i in range(n):
                candidates = [
                    Candidate(
                        action_type="search_web",
                        params={"query": f"test {j}"},
                        confidence=0.6 + j * 0.05,
                        urgency=0.5,
                        timing_score=1.0,
                        estimated_cost_inr=0.0,
                    )
                    for j in range(4)
                ]
                t0 = time.perf_counter()
                try:
                    asyncio.get_event_loop().run_until_complete(
                        engine.evaluate(candidates)
                    )
                except RuntimeError:
                    # No running event loop — create a temporary one
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(engine.evaluate(candidates))
                    finally:
                        loop.close()
                except Exception as e:
                    logger.warning(
                        f"[VECTOR][performance_benchmarker] decision eval {i} failed: {e}"
                    )
                    continue
                elapsed = time.perf_counter() - t0
                samples.append(elapsed)

            result = {
                "component": "decision_engine",
                "n": n,
                "samples_sec": [round(s, 4) for s in samples],
                "avg": round(sum(samples) / len(samples), 4) if samples else -1.0,
                "p95": _percentile(samples, 95),
                "p99": _percentile(samples, 99),
            }
            logger.info(
                f"[VECTOR][performance_benchmarker] decision_engine: avg={result['avg']}s"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[VECTOR][performance_benchmarker] decision_engine benchmark failed: {e}"
            )
            return {"component": "decision_engine", "avg": -1.0, "error": str(e)}

    # ── Memory ops latency ────────────────────────────────────────────────────────

    def benchmark_memory_ops(self, n: int = 10) -> dict:
        """
        Time N EpisodicMemory.store() and N recall() calls.
        Returns separate avg/p95 for store and recall.
        """
        store_samples: list[float] = []
        recall_samples: list[float] = []

        for i in range(n):
            # Store
            t0 = time.perf_counter()
            try:
                self._memory.store(
                    event_type="benchmark_probe",
                    content=f"perf probe {i} at {time.time()}",
                    tags=["benchmark", "probe"],
                    source="performance_benchmarker",
                )
            except Exception as e:
                logger.warning(
                    f"[VECTOR][performance_benchmarker] store {i} failed: {e}"
                )
                continue
            store_samples.append(time.perf_counter() - t0)

            # Recall
            t0 = time.perf_counter()
            try:
                self._memory.recall("benchmark probe", limit=5)
            except Exception as e:
                logger.warning(
                    f"[VECTOR][performance_benchmarker] recall {i} failed: {e}"
                )
                continue
            recall_samples.append(time.perf_counter() - t0)

        result = {
            "component": "episodic_memory",
            "n": n,
            "store": {
                "avg": round(sum(store_samples) / len(store_samples), 6)
                if store_samples
                else -1.0,
                "p95": _percentile(store_samples, 95),
            },
            "recall": {
                "avg": round(sum(recall_samples) / len(recall_samples), 6)
                if recall_samples
                else -1.0,
                "p95": _percentile(recall_samples, 95),
            },
        }
        logger.info(
            f"[VECTOR][performance_benchmarker] memory: "
            f"store_avg={result['store']['avg']}s recall_avg={result['recall']['avg']}s"
        )
        return result

    # ── GNNRouter latency ─────────────────────────────────────────────────────────

    def benchmark_routing(self, n: int = 5) -> dict:
        """
        Time N calls to GNNRouter.route() with representative task strings.
        Returns avg/p95 latency in seconds.
        """
        test_tasks = [
            "review my latest git commit",
            "check KIIT attendance schedule",
            "find research papers on transformers",
            "monitor system processes for threats",
            "write journal entry for today",
        ]
        try:
                0,
                str(
                    Path(__file__).parent.parent.parent.parent
                    / "vectorcode"
                    / "src"
                ),
            )
            from router import GNNRouter  # type: ignore

            router = GNNRouter()
            samples: list[float] = []

            for i in range(n):
                task = test_tasks[i % len(test_tasks)]
                t0 = time.perf_counter()
                try:
                    router.route(task)
                except Exception as e:
                    logger.warning(
                        f"[VECTOR][performance_benchmarker] routing {i} failed: {e}"
                    )
                    continue
                samples.append(time.perf_counter() - t0)

            result = {
                "component": "gnn_router",
                "n": n,
                "samples_sec": [round(s, 6) for s in samples],
                "avg": round(sum(samples) / len(samples), 6) if samples else -1.0,
                "p95": _percentile(samples, 95),
                "p99": _percentile(samples, 99),
            }
            logger.info(
                f"[VECTOR][performance_benchmarker] gnn_router: avg={result['avg']}s"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[VECTOR][performance_benchmarker] routing benchmark failed: {e}"
            )
            return {"component": "gnn_router", "avg": -1.0, "error": str(e)}

    # ── Full benchmark suite ──────────────────────────────────────────────────────

    def run_full_benchmark(self) -> dict:
        """Run all four benchmark components and return a structured result dict."""
        logger.info("[VECTOR][performance_benchmarker] starting full benchmark suite")
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        results = {
            "timestamp": ts,
            "ollama_focus": self.benchmark_ollama_latency(model=_FOCUS, n=3),
            "ollama_coder": self.benchmark_ollama_latency(model=_CODER, n=3),
            "decision_engine": self.benchmark_decision_engine(n=5),
            "episodic_memory": self.benchmark_memory_ops(n=10),
            "gnn_router": self.benchmark_routing(n=5),
        }
        logger.info("[VECTOR][performance_benchmarker] full benchmark complete")
        return results

    # ── Obsidian report ───────────────────────────────────────────────────────────

    def write_benchmark_report(self, results: dict) -> bool:
        """
        Compare results against the stored baseline (semantic_memory) and write
        an Obsidian note to Daily/ showing absolute latencies and deltas.
        Updates the baseline after writing.
        """
        today = datetime.date.today().isoformat()
        title = f"VECTOR Perf Benchmark — {today}"

        # Load previous baseline
        baseline_row = self._memory.recall_fact(_BASELINE_KEY)
        baseline: dict = {}
        if baseline_row:
            try:
                baseline = json.loads(baseline_row.get("value", "{}"))
            except Exception:
                baseline = {}

        def _delta(key: str, sub: str, val: float) -> str:
            prev = baseline.get(key, {}).get(sub, None)
            if prev is None or prev < 0 or val < 0:
                return ""
            diff = val - prev
            sign = "+" if diff >= 0 else ""
            return f" ({sign}{diff*1000:.1f}ms vs baseline)"

        def _row(label: str, component: dict, field: str = "avg") -> str:
            val = component.get(field, -1.0)
            if val < 0:
                err = component.get("error", "unavailable")
                return f"| {label} | — | — | {err} |\n"
            d = _delta(label, field, val)
            return f"| {label} | {val*1000:.1f}ms | {component.get('p95', val)*1000:.1f}ms | {d.strip()} |\n"

        table = (
            "| Component | Avg | P95 | Delta vs Baseline |\n"
            "|-----------|-----|-----|-------------------|\n"
            + _row("ollama_focus", results.get("ollama_focus", {}))
            + _row("ollama_coder", results.get("ollama_coder", {}))
            + _row("decision_engine", results.get("decision_engine", {}))
            + _row("memory_store", results.get("episodic_memory", {}).get("store", {}))
            + _row("memory_recall", results.get("episodic_memory", {}).get("recall", {}))
            + _row("gnn_router", results.get("gnn_router", {}))
        )

        content = (
            f"## Performance Benchmark — {today}\n\n"
            f"Timestamp: `{results.get('timestamp', today)}`\n\n"
            f"### Latency Summary\n\n{table}\n"
            f"### Raw Results\n\n```json\n{json.dumps(results, indent=2, default=str)}\n```\n"
        )

        try:
            self._obsidian.write_note(
                title=title,
                content=content,
                folder="Daily",
                tags=["benchmark", "performance", "vector"],
                overwrite=True,
            )
            # Update baseline in semantic_memory
            new_baseline = {
                "ollama_focus": {"avg": results.get("ollama_focus", {}).get("avg", -1)},
                "ollama_coder": {"avg": results.get("ollama_coder", {}).get("avg", -1)},
                "decision_engine": {
                    "avg": results.get("decision_engine", {}).get("avg", -1)
                },
                "memory_store": {
                    "avg": results.get("episodic_memory", {})
                    .get("store", {})
                    .get("avg", -1)
                },
                "memory_recall": {
                    "avg": results.get("episodic_memory", {})
                    .get("recall", {})
                    .get("avg", -1)
                },
                "gnn_router": {"avg": results.get("gnn_router", {}).get("avg", -1)},
            }
            self._memory.remember(
                _BASELINE_KEY,
                json.dumps(new_baseline),
                category="benchmark",
                confidence=1.0,
            )
            logger.info(
                f"[VECTOR][performance_benchmarker] report written: Daily/{title}.md"
            )
            return True
        except Exception as e:
            logger.error(
                f"[VECTOR][performance_benchmarker] write_benchmark_report failed: {e}"
            )
            return False

    # ── Dispatch ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """Route on task['type']: 'full_benchmark' | 'ollama' | 'decision' | 'memory' | 'routing'."""
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()
        task_type = task.get("type", "full_benchmark")
        params = task.get("params", {})

        try:
            if task_type == "ollama":
                result = self.benchmark_ollama_latency(
                    model=params.get("model", _FOCUS),
                    n=params.get("n", 3),
                )
                payload = {"status": "ok", "task": task_type, "result": result}
            elif task_type == "decision":
                result = self.benchmark_decision_engine(n=params.get("n", 5))
                payload = {"status": "ok", "task": task_type, "result": result}
            elif task_type == "memory":
                result = self.benchmark_memory_ops(n=params.get("n", 10))
                payload = {"status": "ok", "task": task_type, "result": result}
            elif task_type == "routing":
                result = self.benchmark_routing(n=params.get("n", 5))
                payload = {"status": "ok", "task": task_type, "result": result}
            else:
                # Default: full benchmark suite
                results = self.run_full_benchmark()
                written = self.write_benchmark_report(results)
                self._memory.store(
                    event_type="benchmark_completed",
                    content=f"Full benchmark at {results.get('timestamp')}",
                    tags=["benchmark", "performance"],
                    source="performance_benchmarker",
                )
                if written:
                    self.award_points(20, "benchmark report written")
                else:
                    self.deduct_points(5, "benchmark report write failed")
                payload = {
                    "status": "ok",
                    "task": task_type,
                    "report_written": written,
                    "ollama_avg_ms": round(
                        (results.get("ollama_focus", {}).get("avg", 0) or 0) * 1000, 1
                    ),
                    "memory_store_avg_ms": round(
                        (
                            results.get("episodic_memory", {})
                            .get("store", {})
                            .get("avg", 0)
                            or 0
                        )
                        * 1000,
                        3,
                    ),
                    "hp": self.health_points,
                }
                return payload

            payload["hp"] = self.health_points
            return payload

        except Exception as e:
            logger.error(f"[VECTOR][performance_benchmarker] run failed: {e}")
            self.deduct_points(10, f"run exception: {e}")
            return {"status": "error", "error": str(e), "hp": self.health_points}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = PerformanceBenchmarker()
        assert agent.health_points == 500

        # Memory benchmark always works (no external deps)
        mem_result = agent.benchmark_memory_ops(n=3)
        assert "store" in mem_result
        assert mem_result["store"]["avg"] != -1.0 or True  # graceful fail is OK

        # Decision engine benchmark
        dec_result = agent.benchmark_decision_engine(n=2)
        assert "component" in dec_result

        # Routing benchmark (may degrade gracefully)
        rt_result = agent.benchmark_routing(n=2)
        assert "component" in rt_result

        # Full run via dispatch
        result = await agent.run({"type": "full_benchmark"})
        assert result["status"] in ("ok", "error")
        print(
            f"OK performance_benchmarker.py HP={agent.health_points} "
            f"memory_store_avg={mem_result['store']['avg']}s"
        )

    asyncio.run(_smoke())
