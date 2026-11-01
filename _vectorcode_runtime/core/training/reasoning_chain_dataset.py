"""SFT/DPO dataset adapters from VECTOR's own reasoning + counterfactual memory.

Closes the loop: VECTOR reasons -> stores reasoning_chains -> trains its own
LoRA adapter on them. See plans/post-training-pipeline.md.

DPO pairing caveat (read before trusting this as ground truth): a rejection's
``decision_id`` is actually a generic ``action_type`` string (e.g.
"deploy", "code_review"), not a unique per-decision ID — confirmed by
reading every real call site of ``CounterfactualMemory.record_rejection``.
There is no clean 1:1 "this exact proposal was rejected, here's the exact
alternative chosen instead" pairing in the data as it exists today.
``build_dpo_pairs`` approximates: for a rejection, find a high-reward chain
whose ``action_taken`` text contains the rejection's ``decision_id`` as a
keyword. This is a same-category contrastive signal, not a strict causal
pair — don't mistake it for ground-truth preference data later.
"""
from __future__ import annotations

from loguru import logger

from core.memory.reasoning_memory import ReasoningMemory
from core.memory.counterfactual import CounterfactualMemory

__all__ = ["chains_to_sft_examples", "build_dpo_pairs"]


def chains_to_sft_examples(min_reward: float = 0.7, limit: int = 1000) -> list[dict]:
    """High-reward reasoning_chains -> SFT instruction/response pairs.

    ``ReasoningMemory.get_training_data`` already filters server-side to
    ``is_training_data=1`` (set whenever reward > 0.7 at insert time).
    ``min_reward`` is a redundant client-side safety filter on top — useful
    if the server-side threshold ever changes, or for a stricter cutoff on
    a specific training run. Never raises — this is a batch-job input, not
    a request path.
    """
    try:
        chains = ReasoningMemory().get_training_data(limit=limit)
    except Exception as exc:
        logger.warning("[VECTOR][training] chains_to_sft_examples failed: {}", exc)
        return []

    examples: list[dict] = []
    for chain in chains:
        reward = float(chain.get("reward", 0.0) or 0.0)
        if reward < min_reward:
            continue
        situation = str(chain.get("situation", "")).strip()
        action_taken = str(chain.get("action_taken", "")).strip()
        outcome = str(chain.get("outcome", "")).strip()
        if not situation or not action_taken:
            continue
        examples.append({
            "instruction": situation,
            "response": f"{action_taken}\n\nOutcome: {outcome}" if outcome else action_taken,
            "reward": reward,
            "chain_id": chain.get("chain_id", ""),
        })
    return examples


def build_dpo_pairs(min_reward: float = 0.7, action_type_match: bool = True) -> list[dict]:
    """Counterfactual rejections + high-reward chains -> DPO preference pairs.

    See module docstring for the pairing-approximation caveat.
    """
    try:
        rejections = CounterfactualMemory().get_all_rejections()
    except Exception as exc:
        logger.warning("[VECTOR][training] build_dpo_pairs: rejections fetch failed: {}", exc)
        return []

    try:
        chains = ReasoningMemory().get_training_data(limit=1000)
    except Exception as exc:
        logger.warning("[VECTOR][training] build_dpo_pairs: chains fetch failed: {}", exc)
        return []

    high_reward_chains = [c for c in chains if float(c.get("reward", 0.0) or 0.0) >= min_reward]

    pairs: list[dict] = []
    for rejection in rejections:
        decision_id = str(rejection.get("decision_id", "")).strip()
        proposal = str(rejection.get("proposal", "")).strip()
        if not decision_id or not proposal:
            continue

        match = None
        keyword = decision_id.lower().replace("_", " ")
        for chain in high_reward_chains:
            action_taken = str(chain.get("action_taken", ""))
            if keyword in action_taken.lower():
                match = chain
                break

        if match is None:
            logger.debug("[VECTOR][training] no matching high-reward chain for rejection '{}'", decision_id)
            continue

        action_taken = str(match.get("action_taken", "")).strip()
        outcome = str(match.get("outcome", "")).strip()
        pairs.append({
            "prompt": str(match.get("situation") or decision_id),
            "chosen": f"{action_taken}\n\nOutcome: {outcome}" if outcome else action_taken,
            "rejected": proposal,
        })

    return pairs
