"""
Tests for core/training/reasoning_chain_dataset.py — the SFT/DPO dataset
adapters that read real VECTOR memory tables (reasoning_chains,
counterfactual rejections) and convert them into training-ready examples.

Per plans/post-training-pipeline.md: the DPO pairing is an *approximation*
(same action_type keyword match between a rejection and a high-reward
chain), not a strict causal "this exact alternative was chosen instead"
pair — these tests lock in that documented behavior, not stricter.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_chains_to_sft_examples_filters_by_reward_threshold(monkeypatch):
    from core.training.reasoning_chain_dataset import chains_to_sft_examples

    class _FakeReasoningMemory:
        def get_training_data(self, limit=1000):
            return [
                {"situation": "deploy failing", "steps": ["check logs", "rollback"],
                 "action_taken": "rollback", "outcome": "service restored", "reward": 0.9, "chain_id": "c1"},
                {"situation": "low confidence task", "steps": [], "action_taken": "defer",
                 "outcome": "ok", "reward": 0.5, "chain_id": "c2"},  # below threshold — excluded
            ]

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.ReasoningMemory",
        lambda: _FakeReasoningMemory(),
    )
    examples = chains_to_sft_examples(min_reward=0.7)
    assert len(examples) == 1
    assert examples[0]["reward"] == 0.9
    assert "instruction" in examples[0] and "response" in examples[0]


def test_chains_to_sft_examples_empty_table_returns_empty_list(monkeypatch):
    from core.training.reasoning_chain_dataset import chains_to_sft_examples

    class _EmptyReasoningMemory:
        def get_training_data(self, limit=1000):
            return []

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.ReasoningMemory",
        lambda: _EmptyReasoningMemory(),
    )
    assert chains_to_sft_examples() == []


def test_chains_to_sft_examples_returns_empty_on_exception(monkeypatch):
    from core.training.reasoning_chain_dataset import chains_to_sft_examples

    class _BrokenReasoningMemory:
        def get_training_data(self, limit=1000):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "core.training.reasoning_chain_dataset.ReasoningMemory",
        lambda: _BrokenReasoningMemory(),
    )
    assert chains_to_sft_examples() == []


def test_build_dpo_pairs_matches_rejection_to_same_action_type_high_reward_chain(monkeypatch):
    from core.training.reasoning_chain_dataset import build_dpo_pairs

    class _FakeCounterfactual:
        def get_all_rejections(self, limit=200):
            return [{"decision_id": "deploy", "proposal": "deploy untested", "reason": "no tests run"}]

    class _FakeReasoningMemory:
        def get_training_data(self, limit=1000):
            return [{"situation": "deploy ready", "action_taken": "deploy after tests pass",
                      "outcome": "ok", "reward": 0.85}]

    monkeypatch.setattr("core.training.reasoning_chain_dataset.CounterfactualMemory", lambda: _FakeCounterfactual())
    monkeypatch.setattr("core.training.reasoning_chain_dataset.ReasoningMemory", lambda: _FakeReasoningMemory())

    pairs = build_dpo_pairs()
    assert len(pairs) == 1
    assert pairs[0]["rejected"] == "deploy untested"
    assert "deploy after tests pass" in pairs[0]["chosen"]


def test_build_dpo_pairs_skips_rejection_with_no_matching_chain(monkeypatch):
    from core.training.reasoning_chain_dataset import build_dpo_pairs

    class _FakeCounterfactual:
        def get_all_rejections(self, limit=200):
            return [{"decision_id": "totally_unmatched_action", "proposal": "x", "reason": "y"}]

    class _FakeReasoningMemory:
        def get_training_data(self, limit=1000):
            return [{"situation": "unrelated", "action_taken": "unrelated action",
                      "outcome": "ok", "reward": 0.9}]

    monkeypatch.setattr("core.training.reasoning_chain_dataset.CounterfactualMemory", lambda: _FakeCounterfactual())
    monkeypatch.setattr("core.training.reasoning_chain_dataset.ReasoningMemory", lambda: _FakeReasoningMemory())

    assert build_dpo_pairs() == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
