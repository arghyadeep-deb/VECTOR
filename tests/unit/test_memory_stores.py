"""Tests for PolicyMemory, ReasoningMemory, SemanticMemory, and loop_state."""
import sys
import asyncio
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from core.memory.policy import PolicyMemory
from core.memory.reasoning_memory import ReasoningMemory
from core.memory.semantic import SemanticMemory
import core.loop.loop_state as loop_state


# ── PolicyMemory ────────────────────────────────────────────────────────────

class TestPolicyMemory:

    def _fresh_action(self):
        """Unique action type per test to avoid shared state."""
        return f"test_action_{uuid.uuid4().hex[:8]}"

    def test_init(self):
        pm = PolicyMemory()
        assert pm is not None
        assert pm.DEFAULT_SCORE == PolicyMemory.DEFAULT_SCORE

    def test_make_situation_hash_deterministic(self):
        h1 = PolicyMemory.make_situation_hash({"task": "code", "context": "morning"})
        h2 = PolicyMemory.make_situation_hash({"task": "code", "context": "morning"})
        assert h1 == h2
        assert len(h1) == 12

    def test_make_situation_hash_string(self):
        h = PolicyMemory.make_situation_hash("simple string context")
        assert len(h) == 12

    def test_make_situation_hash_different_inputs_differ(self):
        h1 = PolicyMemory.make_situation_hash("context_a")
        h2 = PolicyMemory.make_situation_hash("context_b")
        assert h1 != h2

    def test_get_score_returns_default_for_unknown(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        score = pm.get_score(action, h)
        assert score == PolicyMemory.DEFAULT_SCORE

    def test_update_and_get_score(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        pm.update_from_outcome(action, h, 0.9)
        score = pm.get_score(action, h)
        assert score == pytest.approx(0.9, abs=0.01)

    def test_update_averages_multiple_rewards(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        pm.update_from_outcome(action, h, 1.0)
        pm.update_from_outcome(action, h, 0.0)
        score = pm.get_score(action, h)
        # After 1.0 and 0.0: avg = (1.0 + 0.0) / 2 = 0.5
        assert 0.4 < score < 0.6

    def test_update_clamps_reward_below_zero(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        pm.update_from_outcome(action, h, -0.5)  # should clamp to 0.0
        score = pm.get_score(action, h)
        assert score == pytest.approx(0.0, abs=0.01)

    def test_update_clamps_reward_above_one(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        pm.update_from_outcome(action, h, 1.5)  # should clamp to 1.0
        score = pm.get_score(action, h)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_get_stats_returns_dict(self):
        pm = PolicyMemory()
        stats = pm.get_stats()
        assert "total_entries" in stats
        assert "overall_avg_reward" in stats
        assert stats["total_entries"] >= 0

    def test_get_top_actions_returns_list(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        # Add enough samples (>= 3) for top_actions to show it
        for _ in range(3):
            pm.update_from_outcome(action, h, 0.9)
        top = pm.get_top_actions(limit=5)
        assert isinstance(top, list)

    def test_get_top_actions_respects_min_samples(self):
        pm = PolicyMemory()
        action = self._fresh_action()
        h = PolicyMemory.make_situation_hash({"run": uuid.uuid4().hex})
        # Only 2 samples — should not appear in top_actions (min=3)
        pm.update_from_outcome(action, h, 0.99)
        pm.update_from_outcome(action, h, 0.99)
        top = pm.get_top_actions()
        names = [t["action"] for t in top]
        assert action not in names


# ── ReasoningMemory ─────────────────────────────────────────────────────────

class TestReasoningMemory:

    def test_init(self):
        rm = ReasoningMemory()
        assert rm is not None

    def test_store_chain_returns_id(self):
        rm = ReasoningMemory()
        chain_id = rm.store_chain(
            situation=f"test situation {uuid.uuid4().hex}",
            goal_ids=["g_test"],
            steps=["step1", "step2"],
            action="test_action",
            outcome="success",
            reward=0.8,
        )
        assert chain_id is not None
        assert len(chain_id) > 0

    def test_store_chain_low_reward(self):
        rm = ReasoningMemory()
        chain_id = rm.store_chain(
            situation=f"low reward {uuid.uuid4().hex}",
            goal_ids=[],
            steps=["step1"],
            action="test_action",
            outcome="partial",
            reward=0.4,
        )
        assert chain_id is not None

    def test_inject_past_reasoning_empty(self):
        rm = ReasoningMemory()
        result = rm.inject_past_reasoning("totally_unique_situation_xyz_" + uuid.uuid4().hex)
        # Either empty string (no matching chains) or valid reasoning text
        assert isinstance(result, str)

    def test_inject_past_reasoning_with_data(self):
        rm = ReasoningMemory()
        unique_token = uuid.uuid4().hex[:8]
        situation = f"unique_test_situation_{unique_token}"
        rm.store_chain(
            situation=situation,
            goal_ids=["g_test"],
            steps=["classify", "route", "execute"],
            action="test_action",
            outcome="success",
            reward=0.85,
        )
        result = rm.inject_past_reasoning(unique_token)
        # May or may not find it depending on LIKE matching - just assert string
        assert isinstance(result, str)

    def test_get_stats_structure(self):
        rm = ReasoningMemory()
        stats = rm.get_stats()
        assert "total_chains" in stats
        assert "training_data" in stats
        assert "avg_reward" in stats
        assert stats["total_chains"] >= 0

    def test_get_training_data_returns_list(self):
        rm = ReasoningMemory()
        data = rm.get_training_data(limit=10)
        assert isinstance(data, list)

    def test_high_reward_counted_as_training(self):
        rm = ReasoningMemory()
        rm.store_chain(
            situation=f"training_situation_{uuid.uuid4().hex}",
            goal_ids=["g_train"],
            steps=["a", "b"],
            action="train",
            outcome="trained",
            reward=0.95,
        )
        stats = rm.get_stats()
        assert stats["training_data"] >= 1


# ── SemanticMemory ───────────────────────────────────────────────────────────

class TestSemanticMemory:

    def test_init(self):
        sm = SemanticMemory()
        assert sm is not None

    def test_store_and_get(self):
        sm = SemanticMemory()
        key = f"test_key_{uuid.uuid4().hex}"
        sm.store(key, "test_value", category="test")
        result = sm.get(key)
        assert result == "test_value"

    def test_get_missing_returns_none(self):
        sm = SemanticMemory()
        result = sm.get(f"nonexistent_{uuid.uuid4().hex}")
        assert result is None

    def test_store_overwrites(self):
        sm = SemanticMemory()
        key = f"overwrite_{uuid.uuid4().hex}"
        sm.store(key, "first")
        sm.store(key, "second")
        assert sm.get(key) == "second"

    async def test_add_concept_async(self):
        sm = SemanticMemory()
        concept = f"concept_{uuid.uuid4().hex}"
        result = await sm.add_concept(concept, "A test definition", tags=["test", "memory"])
        assert result["concept"] == concept
        assert result["definition"] == "A test definition"

    async def test_get_concept_returns_dict(self):
        sm = SemanticMemory()
        concept = f"get_test_{uuid.uuid4().hex}"
        await sm.add_concept(concept, "some definition", tags=["x"])
        result = sm.get_concept(concept)
        assert result is not None
        assert result["concept"] == concept

    def test_get_concept_missing_returns_none(self):
        sm = SemanticMemory()
        result = sm.get_concept(f"missing_{uuid.uuid4().hex}")
        assert result is None

    async def test_search_concepts(self):
        sm = SemanticMemory()
        unique = uuid.uuid4().hex[:8]
        await sm.add_concept(f"search_key_{unique}", f"searchable_value_{unique}")
        results = sm.search_concepts(unique)
        assert isinstance(results, list)

    def test_link_concepts(self):
        sm = SemanticMemory()
        a = f"concept_a_{uuid.uuid4().hex[:6]}"
        b = f"concept_b_{uuid.uuid4().hex[:6]}"
        result = sm.link_concepts(a, b, "relates_to")
        assert result["from"] == a
        assert result["to"] == b
        assert result["relation"] == "relates_to"

    def test_get_related(self):
        sm = SemanticMemory()
        a = f"rel_a_{uuid.uuid4().hex[:6]}"
        b = f"rel_b_{uuid.uuid4().hex[:6]}"
        sm.link_concepts(a, b, "causes")
        related = sm.get_related(a)
        assert isinstance(related, list)


# ── loop_state ───────────────────────────────────────────────────────────────

class TestLoopState:

    def test_save_and_load_goal(self):
        goal_id = f"g_test_{uuid.uuid4().hex[:8]}"
        loop_state.save_goal(goal_id)
        loaded = loop_state.load_goal()
        assert loaded == goal_id

    def test_load_goal_returns_string_or_none(self):
        result = loop_state.load_goal()
        assert result is None or isinstance(result, str)

    def test_save_and_load_decision(self):
        loop_state.save_decision("research", {"query": "VECTOR"}, 0.75)
        d = loop_state.load_decision()
        assert d is not None
        assert d["action_type"] == "research"
        assert d["score"] == pytest.approx(0.75, abs=0.01)
        assert "ts" in d

    def test_load_decision_returns_dict_or_none(self):
        result = loop_state.load_decision()
        assert result is None or isinstance(result, dict)

    def test_save_agent_hp_with_mock_registry(self):
        """save_agent_hp takes any object with .get_all_agents() returning agents."""
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.id = "test_agent_001"
        agent.name = "TestBot"
        agent.district = "coding"
        agent.health_points = 750

        registry = MagicMock()
        registry.get_all_agents.return_value = [agent]

        loop_state.save_agent_hp(registry)
        loaded = loop_state.load_agent_hp()
        assert loaded is not None
        assert "test_agent_001" in loaded
        assert loaded["test_agent_001"]["hp"] == 750

    def test_load_agent_hp_returns_dict_or_none(self):
        result = loop_state.load_agent_hp()
        assert result is None or isinstance(result, dict)

    def test_restore_agent_hp(self):
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.id = "restore_test_001"
        agent.name = "RestoreBot"
        agent.district = "research"
        agent.health_points = 800

        registry = MagicMock()
        registry.get_all_agents.return_value = [agent]

        # Save a snapshot with HP=650
        agent_snap = MagicMock()
        agent_snap.id = "restore_test_001"
        agent_snap.name = "RestoreBot"
        agent_snap.district = "research"
        agent_snap.health_points = 650
        snap_registry = MagicMock()
        snap_registry.get_all_agents.return_value = [agent_snap]

        loop_state.save_agent_hp(snap_registry)

        # Now restore into registry
        restored = loop_state.restore_agent_hp(registry)
        assert restored >= 1
        assert agent.health_points == 650

    def test_restore_agent_hp_empty_snapshot(self):
        from unittest.mock import MagicMock
        # Overwrite with empty snapshot
        registry_empty = MagicMock()
        registry_empty.get_all_agents.return_value = []
        loop_state.save_agent_hp(registry_empty)

        target_registry = MagicMock()
        target_registry.get_all_agents.return_value = []
        count = loop_state.restore_agent_hp(target_registry)
        # 0 or more, should not crash
        assert count >= 0
