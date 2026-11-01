"""
VECTOR Hedge — Autonomous multi-agent trading intelligence.

Five-agent pipeline: Trading Director → Quant-Analyst → Risk-Manager →
Execution-Agent → Sentiment-Agent. Covers equities and Solana DEX via
Jupiter Protocol. Analysis only by default; live execution requires
SOLANA_PRIVATE_KEY + JUPITER_API_KEY in .env.
"""
from districts.investment.vector_hedgebot.orchestrator import VECTORHedge

__all__ = ["VECTORHedge"]
