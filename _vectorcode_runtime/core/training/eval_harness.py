"""Evaluation harness for benchmarking trained adapters against standard prompts."""


__all__ = [
    "ComparisonResult",
    "EvalHarness",
    "EvalResult",
]

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from loguru import logger


@dataclass
class EvalResult:
    model_name: str
    adapter_name: str
    benchmark_results: dict
    overall_score: float
    num_prompts: int
    timestamp: str = ""


@dataclass
class ComparisonResult:
    base_model_name: str
    adapter_model_name: str
    base_scores: dict
    adapter_scores: dict
    improvements: dict
    overall_improvement: float


class EvalHarness:
    def __init__(self):
        self._benchmarks: dict[str, Any] = {}
        logger.info("[Training] EvalHarness initialized")

    def register_benchmark(self, name: str, benchmark_class: Any) -> None:
        self._benchmarks[name] = benchmark_class
        logger.info("[Training] Registered benchmark '{}'", name)

    def evaluate(self, model_name: str, adapter_name: str = "", benchmarks: list[str] | None = None) -> EvalResult:
        logger.info("[Training] Evaluating '{}' with adapter '{}'", model_name, adapter_name or "none")
        benchmarks_to_run = benchmarks or list(self._benchmarks.keys())
        results = {}
        total_score = 0.0
        total_prompts = 0
        for name in benchmarks_to_run:
            if name not in self._benchmarks:
                logger.warning("[Training] Benchmark '{}' not registered, skipping", name)
                continue
            try:
                bench = self._benchmarks[name]()
                model_fn = lambda prompt, _n=name, _b=bench: self._run_prompt(model_name, prompt, adapter_name)
                scores = bench.run(model_fn)
                results[name] = scores
                avg = sum(scores.values()) / max(len(scores), 1)
                total_score += avg
                total_prompts += len(scores)
                logger.info("[Training] Benchmark '{}' avg score: {:.2f}", name, avg)
            except Exception as e:
                logger.error("[Training] Benchmark '{}' failed: {}", name, e)
                results[name] = {"error": str(e)}
        overall = total_score / max(len(results), 1)
        return EvalResult(
            model_name=model_name,
            adapter_name=adapter_name or "base",
            benchmark_results=results,
            overall_score=round(overall, 4),
            num_prompts=total_prompts,
            timestamp=datetime.now().isoformat(),
        )

    def compare(self, base_model: str, adapter_model: str, benchmarks: list[str] | None = None) -> ComparisonResult:
        logger.info("[Training] Comparing base '{}' vs adapter '{}'", base_model, adapter_model)
        base_result = self.evaluate(base_model, "", benchmarks)
        adapter_result = self.evaluate(adapter_model, adapter_model, benchmarks)
        improvements = {}
        all_benchmarks = set(base_result.benchmark_results.keys()) | set(adapter_result.benchmark_results.keys())
        for b in all_benchmarks:
            base_scores = base_result.benchmark_results.get(b, {})
            adapter_scores = adapter_result.benchmark_results.get(b, {})
            if isinstance(base_scores, dict) and isinstance(adapter_scores, dict):
                base_avg = sum(base_scores.values()) / max(len(base_scores), 1)
                adapter_avg = sum(adapter_scores.values()) / max(len(adapter_scores), 1)
                diff = adapter_avg - base_avg
                improvements[b] = {"base": round(base_avg, 4), "adapter": round(adapter_avg, 4), "change": round(diff, 4)}
        overall_improvement = adapter_result.overall_score - base_result.overall_score
        return ComparisonResult(
            base_model_name=base_model,
            adapter_model_name=adapter_model,
            base_scores=base_result.benchmark_results,
            adapter_scores=adapter_result.benchmark_results,
            improvements=improvements,
            overall_improvement=round(overall_improvement, 4),
        )

    def _run_prompt(self, model_name: str, prompt: str, adapter_name: str = "") -> str:
        try:
            import ollama
            model = adapter_name or model_name
            response = ollama.generate(model=model, prompt=prompt)
            return response.get("response", "")
        except ImportError:
            logger.warning("[Training] ollama not available, simulating response")
            return f"Simulated response for: {prompt[:50]}..."
        except Exception as e:
            logger.error("[Training] Model inference failed: {}", e)
            return ""
