"""
V.E.C.T.O.R. CouncilBrain.
High-level decision-making orchestration between districts and the LLM council.

2026-09-24 (external review, Phase 2) rewrite. Verified problems in the
original design, sized from data/council_log.jsonl (1,863 real
deliberations):
  - 5.0s timeout was far too short for a cold Ollama model swap under
    OLLAMA_MAX_LOADED_MODELS=1 -- 58% of deliberations timed out and
    defaulted to defer.
  - 3 DIFFERENT models called sequentially (reasoning, cloud_orchestrator,
    cloud_coder) forced a cold swap on nearly every member call.
  - "Ranking" was `sorted(responses, key=len)` -- no real vote was ever
    extracted from a member's response; only the chairman's free text got
    a PROCEED/REJECT/DEFER keyword match, and only by the CALLER
    (permission_gateway.py), not by this class.
  - confidence was hardcoded to exactly 0.75 -- since
    permission_gateway.py's auto-proceed gate is `confidence >= 0.75`,
    the gate never actually filtered anything; every "proceed" verdict
    passed it by construction.

Fix: one model for all 3 members (eliminates the swap-thrashing root
cause -- Strategy 2 of the 3 options), each explicitly asked for a
structured PROCEED/REJECT/DEFER vote, real majority tally, chairman
tiebreak ONLY on a genuine split (saves a call+swap on the common
case), and confidence computed from real vote agreement. Both
ollama.Client() calls are blocking/sync, so they run in
asyncio.to_thread() -- this method is called from the live autonomous
loop's event loop (via permission_gateway.py's RED-tier path) and a
5-30s blocking call inline would freeze it.

Safety behaviour UNCHANGED: any exception or a fully-defer outcome
still returns 'defer'; OWNER_APPROVAL_ONLY and RED_INTERACTIVE_TOOLS
still skip this entirely (see permission_gateway.py's own gate before
calling _handle_red_tier).
"""
import asyncio
import re
from collections import Counter
from datetime import datetime, timezone

from loguru import logger

from core.config import CONFIG

_VOTE_RE = re.compile(r"\b(PROCEED|REJECT|DEFER)\b", re.IGNORECASE)

_MEMBER_ROLES = (
    "You are a CAUTIOUS council member. Weigh risk and reversibility heavily.",
    "You are a PRAGMATIC council member. Weigh whether this action matches "
    "VECTOR's normal, already-approved patterns of behavior.",
    "You are a LONG-TERM council member. Weigh whether this sets a precedent "
    "VECTOR should be comfortable repeating unattended.",
)


def _parse_vote(text: str) -> str:
    """Extract a PROCEED/REJECT/DEFER vote from free text. Fail-closed:
    ambiguous or absent -> defer, matching this file's own established
    convention for the chairman verdict before this rewrite."""
    match = _VOTE_RE.search(text or "")
    return match.group(1).lower() if match else "defer"


class CouncilBrain:
    """
    Orchestrates the governance council for high-stakes decisions.
    Interfaces between district agents and the LLM council.
    """

    def __init__(self):
        self._ollama_host = CONFIG["ollama_host"]
        self._council_model = CONFIG["models"]["chairman"]
        self._member_model = CONFIG["models"]["reasoning"]
        logger.info("[VECTOR][council_brain] CouncilBrain initialized")

    def _timeout(self) -> float:
        return CONFIG.get("council", {}).get("deliberation_timeout", 30.0)

    async def deliberate(self, question: str, hp_gate: int = 700) -> dict:
        """
        Submit a question to the council for deliberation.
        Returns {stage1: [...], votes: [...], verdict: str, confidence: float,
        verdict_text: str, timestamp: str} or {"error": str} on failure.
        """
        timeout = self._timeout()

        def _sync_members() -> list[str]:
            import ollama
            with ollama.Client(host=self._ollama_host, timeout=timeout) as client:
                responses = []
                for role_prompt in _MEMBER_ROLES:
                    resp = client.chat(
                        model=self._member_model,
                        messages=[
                            {"role": "system", "content": role_prompt},
                            {"role": "user", "content": question},
                        ],
                        options={"temperature": 0.7, "num_predict": 400},
                    )
                    responses.append(resp["message"]["content"])
                return responses

        def _sync_chairman(prompt: str) -> str:
            import ollama
            with ollama.Client(host=self._ollama_host, timeout=timeout) as client:
                resp = client.chat(
                    model=self._council_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.3, "num_predict": 500},
                )
                return resp["message"]["content"]

        try:
            stage1_responses = await asyncio.to_thread(_sync_members)
            votes = [_parse_vote(r) for r in stage1_responses]
            tally = Counter(votes).most_common()

            if len(tally) == 1 or tally[0][1] > tally[1][1]:
                # clear majority -- no chairman call needed, saves a model
                # swap on the common case
                verdict = tally[0][0]
                agreement = tally[0][1] / len(votes)
                confidence = round(0.5 + 0.5 * agreement, 2)
                verdict_text = f"Majority vote {tally[0][1]}/{len(votes)}: {verdict}"
            else:
                # genuine split -- chairman breaks the tie; conservative
                # confidence since the council itself did not agree
                synth_prompt = (
                    f"Question: {question}\n\nCouncil member responses:\n"
                    + "\n".join(f"- {r}" for r in stage1_responses)
                    + "\n\nThe council is split. As chairman, break the tie. "
                      "Reply with exactly one of PROCEED, REJECT, or DEFER, "
                      "then one sentence of rationale."
                )
                verdict_text = await asyncio.to_thread(_sync_chairman, synth_prompt)
                verdict = _parse_vote(verdict_text)
                confidence = 0.5

            return {
                "stage1": stage1_responses,
                "votes": votes,
                "verdict": verdict,
                "verdict_text": verdict_text,
                "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            return {
                "verdict": raw.get("verdict", "defer"),
                "votes": raw.get("votes", []),
                "rationale": raw.get("verdict_text", "")[:500],
                "confidence": raw.get("confidence", 0.0),
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
