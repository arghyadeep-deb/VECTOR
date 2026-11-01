"""
V.E.C.T.O.R. SynthesisBridge.
Bridges district outputs into coherent system-level synthesis.
"""
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class SynthesisBridge:
    """
    Synthesizes outputs from multiple districts into coherent narratives.
    Used by the reflection district to create consolidated insights.
    """

    def __init__(self):
        logger.info("[VECTOR][synthesis_bridge] SynthesisBridge initialized")

    async def synthesize(self, district_outputs: list[dict], synthesis_type: str = "reflection") -> str | None:
        """
        Synthesize outputs from multiple districts.
        synthesis_type: reflection, council, planning, report
        Routes through provider_client (summarization tier: gemini → cohere → groq → llm7 → ollama).
        """
        try:
            district_summaries = []
            for output in district_outputs:
                source  = output.get("source", "unknown")
                content = output.get("content", "")
                if len(content) > 2000:
                    content = content[:2000] + "..."
                district_summaries.append(f"[{source}]: {content}")

            prompt = (
                f"Synthesize the following district outputs into a coherent {synthesis_type}:\n\n"
                + "\n\n".join(district_summaries)
            )

            from core.inference.provider_client import ProviderClient
            client = ProviderClient()
            result = await client.chat(
                messages=[{"role": "user", "content": prompt}],
                tier="summarization",
                temperature=0.4,
                max_tokens=1000,
                caller_id="synthesis_bridge",
            )
            synthesis = result.content
            logger.info("[VECTOR][synthesis_bridge] Synthesis complete ({})", synthesis_type)
            return synthesis

        except Exception as e:
            logger.error("[VECTOR][synthesis_bridge] Synthesis failed: {}", e)
            return None

    def get_recent_patterns(self, days: int = 1) -> list[str]:
        """Return cross-domain synthesis patterns stored in episodic memory in the last N days.
        Used by DailyReviewer to include pattern descriptions in the morning briefing."""
        try:
            from datetime import timezone, timedelta
            from core.memory.episodic import EpisodicMemory
            em = EpisodicMemory()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            # source NOT LIKE '%test%': integration tests seed this table on the live DB —
            # their rows must never reach the owner's briefing (A6 placeholder bug, 2026-07-08)
            rows = em.conn.execute(
                """SELECT content FROM episodic_memory
                   WHERE event_type='cross_domain_synthesis' AND timestamp >= ?
                   AND source NOT LIKE '%test%'
                   ORDER BY timestamp DESC LIMIT 20""",
                (cutoff,),
            ).fetchall()
            patterns = [r[0] for r in rows if r[0]]
            logger.debug("[VECTOR][synthesis_bridge] get_recent_patterns: {} found (days={})", len(patterns), days)
            return patterns
        except Exception as e:
            logger.debug("[VECTOR][synthesis_bridge] get_recent_patterns failed: {}", e)
            return []

    def quick_merge(self, texts: list[str], max_len: int = 500) -> str:
        """Quick merge without LLM — concatenate and truncate."""
        merged = "\n---\n".join(texts)
        return merged[:max_len] + "..." if len(merged) > max_len else merged


if __name__ == "__main__":
    sb = SynthesisBridge()
    outputs = [
        {"source": "reflection", "content": "Today I worked on the codebase."},
        {"source": "health", "content": "Slept well, exercised 30 minutes."},
    ]
    import asyncio
    async def test():
        result = await sb.synthesize(outputs)
        print(result)
    asyncio.run(test())