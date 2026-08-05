"""
V.E.C.T.O.R. CouncilBrain.
High-level decision-making orchestration between districts and the LLM council.
"""
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class CouncilBrain:
    """
    Orchestrates the governance council for high-stakes decisions.
    Interfaces between district agents and the LLM council.
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._council_model = CONFIG["models"]["chairman"]
        self._council_members = [
            CONFIG["models"]["reasoning"],
            CONFIG["models"]["cloud_orchestrator"],
            CONFIG["models"]["cloud_coder"],
        ]
        logger.info("[VECTOR][council_brain] CouncilBrain initialized")

    async def deliberate(self, question: str, hp_gate: int = 700) -> dict:
        """
        Submit a question to the council for deliberation.
        Returns {stage1: [...], stage2: [...], verdict: str, confidence: float}
        """
        try:
            import ollama
            # 2026-08-05 (connection-leak fix, same as ollama_safe.py): must be
            # `with ... as client:`, not a bare assignment — ollama.Client()
            # wraps an httpx.Client() whose socket is only reclaimed by a
            # cyclic-GC sweep, not refcounting, if left unclosed.
            with ollama.Client(host=self._ollama_host, timeout=5.0) as client:
                stage1_responses = []
                for member in self._council_members:
                    resp = client.chat(
                        model=member,
                        messages=[{"role": "user", "content": question}],
                        options={"temperature": 0.7, "num_predict": 500}
                    )
                    stage1_responses.append(resp["message"]["content"])

                ranked = sorted(stage1_responses, key=len, reverse=True)
                synthesize_prompt = f"Question: {question}\n\nResponses from council members:\n" + "\n".join(f"- {r}" for r in ranked)
                verdict_resp = client.chat(
                    model=self._council_model,
                    messages=[{"role": "user", "content": synthesize_prompt}],
                    options={"temperature": 0.3, "num_predict": 800}
                )

            return {
                "stage1": stage1_responses,
                "stage2": ranked,
                "verdict": verdict_resp["message"]["content"],
                "confidence": 0.75,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"[VECTOR][council_brain] Deliberation failed: {e}")
            return {"error": str(e)}

    async def deliberate_action(self, action_type: str, params: dict, context: str = "") -> dict:
        """Structured deliberation for a specific action proposal.
        Returns {verdict: proceed|reject|defer, votes: list[str], rationale: str, confidence: float}.
        Falls back to defer when Ollama is unavailable so the gateway can proceed normally."""
        question = (
            f"Proposed action: {action_type}\n"
            f"Parameters: {params}\n"
            f"Context: {context[:400] if context else 'none'}\n\n"
            "Decide: should VECTOR proceed, reject, or defer this action to the owner?\n"
            "Reply with exactly one of: PROCEED, REJECT, DEFER — then one sentence rationale."
        )
        try:
            raw = await self.deliberate(question)
            if "error" in raw:
                return {"verdict": "defer", "votes": [], "rationale": raw["error"][:200], "confidence": 0.0}
            verdict_text = raw.get("verdict", "")
            # Parse structured verdict from LLM text
            upper = verdict_text.upper()
            if "PROCEED" in upper:
                verdict = "proceed"
            elif "REJECT" in upper:
                verdict = "reject"
            else:
                verdict = "defer"
            return {
                "verdict": verdict,
                "votes": raw.get("stage1", []),
                "rationale": verdict_text[:500],
                "confidence": raw.get("confidence", 0.75),
            }
        except Exception as e:
            logger.warning("[VECTOR][council_brain] deliberate_action failed: {}", e)
            return {"verdict": "defer", "votes": [], "rationale": f"Council error: {e!s:.120}", "confidence": 0.0}

    def can_afford_deliberation(self, hp: int) -> bool:
        """Check if the requester's HP meets the council gate."""
        gate = CONFIG.get("council", {}).get("hp_gate", 700)
        return hp >= gate


if __name__ == "__main__":
    import asyncio
    async def test():
        cb = CouncilBrain()
        result = await cb.deliberate("Should V.E.C.T.O.R. deploy the new coding district?")
        print(result["verdict"] if "verdict" in result else result)
    asyncio.run(test())