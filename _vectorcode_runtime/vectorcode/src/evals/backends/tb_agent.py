# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Custom terminal-bench agent that wraps NaiveAgent with LiteLLM construction."""

from __future__ import annotations

from terminal_bench.agents.naive_agent import NaiveAgent
from terminal_bench.llms.lite_llm import LiteLLM

class VectorCodeTerminalBenchAgent(NaiveAgent):
    """NaiveAgent that constructs its own LiteLLM from string kwargs.

    This avoids serialization issues in terminal-bench's lock file
    by accepting string parameters instead of an LiteLLM object.
    """

    @staticmethod
    def name() -> str:
        return "vector"

    def __init__(
        self,
        model_name: str = "openai/default",
        api_base: str = "http://localhost:8000/v1",
        temperature: float = 0.2,
        **kwargs,
    ):
        llm = LiteLLM(
            model_name=model_name,
            temperature=temperature,
            api_base=api_base,
        )
        super().__init__(llm=llm, **kwargs)
