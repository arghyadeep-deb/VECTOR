"""
ReasoningAgent — wraps vectorcode's ReasoningBank for past chain injection.

RULE 8: Every thought-action-outcome stored. inject_past_reasoning() before
similar decisions. This agent is the RULE 8 compliance layer for vectorcode.
High-reward chains (>0.7) tagged as training data for the custom LLM.
"""
from __future__ import annotations


from loguru import logger
from core.config import CONFIG


class ReasoningAgent:
    """
    Reasoning chain manager. Stores, retrieves, and injects past reasoning
    before vectorcode makes decisions. Core RULE 8 enforcement agent.
    """

    def __init__(self):
        self._bank = None
        self._pattern_learner = None
        logger.info("[VECTOR][vc_reasoning] initialized")

    def _get_bank(self):
        if self._bank is None:
            try:
                from vectorcode.src.reasoning_bank import ReasoningBank
                self._bank = ReasoningBank()
                self._bank.load()
            except Exception as e:
                logger.debug("[VECTOR][vc_reasoning] ReasoningBank unavailable: {}", e)
        return self._bank

    def _get_pattern_learner(self):
        if self._pattern_learner is None:
            try:
                from vectorcode.src.reasoning_bank import PatternLearner
                self._pattern_learner = PatternLearner()
                self._pattern_learner.load()
            except Exception as e:
                logger.debug("[VECTOR][vc_reasoning] PatternLearner unavailable: {}", e)
        return self._pattern_learner

    def store(self, thought: str, action: str, outcome: str,
              reward: float = 0.5, task_type: str = "general") -> bool:
        """Store a reasoning chain (RULE 8 — after every action)."""
        bank = self._get_bank()
        if bank:
            try:
                bank.store(thought=thought, action=action, outcome=outcome,
                           reward=reward, task_type=task_type)
                if reward > 0.7:
                    bank.save()
                    logger.info("[VECTOR][vc_reasoning] high-reward chain stored (reward={:.2f})", reward)
                return True
            except Exception as e:
                logger.warning("[VECTOR][vc_reasoning] store failed: {}", e)
        return False

    def inject_past_reasoning(self, task: str, top_k: int = 3) -> str:
        """Retrieve and format past reasoning chains for LLM context injection (RULE 8)."""
        bank = self._get_bank()
        if bank:
            try:
                chains = bank.retrieve(task, top_k=top_k)
                if chains:
                    injected = "\n\n".join(
                        f"[Past reasoning #{i+1} — reward={c.get('reward', 0):.2f}]\n"
                        f"Thought: {c.get('thought', '')[:200]}\n"
                        f"Action: {c.get('action', '')[:100]}\n"
                        f"Outcome: {c.get('outcome', '')[:100]}"
                        for i, c in enumerate(chains)
                    )
                    logger.debug("[VECTOR][vc_reasoning] injected {} chains for '{}'", len(chains), task[:40])
                    return injected
            except Exception as e:
                logger.debug("[VECTOR][vc_reasoning] inject failed: {}", e)
        return ""

    def get_best_strategy(self, situation: str) -> dict:
        """Return the highest-reward strategy for a given situation type."""
        learner = self._get_pattern_learner()
        if learner:
            try:
                return learner.get_best_strategies(situation, top_k=1)[0]
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        return {"strategy": "default", "confidence": 0.5}

    def get_training_data_count(self) -> int:
        """Count high-reward chains flagged as training data."""
        bank = self._get_bank()
        if bank:
            try:
                return bank.training_data_count()
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        return 0


if __name__ == "__main__":
    agent = ReasoningAgent()
    stored = agent.store(
        thought="User asked to review code. Best approach: AST analysis first.",
        action="run code_reviewer with AST mode",
        outcome="found 3 issues, user happy",
        reward=0.8, task_type="code_review"
    )
    print(f"[OK] store: {stored}")
    injection = agent.inject_past_reasoning("code review task")
    print(f"[OK] inject: {len(injection)} chars injected")
    count = agent.get_training_data_count()
    print(f"[OK] training_data: {count} chains")
    print("reasoning_agent.py OK")
