"""
V.E.C.T.O.R. SynthesisBridge.
Bridges district outputs into coherent system-level synthesis.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class SynthesisBridge:
    """
    Synthesizes outputs from multiple districts into coherent narratives.
    Used by the reflection district to create consolidated insights.
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._synthesis_model = CONFIG["models"]["deep"]
        logger.info("[VECTOR][synthesis_bridge] SynthesisBridge initialized")

    async def synthesize(self, district_outputs: list[dict], synthesis_type: str = "reflection") -> str:
        """
        Synthesize outputs from multiple districts.
        synthesis_type: reflection, council, planning, report
        """
        try:
            import ollama
            client = ollama.Client(host=self._ollama_host)

            district_summaries = []
            for output in district_outputs:
                source = output.get("source", "unknown")
                content = output.get("content", "")
                if len(content) > 2000:
                    content = content[:2000] + "..."
                district_summaries.append(f"[{source}]: {content}")

            prompt = f"Synthesize the following district outputs into a coherent {synthesis_type}:\n\n"
            prompt += "\n\n".join(district_summaries)

            response = client.chat(
                model=self._synthesis_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.4, "num_predict": 1000}
            )

            synthesis = response["message"]["content"]
            logger.info(f"[VECTOR][synthesis_bridge] Synthesis complete ({synthesis_type})")
            return synthesis

        except Exception as e:
            logger.error(f"[VECTOR][synthesis_bridge] Synthesis failed: {e}")
            return f"Synthesis failed: {e}"

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