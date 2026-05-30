"""
V.E.C.T.O.R. HypothesisEngine.
Generates and tests hypotheses about the world and V.E.C.T.O.R.'s behavior.
"""
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class HypothesisEngine:
    """
    Generates hypotheses about user behavior, system performance, and environmental changes.
    Tests them against episodic memory and refines understanding over time.
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._reasoning_model = CONFIG["models"]["reasoning"]
        self._hypotheses: list[dict] = []
        self._tests: list[dict] = []
        logger.info("[VECTOR][hypothesis_engine] HypothesisEngine initialized")

    async def generate_hypotheses(self, observation: str, count: int = 3) -> list[dict]:
        """Generate hypotheses from an observation."""
        try:
            import ollama
            client = ollama.Client(host=self._ollama_host)

            prompt = f"Given this observation, generate {count} hypotheses:\n\n{observation}\n\n"
            prompt += "For each hypothesis provide: id, hypothesis_text, why_it_might_be_true, "
            prompt += "how_to_test, expected_evidence"

            response = client.chat(
                model=self._reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.5, "num_predict": 800}
            )

            hypothesis = {
                "id": str(len(self._hypotheses) + 1),
                "observation": observation,
                "text": response["message"]["content"],
                "timestamp": datetime.utcnow().isoformat(),
                "status": "generated",
                "confidence": 0.7,
            }
            self._hypotheses.append(hypothesis)
            logger.info(f"[VECTOR][hypothesis_engine] Generated hypothesis from: {observation[:50]}...")
            # Enqueue in SuggestionQueue so _reflect_tick can surface top-3 (Gap 5)
            try:
                from core.brain.suggestion_queue import SuggestionQueue
                _sq = SuggestionQueue()
                _sq.enqueue(hypothesis["text"][:500], confidence=hypothesis["confidence"])
                _sq.close()
            except Exception as _sqe:
                logger.debug("[VECTOR][hypothesis_engine] SuggestionQueue enqueue skipped: {}", _sqe)
            return hypothesis

        except Exception as e:
            logger.error(f"[VECTOR][hypothesis_engine] Generation failed: {e}")
            return []

    async def test_hypothesis(self, hypothesis_id: str, evidence: str) -> dict:
        """Test a hypothesis against new evidence."""
        for h in self._hypotheses:
            if h["id"] == hypothesis_id:
                prompt = f"Hypothesis: {h['text']}\n\nEvidence: {evidence}\n\n"
                prompt += "Evaluate: supported, refuted, or inconclusive. Update the hypothesis accordingly."

                try:
                    import ollama
                    client = ollama.Client(host=self._ollama_host)
                    response = client.chat(
                        model=self._reasoning_model,
                        messages=[{"role": "user", "content": prompt}],
                        options={"temperature": 0.3, "num_predict": 400}
                    )

                    result = {
                        "hypothesis_id": hypothesis_id,
                        "verdict": response["message"]["content"],
                        "evidence": evidence,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    self._tests.append(result)
                    h["status"] = "tested"
                    h["verdict"] = result["verdict"]
                    return result

                except Exception as e:
                    logger.error(f"[VECTOR][hypothesis_engine] test_hypothesis failed: {e}")
                    return {"error": str(e)}

        return {"error": f"Hypothesis {hypothesis_id} not found"}

    def get_active_hypotheses(self) -> list[dict]:
        """Get all untested hypotheses."""
        return [h for h in self._hypotheses if h.get("status") == "generated"]

    def get_confirmed_hypotheses(self) -> list[dict]:
        """Get all confirmed hypotheses (supported by evidence)."""
        return [h for h in self._hypotheses if h.get("verdict", "").lower().startswith("supported")]


if __name__ == "__main__":
    import asyncio
    he = HypothesisEngine()
    hyp = asyncio.run(he.generate_hypotheses("User tends to be more productive in the morning"))
    print(hyp.get("text", "no hypothesis")[:200])