"""Direct tests for EpisodicMemory CRUD operations and loop_state exception paths."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import patch, MagicMock

from core.memory.episodic import EpisodicMemory, get_db_connection, get_temp_cursor


class TestEpisodicMemoryBasic:
    """Test EpisodicMemory CRUD — no mocks of internal DB operations."""

    def test_init_creates_instance(self):
        mem = EpisodicMemory()
        assert mem is not None
        assert mem.conn is not None

    def test_store_returns_uuid_string(self):
        mem = EpisodicMemory()
        event_id = mem.store("test_event", f"content_{uuid.uuid4().hex}", source="test")
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_store_with_tags_and_context(self):
        mem = EpisodicMemory()
        event_id = mem.store(
            "task_complete",
            f"completed research {uuid.uuid4().hex}",
            tags=["research", "done"],
            context={"district": "research", "hp": 500},
            source="test",
        )
        assert event_id is not None

    def test_store_minimal_args(self):
        mem = EpisodicMemory()
        event_id = mem.store("startup", f"VECTOR online {uuid.uuid4().hex}")
        assert event_id is not None

    def test_recall_returns_list(self):
        mem = EpisodicMemory()
        unique = uuid.uuid4().hex[:10]
        mem.store("recall_test", f"search_payload_{unique}", source="test")
        results = mem.recall(unique, limit=5)
        assert isinstance(results, list)

    def test_recall_with_event_type_filter(self):
        mem = EpisodicMemory()
        unique = uuid.uuid4().hex[:10]
        event_type = f"etype_{unique}"
        mem.store(event_type, f"filtered_data_{unique}", source="test")
        results = mem.recall(unique, limit=5, event_type=event_type)
        assert isinstance(results, list)

    def test_recall_dict_structure(self):
        mem = EpisodicMemory()
        unique = uuid.uuid4().hex[:10]
        mem.store("struct_test", f"structure_check_{unique}", tags=["a", "b"], source="test")
        results = mem.recall(unique, limit=5)
        for r in results:
            for key in ("id", "event_type", "content", "timestamp", "source"):
                assert key in r

    def test_recall_empty_query_returns_list(self):
        mem = EpisodicMemory()
        # FTS5 match with a simple known term always returns a list (may be empty)
        results = mem.recall("zzz_unlikely_match_xyz_9999", limit=1)
        assert isinstance(results, list)

    def test_recall_limit_respected(self):
        mem = EpisodicMemory()
        unique = uuid.uuid4().hex[:10]
        for i in range(5):
            mem.store("limit_test", f"limit_{unique}_{i}", source="test")
        results = mem.recall(unique, limit=2)
        assert len(results) <= 2

    def test_remember_returns_true(self):
        mem = EpisodicMemory()
        key = f"pref_{uuid.uuid4().hex[:8]}"
        ok = mem.remember(key, "my_value", category="prefs", confidence=0.9)
        assert ok is True

    def test_recall_fact_returns_dict(self):
        mem = EpisodicMemory()
        key = f"fact_{uuid.uuid4().hex[:8]}"
        mem.remember(key, "stored_value")
        row = mem.recall_fact(key)
        assert row is not None
        assert row["value"] == "stored_value"

    def test_recall_fact_missing_returns_none(self):
        mem = EpisodicMemory()
        result = mem.recall_fact(f"nonexistent_{uuid.uuid4().hex}")
        assert result is None

    def test_remember_overwrite(self):
        mem = EpisodicMemory()
        key = f"overwrite_{uuid.uuid4().hex[:8]}"
        mem.remember(key, "first_value")
        mem.remember(key, "second_value")
        row = mem.recall_fact(key)
        assert row["value"] == "second_value"

    def test_remember_default_confidence(self):
        mem = EpisodicMemory()
        key = f"default_conf_{uuid.uuid4().hex[:8]}"
        ok = mem.remember(key, "value_here")
        assert ok is True

    def test_store_chain_high_reward_returns_id(self):
        mem = EpisodicMemory()
        chain_id = mem.store_chain(
            situation=f"test_sit_{uuid.uuid4().hex[:6]}",
            goal_ids=["g_test"],
            steps=["step1", "step2"],
            action="test_action",
            outcome="success",
            reward=0.85,
        )
        assert isinstance(chain_id, str)
        assert len(chain_id) > 0

    def test_store_chain_low_reward_returns_id(self):
        mem = EpisodicMemory()
        chain_id = mem.store_chain(
            situation=f"low_{uuid.uuid4().hex[:6]}",
            goal_ids=[],
            steps=["step1"],
            action="attempt",
            outcome="partial",
            reward=0.3,
        )
        assert isinstance(chain_id, str)

    def test_store_chain_empty_goals_and_steps(self):
        mem = EpisodicMemory()
        chain_id = mem.store_chain(
            situation=f"empty_{uuid.uuid4().hex[:6]}",
            goal_ids=[],
            steps=[],
            action="noop",
            outcome="nothing",
            reward=0.0,
        )
        assert chain_id is not None

    def test_get_training_data_returns_list(self):
        mem = EpisodicMemory()
        mem.store_chain(
            situation=f"train_{uuid.uuid4().hex}",
            goal_ids=["g_train"],
            steps=["a", "b"],
            action="train",
            outcome="trained",
            reward=0.9,
        )
        data = mem.get_training_data(limit=10)
        assert isinstance(data, list)
        # High-reward chains end up as training data
        if data:
            assert "chain_id" in data[0] or "reward" in data[0]

    def test_get_training_data_limit(self):
        mem = EpisodicMemory()
        for i in range(5):
            mem.store_chain(
                situation=f"tlimit_{uuid.uuid4().hex[:6]}",
                goal_ids=[],
                steps=["x"],
                action="act",
                outcome="ok",
                reward=0.95,
            )
        data = mem.get_training_data(limit=2)
        assert len(data) <= 2

    def test_update_skill_returns_true(self):
        mem = EpisodicMemory()
        result = mem.update_skill(f"py_{uuid.uuid4().hex[:6]}", 0.85, evidence=["proj1"])
        assert result is True

    def test_update_skill_no_evidence(self):
        mem = EpisodicMemory()
        result = mem.update_skill(f"skill_{uuid.uuid4().hex[:6]}", 0.7)
        assert result is True

    def test_get_skill_after_update(self):
        mem = EpisodicMemory()
        skill_name = f"getskill_{uuid.uuid4().hex[:6]}"
        mem.update_skill(skill_name, 0.7, evidence=["e1"])
        result = mem.get_skill(skill_name)
        assert result is not None
        assert result["skill_name"] == skill_name
        assert result["confidence"] == pytest.approx(0.7, abs=0.01)

    def test_get_skill_missing_returns_none(self):
        mem = EpisodicMemory()
        result = mem.get_skill(f"nosuchskill_{uuid.uuid4().hex}")
        assert result is None

    def test_update_skill_overwrites(self):
        mem = EpisodicMemory()
        name = f"overskill_{uuid.uuid4().hex[:6]}"
        mem.update_skill(name, 0.5)
        mem.update_skill(name, 0.9)
        result = mem.get_skill(name)
        assert result["confidence"] == pytest.approx(0.9, abs=0.01)

    def test_get_stats_returns_dict(self):
        mem = EpisodicMemory()
        stats = mem.get_stats()
        assert isinstance(stats, dict)

    def test_get_stats_has_required_tables(self):
        mem = EpisodicMemory()
        stats = mem.get_stats()
        for table in ("episodic_memory", "semantic_memory", "reasoning_chains", "agent_history"):
            assert table in stats

    def test_get_stats_counts_nonneg(self):
        mem = EpisodicMemory()
        stats = mem.get_stats()
        for count in stats.values():
            assert count >= 0

    def test_get_db_connection_returns_connection(self):
        conn = get_db_connection()
        assert conn is not None

    def test_get_db_connection_is_singleton(self):
        conn1 = get_db_connection()
        conn2 = get_db_connection()
        assert conn1 is conn2

    def test_get_temp_cursor_executes_query(self):
        with get_temp_cursor() as cursor:
            cursor.execute("SELECT 1 + 1")
            result = cursor.fetchone()
        assert result[0] == 2

    def test_recall_with_tags(self):
        mem = EpisodicMemory()
        unique = uuid.uuid4().hex[:10]
        mem.store("tagged_event", f"event_data_{unique}", tags=["tag1", "tag2"], source="test")
        results = mem.recall(unique, limit=5)
        assert isinstance(results, list)
        for r in results:
            assert "tags" in r


class TestLoopStateExceptionPaths:
    """Cover the exception-handling paths in loop_state (lines 35-36, 43-45, etc.)."""

    def test_save_goal_exception_does_not_propagate(self):
        import core.loop.loop_state as ls
        with patch("core.loop.loop_state._mem", side_effect=Exception("db down")):
            ls.save_goal("g_exception_test")  # must not raise

    def test_load_goal_exception_returns_none(self):
        import core.loop.loop_state as ls
        with patch("core.loop.loop_state._mem", side_effect=Exception("db down")):
            result = ls.load_goal()
        assert result is None

    def test_save_decision_exception_does_not_propagate(self):
        import core.loop.loop_state as ls
        with patch("core.loop.loop_state._mem", side_effect=Exception("db down")):
            ls.save_decision("test_action", {"key": "val"}, 0.75)  # must not raise

    def test_load_decision_exception_returns_none(self):
        import core.loop.loop_state as ls
        with patch("core.loop.loop_state._mem", side_effect=Exception("db down")):
            result = ls.load_decision()
        assert result is None

    def test_save_agent_hp_exception_does_not_propagate(self):
        import core.loop.loop_state as ls
        mock_reg = MagicMock()
        mock_reg.get_all_agents.side_effect = Exception("registry down")
        # No patch on _mem — exception from get_all_agents hits the handler
        ls.save_agent_hp(mock_reg)  # must not raise

    def test_load_agent_hp_exception_returns_none(self):
        import core.loop.loop_state as ls
        with patch("core.loop.loop_state._mem", side_effect=Exception("db down")):
            result = ls.load_agent_hp()
        assert result is None

    def test_load_decision_malformed_json_returns_none(self):
        import core.loop.loop_state as ls
        mock_mem = MagicMock()
        mock_mem.return_value.recall_fact.return_value = {"value": "not_valid_json{{{{"}
        with patch("core.loop.loop_state._mem", mock_mem):
            result = ls.load_decision()
        assert result is None

    def test_load_agent_hp_malformed_json_returns_none(self):
        import core.loop.loop_state as ls
        mock_mem = MagicMock()
        mock_mem.return_value.recall_fact.return_value = {"value": "<<<invalid>>>"}
        with patch("core.loop.loop_state._mem", mock_mem):
            result = ls.load_agent_hp()
        assert result is None
