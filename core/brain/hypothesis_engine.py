"""
V.E.C.T.O.R. HypothesisEngine — Gap 5: proactive insights every 4h.
Routes through provider_client (reasoning tier: github_models → groq → llm7 → ollama).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from core.config import CONFIG


class HypothesisEngine:
    """
    Generates hypotheses about user behaviour, system performance, and
    environmental changes. Tests them against episodic memory over time.
    """

    _SYSTEM = (
        "You are VECTOR's hypothesis engine. You observe patterns and generate "
        "testable hypotheses about the user, the system, and the environment. "
        "Be specific, falsifiable, and prioritise hypotheses that lead to action."
    )

    def __init__(self) -> None:
        self._hypotheses: list[dict] = []
        self._tests: list[dict] = []
        logger.info("[VECTOR][hypothesis_engine] HypothesisEngine initialized")

    async def _call(self, user_prompt: str, temperature: float = 0.5, max_tokens: int = 800) -> str:
        from core.inference.provider_client import ProviderClient
        client = ProviderClient()
        result = await client.chat(
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            tier="reasoning",
            temperature=temperature,
            max_tokens=max_tokens,
            caller_id="hypothesis_engine",
        )
        return result.content

    async def generate_hypotheses(self, observation: str, count: int = 3) -> dict:
        """Generate hypotheses from an observation."""
        prompt = (
            f"Given this observation, generate {count} hypotheses:\n\n{observation}\n\n"
            "For each hypothesis provide: id, hypothesis_text, why_it_might_be_true, "
            "how_to_test, expected_evidence"
        )
        try:
            content = await self._call(prompt, temperature=0.5, max_tokens=800)
            hypothesis = {
                "id":          str(len(self._hypotheses) + 1),
                "observation": observation,
                "text":        content,
                "timestamp":   datetime.utcnow().isoformat(),
                "status":      "generated",
                "confidence":  0.7,
            }
            self._hypotheses.append(hypothesis)
            logger.info("[VECTOR][hypothesis_engine] Generated hypothesis from: {}...", observation[:50])
            try:
                from core.brain.suggestion_queue import SuggestionQueue
                sq = SuggestionQueue()
                sq.enqueue(hypothesis["text"][:500], confidence=hypothesis["confidence"])
                sq.close()
            except Exception as e:
                logger.debug("[VECTOR][hypothesis_engine] SuggestionQueue skipped: {}", e)
            return hypothesis
        except Exception as e:
            logger.error("[VECTOR][hypothesis_engine] generate_hypotheses failed: {}", e)
            return {"error": str(e)}

    async def test_hypothesis(self, hypothesis_id: str, evidence: str) -> dict:
        """Test a hypothesis against new evidence."""
        for h in self._hypotheses:
            if h["id"] == hypothesis_id:
                prompt = (
                    f"Hypothesis: {h['text']}\n\nEvidence: {evidence}\n\n"
                    "Evaluate: supported, refuted, or inconclusive. Update the hypothesis accordingly."
                )
                try:
                    content = await self._call(prompt, temperature=0.3, max_tokens=400)
                    result = {
                        "hypothesis_id": hypothesis_id,
                        "verdict":       content,
                        "evidence":      evidence,
                        "timestamp":     datetime.utcnow().isoformat(),
                    }
                    self._tests.append(result)
                    h["status"]  = "tested"
                    h["verdict"] = content
                    return result
                except Exception as e:
                    logger.error("[VECTOR][hypothesis_engine] test_hypothesis failed: {}", e)
                    return {"error": str(e)}
        return {"error": f"Hypothesis {hypothesis_id} not found"}

    def get_active_hypotheses(self) -> list[dict]:
        return [h for h in self._hypotheses if h.get("status") == "generated"]

    def get_confirmed_hypotheses(self) -> list[dict]:
        return [h for h in self._hypotheses if h.get("verdict", "").lower().startswith("supported")]


if __name__ == "__main__":
    import asyncio
    he = HypothesisEngine()
    hyp = asyncio.run(he.generate_hypotheses("User tends to be more productive in the morning"))
    print(str(hyp.get("text", hyp.get("error", "no result")))[:200])
    print("OK hypothesis_engine.py")
