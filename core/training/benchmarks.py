"""Lightweight evaluation benchmarks for VECTOR adapter quality gates.

No heavy ML dependencies — scoring is pattern-based so benchmarks run
even without a live Ollama instance (graceful degradation to 0.5 score).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import re
from typing import Callable
from loguru import logger

__all__ = ["CodingBenchmark", "ResearchBenchmark"]

# Minimum non-empty response length to be considered substantive
_MIN_RESPONSE_LEN = 20


def _score_response(response: str, keywords: list[str], anti_keywords: list[str] | None = None) -> float:
    """Score a model response 0.0–1.0 based on keyword presence."""
    if not response or len(response.strip()) < _MIN_RESPONSE_LEN:
        return 0.1
    lower = response.lower()
    hits = sum(1 for k in keywords if k.lower() in lower)
    anti_hits = sum(1 for k in (anti_keywords or []) if k.lower() in lower)
    base = min(hits / max(len(keywords), 1), 1.0)
    penalty = 0.2 * anti_hits
    return round(max(0.0, min(1.0, 0.5 + 0.5 * base - penalty)), 4)


class CodingBenchmark:
    """Benchmark for code generation and explanation quality.

    Prompts cover Python async, FastAPI, SQLite, loguru, and error handling —
    all patterns used heavily in VECTOR's codebase.
    """

    PROMPTS: list[tuple[str, list[str]]] = [
        (
            "Write a Python async function that retries an HTTP call up to 3 times with exponential backoff.",
            ["async", "await", "retry", "except", "sleep"],
        ),
        (
            "Show a FastAPI route that returns a JSON response with a 200 status code.",
            ["@app", "get", "post", "return", "status_code"],
        ),
        (
            "Write a Python function to insert a row into a SQLite table safely using parameterised queries.",
            ["execute", "?", "sqlite", "conn", "commit"],
        ),
        (
            "How do you configure loguru to write logs to a file with rotation at 10 MB?",
            ["logger.add", "rotation", "10", "mb", "sink"],
        ),
        (
            "Write a Python dataclass with pydantic BaseModel validation for a user record.",
            ["basemodel", "field", "str", "int", "validator"],
        ),
        (
            "Explain what asyncio.gather does and give a short example.",
            ["asyncio", "gather", "await", "coroutine", "concurrent"],
        ),
        (
            "Write a Python context manager that times a code block and logs the duration.",
            ["contextmanager", "yield", "time", "logger", "elapsed"],
        ),
        (
            "How do you handle circular imports in a Python package?",
            ["import", "lazy", "module", "init", "local"],
        ),
    ]

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for i, (prompt, keywords) in enumerate(self.PROMPTS):
            key = f"coding_{i+1}"
            try:
                response = model_fn(prompt)
                scores[key] = _score_response(response, keywords)
                logger.debug("[Training][CodingBenchmark] {} score={:.2f}", key, scores[key])
            except Exception as e:
                logger.warning("[Training][CodingBenchmark] prompt {} failed: {}", key, e)
                scores[key] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Training][CodingBenchmark] avg={:.2f} over {} prompts", avg, len(scores))
        return scores


class ResearchBenchmark:
    """Benchmark for research synthesis and factual recall quality.

    Prompts test the model's ability to summarise, compare, and reason —
    skills used by VECTOR's research and intelligence districts.
    """

    PROMPTS: list[tuple[str, list[str]]] = [
        (
            "Summarise the MITRE ATT&CK framework in 3 bullet points.",
            ["tactic", "technique", "adversary", "detection", "mitre"],
        ),
        (
            "What is the difference between episodic memory and semantic memory?",
            ["episodic", "semantic", "event", "fact", "recall"],
        ),
        (
            "Explain LoRA fine-tuning in 2–3 sentences suitable for a non-ML engineer.",
            ["lora", "rank", "parameter", "adapter", "fine-tun"],
        ),
        (
            "What are the trade-offs between local-first inference and cloud inference?",
            ["latency", "privacy", "cost", "ollama", "cloud"],
        ),
        (
            "List 3 key properties of a production-ready autonomous agent system.",
            ["reliable", "observab", "permiss", "fallback", "monitor"],
        ),
        (
            "What is a circuit breaker pattern and why is it used in distributed systems?",
            ["circuit", "open", "closed", "failure", "threshold"],
        ),
        (
            "Describe what a Darwinian agent system means in the context of AI.",
            ["hp", "fitness", "evolut", "generation", "inherit"],
        ),
    ]

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for i, (prompt, keywords) in enumerate(self.PROMPTS):
            key = f"research_{i+1}"
            try:
                response = model_fn(prompt)
                scores[key] = _score_response(response, keywords)
                logger.debug("[Training][ResearchBenchmark] {} score={:.2f}", key, scores[key])
            except Exception as e:
                logger.warning("[Training][ResearchBenchmark] prompt {} failed: {}", key, e)
                scores[key] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Training][ResearchBenchmark] avg={:.2f} over {} prompts", avg, len(scores))
        return scores


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    def mock_model(prompt: str) -> str:
        return (
            "async def retry(fn, retries=3):\n"
            "    for i in range(retries):\n"
            "        try:\n"
            "            return await fn()\n"
            "        except Exception:\n"
            "            await asyncio.sleep(2**i)\n"
            "This uses asyncio, loguru, sqlite, lora, adapter, circuit breaker pattern, "
            "episodic semantic recall mitre tactic technique detection adversary.\n"
        )

    cb = CodingBenchmark()
    cs = cb.run(mock_model)
    rb = ResearchBenchmark()
    rs = rb.run(mock_model)
    print(f"CodingBenchmark: avg={sum(cs.values())/len(cs):.2f} over {len(cs)} prompts")
    print(f"ResearchBenchmark: avg={sum(rs.values())/len(rs):.2f} over {len(rs)} prompts")
    print("benchmarks.py OK")
