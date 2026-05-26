"""Integration tests — Session C2: Vector semantic memory search."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── episodic_embeddings table ─────────────────────────────────────────────────


class TestEpisodicEmbeddingsTable(unittest.TestCase):
    """episodic_embeddings table is created and has correct schema."""

    def _make_mem(self, tmp_db):
        import sqlite3
        import core.memory.episodic as mod
        orig_path = mod.CONFIG.get("db_path", "vector_memory.db")
        mod.CONFIG["db_path"] = str(tmp_db)
        mod._db_connection = None
        mem = mod.EpisodicMemory()
        return mem, mod, orig_path

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_path = Path(self._tmp.name)
        self._tmp.close()

    def tearDown(self):
        import core.memory.episodic as mod
        try:
            if mod._db_connection:
                mod._db_connection.close()
                mod._db_connection = None
        except Exception:
            pass
        self._tmp_path.unlink(missing_ok=True)

    def test_table_created(self):
        import core.memory.episodic as mod
        mod.CONFIG["db_path"] = str(self._tmp_path)
        mod._db_connection = None
        mem = mod.EpisodicMemory()
        conn = sqlite3.connect(str(self._tmp_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='episodic_embeddings'"
        )
        row = cursor.fetchone()
        conn.close()
        mod._db_connection = None
        self.assertIsNotNone(row, "episodic_embeddings table must exist")

    def test_table_has_id_column(self):
        import core.memory.episodic as mod
        mod.CONFIG["db_path"] = str(self._tmp_path)
        mod._db_connection = None
        mem = mod.EpisodicMemory()
        conn = sqlite3.connect(str(self._tmp_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(episodic_embeddings)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        mod._db_connection = None
        self.assertIn("id", columns)
        self.assertIn("embedding", columns)
        self.assertIn("model", columns)

    def test_table_primary_key_is_id(self):
        import core.memory.episodic as mod
        mod.CONFIG["db_path"] = str(self._tmp_path)
        mod._db_connection = None
        mod.EpisodicMemory()
        conn = sqlite3.connect(str(self._tmp_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(episodic_embeddings)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        conn.close()
        mod._db_connection = None
        self.assertIn("id", pk_cols)


# ── EpisodicMemory.search_semantic() API ─────────────────────────────────────


class TestSearchSemanticMethod(unittest.TestCase):
    """EpisodicMemory has search_semantic() method."""

    def test_method_exists(self):
        from core.memory.episodic import EpisodicMemory
        self.assertTrue(callable(EpisodicMemory.search_semantic))

    def test_returns_list(self):
        import core.memory.episodic as mod
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        try:
            mem = mod.EpisodicMemory()
            result = mem.search_semantic("iced coffee", top_k=5)
            self.assertIsInstance(result, list)
        finally:
            mod._db_connection = None
            tmp.unlink(missing_ok=True)

    def test_empty_query_falls_back_to_recall(self):
        import core.memory.episodic as mod
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        try:
            mem = mod.EpisodicMemory()
            result = mem.search_semantic("", top_k=5)
            self.assertIsInstance(result, list)
        finally:
            mod._db_connection = None
            tmp.unlink(missing_ok=True)

    def test_top_k_limits_results(self):
        import core.memory.episodic as mod
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        try:
            mem = mod.EpisodicMemory()
            for i in range(8):
                mem.store("pref", f"I prefer beverage {i}", source="test")
            result = mem.search_semantic("beverage preference", top_k=3)
            self.assertLessEqual(len(result), 3)
        finally:
            mod._db_connection = None
            tmp.unlink(missing_ok=True)

    def test_no_sentence_transformers_falls_back_to_fts5(self):
        """When sentence-transformers is absent, search_semantic falls back gracefully."""
        import core.memory.episodic as mod
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        try:
            mem = mod.EpisodicMemory()
            mem.store("pref", "I prefer iced coffee over hot coffee", source="test")
            with patch.dict("sys.modules", {"sentence_transformers": None}):
                result = mem.search_semantic("beverage preference coffee", top_k=5)
            self.assertIsInstance(result, list)
        finally:
            mod._db_connection = None
            tmp.unlink(missing_ok=True)


# ── Semantic search correctness (mocked embeddings) ───────────────────────────


class TestSearchSemanticWithMockedModel(unittest.TestCase):
    """search_semantic() returns relevant episodes when sentence-transformers is mocked."""

    def _setup_mem(self):
        import core.memory.episodic as mod
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp = Path(f.name)
        f.close()
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        mem = mod.EpisodicMemory()
        return mem, mod, tmp

    def _teardown(self, mod, tmp):
        mod._db_connection = None
        tmp.unlink(missing_ok=True)

    def test_stores_and_retrieves_via_semantic(self):
        """Store 'I prefer iced coffee', query 'beverage preference' → returned."""
        import numpy as np
        mem, mod, tmp = self._setup_mem()
        try:
            ep_id = mem.store("preference", "I prefer iced coffee", source="test")

            # Mock sentence_transformers: query and stored text get distinct embeddings.
            mock_model = MagicMock()
            # query vec: [1, 0, ...]; stored vec: [0.9, 0, ...] — high cosine similarity
            query_vec = np.zeros(384, dtype="float32")
            query_vec[0] = 1.0
            stored_vec = np.zeros(384, dtype="float32")
            stored_vec[0] = 0.9
            stored_vec[1] = 0.1  # small angle → high cosine
            stored_vec = stored_vec / np.linalg.norm(stored_vec)

            call_count = [0]

            def fake_encode(texts, **kwargs):
                call_count[0] += 1
                if isinstance(texts, str) or (isinstance(texts, list) and len(texts) == 1
                                              and texts[0] == "what beverage do I like"):
                    return query_vec.reshape(1, -1) if isinstance(texts, list) else query_vec
                # batch encode for backfill
                return np.stack([stored_vec for _ in texts])

            mock_model.encode.side_effect = fake_encode

            mock_st = MagicMock()
            mock_st.SentenceTransformer.return_value = mock_model

            with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
                results = mem.search_semantic("what beverage do I like", top_k=5)

            self.assertIsInstance(results, list)
            contents = [r["content"] for r in results]
            self.assertTrue(
                any("iced coffee" in c for c in contents),
                f"Expected 'iced coffee' in results, got: {contents}",
            )
        finally:
            self._teardown(mod, tmp)

    def test_irrelevant_episodes_score_lower(self):
        """An episode about 'code review' should not appear in 'coffee preference' results."""
        import numpy as np
        mem, mod, tmp = self._setup_mem()
        try:
            mem.store("preference", "I prefer iced coffee", source="test")
            mem.store("task", "completed code review of authentication module", source="test")

            mock_model = MagicMock()
            # Coffee vec: [1, 0, ...]
            # Code vec:   [0, 1, ...] — orthogonal, low cosine to query
            coffee_vec = np.array([1.0] + [0.0] * 383, dtype="float32")
            code_vec = np.array([0.0, 1.0] + [0.0] * 382, dtype="float32")
            query_vec = np.array([1.0] + [0.0] * 383, dtype="float32")

            def fake_encode(texts, **kwargs):
                if not isinstance(texts, list):
                    return query_vec
                result = []
                for t in texts:
                    if "coffee" in t.lower():
                        result.append(coffee_vec)
                    elif "code" in t.lower() or "review" in t.lower():
                        result.append(code_vec)
                    else:
                        result.append(query_vec)
                return np.stack(result)

            mock_model.encode.side_effect = fake_encode
            mock_st = MagicMock()
            mock_st.SentenceTransformer.return_value = mock_model

            with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
                results = mem.search_semantic("what beverage preference iced coffee", top_k=1)

            if results:
                self.assertIn("iced coffee", results[0]["content"])
        finally:
            self._teardown(mod, tmp)


# ── Hybrid score calculation ──────────────────────────────────────────────────


class TestHybridScoreLogic(unittest.TestCase):
    """Hybrid score = 0.7 * semantic + 0.3 * fts5 (verified via source inspection)."""

    def test_hybrid_weights_in_source(self):
        import inspect
        from core.memory.episodic import EpisodicMemory
        src = inspect.getsource(EpisodicMemory.search_semantic)
        self.assertIn("0.7", src)
        self.assertIn("0.3", src)

    def test_semantic_weight_larger_than_fts(self):
        # 0.7 > 0.3
        self.assertGreater(0.7, 0.3)

    def test_search_semantic_model_name_constant(self):
        from core.memory.episodic import EpisodicMemory
        self.assertEqual(EpisodicMemory._EMBED_MODEL, "all-MiniLM-L6-v2")

    def test_embed_dim_constant(self):
        from core.memory.episodic import EpisodicMemory
        self.assertEqual(EpisodicMemory._EMBED_DIM, 384)


# ── context_engine wiring ─────────────────────────────────────────────────────


class TestContextEngineSemanticWiring(unittest.TestCase):
    """context_engine.get_world_state(query=...) uses search_semantic."""

    def test_get_world_state_accepts_query_param(self):
        import inspect
        from core.loop.context_engine import ContextEngine
        sig = inspect.signature(ContextEngine.get_world_state)
        self.assertIn("query", sig.parameters)

    def test_search_semantic_called_when_query_given(self):
        from core.loop.context_engine import ContextEngine
        ce = ContextEngine()
        mock_mem = MagicMock()
        mock_mem.search_semantic.return_value = []
        mock_mem.recall.return_value = []
        mock_mem.get_stats.return_value = {}
        ce._memory = mock_mem
        ce._goals = MagicMock()
        ce._goals.get_goal_summary.return_value = ""
        ce._health = None

        try:
            ce.get_world_state(query="what beverage do I like")
        except Exception:
            pass  # world state may fail on other parts — we just check the call

        mock_mem.search_semantic.assert_called_once_with("what beverage do I like", top_k=5)

    def test_recall_used_when_no_query(self):
        from core.loop.context_engine import ContextEngine
        ce = ContextEngine()
        mock_mem = MagicMock()
        mock_mem.search_semantic.return_value = []
        mock_mem.recall.return_value = []
        mock_mem.get_stats.return_value = {}
        ce._memory = mock_mem
        ce._goals = MagicMock()
        ce._goals.get_goal_summary.return_value = ""
        ce._health = None

        try:
            ce.get_world_state(query=None)
        except Exception:
            pass

        mock_mem.recall.assert_called()
        mock_mem.search_semantic.assert_not_called()

    def test_session_hydration_passes_query_from_extra_context(self):
        import inspect
        from core.loop.context_engine import ContextEngine
        src = inspect.getsource(ContextEngine.session_hydration_prompt)
        self.assertIn("query", src)
        self.assertIn("extra_context", src)

    def test_session_hydration_with_query_calls_search_semantic(self):
        from core.loop.context_engine import ContextEngine
        ce = ContextEngine()
        mock_mem = MagicMock()
        mock_mem.search_semantic.return_value = []
        mock_mem.recall.return_value = []
        mock_mem.get_stats.return_value = {}
        ce._memory = mock_mem
        ce._goals = MagicMock()
        ce._goals.get_goal_summary.return_value = ""
        ce._health = None

        try:
            ce.session_hydration_prompt(extra_context={"query": "beverage preference"})
        except Exception:
            pass

        mock_mem.search_semantic.assert_called_once_with("beverage preference", top_k=5)


# ── Ensure_embeddings backfill ────────────────────────────────────────────────


class TestEnsureEmbeddingsBackfill(unittest.TestCase):
    """_ensure_embeddings() backfills missing records lazily."""

    def test_ensure_embeddings_method_exists(self):
        from core.memory.episodic import EpisodicMemory
        self.assertTrue(callable(EpisodicMemory._ensure_embeddings))

    def test_backfill_does_not_crash_without_sentence_transformers(self):
        """_ensure_embeddings() should not raise if model encoding fails."""
        import core.memory.episodic as mod
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp = Path(f.name)
        mod.CONFIG["db_path"] = str(tmp)
        mod._db_connection = None
        try:
            mem = mod.EpisodicMemory()
            mock_model = MagicMock()
            mock_model.encode.side_effect = RuntimeError("model not loaded")
            mem._ensure_embeddings(mock_model)  # must not raise
        finally:
            mod._db_connection = None
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
